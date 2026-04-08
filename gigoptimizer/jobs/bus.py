from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Any

from ..config import GigOptimizerConfig


class JobEventBus:
    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config
        self._subscribers: set[Callable[[dict[str, Any]], None]] = set()
        self._stop = threading.Event()
        self._listener_thread: threading.Thread | None = None
        self._redis = self._connect_redis()

    def subscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.add(callback)

    def unsubscribe(self, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.discard(callback)

    def start(self) -> None:
        if self._redis is None:
            return
        if self._listener_thread and self._listener_thread.is_alive():
            return
        self._stop.clear()
        self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._listener_thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._listener_thread and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=2)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "payload": payload,
        }
        if self._redis is None:
            self._dispatch(event)
            return
        try:
            self._redis.publish(
                self.config.job_progress_channel,
                json.dumps(event, default=str),
            )
        except Exception:
            # Fall back to local fanout so the app still stays interactive even if Redis drops.
            self._dispatch(event)

    def healthcheck(self) -> tuple[bool, str]:
        if self._redis is None:
            return True, "local in-process event bus active"
        try:
            self._redis.ping()
        except Exception as exc:
            return False, str(exc)
        return True, f"redis pub-sub active on {self.config.job_progress_channel}"

    def _dispatch(self, event: dict[str, Any]) -> None:
        stale: list[Callable[[dict[str, Any]], None]] = []
        for callback in list(self._subscribers):
            try:
                callback(event)
            except Exception:
                stale.append(callback)
        for callback in stale:
            self._subscribers.discard(callback)

    def _listen_loop(self) -> None:
        if self._redis is None:
            return
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        try:
            pubsub.subscribe(self.config.job_progress_channel)
            while not self._stop.is_set():
                message = pubsub.get_message(timeout=1.0)
                if not message:
                    time.sleep(0.05)
                    continue
                raw = message.get("data")
                if not raw:
                    continue
                try:
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", errors="ignore")
                    payload = json.loads(raw)
                except Exception:
                    continue
                if isinstance(payload, dict):
                    self._dispatch(payload)
        finally:
            pubsub.close()

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
