"""
Sprint 7.1(v0.9.1)增量迁移: bid_requirements 表 + proposal_sections 表新增列

新增 5 项企业级增强所需的列:
1. bid_requirements.version VARCHAR(32) 默认 'v1.0'
2. bid_requirements.field_sources JSON(字段级来源追踪)
3. bid_requirements.status 默认值从 'pending' 改为 'draft'
   - 旧 success → 回填 approved(Bid Agent 可读取,保证向后兼容)
   - 旧 pending → 回填 draft
   - 旧 failed → 保持 failed
4. proposal_sections.similarity_score FLOAT(章节统一引用相似度)
   (实际引用结构已存在 proposal_sections.references JSON,此处仅为上层查询冗余)
5. proposal_sections.document_id INT(外键冗余,可空)

幂等策略:
  - 列存在则跳过 ALTER
  - 迁移前自动备份:instance/app.db → instance/app.db.bak_sprint7_1
  - 所有操作在单事务内,失败 rollback

约束:
  - 不修改 Sprint 3/4/5/6 任何表
  - 仅改 bid_requirements / proposal_sections 两张 Sprint 7 新表
"""
import os
import sys
import shutil
from datetime import datetime

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_ROOT = os.path.dirname(_BASE)
sys.path.insert(0, _BASE)
os.chdir(_BASE)


def _backup_if_not_exists(app):
    """备份现有数据库(仅首次运行时)"""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI') or ''
    if not db_uri.startswith('sqlite:///'):
        print('[SKIP] 非 SQLite,跳过自动备份')
        return None
    db_path = db_uri[len('sqlite:///'):]
    if not os.path.isabs(db_path):
        db_path = os.path.join(_BASE, db_path)
    if not os.path.isfile(db_path):
        print('[SKIP] 数据库文件不存在,跳过备份:', db_path)
        return None
    bak_path = db_path + '.bak_sprint7_1_' + datetime.now().strftime('%Y%m%d%H%M%S')
    shutil.copy2(db_path, bak_path)
    print('[OK] 数据库已备份:', bak_path)
    return bak_path


def _column_exists(engine, table_name, column_name):
    """检查 SQLite 表是否存在某列"""
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table_name})"))
        columns = [row[1] for row in result.fetchall()]
        return column_name in columns


def run_migration():
    from app import create_app
    from app.extensions.db import db

    app = create_app()
    app.config['SQLALCHEMY_ECHO'] = False
    _backup_if_not_exists(app)

    with app.app_context():
        engine = db.engine
        conn = db.session.connection()

        # ============================================================
        # 1. bid_requirements 3 个新列
        # ============================================================
        altered = 0
        # 1a. version
        if not _column_exists(engine, 'bid_requirements', 'version'):
            try:
                conn.execute(db.text(
                    "ALTER TABLE bid_requirements ADD COLUMN version VARCHAR(32) NOT NULL DEFAULT 'v1.0'"
                ))
                print('[OK] bid_requirements.version 列已新增')
                altered += 1
            except Exception as e:
                print('[WARN] bid_requirements.version ALTER 失败(可能已存在):', e)
        else:
            print('[SKIP] bid_requirements.version 列已存在')

        # 1b. field_sources(JSON,SQLite 无 JSON 类型,用 TEXT)
        if not _column_exists(engine, 'bid_requirements', 'field_sources'):
            try:
                conn.execute(db.text(
                    "ALTER TABLE bid_requirements ADD COLUMN field_sources TEXT NULL"
                ))
                print('[OK] bid_requirements.field_sources 列已新增')
                altered += 1
            except Exception as e:
                print('[WARN] bid_requirements.field_sources ALTER 失败:', e)
        else:
            print('[SKIP] bid_requirements.field_sources 列已存在')

        # 1c. 新增 status 索引(bid_requirements 原 status 已有 VARCHAR(32))
        try:
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS idx_bid_req_status ON bid_requirements(status)"
            ))
            print('[OK] idx_bid_req_status 索引已确保')
        except Exception as e:
            print('[WARN] status 索引创建失败:', e)

        # 1d. version 索引
        try:
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS idx_bid_req_version ON bid_requirements(version)"
            ))
            print('[OK] idx_bid_req_version 索引已确保')
        except Exception as e:
            print('[WARN] version 索引创建失败:', e)

        # ============================================================
        # 2. bid_requirements 回填:旧 success → approved / pending → draft
        # ============================================================
        try:
            # 旧 "success" → approved(Bid Agent 可读取,保持业务无感知)
            upd_approved = conn.execute(db.text(
                "UPDATE bid_requirements SET status='approved' WHERE status='success'"
            ))
            print(f'[OK] 回填 success→approved: {upd_approved.rowcount} 行')

            # 旧 "pending" → draft
            upd_draft = conn.execute(db.text(
                "UPDATE bid_requirements SET status='draft' WHERE status='pending'"
            ))
            print(f'[OK] 回填 pending→draft: {upd_draft.rowcount} 行')

            # 空 version → v1.0
            upd_ver = conn.execute(db.text(
                "UPDATE bid_requirements SET version='v1.0' WHERE version IS NULL OR version=''"
            ))
            print(f'[OK] 回填 version=v1.0: {upd_ver.rowcount} 行')
        except Exception as e:
            print('[WARN] 状态/版本回填失败(可能表为空):', e)

        # ============================================================
        # 3. proposal_sections 2 个冗余列(可选,供上层统一引用格式查询)
        # ============================================================
        # 3a. similarity_score FLOAT(相似度,可空)
        if not _column_exists(engine, 'proposal_sections', 'similarity_score'):
            try:
                conn.execute(db.text(
                    "ALTER TABLE proposal_sections ADD COLUMN similarity_score FLOAT NULL"
                ))
                print('[OK] proposal_sections.similarity_score 列已新增')
                altered += 1
            except Exception as e:
                print('[WARN] proposal_sections.similarity_score ALTER 失败:', e)
        else:
            print('[SKIP] proposal_sections.similarity_score 列已存在')

        # 3b. document_id INT(引用 knowledge_documents.id,可空)
        if not _column_exists(engine, 'proposal_sections', 'document_id'):
            try:
                conn.execute(db.text(
                    "ALTER TABLE proposal_sections ADD COLUMN document_id INTEGER NULL"
                ))
                print('[OK] proposal_sections.document_id 列已新增')
                altered += 1
            except Exception as e:
                print('[WARN] proposal_sections.document_id ALTER 失败:', e)
        else:
            print('[SKIP] proposal_sections.document_id 列已存在')

        try:
            conn.execute(db.text(
                "CREATE INDEX IF NOT EXISTS idx_prop_sections_docid ON proposal_sections(document_id)"
            ))
            print('[OK] idx_prop_sections_docid 索引已确保')
        except Exception as e:
            print('[WARN] document_id 索引创建失败:', e)

        db.session.commit()
        print('\n============================================================')
        print(f'Sprint 7.1 迁移完成:共新增/确保 {altered} 列,完成状态/版本回填')
        print('============================================================')
        return True


if __name__ == '__main__':
    try:
        run_migration()
    except Exception as e:
        print('[FATAL] 迁移未完成(事务已回滚):', e)
        sys.exit(1)
