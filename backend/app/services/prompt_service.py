"""
Prompt 模板管理服务(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

职责:
- get_active_template(name):查询 DB 中该 name 的 active 模板;用于 Agent 加载时 DB 优先
- load_prompt(name, fallback_file, parse_file_fn):组合函数;DB 命中则返回,否则调 parse_file_fn 读 .md 文件(保持向后兼容)
- CRUD + activate(同 name 仅一个 active,用事务保证)

设计原则:
- **只读方法(get_active_template / load_prompt)全程 try/except**;任意异常 → 回退 .md 文件,绝不抛出
- PromptTemplate 异常绝不影响 Agent 主流程(保持 Sprint 0~7 行为)
- parse_prompt_file 抽取为复用工具;4 个 Agent + RAG 的 _load_prompt 原逻辑保持不变仅顶部加 DB 优先查询
"""
from datetime import datetime
from app.extensions.db import db
from app.extensions.logger import logger
from app.models.prompt_template import PromptTemplate, VALID_NAMES, VALID_STATUS
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError


def parse_prompt_file(file_path):
    """
    从 .md 文件解析 ## System Prompt / ## Human Prompt 两段文本。

    该函数由 4 处 `_load_prompt()` 原文件解析逻辑**抽取复用**;
    与原实现完全兼容(保留兜底默认值、解析规则)。

    :return: (system_prompt, human_prompt)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError as e:
        logger.warning('[PromptService] 文件加载失败: %s err=%s', file_path, e)
        raise

    system_lines = []
    human_lines = []
    current = None

    for line in content.split('\n'):
        s = line.strip()
        if s == '## System Prompt':
            current = 'system'
            continue
        if s == '## Human Prompt':
            current = 'human'
            continue
        if s.startswith('## ') and current is not None:
            # 其他 ## 子章节(如 ## Examples)出界后停止收集
            current = None
            continue
        if current == 'system':
            system_lines.append(line)
        elif current == 'human':
            human_lines.append(line)

    system = '\n'.join(system_lines).strip()
    human = '\n'.join(human_lines).strip()
    return system, human


def get_active_template(name):
    """
    查询指定 name 的 active 模板(优先用于 Agent DB 优先加载)。

    :return: dict(含 system_prompt/human_prompt/name/version) 或 None(未找到 / 异常)
    """
    try:
        tpl = (
            PromptTemplate.query
            .filter_by(name=name, status='active')
            .order_by(PromptTemplate.updated_time.desc())
            .first()
        )
        if tpl is None:
            return None
        return tpl.to_dict(include_content=True)
    except Exception as e:
        # DB 故障:不抛出,调用方应回退文件
        logger.warning('[PromptService] get_active_template 失败: name=%s err=%s', name, e)
        return None


def load_prompt(name, fallback_file, default_system=None, default_human=None):
    """
    统一加载入口:DB 优先 → 文件 → 兜底 default。

    全路径永不抛出(任何异常 → 返回 default_system/default_human)。

    :param name: VALID_NAMES 中的名称
    :param fallback_file: .md 绝对路径
    :param default_system: 双层失败时的兜底系统提示
    :param default_human: 双层失败时的兜底用户提示模板
    :return: (system_prompt, human_prompt)
    """
    # 1. DB 优先
    try:
        tpl = get_active_template(name)
        if tpl and tpl.get('system_prompt') and tpl.get('human_prompt'):
            return tpl['system_prompt'], tpl['human_prompt']
    except Exception as e:
        logger.warning('[PromptService] DB prompt 读取异常,降级文件: name=%s err=%s', name, e)

    # 2. 文件降级
    try:
        return parse_prompt_file(fallback_file)
    except Exception as e:
        logger.warning('[PromptService] 文件降级失败,使用最终 default: name=%s err=%s', name, e)

    # 3. 最终兜底(default 通常为原 _load_prompt 内联的 default)
    sys_ = default_system or '你是企业合同与招投标知识助手,输出严格 JSON 决策,禁止编造。'
    hum_ = default_human or '{input}'
    return sys_, hum_


# ============================================================
# CRUD 管理(仅 API 层使用)
# ============================================================
def _validate_name(name):
    if not name or (VALID_NAMES and name not in VALID_NAMES):
        raise ValidationError(f'name 非法,允许值: {", ".join(VALID_NAMES)}')


def _validate_status(status):
    if status not in VALID_STATUS:
        raise ValidationError(f'status 非法,允许值: {", ".join(VALID_STATUS)}')


def list_templates(name=None, status=None, page=1, size=20):
    """分页查询(过滤:name/status)"""
    page, size = _normalize_paging(page, size)
    q = PromptTemplate.query
    if name:
        _validate_name(name)
        q = q.filter_by(name=name)
    if status:
        _validate_status(status)
        q = q.filter_by(status=status)
    total = q.count()
    items = (
        q.order_by(PromptTemplate.name.asc(), PromptTemplate.version.desc())
        .offset((page - 1) * size).limit(size)
        .all()
    )
    return {
        'total': total,
        'page': page,
        'size': size,
        'items': [t.to_dict(include_content=True) for t in items],
    }


def get_template(prompt_id, current_user=None):
    """查询详情"""
    try:
        pid = int(prompt_id)
    except (TypeError, ValueError):
        raise ValidationError('Prompt ID 非法')
    tpl = db.session.get(PromptTemplate, pid)
    if not tpl:
        raise NotFoundError('Prompt 模板不存在')
    return tpl.to_dict(include_content=True)


def create_template(name, version, system_prompt, human_prompt,
                    description=None, status='draft', created_by=None):
    """创建模板(默认 draft 不影响现有 active)"""
    _validate_name(name)
    if not version or not isinstance(version, str) or len(version) > 32:
        raise ValidationError('version 非法(最大 32 字符)')
    if not system_prompt or not isinstance(system_prompt, str):
        raise ValidationError('system_prompt 不能为空')
    if not human_prompt or not isinstance(human_prompt, str):
        raise ValidationError('human_prompt 不能为空')
    _validate_status(status)

    # 同一 name 不允许重复 version
    exists = (
        PromptTemplate.query
        .filter_by(name=name, version=version)
        .first()
    )
    if exists:
        raise BusinessError(f'name={name} version={version} 已存在')

    tpl = PromptTemplate(
        name=name,
        version=version,
        system_prompt=system_prompt,
        human_prompt=human_prompt,
        description=description,
        status=status,
        created_by=created_by,
    )
    # 若直接创建为 active,则同 name 其他 active 需置 inactive
    if status == 'active':
        _deactivate_others(name, exclude=tpl)

    db.session.add(tpl)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('[PromptService] create 提交失败: %s', e)
        raise BusinessError(f'创建失败: {e}')
    logger.info('[PromptService] 模板创建: id=%s name=%s version=%s status=%s',
                tpl.id, tpl.name, tpl.version, tpl.status)
    return tpl.to_dict(include_content=True)


def update_template(prompt_id, current_user, *, system_prompt=None, human_prompt=None,
                    description=None, status=None, version=None):
    """更新模板;status → active 自动触发同 name 其他置 inactive"""
    tpl = db.session.get(PromptTemplate, prompt_id)
    if not tpl:
        raise NotFoundError('Prompt 模板不存在')

    changed = False
    if system_prompt is not None:
        tpl.system_prompt = system_prompt
        changed = True
    if human_prompt is not None:
        tpl.human_prompt = human_prompt
        changed = True
    if description is not None:
        tpl.description = description
        changed = True
    if version is not None:
        if not version or len(version) > 32:
            raise ValidationError('version 非法')
        conflict = (
            PromptTemplate.query
            .filter(PromptTemplate.name == tpl.name, PromptTemplate.version == version,
                    PromptTemplate.id != tpl.id)
            .first()
        )
        if conflict:
            raise BusinessError('version 冲突')
        tpl.version = version
        changed = True
    if status is not None:
        _validate_status(status)
        tpl.status = status
        changed = True
        if status == 'active':
            _deactivate_others(tpl.name, exclude=tpl)

    if changed:
        tpl.updated_time = datetime.utcnow()
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('[PromptService] update 提交失败: id=%s err=%s', prompt_id, e)
        raise BusinessError(f'更新失败: {e}')
    logger.info('[PromptService] 模板更新: id=%s name=%s status=%s', tpl.id, tpl.name, tpl.status)
    return tpl.to_dict(include_content=True)


def activate_template(prompt_id, current_user):
    """激活指定模板(同 name 其他 active 自动置 inactive)"""
    return update_template(prompt_id, current_user, status='active')


def delete_template(prompt_id, current_user):
    """删除模板(active 模板禁止直接删除,需先 inactive)"""
    tpl = db.session.get(PromptTemplate, prompt_id)
    if not tpl:
        raise NotFoundError('Prompt 模板不存在')
    if tpl.status == 'active':
        raise BusinessError('active 状态模板禁止直接删除,请先停用或 activate 其他版本')
    db.session.delete(tpl)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.exception('[PromptService] delete 提交失败: id=%s err=%s', prompt_id, e)
        raise BusinessError(f'删除失败: {e}')
    logger.info('[PromptService] 模板删除: id=%s name=%s version=%s', prompt_id, tpl.name, tpl.version)
    return {'deleted': True, 'id': prompt_id}


def _deactivate_others(name, exclude):
    """将同 name 的其他 active 模板置 inactive(exclude 除外)"""
    others = (
        PromptTemplate.query
        .filter_by(name=name, status='active')
        .all()
    )
    for t in others:
        if exclude is not None and t.id == exclude.id:
            continue
        t.status = 'inactive'
        t.updated_time = datetime.utcnow()


def _normalize_paging(page, size):
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(int(size), 100))
    except (TypeError, ValueError):
        size = 20
    return page, size
