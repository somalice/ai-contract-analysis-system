"""
合同业务服务(Sprint 2 - v0.4.0 / Sprint 3 - v0.5.0 调整)

职责:
- 创建合同(文件保存 → 建记录;Sprint 3 起不再自动分析,改为 pending 等待手动触发)
- 合同分页列表(支持关键字搜索 / 状态过滤 / 创建人过滤 / 按 created_time DESC 排序)
- 合同详情(含创建人 / 状态 / 文件信息 / AI 分析结果)
- 更新合同状态(状态机校验:draft→reviewed→archived)

权限设计(在 Service 层落地数据级过滤):
- admin:全部合同
- contract_manager:全部合同
- employee:仅 creator_id == 自己 的合同

Sprint 3 变更(v0.5.0):
- create_contract 不再调用 analyze_document;analysis_status 设为 'pending'
- AI 分析改为由 analysis_service.trigger_analysis 手动触发(前端"开始分析"按钮)
- 旧合同(Sprint 2 已上传)的 analysis_result 保留,详情接口降级读取

约束:
- 本层不直接渲染模板、不访问 request 对象;参数由 API 层传入
- 所有异常抛出 AppException 子类,由全局处理器统一返回
- 禁止 print() / return str(e)

调用链:api/contract/routes.py → contract_service → models/contract.py
                                analysis_service → ai/pipeline(Sprint 3)
"""
import os
import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.contract import Contract
from app.utils.file_utils import get_file_type
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError


# ---------- 配置常量 ----------
_CONTRACT_SUBDIR = 'contracts'  # 合同文件子目录(相对 UPLOAD_FOLDER)


