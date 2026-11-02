"""Remove expired terminal Agent runs and unused checkpoint threads."""

import argparse
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select

from app.core.config import get_settings
from app.core.database import Database
from app.infrastructure.checkpoint import CheckpointerManager
from app.modules.agent.models import AgentRun, AgentRunEvent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings)
    cutoff = datetime.now(UTC) - timedelta(days=max(1, args.days))
    with database.session() as session:
        expired_runs = list(
            session.scalars(
                select(AgentRun).where(
                    AgentRun.created_at < cutoff,
                    AgentRun.status.in_(["completed", "failed", "cancelled"]),
                )
            )
        )
        old_run_ids = [run.id for run in expired_runs]
        event_count = 0
        if old_run_ids:
            event_count = (
                session.scalar(
                    select(func.count())
                    .select_from(AgentRunEvent)
                    .where(AgentRunEvent.run_id.in_(old_run_ids))
                )
                or 0
            )
        recent_threads = set(
            session.scalars(
                select(AgentRun.thread_id).where(AgentRun.created_at >= cutoff).distinct()
            )
        )
        checkpoint_threads = sorted({run.thread_id for run in expired_runs} - recent_threads)
        print(
            {
                "runs": len(expired_runs),
                "events": event_count,
                "checkpointThreads": len(checkpoint_threads),
                "apply": args.apply,
            }
        )
        if not args.apply:
            return
        with CheckpointerManager(settings) as saver:
            for thread_id in checkpoint_threads:
                saver.delete_thread(thread_id)
        if old_run_ids:
            session.execute(delete(AgentRunEvent).where(AgentRunEvent.run_id.in_(old_run_ids)))
            session.execute(delete(AgentRun).where(AgentRun.id.in_(old_run_ids)))
    database.dispose()


if __name__ == "__main__":
    main()
