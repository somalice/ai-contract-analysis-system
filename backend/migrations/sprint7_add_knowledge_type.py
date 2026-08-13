"""
Sprint 7 迁移:为 knowledge_documents 增加 knowledge_type 字段

用途:
- Sprint 7 要求扩展 Knowledge Layer,新增 knowledge_type 区分企业资料 / 招标规范 / 案例等
- 该字段在 Model 层已添加(backend/app/models/knowledge_document.py),此处同步 SQLite 物理表结构

执行策略:
- 增量迁移(ALTER TABLE ADD COLUMN),不删除/重建表,不丢失现有知识文档数据
- 默认值 'general',保证旧记录具备合理类型(不强制 'contract',避免误分类)
- 幂等:若 knowledge_type 列已存在,跳过 ADD COLUMN 并仅打印提示

执行方式:
    cd backend
    python migrations/sprint7_add_knowledge_type.py

约束:
- 仅修改 knowledge_documents 表(加 1 列,additive)
- 不动 Sprint 3/5/6 的任何表(documents / analysis_tasks / contract_fields /
  review_reports / contract_templates / generated_contracts 等)
- 不动 Sprint 4 的 knowledge_chunks 表
- 不修改 Embedding / VectorStore / Retriever 组件(保持五层解耦)
"""
import os
import sqlite3
import sys


# ---------- 数据库路径 ----------
# 与 settings.py / .env 保持一致:backend/instance/app.db
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DB_PATH = os.path.join(_BASE_DIR, 'instance', 'app.db')


def get_connection():
    if not os.path.exists(_DB_PATH):
        print('[ERROR] 数据库文件不存在: {}'.format(_DB_PATH))
        sys.exit(1)
    return sqlite3.connect(_DB_PATH)


def column_exists(cur, table, column):
    cur.execute('PRAGMA table_info({})'.format(table))
    for row in cur.fetchall():
        if row[1] == column:
            return True
    return False


def main():
    print('=' * 60)
    print('Sprint 7 迁移:knowledge_documents.knowledge_type')
    print('=' * 60)
    print('数据库路径: {}'.format(_DB_PATH))

    conn = get_connection()
    cur = conn.cursor()

    # ---------- 前置检查 ----------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_documents'")
    if not cur.fetchone():
        print('[ERROR] 表 knowledge_documents 不存在,请先初始化数据库')
        sys.exit(1)

    if column_exists(cur, 'knowledge_documents', 'knowledge_type'):
        print('[SKIP] knowledge_type 列已存在,无需迁移(幂等)')
        cur.execute('SELECT id, doc_no, title, knowledge_type FROM knowledge_documents')
        rows = cur.fetchall()
        print('当前知识文档数据(共 {} 条):'.format(len(rows)))
        for r in rows:
            print('  id={} doc_no={} title={} knowledge_type={}'.format(*r))
        conn.close()
        return

    # ---------- 执行迁移 ----------
    sql = "ALTER TABLE knowledge_documents ADD COLUMN knowledge_type VARCHAR(32) NOT NULL DEFAULT 'general'"
    print('[SQL] {}'.format(sql))
    cur.execute(sql)

    # 创建索引(加速 BidKnowledgeSearchTool 后过滤查询)
    idx_sql = 'CREATE INDEX IF NOT EXISTS idx_knowledge_documents_knowledge_type ON knowledge_documents(knowledge_type)'
    print('[SQL] {}'.format(idx_sql))
    cur.execute(idx_sql)

    conn.commit()
    print('[OK] knowledge_type 列添加成功(默认 general)+ 索引创建成功')

    # ---------- 验证 ----------
    cur.execute('PRAGMA table_info(knowledge_documents)')
    print('\n迁移后 knowledge_documents 字段:')
    for row in cur.fetchall():
        print('  {} | {} | nullable={} | default={}'.format(
            row[1], row[2], not row[3], row[4]))

    cur.execute('SELECT id, doc_no, title, knowledge_type FROM knowledge_documents')
    rows = cur.fetchall()
    print('\n现有知识文档数据(共 {} 条,均回填 knowledge_type=general):'.format(len(rows)))
    for r in rows:
        print('  id={} doc_no={} title={} knowledge_type={}'.format(*r))

    conn.close()
    print('\n[完成] Sprint 7 knowledge_type 字段迁移结束')


if __name__ == '__main__':
    main()
