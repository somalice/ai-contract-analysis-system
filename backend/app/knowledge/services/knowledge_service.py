"""
知识文档业务服务(Sprint 4 - v0.6.0)

职责:
- upload_knowledge_document:上传知识文档 → 解析 → chunk → embedding → FAISS → 持久化
- get_knowledge_document_list:分页列表(含 chunk_count / embedding_status)
- get_knowledge_document_detail:详情(含 chunks 概要)
- delete_knowledge_document:软删 + 从 FAISS 移除向量

编排链:
api/knowledge/routes.py
  → knowledge_service
    → parser(文件 → 文本 + page_map)
    → chunker(文本 → Chunk[])
    → embedding(Chunk → 向量)
    → vectorstore(向量 → FAISS)
    → models(knowledge_documents / knowledge_chunks 持久化)

权限:
- admin / contract_manager:可上传 / 删除任意知识文档
- 全部角色:可查询知识文档列表 / 详情(employee 亦可,知识库为公共知识)

约束:
- 不直接渲染模板、不访问 request 对象
- 禁止 print() / return str(e)
- 不修改 Sprint 3 的 Document / AnalysisTask / ContractField 表
- Embedding 失败:chunks + document 仍持久化,embedding_status=failed(可重试)
"""
import os
import uuid
from datetime import datetime
from flask import current_app
from sqlalchemy.orm import joinedload

from app.extensions.db import db
from app.extensions.logger import logger
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_chunk import KnowledgeChunk
from app.utils.exceptions import ValidationError, BusinessError, NotFoundError
from app.knowledge.parser import parse_document, get_supported_extensions
from app.knowledge.chunk import SemanticChunker, get_chunker
from .vector_store_registry import vector_store_registry


# ---------- 配置常量 ----------
_KNOWLEDGE_SUBDIR = 'knowledge'  # 知识文件子目录(相对 UPLOAD_FOLDER)


def _get_knowledge_upload_dir():
    """获取知识文档上传目录(uploads/knowledge/),并确保目录存在。"""
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], _KNOWLEDGE_SUBDIR)
    os.makedirs(upload_dir, exist_ok=True)
    return upload_dir


def _generate_doc_no():
    """
    生成知识文档编号:KD-YYYYMMDDHHMMSS-XXXXXXXX
    (时间戳 + 8 位 UUID 大写,避免并发冲突)
    """
    timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
    suffix = uuid.uuid4().hex[:8].upper()
    return f'KD-{timestamp}-{suffix}'


def _get_file_ext(filename: str) -> str:
    """获取小写扩展名(无点)"""
    return filename.rsplit('.', 1)[1].lower() if '.' in filename else ''


def _is_supported_knowledge_file(filename: str) -> bool:
    """校验是否为支持的知识文档类型(pdf/docx/txt)"""
    return _get_file_ext(filename) in get_supported_extensions()


