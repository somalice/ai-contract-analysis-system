"""
合同模板业务服务(Sprint 6 - v0.8.0)

职责:
- create_template:上传模板 → 保存文件 → 解析 {{variable}} 占位符 → 建记录
- get_template_list:模板分页列表(支持关键字 / 状态 / 类型过滤)
- get_template:模板详情(含 variables)
- update_template_status:启停模板(active ⇄ disabled)
- delete_template:删除模板(清理文件 + 删记录)

权限设计(与 contract_service / review_service 一致):
- admin / contract_manager:可上传 / 启停 / 删除 / 查看全部模板
- employee:仅可查看 active 模板(用于生成);不可上传 / 启停 / 删除

调用链:api/generation/routes.py(templates 路由)
  → template_service
    → models/contract_template.py
    → docxtpl(解析模板变量)

约束:
- 本层不直接渲染模板、不访问 request 对象
- 模板文件统一 uploads/templates/{uuid}.docx,UUID 命名
- 所有异常抛出 AppException 子类
- 禁止 print() / return str(e)
- 不修改 Sprint 0~5 任何 Service / Model
"""
import os
import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.contract_template import ContractTemplate
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError, AuthError


# ---------- 配置常量 ----------
_TEMPLATE_SUBDIR = 'templates'  # 模板文件子目录(相对 UPLOAD_FOLDER)
_ALLOWED_TEMPLATE_EXTENSIONS = {'docx'}  # 仅允许 .docx 模板


def _get_template_upload_dir():
    """获取模板上传目录(uploads/templates/),并确保目录存在。"""
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], _TEMPLATE_SUBDIR)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _generate_template_no():
    """
    生成模板编号:TPL-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突;与 contract_no / review_no 同模式)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'TPL-{timestamp}-{suffix}'


def _is_allowed_template_file(filename):
    """校验模板文件扩展名(仅允许 .docx)"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in _ALLOWED_TEMPLATE_EXTENSIONS


def _parse_template_variables(file_path):
    """
    使用 docxtpl 解析模板中的 {{variable}} 占位符

    策略:
    - DocxTemplate.get_undeclared_template_variables() 返回 Jinja2 未声明变量集合
    - 每个变量输出 {name, label, required, sample}
    - label 默认取 name(中文友好名可后续维护)
    - required 默认 true(必填)
    - sample 默认空(示例值,供前端表单提示)

    :param file_path: 模板文件路径
    :return: list[dict] [{name, label, required, sample}]
    :raises BusinessError: 模板文件损坏 / 解析失败
    """
    try:
        from docxtpl import DocxTemplate
        doc = DocxTemplate(file_path)
        var_names = doc.get_undeclared_template_variables()
    except Exception as e:
        logger.exception('[Template] 模板变量解析失败: %s', file_path)
        raise BusinessError(f'模板文件解析失败,请确认是有效的 .docx 模板: {e}')

    # 排序变量名,保证稳定输出
    variables = []
    for name in sorted(var_names):
        variables.append({
            'name': name,
            'label': name,
            'required': True,
            'sample': '',
        })
    logger.info('[Template] 变量解析完成: count=%s names=%s',
                len(variables), [v['name'] for v in variables])
    return variables


