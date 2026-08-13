"""
Flask 扩展层

集中声明扩展实例,避免循环导入,在 create_app() 中 init_app。
- db:SQLAlchemy(数据模型)
- jwt:Flask-JWT-Extended(JWT 认证,Sprint 1)
- logger:统一日志句柄
- redis_client:可选 Redis 客户端(Sprint 8 新增;不可用时自动降级内存缓存)
"""
from .db import db
from .jwt import jwt, init_jwt
from .logger import logger, setup_logging
from .redis_client import (  # noqa: F401  Sprint 8 新增:统一 Redis 访问入口
    redis_client, init_redis, is_available as redis_is_available,
    memory_fallback as redis_memory_fallback,
)

__all__ = [
    'db', 'jwt', 'init_jwt', 'logger', 'setup_logging',
    'redis_client', 'init_redis', 'redis_is_available', 'redis_memory_fallback',
]
