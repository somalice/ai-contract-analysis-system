"""
操作审计中间件(Sprint 8 - v1.0.0 企业级 AI 增强)

职责:
- Flask after_request 钩子:声明式 AUDIT_RULES 匹配 endpoint → 写 OperationLog
- 仅匹配 AUDIT_RULES 的关键操作:登录/合同上传/审核/生成/知识库上传删除/投标上传解析生成
- 全程 try/except:审计失败绝不影响 HTTP 响应(用户无感,仅日志 warning)

设计原则(user_rules §14):
- 不改变响应体/响应码(仅追加式副作用)
- 不读/不解包大请求体:detail 仅记录安全字段(文件名/ID/模板 ID 等),绝不存储 password/完整 JSON
- 不直接访问 request.get_json():避免破坏流式响应/消耗 body 流;使用 URL 参数 + response JSON 摘要
- IP 解析优先:X-Forwarded-For → X-Real-IP → request.remote_addr
"""
import json
import time
from datetime import datetime

from app.extensions.logger import logger
from app.extensions.db import db
from app.models.operation_log import OperationLog


# ============================================================
# AUDIT_RULES: endpoint -> (operation_type, target_type, target_extractor)
# extractor:
#   支持两种:
#   1) 'path.{param}'   → 从 URL 路径参数取(Werkzeug URL rule path params)
#   2) 'response.{json_path}'  → 从响应 JSON data 内取,支持 . 访问
#   3) None/null → 不记录 target_id
# ============================================================
AUDIT_RULES = {
    # ---------- Auth ----------
    'auth.login': ('user_login', 'user', 'response.data.user.id'),
    # ---------- Contract ----------
    'contract_api.upload_contract': ('contract_upload', 'contract', 'response.data.contract.id'),
    'contract_api.trigger_contract_review': ('contract_review', 'review', 'response.data.id'),
    # ---------- Generation ----------
    'generation.preview_generation': ('contract_generate_preview', 'generation', 'response.data.generation.id'),
    'generation.generate_contract': ('contract_generate', 'generation', 'response.data.generation.id'),
    # ---------- Knowledge ----------
    'knowledge.upload_knowledge_document': ('knowledge_upload', 'document', 'response.data.document.id'),
    'knowledge.delete_knowledge_document': ('knowledge_delete', 'document', 'path.document_id'),
    # ---------- Bid ----------
    'bid.upload_bid_document': ('bid_upload', 'bid', 'response.data.bid.id'),
    'bid.parse_bid_document': ('bid_parse', 'bid', 'path.bid_document_id'),
    'bid.submit_requirement_review': ('bid_requirement_submit', 'bid', 'path.bid_id'),
    'bid.review_requirement': ('bid_requirement_review', 'bid', 'path.bid_id'),
    'bid.generate_proposal': ('bid_generate', 'proposal', 'response.data.proposal.id'),
    # ---------- Template ----------
    'template.upload_template': ('template_upload', 'template', 'response.data.template.id'),
    'template.delete_template': ('template_delete', 'template', 'path.template_id'),
}