def create_template(file, current_user, name=None, description=None,
                    contract_type='未分类', version=None):
    """
    上传并创建模板

    流程:
    1. 校验文件类型(.docx)+ 名称长度 + version 格式
    2. 保存文件到 uploads/templates/{uuid}.docx
    3. 解析 {{variable}} 占位符
    4. 创建 ContractTemplate 记录(status=active,version=传入值或默认 v1.0)

    权限:仅 admin / contract_manager(API 层 @role_required 拦截,此处不重复校验)

    异常边界:
    - 文件保存失败 → 抛 BusinessError(无残留文件)
    - 变量解析失败 → 删除已保存文件,抛 BusinessError
    - DB 插入失败 → 删除已保存文件,抛 BusinessError

    :param file: werkzeug FileStorage
    :param current_user: {'id','role','username'}
    :param name: 模板名称(默认取文件名去扩展名)
    :param description: 模板说明(可选)
    :param contract_type: 合同类型(默认"未分类")
    :param version: 模板版本(可选,默认 v1.0;用于区分同名模板的不同迭代版本)
    :return: dict 模板完整信息
    """
    # ---------- 输入校验 ----------
    if not file or not file.filename:
        raise ValidationError('未选择模板文件')
    original_filename = file.filename
    if not _is_allowed_template_file(original_filename):
        raise ValidationError('模板文件类型不允许,仅支持 .docx')
    if name and len(name) > 255:
        raise ValidationError('模板名称长度不能超过 255 字符')
    if contract_type and len(contract_type) > 64:
        raise ValidationError('合同类型长度不能超过 64 字符')
    if description and len(description) > 5000:
        raise ValidationError('模板说明长度不能超过 5000 字符')
    # version 校验:非空时校验长度,默认 v1.0
    version = (version or 'v1.0').strip()
    if len(version) > 32:
        raise ValidationError('模板版本长度不能超过 32 字符')
    if not version:
        version = 'v1.0'

    # ---------- 1. 保存文件(UUID 命名) ----------
    template_dir = _get_template_upload_dir()
    saved_filename = f'{uuid.uuid4().hex}.docx'
    file_path = os.path.join(template_dir, saved_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception:
        logger.exception('[Template] 模板文件保存失败: filename=%s', original_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise BusinessError('模板文件保存失败,请重试')

    # ---------- 2. 解析变量 ----------
    variables = _parse_template_variables(file_path)

    # ---------- 3. 创建模板记录 ----------
    template_no = _generate_template_no()
    if not name or not name.strip():
        name = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

    template = ContractTemplate(
        template_no=template_no,
        name=name.strip(),
        description=description,
        contract_type=contract_type or '未分类',
        file_name=original_filename,
        file_path=file_path,
        file_size=file_size,
        variables=variables,
        variable_count=len(variables),
        version=version,
        status='active',
        creator_id=current_user['id'],
    )

    try:
        db.session.add(template)
        db.session.commit()
    except Exception:
        db.session.rollback()
        # DB 失败时清理已保存文件
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        logger.exception('[Template] 模板记录创建失败: template_no=%s', template_no)
        raise BusinessError('模板记录创建失败,请重试')

    logger.info('[Template] 模板上传成功: id=%s template_no=%s name=%s version=%s vars=%s creator=%s',
                template.id, template.template_no, template.name, template.version,
                template.variable_count, current_user.get('username'))

    return template.to_dict()


def get_template_list(page=1, size=20, keyword=None, status=None,
                      contract_type=None, version=None, current_user=None):
    """
    模板分页列表

    支持:分页 / 关键字搜索(name + template_no 模糊)/ 状态过滤 / 类型过滤 /
         版本过滤 / 按 created_time DESC 排序

    权限:
    - admin / contract_manager:可见全部模板(含 disabled)
    - employee:仅可见 active 模板(强制 status=active,忽略传入)

    :param page: 页码(默认 1)
    :param size: 每页数量(默认 20,范围 [1, 100])
    :param keyword: 关键字(name / template_no 模糊搜索)
    :param status: 状态过滤(active / disabled)
    :param contract_type: 合同类型过滤
    :param version: 模板版本过滤(精确匹配,如 v1.0)
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
    if status and status not in ContractTemplate.VALID_STATUSES:
        raise ValidationError(
            f'模板状态非法,允许: {", ".join(ContractTemplate.VALID_STATUSES)}')

    # ---------- 查询构建 ----------
    query = ContractTemplate.query.options(joinedload(ContractTemplate.creator))

    # 权限过滤:employee 仅可见 active 模板
    is_manager = current_user and current_user.get('role') in ('admin', 'contract_manager')
    if not is_manager:
        query = query.filter_by(status='active')
    elif status:
        query = query.filter_by(status=status)

    # 关键字搜索(name + template_no 模糊)
    if keyword:
        kw = f'%{keyword}%'
        query = query.filter(
            db.or_(ContractTemplate.name.like(kw),
                   ContractTemplate.template_no.like(kw))
        )

    # 类型过滤
    if contract_type:
        query = query.filter_by(contract_type=contract_type)

    # 版本过滤(精确匹配,区分大小写)
    if version:
        query = query.filter_by(version=version)

    # 排序:created_time DESC
    query = query.order_by(ContractTemplate.created_time.desc())

    # ---------- 分页 ----------
    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    items = [t.to_dict(include_variables=False) for t in pagination.items]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


def get_template(template_id, current_user=None):
    """
    获取模板详情(含 variables)

    权限:
    - admin / contract_manager:可见任意模板
    - employee:仅可见 active 模板(disabled 返回 404 防枚举)

    :param template_id: 模板 ID
    :param current_user: {'id','role'}
    :return: dict 模板完整信息(含 variables)
    """
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise ValidationError('模板 ID 非法')

    template = db.session.get(ContractTemplate, tid)
    if not template:
        raise NotFoundError('模板不存在')

    # employee 仅可见 active 模板(404 防枚举)
    is_manager = current_user and current_user.get('role') in ('admin', 'contract_manager')
    if not is_manager and template.status != 'active':
        raise NotFoundError('模板不存在')

    return template.to_dict(include_variables=True)


def update_template_status(template_id, target_status, current_user):
    """
    启停模板(active ⇄ disabled)

    权限:仅 admin / contract_manager(API 层 @role_required 拦截)

    :param template_id: 模板 ID
    :param target_status: 目标状态(active / disabled)
    :param current_user: {'id','role','username'}
    :return: dict 更新后的模板信息
    """
    if not target_status or target_status not in ContractTemplate.VALID_STATUSES:
        raise ValidationError(
            f'模板状态非法,允许: {", ".join(ContractTemplate.VALID_STATUSES)}')

    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise ValidationError('模板 ID 非法')

    template = db.session.get(ContractTemplate, tid)
    if not template:
        raise NotFoundError('模板不存在')

    # active ⇄ disabled 可反复切换(同状态也允许,幂等)
    old_status = template.status
    template.status = target_status
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Template] 模板状态更新失败: template_id=%s', tid)
        raise BusinessError('模板状态更新失败,请重试')

    logger.info('[Template] 模板状态变更: id=%s %s → %s operator=%s',
                template.id, old_status, target_status, current_user.get('username'))

    return template.to_dict(include_variables=True)


def delete_template(template_id, current_user):
    """
    删除模板(硬删除 + 清理文件)

    设计说明:
    - 模板删除为硬删除(连同文件一起清理)
    - 若模板已被用于生成(存在 generated_contracts 记录),禁止删除,提示"已有生成记录,建议停用"
      (避免历史生成记录的 template_id 悬空;若需删除,先停用)
    - 文件清理失败不阻断 DB 删除(记录孤儿文件,日志告警)

    权限:仅 admin / contract_manager(API 层 @role_required 拦截)

    :param template_id: 模板 ID
    :param current_user: {'id','role','username'}
    """
    try:
        tid = int(template_id)
    except (TypeError, ValueError):
        raise ValidationError('模板 ID 非法')

    template = db.session.get(ContractTemplate, tid)
    if not template:
        raise NotFoundError('模板不存在')

    # 检查是否已被用于生成
    if template.generations.count() > 0:
        raise BusinessError('该模板已有生成记录,无法删除;建议改为停用(disabled)')

    file_path = template.file_path
    template_no = template.template_no

    try:
        db.session.delete(template)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Template] 模板删除失败: template_id=%s', tid)
        raise BusinessError('模板删除失败,请重试')

    # 清理文件(DB 已删除,文件清理失败仅告警)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except OSError:
            logger.warning('[Template] 模板文件清理失败(记录已删除): %s', file_path)

    logger.info('[Template] 模板删除成功: id=%s template_no=%s operator=%s',
                tid, template_no, current_user.get('username'))


def get_template_file_path(template_id):
    """
    获取模板文件路径(供 generation_service 内部使用,不暴露给 API 层)

    :param template_id: 模板 ID
    :return: (template, file_path) 模板实例 + 文件路径
    :raises NotFoundError: 模板不存在
    """
    template = db.session.get(ContractTemplate, int(template_id))
    if not template:
        raise NotFoundError('模板不存在')
    return template, template.file_path
