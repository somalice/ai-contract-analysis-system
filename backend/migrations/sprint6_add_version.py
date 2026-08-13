"""
Sprint 6 补充迁移:为 contract_templates 增加 version 字段

用途:
- Sprint 6 补充要求:模板中心增强,支持模板版本管理(version)
- 该字段在 Model 层已添加(backend/app/models/contract_template.py),此处同步 SQLite 物理表结构

执行策略:
- 增量迁移(ALTER TABLE ADD COLUMN),不删除/重建表,不丢失现有模板数据
- 默认值 v1.0,保证旧记录具备合理版本号
- 幂等:若 version 列已存在,跳过 ADD COLUMN 并仅打印提示

执行方式:
    cd backend
    python migrations/sprint6_add_version.py

约束:
- 仅修改 contract_templates 表
- 不动 Sprint 3/4/5 的任何表(documents / analysis_tasks / contract_fields /
  knowledge_documents / knowledge_chunks / review_reports / generated_contracts 等)
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
    print('Sprint 6 补充迁移:contract_templates.version')
    print('=' * 60)
    print('数据库路径: {}'.format(_DB_PATH))

    conn = get_connection()
    cur = conn.cursor()

    # ---------- 前置检查 ----------
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contract_templates'")
    if not cur.fetchone():
        print('[ERROR] 表 contract_templates 不存在,请先初始化数据库')
        sys.exit(1)

    if column_exists(cur, 'contract_templates', 'version'):
        print('[SKIP] version 列已存在,无需迁移(幂等)')
        cur.execute('SELECT id, template_no, name, version FROM contract_templates')
        rows = cur.fetchall()
        print('当前模板数据(共 {} 条):'.format(len(rows)))
        for r in rows:
            print('  id={} template_no={} name={} version={}'.format(*r))
        conn.close()
        return

    # ---------- 执行迁移 ----------
    sql = "ALTER TABLE contract_templates ADD COLUMN version VARCHAR(32) NOT NULL DEFAULT 'v1.0'"
    print('[SQL] {}'.format(sql))
    cur.execute(sql)
    conn.commit()
    print('[OK] version 列添加成功(默认 v1.0)')

    # ---------- 验证 ----------
    cur.execute('PRAGMA table_info(contract_templates)')
    print('\n迁移后 contract_templates 字段:')
    for row in cur.fetchall():
        print('  {} | {} | nullable={} | default={}'.format(
            row[1], row[2], not row[3], row[4]))

    cur.execute('SELECT id, template_no, name, version FROM contract_templates')
    rows = cur.fetchall()
    print('\n现有模板数据(共 {} 条,均回填 version=v1.0):'.format(len(rows)))
    for r in rows:
        print('  id={} template_no={} name={} version={}'.format(*r))

    conn.close()
    print('\n[完成] Sprint 6 version 字段迁移结束')


if __name__ == '__main__':
    main()
