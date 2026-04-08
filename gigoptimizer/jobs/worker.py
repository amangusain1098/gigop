from __future__ import annotations

import os


def main() -> None:
    if os.name == "nt":
        print("GigOptimizer worker fallback: RQ worker mode is intended for Linux hosting. Use the FastAPI app's local background queue on Windows.")
        return

    from redis import Redis
    from rq import Queue, Worker

    from ..config import GigOptimizerConfig

    config = GigOptimizerConfig.from_env()
    if not config.redis_url:
        print("REDIS_URL is not configured. Configure Redis before starting a dedicated worker.")
        return

    connection = Redis.from_url(config.redis_url)
    queue = Queue(config.rq_queue_name, connection=connection)
    worker = Worker([queue], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
