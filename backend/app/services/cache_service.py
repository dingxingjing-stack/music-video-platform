"""内存缓存服务 (Memory Cache Service)"""
import time

_cache: dict = {}

def cached(ttl: int = 60):
    def decorator(func):
        def wrapper(*args, **kwargs):
            key = str(args) + str(kwargs)
            now = time.time()
            if key in _cache and now - _cache[key]['t'] < ttl:
                return _cache[key]['d']
            result = func(*args, **kwargs)
            _cache[key] = {'d': result, 't': now}
            return result
        return wrapper
    return decorator

def invalidate(prefix: str = ""):
    global _cache
    if prefix:
        _cache = {k: v for k, v in _cache.items() if not k.startswith(prefix)}
    else:
        _cache.clear()