# ============================================================
# 上传知识文档
# ============================================================
def upload_knowledge_document(file, current_user, title=None, source_type='manual_upload',
                              knowledge_type='general', chunk_title=None):
    """
    上传知识文档:保存 → 解析 → chunk → embedding → FAISS → 持久化

    流程:
    1. 校验文件类型(pdf/docx/txt)
    2. 保存文件到 uploads/knowledge/{uuid}.ext
    3. 创建 KnowledgeDocument(processing)
    4. parse_document → 文本 + page_map
    5. SemanticChunker.split → Chunk[]
    6. 持久化 KnowledgeChunk
    7. embedding.encode + vectorstore.add → 回写 vector_id
    8. 更新 document 状态 + vectorstore.save
    9. 提交事务

    容错:
    - 解析失败 → 抛 BusinessError(删除已存文件)
    - embedding/FAISS 失败 → chunks + document 仍持久化,embedding_status=failed
      (可重新触发;本阶段未提供重试接口,可删除后重新上传)

    :param file: werkzeug FileStorage
    :param current_user: {'id','role','username'}
    :param title: 文档标题(默认取文件名去扩展名)
    :param source_type: 来源类型(默认 manual_upload)
    :param knowledge_type: 知识类型(Sprint 7 新增,默认 general;
        允许 general/contract/bid/company/case/qualification;向后兼容)
    :param chunk_title: Sprint 8.8 可选,注入 chunk 的文档标题(用于上下文前缀);
        默认取 title(便于导入工具区分"库内标题"与"chunk 标题",如评估测试文档)
    :return: dict 知识文档信息
    """
    # ---------- 1. 校验 ----------
    original_filename = file.filename
    if not original_filename:
        raise ValidationError('文件名为空')
    if not _is_supported_knowledge_file(original_filename):
        raise ValidationError(
            f'知识文档类型不支持,允许: {", ".join(get_supported_extensions())}')

    if title and len(title) > 255:
        raise ValidationError('文档标题长度不能超过 255 字符')

    # 校验 knowledge_type(Sprint 7 新增)
    if knowledge_type not in KnowledgeDocument.VALID_KNOWLEDGE_TYPES:
        raise ValidationError(
            f'知识类型非法,允许: {", ".join(KnowledgeDocument.VALID_KNOWLEDGE_TYPES)}')

    ext = _get_file_ext(original_filename)

    # ---------- 2. 保存文件 ----------
    knowledge_dir = _get_knowledge_upload_dir()
    saved_filename = f"{uuid.uuid4().hex}.{ext}"
    file_path = os.path.join(knowledge_dir, saved_filename)

    try:
        file.save(file_path)
        file_size = os.path.getsize(file_path)
    except Exception:
        logger.exception('[Knowledge:upload] 文件保存失败: filename=%s', original_filename)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
            except OSError:
                pass
        raise BusinessError('文件保存失败,请重试')

    # ---------- 3. 创建 KnowledgeDocument ----------
    doc_no = _generate_doc_no()
    if not title or not title.strip():
        title = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

    document = KnowledgeDocument(
        doc_no=doc_no,
        title=title.strip(),
        knowledge_type=knowledge_type,
        source_type=source_type,
        file_name=original_filename,
        file_path=file_path,
        file_size=file_size,
        file_type=ext,
        page_count=0,
        text_content=None,
        text_length=0,
        chunk_count=0,
        embedding_status='processing',
        vector_indexed=False,
        uploader_id=current_user['id'],
        status='active',
        error_message=None,
    )
    db.session.add(document)
    db.session.flush()  # 拿到 document.id

    logger.info('[Knowledge:upload] 知识文档创建: doc_no=%s uploader=%s',
                doc_no, current_user.get('username'))

    # ---------- 4. 解析文档 ----------
    try:
        parsed = parse_document(file_path)
    except Exception:
        logger.exception('[Knowledge:upload] 文档解析失败: doc_no=%s', doc_no)
        document.embedding_status = 'failed'
        document.error_message = '文档解析失败'
        db.session.commit()
        # 解析失败:保留文件(可调试),返回 failed 状态
        return document.to_dict()

    if not parsed.text or not parsed.text.strip():
        logger.warning('[Knowledge:upload] 文档无文本: doc_no=%s', doc_no)
        document.embedding_status = 'failed'
        document.error_message = '文档未提取到文本(可能是扫描件或空文件)'
        document.text_content = parsed.text
        db.session.commit()
        return document.to_dict()

    # ---------- 5. Chunk 切分 ----------
    # Sprint 8.6: 使用工厂按 config.CHUNKER_MODE 选择切分器
    # (auto 模式:合同文档自动走 ContractStructureChunker,其余回退 SemanticChunker)
    # Sprint 8.8: 注入 doc_title,contract chunk 前置【合同名称】上下文前缀
    # (chunk_title 可选覆盖:便于"库内标题"与"chunk 标题"分离,默认即文档标题)
    chunker = get_chunker(filename=original_filename, text=parsed.text,
                          knowledge_type=knowledge_type,
                          doc_title=(chunk_title or title))
    chunks = chunker.split(parsed.text, parsed.page_map)

    if not chunks:
        logger.warning('[Knowledge:upload] Chunk 切分为空: doc_no=%s', doc_no)
        document.embedding_status = 'failed'
        document.error_message = '文本切分后无有效 Chunk'
        document.text_content = parsed.text
        document.text_length = len(parsed.text)
        db.session.commit()
        return document.to_dict()

    # ---------- 6. 持久化 KnowledgeChunk ----------
    chunk_rows = []
    for c in chunks:
        row = KnowledgeChunk(
            document_id=document.id,
            chunk_index=c.chunk_index,
            page_number=c.page_number,
            start_offset=c.start_offset,
            end_offset=c.end_offset,
            token_count=c.token_count,
            text=c.text,
            chunk_metadata=c.metadata,
            vector_id=None,
        )
        db.session.add(row)
        chunk_rows.append(row)
    db.session.flush()  # 拿到 chunk.id

    # 更新文档统计
    document.text_content = parsed.text
    document.text_length = len(parsed.text)
    document.page_count = parsed.page_count
    document.chunk_count = len(chunk_rows)

    # ---------- 7. Embedding + VectorStore ----------
    try:
        embedding = vector_store_registry.embedding
        vectorstore = vector_store_registry.vectorstore

        texts = [c.text for c in chunks]
        vectors = embedding.encode(texts)

        chunk_ids = [r.id for r in chunk_rows]
        document_ids = [document.id] * len(chunk_rows)
        vector_ids = vectorstore.add(vectors, chunk_ids, document_ids)

        # 回写 vector_id
        for row, vid in zip(chunk_rows, vector_ids):
            row.vector_id = vid

        vectorstore.save()

        document.embedding_status = 'completed'
        document.vector_indexed = True
        document.error_message = None
        logger.info('[Knowledge:upload] Embedding + 入库完成: doc_no=%s chunks=%s',
                    doc_no, len(chunk_rows))
    except Exception:
        logger.exception('[Knowledge:upload] Embedding/FAISS 失败: doc_no=%s', doc_no)
        # chunks + document 仍持久化,标记 failed(可删除后重新上传)
        document.embedding_status = 'failed'
        document.vector_indexed = False
        document.error_message = 'Embedding 或向量入库失败(文档与 Chunk 已保存,但不可检索)'

    # ---------- 8. 提交事务 ----------
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Knowledge:upload] 事务提交失败: doc_no=%s', doc_no)
        raise BusinessError('知识文档保存失败,请重试')

    # ---------- Sprint 8: 知识库更新 → 失效全部 RAG 缓存(命中可能过时)----------
    try:
        from app import services as _svc
        _svc.cache_service.invalidate_prefix('rag:')
    except Exception as _e:
        logger.warning('[Knowledge:upload] RAG 缓存失效失败(不影响业务): %s', _e)

    return document.to_dict()