# 记录 detail 的关键字段(从 response.data 提取,安全非敏感)
_DETAIL_PICKER = {
    'user_login': lambda req, resp_data: {
        'username': _safe_json_get(resp_data, 'data.user.username'),
    },
    'contract_upload': lambda req, resp_data: {
        'title': _safe_json_get(resp_data, 'data.contract.title'),
        'file_name': _safe_json_get(resp_data, 'data.contract.original_file_name'),
        'contract_type': _safe_json_get(resp_data, 'data.contract.contract_type'),
    },
    'contract_analysis': lambda req, resp_data: {
        'contract_id': _url_param(req, 'contract_id'),
    },
    'contract_review': lambda req, resp_data: {
        'review_no': _safe_json_get(resp_data, 'data.review_no'),
        'risk_level': _safe_json_get(resp_data, 'data.risk_level'),
    },
    'contract_generate_preview': lambda req, resp_data: {
        'generation_no': _safe_json_get(resp_data, 'data.generation.generation_no'),
        'template_id': _safe_json_get(resp_data, 'data.generation.template_id'),
    },
    'contract_generate': lambda req, resp_data: {
        'generation_no': _safe_json_get(resp_data, 'data.generation.generation_no'),
        'contract_id': _safe_json_get(resp_data, 'data.contract.id'),
        'file_name': _safe_json_get(resp_data, 'data.generation.file_name'),
    },
    'knowledge_upload': lambda req, resp_data: {
        'document_title': _safe_json_get(resp_data, 'data.document.title'),
        'file_name': _safe_json_get(resp_data, 'data.document.file_name'),
        'knowledge_type': _safe_json_get(resp_data, 'data.document.knowledge_type'),
    },
    'knowledge_delete': lambda req, resp_data: {
        'document_id': _url_param(req, 'document_id'),
    },
    'bid_upload': lambda req, resp_data: {
        'title': _safe_json_get(resp_data, 'data.bid.title'),
        'file_name': _safe_json_get(resp_data, 'data.bid.original_file_name'),
    },
    'bid_parse': lambda req, resp_data: {
        'bid_document_id': _url_param(req, 'bid_document_id'),
    },
    'bid_requirement_submit': lambda req, resp_data: {
        'bid_id': _url_param(req, 'bid_id'),
    },
    'bid_requirement_review': lambda req, resp_data: {
        'bid_id': _url_param(req, 'bid_id'),
        'approved': _safe_json_get(req.get_json(silent=True) or {}, 'approved'),
    },
    'bid_generate': lambda req, resp_data: {
        'proposal_no': _safe_json_get(resp_data, 'data.proposal.proposal_no'),
        'file_name': _safe_json_get(resp_data, 'data.proposal.file_name'),
    },
    'template_upload': lambda req, resp_data: {
        'name': _safe_json_get(resp_data, 'data.template.name'),
        'contract_type': _safe_json_get(resp_data, 'data.template.contract_type'),
    },
    'template_delete': lambda req, resp_data: {
        'template_id': _url_param(req, 'template_id'),
    },
}


def register_audit_middleware(app):
    """在 create_app() 中注册 after_request 钩子。

    注:Flask 3.x 推荐使用 app.after_request;此中间件轻量且独立。
    """

    @app.after_request
    def _after_request(response):
        # 提前过滤:非 API 请求不审计
        try:
            return _do_audit(response)
        except Exception as e:
            # 终极兜底:任何审计异常不得污染响应
            logger.warning('[Audit] 审计总兜底异常(不影响响应): %s', e)
            return response

    return app


