"""
Sprint 8.5 评估测试知识库初始化脚本

功能:
  将 backend/app/evaluation/test_documents/ 下的测试合同文档批量导入知识库,
  复用现有 KnowledgeDocument + Embedding + FAISS 链路(knowledge_service.upload_knowledge_document),
  不重新实现 RAG。

  导入后, RAG 评估时 FAISS 才有可召回的合同知识文档,
  避免 "context_hit_count == 0" 导致评估 PENDING。

使用:
  cd backend && python ../scripts/init_evaluation_knowledge.py [--dry-run] [--clear]

  --dry-run: 仅扫描文档,不实际导入
  --clear:   导入前先删除已有的 evaluation 测试文档(按 doc_no 前缀 EVALTEST- 或标题前缀 [评估测试])

约束:
  - 复用 knowledge_service.upload_knowledge_document (FileStorage 入口)
  - 不修改 knowledge_service / RAG 链路 / 数据库结构
  - knowledge_type 统一为 'contract' (合同规范),与 QA 数据集对齐
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / 'backend'
TEST_DOCS_DIR = BACKEND_DIR / 'app' / 'evaluation' / 'test_documents'
sys.path.insert(0, str(BACKEND_DIR))

# evaluation 测试文档标识(标题前缀),用于 --clear 时识别
EVAL_DOC_TITLE_PREFIX = '[评估测试] '


def build_app():
    """创建 Flask app。"""
    from app import create_app
    from dotenv import load_dotenv
    load_dotenv(BACKEND_DIR / '.env')
    return create_app()


def get_admin_user(app):
    """获取一个 admin 用户作为导入操作者(测试知识库归属)。"""
    with app.app_context():
        from app.models.user import User
        admin = User.query.filter_by(role='admin').order_by(User.id.asc()).first()
        if admin is None:
            raise RuntimeError('未找到 admin 用户,请先创建管理员账号')
        return {'id': admin.id, 'username': admin.username, 'role': admin.role}


def list_test_documents():
    """扫描 test_documents/ 下的 .txt/.pdf/.docx 文件。"""
    if not TEST_DOCS_DIR.exists():
        return []
    exts = ('.txt', '.pdf', '.docx')
    files = sorted(
        [p for p in TEST_DOCS_DIR.iterdir()
         if p.is_file() and p.suffix.lower() in exts],
        key=lambda p: p.name,
    )
    return files


def clear_existing_eval_docs(app):
    """删除已有的 evaluation 测试文档(按标题前缀识别,复用 knowledge_service 软删)。"""
    from app.extensions.db import db
    from app.models.knowledge_document import KnowledgeDocument
    from app.knowledge.services import knowledge_service

    cleared = 0
    with app.app_context():
        admin = get_admin_user(app)
        docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{EVAL_DOC_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .all()
        )
        print(f'[Clear] 发现 {len(docs)} 份历史评估测试文档,开始删除 ...')
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
    """将单个文件导入知识库(复用 upload_knowledge_document)。

    :param chunk_title: Sprint 8.8 可选,注入 chunk 的纯净标题(不带 [评估测试] 前缀),
        用于评估"前缀质量"对检索的影响;库内标题仍保留前缀(供 --clear 识别)。
    """
    from werkzeug.datastructures import FileStorage
    from app.knowledge.services import knowledge_service

    # 去掉文件名中的序号前缀和扩展名,作为标题
    stem = file_path.stem
    # 文件名格式: 01_contract_xxx → 标题取 xxx 部分
    parts = stem.split('_', 2)
    raw_title = parts[-1] if len(parts) >= 3 else stem
    title = f'{EVAL_DOC_TITLE_PREFIX}{raw_title}'

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
            knowledge_type='contract',
            chunk_title=chunk_title,
        )
    return result


def apply_chunk_config(app, chunk_size=None, chunk_overlap=None, include_title=None,
                       group_clauses=None):
    """Sprint 8.8: 覆盖 contract chunker 配置(导入前调用,仅影响本次导入)。

    通过 app.config 控制 factory._make_contract_chunker 的行为,
    不修改任何生产代码路径,便于 chunk 策略实验。
    """
    if chunk_size is not None:
        app.config['CONTRACT_CHUNK_SIZE'] = int(chunk_size)
    if chunk_overlap is not None:
        app.config['CONTRACT_CHUNK_OVERLAP'] = int(chunk_overlap)
    if include_title is not None:
        app.config['CONTRACT_CHUNK_INCLUDE_TITLE'] = bool(include_title)
    if group_clauses is not None:
        app.config['CONTRACT_CHUNK_GROUP_CLAUSES'] = bool(group_clauses)


def rebuild_knowledge_base(app, chunk_size=None, chunk_overlap=None, clear=True,
                           clean_title=False):
    """重建评估测试知识库(clear 后按当前 chunk 配置重新导入全部测试文档)。

    Sprint 8.8: 供实验运行器复用 —— 每次 chunk 策略实验前重建知识库,
    使 FAISS 中 chunk 与实验配置一致。
    :param clean_title: True 时注入纯净 chunk 标题(不带 [评估测试] 前缀)。
    :return: dict(success, failed, results, eval_docs, eval_chunks)
    """
    apply_chunk_config(app, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if clear:
        print('\n[Init] --clear 模式,先清理历史评估测试文档 ...')
        clear_existing_eval_docs(app)

    print('\n[Init] 获取 admin 用户 ...')
    admin = get_admin_user(app)

    docs = list_test_documents()
    print(f'[Init] 扫描测试文档目录: {TEST_DOCS_DIR}')
    print(f'[Init] 发现 {len(docs)} 份测试文档')
    if not docs:
        print('[Init] ⚠ 未找到测试文档,请先运行: python scripts/generate_test_documents.py')
        return None

    print('\n[Init] 开始批量导入(复用 knowledge_service.upload_knowledge_document) ...')
    success = failed = 0
    results = []
    for idx, fp in enumerate(docs, 1):
        title = f'{EVAL_DOC_TITLE_PREFIX}{fp.stem.split("_", 2)[-1]}'
        chunk_title = None
        if clean_title:
            chunk_title = fp.stem.split('_', 2)[-1]
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
        eval_docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{EVAL_DOC_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .count()
        )
        completed_docs = (
            KnowledgeDocument.query
            .filter(KnowledgeDocument.title.like(f'{EVAL_DOC_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .filter(KnowledgeDocument.embedding_status == 'completed')
            .count()
        )
        eval_chunks = (
            db.session.query(KnowledgeChunk)
            .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
            .filter(KnowledgeDocument.title.like(f'{EVAL_DOC_TITLE_PREFIX}%'))
            .filter(KnowledgeDocument.status == 'active')
            .count()
        )

    print(f'\n[Init] ===== 导入结果 =====')
    print(f'  本次导入: 成功 {success} / 失败 {failed} / 共 {len(docs)}')
    print(f'  知识库总文档数(active): {total_docs}')
    print(f'  评估测试文档数(active): {eval_docs} (embedding completed: {completed_docs})')
    print(f'  评估测试 Chunk 数: {eval_chunks}')
    if eval_docs > 0 and completed_docs > 0:
        print(f'\n[Init] ✅ 知识库已具备可召回的合同知识文档,可执行 RAG 评估')
    else:
        print(f'\n[Init] ⚠ 仍有文档未完成 embedding,请检查 Embedding 模型 / FAISS 索引')

    return {
        'success': success, 'failed': failed, 'total': len(docs),
        'eval_docs': eval_docs, 'completed_docs': completed_docs,
        'eval_chunks': eval_chunks, 'results': results,
    }


def main():
    parser = argparse.ArgumentParser(description='Sprint 8.5 评估测试知识库初始化')
    parser.add_argument('--dry-run', action='store_true', help='仅扫描,不导入')
    parser.add_argument('--clear', action='store_true', help='导入前删除历史评估测试文档')
    parser.add_argument('--chunk-size', type=int, default=None,
                        help='Sprint 8.8: 覆盖 CONTRACT_CHUNK_SIZE(默认取 config)')
    parser.add_argument('--chunk-overlap', type=int, default=None,
                        help='Sprint 8.8: 覆盖 CONTRACT_CHUNK_OVERLAP(默认取 config)')
    args = parser.parse_args()

    print('[Init] 初始化 Flask app ...')
    app = build_app()

    docs = list_test_documents()
    print(f'[Init] 扫描测试文档目录: {TEST_DOCS_DIR}')
    print(f'[Init] 发现 {len(docs)} 份测试文档')
    if not docs:
        print('[Init] ⚠ 未找到测试文档,请先运行: python scripts/generate_test_documents.py')
        return

    for p in docs:
        print(f'  - {p.name}')

    if args.dry_run:
        print('\n[Init] --dry-run 模式,不实际导入。退出。')
        return

    if args.chunk_size or args.chunk_overlap is not None:
        print(f'\n[Init] 覆盖 chunk 配置: size={args.chunk_size} overlap={args.chunk_overlap}')

    rebuild_knowledge_base(
        app,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap,
        clear=args.clear,
    )


if __name__ == '__main__':
    main()
