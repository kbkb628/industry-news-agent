from __future__ import annotations

import json

from app.core.config import get_settings
from app.demo.bootstrap import bootstrap_demo_run
from app.storage.database import get_session_factory


def main() -> None:
    settings = get_settings()
    result = bootstrap_demo_run(
        session_factory=get_session_factory(settings),
        settings=settings,
    )
    print(
        json.dumps(
            {
                "topic_id": result.topic_id,
                "run_id": result.run_id,
                "candidate_count": result.candidate_count,
                "push_count": result.push_count,
                "event_count": result.event_count,
                "candidate_task_count": result.candidate_task_count,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