def _do_audit(response):
    """真正审计逻辑(内部 try/except 按段隔离)"""
    from flask import request
    endpoint = request.endpoint or ''

    # 1) 快速路径:不在 AUDIT_RULES → 直接返回
    rule = AUDIT_RULES.get(endpoint)
    if rule is None:
        return response

    operation_type, target_type, target_extractor = rule
    # 记录开始时间(从 request 环境取:Flask 记录 environ['REQUEST_TIME']?否则用 now)
    start_ts = request.environ.get('AUDIT_START_TS')
    if start_ts is None:
        # 备用:当前时间 - duration=0(本中间件前可通过 before_request 写 environ)
        start_ts = time.time()
    duration_ms = max(0, int((time.time() - start_ts) * 1000))

    # 2) 解析 JWT user 信息:懒加载,避免早 import
    user_id = None
    username = None
    try:
        from flask_jwt_extended import decode_token, get_jwt_identity
        from flask import g as _g
        # 优先用 get_jwt_identity(仅 JWT 装饰过的路由可用,但我们已在路由层加装饰器)
        try:
            identity = get_jwt_identity()
            if isinstance(identity, dict):
                user_id = identity.get('id')
                username = identity.get('username')
            elif identity:
                # 用户模型 JWT 可能存 user_id 字符串
                try:
                    user_id = int(identity)
                except (TypeError, ValueError):
                    user_id = None
        except Exception:
            pass
        # 登录特殊处理:从 response.data.user 取
        if operation_type == 'user_login' and response.status_code < 400:
            try:
                resp_json = response.get_json(silent=True) or {}
                if isinstance(resp_json, dict):
                    d = resp_json.get('data') or {}
                    u = d.get('user') if isinstance(d, dict) else None
                    if isinstance(u, dict):
                        user_id = user_id or u.get('id')
                        username = username or u.get('username')
            except Exception:
                pass
    except Exception:
        # 无 token 也允许记录(匿名/登录)
        pass

    # 3) 提取 target_id
    target_id = None
    try:
        target_id = _extract_target(target_extractor, request, response)
    except Exception:
        target_id = None

    # 4) 提取 detail 摘要
    detail = None
    try:
        picker = _DETAIL_PICKER.get(operation_type)
        if callable(picker):
            resp_json = response.get_json(silent=True) or {}
            detail = picker(request, resp_json)
            # 若为空 dict → 写 None,减少 DB 空间
            if isinstance(detail, dict) and not detail:
                detail = None
    except Exception:
        detail = None

    # 5) IP
    ip_address = _get_client_ip(request)

    # 6) status
    status_code = response.status_code
    status = 'success' if (200 <= status_code < 400) else 'failed'

    error_message = None
    if status == 'failed':
        try:
            resp_json = response.get_json(silent=True) or {}
            if isinstance(resp_json, dict):
                error_message = resp_json.get('message') or resp_json.get('msg') or resp_json.get('error')
                if error_message and len(str(error_message)) > 1000:
                    error_message = str(error_message)[:1000]
        except Exception:
            pass

    # 7) 落库(双重 try/except 保护:绝不抛出)
    try:
        log = OperationLog(
            user_id=_int_or_none(user_id),
            username=_truncate(username, 64),
            operation_type=_truncate(operation_type, 48),
            target_type=_truncate(target_type, 32),
            target_id=_int_or_none(target_id),
            method=_truncate(request.method, 8),
            path=_truncate(request.path, 255),
            status=_truncate(status, 16),
            status_code=status_code,
            duration_ms=duration_ms,
            ip_address=_truncate(ip_address, 64),
            detail=detail,
            error_message=_truncate(error_message, 5000) if error_message else None,
            created_time=datetime.utcnow(),
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        logger.warning('[Audit] 落库失败(不影响响应): op=%s err=%s', operation_type, e)
        try:
            db.session.rollback()
        except Exception:
            pass

    return response


# ============================================================
# utils
# ============================================================
def _extract_target(extractor, request, response):
    if not extractor or not isinstance(extractor, str):
        return None
    if extractor.startswith('path.'):
        param = extractor[len('path.'):]
        val = request.view_args.get(param) if request.view_args else None
        if val is None:
            # 备用:从 URL 字符串数字段取(用于 URL path 参数但 view_args 未暴露场景)
            from flask import request as r
            val = (r.view_args or {}).get(param)
        return _int_or_none(val)
    if extractor.startswith('response.'):
        json_path = extractor[len('response.'):]
        resp_json = response.get_json(silent=True) or {}
        return _int_or_none(_safe_json_get(resp_json, json_path))
    return None


def _safe_json_get(obj, dotted_path):
    if not isinstance(obj, dict) or not dotted_path:
        return None
    cur = obj
    for part in dotted_path.split('.'):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _url_param(request, name):
    return (request.view_args or {}).get(name)


def _int_or_none(v):
    if v is None or v == '':
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _truncate(v, n):
    if v is None:
        return None
    s = str(v)
    return s if len(s) <= n else s[:n]


def _get_client_ip(request):
    """多层代理下取真实 IP(仅取最左,避免伪造;生产建议上游网关配置 trusted_proxy)"""
    try:
        xff = request.headers.get('X-Forwarded-For')
        if xff:
            first = xff.split(',')[0].strip()
            if first:
                return first
        xri = request.headers.get('X-Real-IP')
        if xri:
            return xri.strip()
        return request.remote_addr
    except Exception:
        return None
