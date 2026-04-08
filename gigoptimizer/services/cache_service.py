from __future__ import annotations

import json
import threading
import time
from typing import Any

from ..config import GigOptimizerConfig


class CacheService:
    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        self._redis = self._connect_redis()
        self._memory_cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get_json(self, key: str) -> Any | None:
        if self._redis is not None:
            try:
                value = self._redis.get(key)
                if value:
                    return json.loads(value)
            except Exception:
                pass
        with self._lock:
            entry = self._memory_cache.get(key)
            if entry is None:
                return None
            expires_at, raw = entry
            if expires_at and expires_at < time.time():
                self._memory_cache.pop(key, None)
                return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, *, ttl_seconds: int) -> None:
        serialized = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                self._redis.setex(key, max(1, ttl_seconds), serialized)
                return
            except Exception:
                pass
        expires_at = time.time() + max(1, ttl_seconds)
        with self._lock:
            self._memory_cache[key] = (expires_at, serialized)

    def delete(self, key: str) -> None:
        if self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        with self._lock:
            self._memory_cache.pop(key, None)

    def set_json_if_absent(self, key: str, value: Any, *, ttl_seconds: int) -> bool:
        serialized = json.dumps(value, default=str)
        if self._redis is not None:
            try:
                return bool(self._redis.set(key, serialized, ex=max(1, ttl_seconds), nx=True))
            except Exception:
                pass
        expires_at = time.time() + max(1, ttl_seconds)
        with self._lock:
            entry = self._memory_cache.get(key)
            if entry is not None:
                current_expires_at, _ = entry
                if not current_expires_at or current_expires_at >= time.time():
                    return False
            self._memory_cache[key] = (expires_at, serialized)
            return True

    def _connect_redis(self):
        if not self.config.redis_url:
            return None
        try:
            import redis
        except Exception:
            return None
        try:
            return redis.Redis.from_url(self.config.redis_url, decode_responses=True)
        except Exception:
            return None