# ============================================================
# 知识文档列表
# ============================================================
def get_knowledge_document_list(page=1, size=20, keyword=None,
                                embedding_status=None, knowledge_type=None,
                                current_user=None):
    """
    知识文档分页列表
    支持:分页 / 关键字搜索(title + doc_no)/ embedding_status 过滤 /
         knowledge_type 过滤(Sprint 7 新增,向后兼容)/
         按 created_time DESC 排序 / 仅 active 文档(排除软删)

    权限:全部角色可查(知识库为公共知识)

    :param page: 页码
    :param size: 每页数量
    :param keyword: 关键字(title / doc_no 模糊)
    :param embedding_status: 状态过滤(pending/processing/completed/failed)
    :param knowledge_type: 知识类型过滤(Sprint 7 新增,默认 None=不过滤;
        允许 general/contract/bid/company/case/qualification)
    :param current_user: {'id','role'}
    :return: dict {items, total, page, size}
    """
    try:
        page = max(1, int(page))
    except (TypeError, ValueError):
        page = 1
    try:
        size = max(1, min(100, int(size)))
    except (TypeError, ValueError):
        size = 20

    if embedding_status and embedding_status not in KnowledgeDocument.VALID_EMBEDDING_STATUSES:
        raise ValidationError(
            f'embedding_status 非法,允许: {", ".join(KnowledgeDocument.VALID_EMBEDDING_STATUSES)}')

    if knowledge_type and knowledge_type not in KnowledgeDocument.VALID_KNOWLEDGE_TYPES:
        raise ValidationError(
            f'知识类型非法,允许: {", ".join(KnowledgeDocument.VALID_KNOWLEDGE_TYPES)}')

    query = KnowledgeDocument.query.options(joinedload(KnowledgeDocument.uploader))

    # 仅查 active(排除软删)
    query = query.filter_by(status='active')

    if keyword:
        kw = f"%{keyword}%"
        query = query.filter(
            db.or_(KnowledgeDocument.title.like(kw),
                   KnowledgeDocument.doc_no.like(kw))
        )

    if embedding_status:
        query = query.filter_by(embedding_status=embedding_status)

    if knowledge_type:
        query = query.filter_by(knowledge_type=knowledge_type)

    query = query.order_by(KnowledgeDocument.created_time.desc())

    total = query.count()
    pagination = query.paginate(page=page, per_page=size, error_out=False)
    items = [d.to_dict(include_text=False) for d in pagination.items]

    return {
        'items': items,
        'total': total,
        'page': page,
        'size': size,
    }


