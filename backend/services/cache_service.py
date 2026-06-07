import hashlib
import json
from typing import Optional, Dict, Any
from functools import lru_cache
from cachetools import TTLCache, LRUCache
import time

# Simple in-memory cache (no Redis required)
class MemoryCache:
    def __init__(self, maxsize=100, ttl=3600):
        self.cache = TTLCache(maxsize=maxsize, ttl=ttl)
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        value = self.cache.get(key)
        if value:
            self.hits += 1
        else:
            self.misses += 1
        return value
    
    def set(self, key: str, value: Any):
        self.cache[key] = value
    
    def clear(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def get_stats(self):
        return {"hits": self.hits, "misses": self.misses, "hit_rate": self.hits/(self.hits+self.misses) if (self.hits+self.misses) > 0 else 0}

# Embedding cache for document chunks
embedding_cache = MemoryCache(maxsize=200, ttl=7200)  # 2 hours TTL

def get_cache_key(text: str, model: str = "default") -> str:
    """Generate cache key for text"""
    content = f"{model}:{text}"
    return hashlib.md5(content.encode()).hexdigest()

def cached_embedding(func):
    """Decorator for caching embeddings"""
    def wrapper(text, *args, **kwargs):
        cache_key = get_cache_key(text)
        cached = embedding_cache.get(cache_key)
        if cached:
            return cached
        result = func(text, *args, **kwargs)
        embedding_cache.set(cache_key, result)
        return result
    return wrapper