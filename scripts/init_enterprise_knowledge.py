"""
Sprint 8.8 企业级合同知识库初始化脚本

功能:
  将 backend/app/evaluation/enterprise_documents/ 下的企业级知识文档批量导入知识库,
  复用现有 KnowledgeDocument + Embedding + FAISS 链路(knowledge_service.upload_knowledge_document),
  不重新实现 RAG,不修改业务模块。

  目录结构(文件名前缀 → knowledge_type):
    legal_*      → general(法律基础知识)
    review_*     → contract(合同审核规则)
    risk_*       → contract(合同风险规则)
    bid_*        → bid(招投标规则)
    enterprise_* → company(企业内部管理规则)

使用:
  cd backend && python ../scripts/init_enterprise_knowledge.py [--dry-run] [--clear]

  --dry-run: 仅扫描文档,不实际导入
  --clear:   导入前先删除已有的企业知识文档(按标题前缀 [企业知识] 识别)

约束:
  - 复用 knowledge_service.upload_knowledge_document (FileStorage 入口)
  - 不修改 knowledge_service / RAG 链路 / 数据库结构
  - 企业文档标题前缀 [企业知识],与评估测试文档([评估测试])相互独立,
    便于各自 --clear 时互不误删
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
ENTERPRISE_DOCS_DIR = BACKEND_DIR / 'app' / 'evaluation' / 'enterprise_documents'
sys.path.insert(0, str(BACKEND_DIR))

# 企业知识文档标识(标题前缀),用于 --clear 时识别
ENTERPRISE_TITLE_PREFIX = '[企业知识] '

# 文件名前缀 → knowledge_type 映射
_PREFIX_KNOWLEDGE_TYPE = {
    'legal': 'general',
    'review': 'contract',
    'risk': 'contract',
    'bid': 'bid',
    'enterprise': 'company',
}


def build_app():
    """创建 Flask app。"""
    from app import create_app
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / '.env')
    return create_app()


def get_admin_user(app):
    """获取一个 admin 用户作为导入操作者。"""
    with app.app_context():
        from app.models.user import User
        admin = User.query.filter_by(role='admin').order_by(User.id.asc()).first()
        if admin is None:
            raise RuntimeError('未找到 admin 用户,请先创建管理员账号')
        return {'id': admin.id, 'username': admin.username, 'role': admin.role}


def list_enterprise_documents():
    """扫描 enterprise_documents/ 下的 .txt/.pdf/.docx 文件。"""
    if not ENTERPRISE_DOCS_DIR.exists():
        return []
    exts = ('.txt', '.pdf', '.docx')
    files = sorted(
        [p for p in ENTERPRISE_DOCS_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in exts],
        key=lambda p: p.name,
    )
    return files


def infer_knowledge_type(filename: str) -> str:
    """按文件名前缀推断 knowledge_type。"""
    for prefix, ktype in _PREFIX_KNOWLEDGE_TYPE.items():
        if filename.startswith(prefix + '_'):
            return ktype
    return 'general'


def clear_existing_enterprise_docs(app):
    """删除已有的企业知识文档(按标题前缀识别,复用 knowledge_service 软删)。"""
    from app.extensions.db import db
    from app.models.knowledge_document import KnowledgeDocument
    from app.knowledge.services import knowledge_service

    cleared = 0
    with app.app_context():
        admin = get_admin_user(app)
        docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{ENTERPRISE_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .all()
        )
        print(f'[Clear] 发现 {len(docs)} 份历史企业知识文档,开始删除 ...')
        for d in docs:
            try:
                knowledge_service.delete_knowledge_document(d.id, admin)
                cleared += 1
                print(f'  - 删除 doc_no={d.doc_no} title={d.title}')
            except Exception as e:
                print(f'  ! 删除失败 doc_no={d.doc_no}: {e}')
                db.session.rollback()
    print(f'[Clear] 完成,共删除 {cleared} 份')
    return cleared


def import_one_document(app, file_path, admin_user, chunk_title=None):
    """将单个文件导入知识库(复用 upload_knowledge_document)。"""
    from werkzeug.datastructures import FileStorage
    from app.knowledge.services import knowledge_service

    # 去掉文件名中的前缀序号和扩展名,作为标题
    stem = file_path.stem  # 如 legal_让与担保与非典型担保
    raw_title = stem.split('_', 1)[-1] if '_' in stem else stem
    title = f'{ENTERPRISE_TITLE_PREFIX}{raw_title}'
    knowledge_type = infer_knowledge_type(stem)

    with open(file_path, 'rb') as f:
        data = f.read()
    file_storage = FileStorage(
        stream=io.BytesIO(data),
        filename=file_path.name,
        content_type='text/plain',
    )

    with app.app_context():
        result = knowledge_service.upload_knowledge_document(
            file=file_storage,
            current_user=admin_user,
            title=title,
            source_type='manual_upload',
            knowledge_type=knowledge_type,
            chunk_title=chunk_title,
        )
    return result


def rebuild_enterprise_knowledge(app, clear=True, clean_title=False):
    """导入企业级知识文档(clear 后按当前 chunk 配置重新导入全部企业文档)。

    :param clean_title: True 时注入纯净 chunk 标题(不带 [企业知识] 前缀)。
    :return: dict(success, failed, results, docs, chunks)
    """
    if clear:
        print('\n[Init] --clear 模式,先清理历史企业知识文档 ...')
        clear_existing_enterprise_docs(app)

    print('\n[Init] 获取 admin 用户 ...')
    admin = get_admin_user(app)

    docs = list_enterprise_documents()
    print(f'[Init] 扫描企业知识文档目录: {ENTERPRISE_DOCS_DIR}')
    print(f'[Init] 发现 {len(docs)} 份企业知识文档')
    if not docs:
        print('[Init] ⚠ 未找到企业知识文档')
        return None

    print('\n[Init] 开始批量导入(复用 knowledge_service.upload_knowledge_document) ...')
    success = failed = 0
    results = []
    for idx, fp in enumerate(docs, 1):
        stem = fp.stem
        title = f'{ENTERPRISE_TITLE_PREFIX}{stem.split("_", 1)[-1] if "_" in stem else stem}'
        chunk_title = None
        if clean_title:
            chunk_title = stem.split('_', 1)[-1] if '_' in stem else stem
        try:
            print(f'  [{idx:02d}/{len(docs)}] 导入 {fp.name} ...', end=' ')
            result = import_one_document(app, fp, admin, chunk_title=chunk_title)
            emb_status = result.get('embedding_status')
            chunk_count = result.get('chunk_count', 0)
            if emb_status == 'completed':
                print(f'✅ chunks={chunk_count} embedding=completed')
                success += 1
                results.append({'file': fp.name, 'status': 'ok', 'chunks': chunk_count})
            else:
                err = result.get('error_message', '')
                print(f'⚠ embedding={emb_status} chunks={chunk_count} err={err}')
                failed += 1
                results.append({'file': fp.name, 'status': 'emb_failed', 'chunks': chunk_count, 'err': err})
        except Exception as e:
            print(f'❌ {type(e).__name__}: {e}')
            failed += 1
            results.append({'file': fp.name, 'status': 'error', 'err': str(e)})

    # 统计知识库现状
    print('\n[Init] 知识库现状统计 ...')
    with app.app_context():
        from app.extensions.db import db
        from app.models.knowledge_document import KnowledgeDocument
        from app.models.knowledge_chunk import KnowledgeChunk
        total_docs = KnowledgeDocument.query.filter_by(status='active').count()
        ent_docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{ENTERPRISE_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .count()
        )
        completed_docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{ENTERPRISE_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .filter(KnowledgeDocument.embedding_status == 'completed')
            .count()
        )
        ent_chunks = (
            db.session.query(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .filter(KnowledgeDocument.title.like(f'{ENTERPRISE_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .count()
        )

    print(f'\n[Init] ===== 导入结果 =====')
    print(f'  本次导入: 成功 {success} / 失败 {failed} / 共 {len(docs)}')
    print(f'  知识库总文档数(active): {total_docs}')
    print(f'  企业知识文档数(active): {ent_docs} (embedding completed: {completed_docs})')
    print(f'  企业知识 Chunk 数: {ent_chunks}')

    return {
        'success': success, 'failed': failed, 'total': len(docs),
        'ent_docs': ent_docs, 'completed_docs': completed_docs,
        'ent_chunks': ent_chunks, 'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description='Sprint 8.8 企业级合同知识库初始化')
    parser.add_argument('--dry-run', action='store_true', help='仅扫描,不导入')
    parser.add_argument('--clear', action='store_true', help='导入前删除历史企业知识文档')
    args = parser.parse_args()

    print('[Init] 初始化 Flask app ...')
    app = build_app()

    docs = list_enterprise_documents()
    print(f'[Init] 扫描企业知识文档目录: {ENTERPRISE_DOCS_DIR}')
    print(f'[Init] 发现 {len(docs)} 份企业知识文档')
    for p in docs:
        print(f'  - {p.name} → knowledge_type={infer_knowledge_type(p.stem)}')

    if args.dry_run:
        print('\n[Init] --dry-run 模式,不实际导入。退出。')
        return

    rebuild_enterprise_knowledge(app, clear=args.clear)


if __name__ == '__main__':
    main()