# ============================================================
# 知识文档详情
# ============================================================
def get_knowledge_document_detail(document_id, current_user=None):
    """
    知识文档详情(含 chunks 概要:前 3 个 chunk 预览)

    :param document_id: 文档 ID
    :param current_user: {'id','role'}
    :return: dict 知识文档信息
    """
    try:
        did = int(document_id)
    except (TypeError, ValueError):
        raise ValidationError('文档 ID 非法')

    document = db.session.get(KnowledgeDocument, did)
    if not document or document.status != 'active':
        raise NotFoundError('知识文档不存在')

    return document.to_dict(include_text=False, include_chunks=True)


# ============================================================
# 删除知识文档
# ============================================================
def delete_knowledge_document(document_id, current_user):
    """
    删除知识文档(软删 + 从 FAISS 移除向量)

    流程:
    1. 校验存在 + 权限(admin / contract_manager)
    2. 查该文档所有 chunk 的 vector_id
    3. 从 FAISS 移除向量(若已索引)
    4. vectorstore.save
    5. 软删:document.status=deleted(记录保留;chunk 记录保留)
    6. 提交事务

    :param document_id: 文档 ID
    :param current_user: {'id','role','username'}
    :return: dict {id, doc_no, status}
    """
    # 权限:仅 admin / contract_manager(service 层兜底;API 层亦有 role_required)
    if current_user.get('role') not in ('admin', 'contract_manager'):
        raise NotFoundError('知识文档不存在')  # 403 亦可,这里用 404 防枚举

    try:
        did = int(document_id)
    except (TypeError, ValueError):
        raise ValidationError('文档 ID 非法')

    document = db.session.get(KnowledgeDocument, did)
    if not document or document.status != 'active':
        raise NotFoundError('知识文档不存在')

    # ---------- 从 FAISS 移除向量 ----------
    if document.vector_indexed:
        try:
            vectorstore = vector_store_registry.vectorstore
            vector_ids = vectorstore.get_vector_ids_by_document(document.id)
            if vector_ids:
                vectorstore.delete(vector_ids)
                vectorstore.save()
                logger.info('[Knowledge:delete] 从 FAISS 移除 %s 条向量: doc_no=%s',
                            len(vector_ids), document.doc_no)
            # 清空 chunk 的 vector_id
            KnowledgeChunk.query.filter_by(document_id=document.id).update(
                {KnowledgeChunk.vector_id: None}
            )
        except Exception:
            logger.exception('[Knowledge:delete] FAISS 移除失败(仍软删记录): doc_no=%s',
                             document.doc_no)
            # 不阻断软删:记录仍标记 deleted,向量可能残留(可重建索引)

    # ---------- 软删 ----------
    document.status = 'deleted'
    document.vector_indexed = False

    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('[Knowledge:delete] 事务提交失败: doc_no=%s', document.doc_no)
        raise BusinessError('删除失败,请重试')

    logger.info('[Knowledge:delete] 知识文档已删除: doc_no=%s operator=%s',
                document.doc_no, current_user.get('username'))

    # ---------- Sprint 8: 知识库删除 → 失效全部 RAG 缓存 ----------
    try:
        from app import services as _svc
        _svc.cache_service.invalidate_prefix('rag:')
    except Exception as _e:
        logger.warning('[Knowledge:delete] RAG 缓存失效失败(不影响业务): %s', _e)

    return {
        'id': document.id,
        'doc_no': document.doc_no,
        'status': document.status,
    }
