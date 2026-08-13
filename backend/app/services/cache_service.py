"""
缓存服务(Sprint 8 - v1.0.0 Enterprise AI Enhancement)

职责:
- 统一封装 Redis / 内存降级缓存的读写与失效
- 提供 namespace + SHA1 构造 Key(原始字符串作为 Key 可能过长/冲突)
- 支持:RAG 查询结果缓存、Agent 审核结果缓存、按前缀批量失效

设计原则(遵循 user_rules §14 错误处理规范):
- 所有 public 方法:异常 → logger.warning + 空结果(None/[]/False),绝不抛出
- JSON 序列化/反序列化失败:回退无缓存,不影响业务
- 任何错误不得影响上层请求的主流程

约束(遵循 project_memory §Redis 集成):
- 不引入 Flask-Caching;直接操作 redis_client / 内存降级
- Key 构造:namespace:sha1(parts)
- Redis 不可用时:全部请求走内存降级(_MemoryFallback,已在 init_redis 初始化)
"""
import hashlib
import json
import sys

from app.extensions import logger


def _redis_mod():
    """运行时获取 redis_client 模块(规避 import-time 循环引用导致 _redis_mod 为 None)"""
    mod = sys.modules.get('app.extensions.redis_client')
    if mod is None:
        # fallback:直接 import(确保加载)
        import app.extensions.redis_client as m
        return m
    return mod


def _rc():
    """运行时获取当前 redis_client(动态访问模块属性,因为 init_redis 后才赋值)"""
    return _redis_mod().redis_client


def _mb():
    """运行时获取内存降级实例"""
    return _redis_mod().memory_fallback()


def _available():
    return _redis_mod().is_available()


def is_redis_available():
    """对外暴露:后端 Redis 是否真实可用(非内存降级)。Redis 失败 → 自动降级内存。"""
    try:
        return _available()
    except Exception as e:
        logger.warning('[Cache] is_available 异常(视为不可用):%s', e)
        return False


def get_cache_status():
    """对外暴露:{'redis_available':bool, 'mode':'redis'|'memory'|'unknown'}"""
    try:
        available = _available()
    except Exception:
        available = False
    return {
        'redis_available': available,
        'mode': 'redis' if available else 'memory',
    }


def build_key(namespace, *parts):
    """
    构造缓存 Key:namespace:sha1(parts 序列化)

    规则:
    - parts 为任意可 JSON 序列化的对象(list/tuple/str/int/dict)
    - 相同 parts + 相同 namespace → 相同 key
    - namespace 使用短前缀:避免 key 过长,如 'rag','review','template'

    :return: str key,不超过 Redis 推荐的 200 字符
    """
    try:
        raw = json.dumps(parts, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        raw = str(parts)
    digest = hashlib.sha1(raw.encode('utf-8')).hexdigest()
    key = f"{namespace}:{digest}"
    # 防御性截断(正常情况下不触发)
    if len(key) > 200:
        key = key[:200]
    return key


def _serialize(value):
    """对象 → JSON 字符串(失败返回 None)"""
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError) as e:
        logger.warning('[Cache] 序列化失败(type=%s): %s', type(value).__name__, e)
        return None


def _deserialize(payload):
    """JSON 字符串 → 对象(失败返回 None)"""
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except (TypeError, ValueError, json.JSONDecodeError) as e:
        logger.warning('[Cache] 反序列化失败: %s', e)
        return None


def get(key):
    """
    读取缓存。

    优先 Redis(若可用),否则读内存降级。
    :return: 原对象 or None(不存在/失败)
    """
    # 1. Redis 可用
    r = _rc()
    if r is not None:
        try:
            raw = r.get(key)
            if raw is None:
                pass  # 不存在,继续读内存(避免两者 miss 频繁切换)
            else:
                value = _deserialize(raw)
                if value is not None:
                    return value
        except Exception as e:
            logger.warning('[Cache] Redis get 失败,降级内存: key=%s err=%s', key[:20], e)
    # 2. 内存降级
    try:
        mem = _mb()
        raw = mem.get(key)
        if raw is None:
            return None
        # 内存里可能已存对象(首次 set from redis 时),也可能存 JSON
        if isinstance(raw, str):
            return _deserialize(raw)
        return raw
    except Exception as e:
        logger.warning('[Cache] Memory fallback get 失败: key=%s err=%s', key[:20], e)
        return None


def set(key, value, ttl_seconds=None):
    """
    写入缓存(双写:Redis + 内存,保证下次读取一致)。

    :param key: build_key() 构造的 key
    :param value: 可 JSON 序列化的任意对象
    :param ttl_seconds: TTL 秒(None=永久,但 CacheService 建议始终传 TTL)
    """
    payload = _serialize(value)
    if payload is None:
        return False  # 序列化失败:不写

    # 1. Redis
    r = _rc()
    if r is not None:
        try:
            if ttl_seconds is not None and int(ttl_seconds) > 0:
                r.set(key, payload, ex=int(ttl_seconds))
            else:
                r.set(key, payload)
        except Exception as e:
            logger.warning('[Cache] Redis set 失败(不阻断内存写): key=%s err=%s', key[:20], e)
    # 2. 内存降级(始终写,Redis 短暂故障也有缓存)
    try:
        mem = _mb()
        mem.set(key, value, ex=ttl_seconds)
    except Exception as e:
        logger.warning('[Cache] Memory fallback set 失败: key=%s err=%s', key[:20], e)
        return False
    return True


def delete(key):
    """删除单 key。返回 True=至少一处命中"""
    ok = False
    r = _rc()
    if r is not None:
        try:
            ok = (r.delete(key) is not None) or ok
        except Exception as e:
            logger.warning('[Cache] Redis delete 失败: key=%s err=%s', key[:20], e)
    try:
        mem = _mb()
        deleted = mem.delete(key)
        ok = (deleted > 0) or ok
    except Exception as e:
        logger.warning('[Cache] Memory delete 失败: key=%s err=%s', key[:20], e)
    return ok


def invalidate_prefix(prefix):
    """
    批量失效以 prefix 开头的所有 key(例如 'rag:')。

    实现:
    - Redis:使用 SCAN MATCH(大 keyspace 也不会阻塞)
    - 内存:MemoryFallback.delete_prefix 直接遍历
    """
    count = 0
    r = _rc()
    if r is not None:
        try:
            cursor = 0
            while True:
                cursor, keys = r.scan(cursor=cursor, match=prefix + '*', count=200)
                if keys:
                    r.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning('[Cache] Redis invalidate_prefix 失败: prefix=%s err=%s', prefix, e)
    try:
        mem = _mb()
        count += mem.delete_prefix(prefix)
    except Exception as e:
        logger.warning('[Cache] Memory invalidate_prefix 失败: prefix=%s err=%s', prefix, e)
    if count > 0:
        logger.info('[Cache] 按前缀失效: prefix=%s count=%s', prefix, count)
    return count


def is_redis_available():
    """对外暴露 Redis 实际可用状态(供 EvaluationService 统计用)"""
    return _available()
