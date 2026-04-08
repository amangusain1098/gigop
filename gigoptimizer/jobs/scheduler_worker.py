from __future__ import annotations

import os
import time
from datetime import datetime

from ..config import GigOptimizerConfig
from ..jobs.service import JobService
from ..persistence import BlueprintRepository, DatabaseManager
from .bus import JobEventBus


def main() -> None:
    config = GigOptimizerConfig.from_env()
    repository = BlueprintRepository(DatabaseManager(config))
    event_bus = JobEventBus(config)
    job_service = JobService(config, repository, event_bus)

    if os.name == "nt":
        print("Scheduler worker is running in compatibility mode on Windows. It will enqueue local background jobs.")
    else:
        print("Scheduler worker is running. Configure REDIS_URL for distributed queue mode.")

    last_weekly_day: str | None = None
    while True:
        now = datetime.now()
        if now.weekday() == 6 and now.hour == 8 and now.minute == 0:
            today_key = now.strftime("%Y-%m-%d")
            if today_key != last_weekly_day:
                job_service.enqueue_weekly_report(use_live_connectors=False)
                last_weekly_day = today_key
        time.sleep(30)


if __name__ == "__main__":
    main()
