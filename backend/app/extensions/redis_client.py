"""
Redis 客户端扩展(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

职责:
- 声明可选 Redis 客户端实例(不可用时为 None,永不阻断启动)
- 在 create_app() 中通过 init_redis(app) 初始化
- 提供 _MemoryFallback 内存 dict 兜底:Redis 不可用时自动降级
- 提供统一 is_available() 供上层判断

设计原则(遵循 §14 Enterprise AI 规则):
- 所有网络操作 timeout=1s,防止慢 Redis 拖慢请求
- 所有异常 try/except + logger.warning,绝不抛出到业务层
- 不依赖 redis 包:import 失败时走降级

约束:
- 本层无业务逻辑,仅做连接/降级
- 业务层必须通过 services/cache_service.py 访问,禁止项目其他处直接 import redis_client
"""
import os
from threading import Lock

from app.extensions.logger import logger

# 全局 Redis 客户端实例;None 表示不可用(降级或未配置)
redis_client = None

# 内存降级字典(简单 LRU:按插入顺序保留最近 N 条)
_MEMORY_FALLBACK = None

# 读写锁,保证多线程场景下内存缓存一致性
_lock = Lock()

# 内存降级最大条目数(默认 2000;防止内存膨胀)
_MEMORY_MAX_ITEMS = 2000


class _MemoryFallback:
    """内存缓存降级实现:TTL 感知 + 简单 LRU(按插入顺序丢弃最旧)

    仅在 Redis 不可用时启用;接口与 redis.get/set/delete 保持相似签名,
    便于 CacheService 统一调用。
    """

    def __init__(self, max_items=_MEMORY_MAX_ITEMS):
        self._store = {}   # key -> (value, expire_at_ts or None)
        self._max = max_items

    def _now(self):
        import time
        return time.time()

    def get(self, key):
        with _lock:
            item = self._store.get(key)
            if item is None:
                return None
            value, expire_at = item
            if expire_at is not None and self._now() > expire_at:
                # 惰性过期
                self._store.pop(key, None)
                return None
            return value

    def set(self, key, value, ex=None):
        """
        :param ex: TTL 秒(int/float 或 None=永不过期)
        """
        import time
        expire_at = None if ex is None else (self._now() + float(ex))
        with _lock:
            self._store[key] = (value, expire_at)
            # 简单 LRU:超上限时按插入顺序丢弃最早的 10%
            if len(self._store) > self._max:
                drop_n = max(1, int(self._max * 0.1))
                keys_to_drop = list(self._store.keys())[:drop_n]
                for k in keys_to_drop:
                    self._store.pop(k, None)
        return True

    def delete(self, key):
        with _lock:
            existed = key in self._store
            self._store.pop(key, None)
        return 1 if existed else 0

    def delete_prefix(self, prefix):
        """删除所有以 prefix 开头的 key(用于命名空间批量失效)"""
        with _lock:
            matches = [k for k in self._store.keys() if k.startswith(prefix)]
            for k in matches:
                self._store.pop(k, None)
        return len(matches)

    def flushdb(self):
        with _lock:
            self._store.clear()


def is_available():
    """Redis 是否可用(不包含内存降级)"""
    return redis_client is not None


def memory_fallback():
    """获取内存降级实例(不存在则初始化)"""
    global _MEMORY_FALLBACK
    if _MEMORY_FALLBACK is None:
        _MEMORY_FALLBACK = _MemoryFallback()
    return _MEMORY_FALLBACK


def init_redis(app):
    """
    初始化 Redis 客户端。

    流程:
    1. 读取 config['REDIS_URL'];空=禁用,仅用内存降级
    2. 尝试 import redis(import 失败=降级)
    3. 构造 redis.Redis(socket_timeout=1, socket_connect_timeout=1)
    4. ping() 探活;失败 → 降级,不阻断启动

    :param app: Flask app 实例(用于读取 config)
    """
    global redis_client

    redis_url = (app.config.get('REDIS_URL') or '').strip()
    cache_enabled = app.config.get('CACHE_ENABLED', True)
    if not cache_enabled:
        logger.info('[Redis] CACHE_ENABLED=False,缓存显式禁用,使用内存降级')
        memory_fallback()
        return
    if not redis_url:
        logger.info('[Redis] REDIS_URL 未配置,使用内存降级缓存')
        memory_fallback()
        return

    try:
        import redis as _redis  # 局部 import:未安装也不阻断
    except ImportError:
        logger.warning('[Redis] redis 包未安装(请 pip install redis==5.0.1),使用内存降级')
        memory_fallback()
        return

    try:
        client = _redis.Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_timeout=1,
            socket_connect_timeout=1,
            retry_on_timeout=False,
            max_connections=20,
        )
        # 探活
        client.ping()
        redis_client = client
        logger.info('[Redis] 连接成功 | url=%s***', redis_url[:8])
    except Exception as e:
        logger.warning('[Redis] 连接失败,自动降级内存缓存: %s', e)
        redis_client = None
        memory_fallback()