def _get_contract_upload_dir():
    """获取合同上传目录(uploads/contracts/),并确保目录存在。"""
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], _CONTRACT_SUBDIR)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _generate_contract_no():
    """
    生成合同编号:CT-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'CT-{timestamp}-{suffix}'


def create_contract(file, current_user, contract_type='未分类', title=None, description=None):
    """
    上传并创建合同

    流程(Sprint 3 调整):
    1. 类型判断 → 保存文件到 uploads/contracts/{uuid}.ext
    2. 创建 Contract 记录(status=draft, analysis_status=pending)
    3. 不再自动调用 AI 分析(改为由 analysis_service.trigger_analysis 手动触发)

    Sprint 3 变更:
    - analysis_status 从 'processing' 改为 'pending'(等待手动触发分析)
    - 移除 analyze_document 调用与 analysis_result 回写
    - 上传接口立即返回,不再阻塞等待 AI

    异常边界:
    - 文件保存失败 → 抛 BusinessError(无残留文件)
    - DB 插入失败 → 删除已保存文件,抛 BusinessError

    :param file: werkzeug FileStorage
    :param current_user: {'id','role','username'}
    :param contract_type: 合同类型(默认"未分类")
    :param title: 合同标题(默认取文件名去扩展名)
    :param description: 描述(可选)
    :return: dict 合同完整信息
    """
    # ---------- 输入长度校验 ----------
    if contract_type and len(contract_type) > 64:
        raise ValidationError('合同类型长度不能超过 64 字符')
    if title and len(title) > 255:
        raise ValidationError('合同标题长度不能超过 255 字符')
    if description and len(description) > 5000:
        raise ValidationError('描述长度不能超过 5000 字符')

    original_filename = file.filename
    file_type = get_file_type(original_filename)
    ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'pdf'

    # ---------- 1. 保存文件(UUID 命名) ----------
    contract_dir = _get_contract_upload_dir()
    saved_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(contract_dir, saved_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception as e:
        logger.exception('合同文件保存失败: filename=%s', original_filename)
        # 保存失败时清理可能产生的残留文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise BusinessError('文件保存失败,请重试')

    # ---------- 2. 创建合同记录 ----------
    contract_no = _generate_contract_no()
    # title 默认取文件名去扩展名
    if not title or not title.strip():
        title = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

    contract = Contract(
        contract_no=contract_no,
        title=title.strip(),
        contract_type=contract_type or '未分类',
        description=description,
        creator_id=current_user['id'],
        status='draft',
        file_name=original_filename,
        file_path=file_path,
        file_size=file_size,
        # Sprint 3:上传后不再自动分析,analysis_status='pending' 等待手动触发
        analysis_status='pending',
    )

    try:
        db.session.add(contract)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        # DB 失败时清理已保存文件,避免孤儿文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        logger.exception('合同记录创建失败: contract_no=%s', contract_no)
        raise BusinessError('合同记录创建失败,请重试')

    # ---------- 3. Sprint 3:不再自动调用 AI 分析 ----------
    # AI 分析改为由 analysis_service.trigger_analysis 手动触发(前端"开始分析"按钮)
    # 上传接口立即返回,不再阻塞等待 AI

    logger.info('合同上传成功: id=%s contract_no=%s creator=%s role=%s status=%s analysis=%s',
                contract.id, contract.contract_no, current_user['username'],
                current_user['role'], contract.status, contract.analysis_status)

    return contract.to_dict()


def get_contract_list(page=1, size=20, keyword=None, status=None,
                      creator_id=None, current_user=None):
    """
    合同分页列表

    支持:分页 / 关键字搜索(title + contract_no 模糊)/ 状态过滤 / 创建人过滤 /
         按 created_time DESC 排序

    权限:
    - employee:强制只看 creator_id == 自己(忽略传入的 creator_id)
    - admin / contract_manager:可见全部;creator_id 参数可选过滤

    :param page: 页码(默认 1,< 1 取 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param keyword: 关键字(title / contract_no 模糊搜索)
    :param status: 状态过滤(必须 ∈ VALID_STATUSES)
    :param creator_id: 创建者过滤(employee 自动忽略)
    :param current_user: {'id','role'}
    :return: dict {items, total, page, size}
    """
    # ---------- 参数规范化 ----------
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(100, int(size)))
    except (TypeError, ValueError):
        size = 20

    # 状态合法性校验
    if status and status not in Contract.VALID_STATUSES:
        raise ValidationError(
            f'合同状态非法,允许: {", ".join(Contract.VALID_STATUSES)}')

    # ---------- 查询构建 ----------
    # joinedload 预加载 creator,避免 to_dict() 时 N+1 查询
    query = Contract.query.options(joinedload(Contract.creator))

    # 权限过滤:employee 强制只看自己
    if current_user and current_user.get('role') == 'employee':
        query = query.filter_by(creator_id=current_user['id'])
    elif creator_id:
        try:
            query = query.filter_by(creator_id=int(creator_id))
        except (TypeError, ValueError):
            raise ValidationError('创建者 ID 非法')

    # 关键字搜索(title + contract_no 模糊)
    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(
            db.or_(Contract.title.like(kw), Contract.contract_no.like(kw))
        )

    # 状态过滤
    if status:
        query = query.filter_by(status=status)

    # 排序:created_time DESC
    query = query.order_by(Contract.created_time.desc())

    # ---------- 分页 ----------
    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    items = [c.to_dict(include_analysis=False) for c in pagination.items]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def get_contract_detail(contract_id, current_user):
    """
    获取合同详情(含创建人 / 状态 / 文件信息 / AI 分析结果)

    权限:
    - admin / contract_manager:可见任意合同
    - employee:仅可见 creator_id == 自己 的合同;他人合同返回 404(防 ID 枚举)

    :param contract_id: 合同 ID
    :param current_user: {'id','role'}
    :return: dict 合同完整信息(含 analysis_result)
    """
    try:
        cid = int(contract_id)
    except (TypeError, ValueError):
        raise ValidationError('合同 ID 非法')

    contract = db.session.get(Contract, cid)
    if not contract:
        raise NotFoundError('合同不存在')

    # 权限校验:employee 仅可见自己的合同(404 防枚举,不泄露存在性)
    if current_user and current_user.get('role') == 'employee' \
            and contract.creator_id != current_user['id']:
        raise NotFoundError('合同不存在')

    return contract.to_dict(include_analysis=True)


def update_contract_status(contract_id, target_status, current_user):
    """
    更新合同状态(状态机校验)

    状态机:仅允许 draft→reviewed→archived 单向流转
    - 同状态转换(draft→draft)→ 非法
    - 跨级(draft→archived)→ 非法
    - 回退(reviewed→draft)→ 非法
    - archived 为终态,不可转出

    权限:仅 admin / contract_manager(由 API 层 @role_required 拦截,employee 无法进入)

    :param contract_id: 合同 ID
    :param target_status: 目标状态
    :param current_user: {'id','role','username'}
    :return: dict 更新后的合同信息
    """
    # 目标状态合法性校验
    if not target_status or target_status not in Contract.VALID_STATUSES:
        raise ValidationError(
            f'合同状态非法,允许: {", ".join(Contract.VALID_STATUSES)}')

    try:
        cid = int(contract_id)
    except (TypeError, ValueError):
        raise ValidationError('合同 ID 非法')

    contract = db.session.get(Contract, cid)
    if not contract:
        raise NotFoundError('合同不存在')

    # 状态机校验
    if not Contract.is_valid_transition(contract.status, target_status):
        raise BusinessError(
            f'非法状态跳转: {contract.status} → {target_status}')

    old_status = contract.status
    contract.status = target_status
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('合同状态更新失败: contract_id=%s', cid)
        raise BusinessError('合同状态更新失败,请重试')

    logger.info('合同状态变更: id=%s %s → %s operator=%s role=%s',
                contract.id, old_status, target_status,
                current_user.get('username'), current_user.get('role'))

    return contract.to_dict()


# ============================================================
# Sprint 6 - v0.8.0:AI 生成合同创建(供 generation_service 复用)
# ============================================================
def create_contract_from_generation(file_path, file_name, file_size,
                                     current_user, title=None,
                                     contract_type='未分类', description=None,
                                     auto_commit=True):
    """
    从 AI 生成的 Word 文件创建合同记录(Sprint 6 新增)

    与 create_contract 区别:
    - create_contract 接收 werkzeug FileStorage(用户上传)
    - 本函数接收已生成的文件路径(generation_service 渲染后的 .docx)
    - 复用 _generate_contract_no() 编号生成逻辑
    - 不再保存文件(文件已由 word_renderer 生成)

    约束:
    - 遵循"ContractService 负责合同创建"原则,生成合同也由本层创建
    - 文件路径必须存在(由调用方 word_renderer 保证)
    - status='draft', analysis_status='pending'(与上传合同一致,等待手动触发分析)

    Sprint 6.2 Transaction Hotfix:
    - 新增 auto_commit 参数,支持外层统一事务管理
    - auto_commit=True(默认):本函数自行 commit(向后兼容)
    - auto_commit=False:仅 add + flush(获取 id),不 commit/rollback
      → 由调用方(generation_service)统一管理事务边界

    :param file_path: 生成的 .docx 文件路径
    :param file_name: 文件名(用于 file_name 字段)
    :param file_size: 文件大小(字节)
    :param current_user: {'id','role','username'}
    :param title: 合同标题(默认取 file_name 去扩展名)
    :param contract_type: 合同类型(默认"未分类")
    :param description: 描述(可选)
    :param auto_commit: 是否在本函数内 commit(默认 True;False 时由调用方管理事务)
    :return: dict 合同完整信息
    """
    # ---------- 输入校验 ----------
    if not file_path or not os.path.exists(file_path):
        raise BusinessError('生成的合同文件不存在,无法创建合同记录')
    if contract_type and len(contract_type) > 64:
        raise ValidationError('合同类型长度不能超过 64 字符')
    if title and len(title) > 255:
        raise ValidationError('合同标题长度不能超过 255 字符')
    if description and len(description) > 5000:
        raise ValidationError('描述长度不能超过 5000 字符')

    # ---------- 创建合同记录 ----------
    contract_no = _generate_contract_no()
    if not title or not title.strip():
        title = file_name.rsplit('.', 1)[0] if '.' in file_name else file_name

    contract = Contract(
        contract_no=contract_no,
        title=title.strip(),
        contract_type=contract_type or '未分类',
        description=description,
        creator_id=current_user['id'],
        status='draft',
        file_name=file_name,
        file_path=file_path,
        file_size=file_size,
        # 与上传合同一致:等待手动触发 Sprint 3 分析
        analysis_status='pending',
    )

    if auto_commit:
        # 独立事务模式(向后兼容:其他调用方使用)
        try:
            db.session.add(contract)
            db.session.commit()
        except Exception:
            db.session.rollback()
            logger.exception('[Contract] 生成合同记录创建失败: contract_no=%s', contract_no)
            raise BusinessError('生成合同记录创建失败,请重试')
    else:
        # 外层统一事务模式(Sprint 6.2:generation_service 管理事务边界)
        # 仅 add + flush 获取 id,不 commit/rollback
        db.session.add(contract)
        db.session.flush()  # 获取 contract.id,不提交

    logger.info('[Contract] AI 生成合同创建成功: id=%s contract_no=%s creator=%s type=%s '
                'auto_commit=%s',
                contract.id, contract.contract_no, current_user.get('username'),
                contract.contract_type, auto_commit)

    return contract.to_dict()
