"""
数据库扩展实例(Sprint 0 Release Check - P6)

职责:
- 声明 SQLAlchemy 实例(避免循环导入)
- 在 create_app() 中通过 db.init_app(app) 初始化

约束(Sprint 0 Release 阶段):
- 仅完成初始化,**不创建任何表**
- **不创建任何业务模型**(User 等 Model 留待 Sprint 1)
- 不调用 db.create_all()
- 目标:Sprint 1 可直接新增 User Model 并使用

SQLALCHEMY_DATABASE_URI 来自 .env(默认 SQLite 本地文件,Sprint 1 起可改为 MySQL)。
"""
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

# 全局唯一 db 实例(在 create_app 中 init_app)
db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """
    SQLite 连接时强制开启:
    1. foreign_keys=ON : 启用外键约束,BidDocument 删除时级联删除 BidRequirement
       (SQLAlchemy cascade 配置需要底层 FK 真正生效才能保证一致)
    2. 其他数据库驱动忽略 dbapi_connection 的 cursor 类型判断
    """
    try:
        cursor = dbapi_connection.cursor()
        # 判断后端是否为 SQLite(connection.driver_connection 适用于 sqlite3)
        backend_name = getattr(dbapi_connection, '__class__', type(dbapi_connection)).__module__
        if backend_name.startswith('sqlite3') or 'sqlite' in str(type(dbapi_connection)).lower():
            cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
    except Exception:
        # 该 hook 为防御性增强,失败绝不影响主流程
        pass
