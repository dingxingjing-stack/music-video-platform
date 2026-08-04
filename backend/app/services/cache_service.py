"""内存缓存服务 (Memory Cache Service)

修复：
1. 使用 functools.wraps 保留原函数签名，避免 *args/**kwargs 被冒泡到 FastAPI
2. 同时支持 sync 和 async 函数
"""
import time
import inspect
from functools import wraps

_cache: dict = {}

def cached(ttl: int = 60):
    def decorator(func):
        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = str(args) + str(kwargs)
                now = time.time()
                if key in _cache and now - _cache[key]['t'] < ttl:
                    return _cache[key]['d']
                result = await func(*args, **kwargs)
                _cache[key] = {'d': result, 't': now}
                return result
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                key = str(args) + str(kwargs)
                now = time.time()
                if key in _cache and now - _cache[key]['t'] < ttl:
                    return _cache[key]['d']
                result = func(*args, **kwargs)
                _cache[key] = {'d': result, 't': now}
                return result
            return sync_wrapper
    return decorator

def invalidate(prefix: str = ""):
    global _cache
    if prefix:
        _cache = {k: v for k, v in _cache.items() if not k.startswith(prefix)}
    else:
        _cache.clear()
