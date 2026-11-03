from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.database import Database
from app.modules.agent.models import AgentRun, AgentRunEvent
from app.modules.agent.repository import AgentRepository


def test_active_run_lookup_handles_large_pending_action(settings: Settings) -> None:
    """确认待确认动作很大时也能取到活跃运行。

    MySQL 在 262144 字节的 sort_buffer 下排序含大 JSON 的整行会直接报
    1038 Out of sort memory，因此查询必须只按主键排序再回表。
    """
    database = Database(settings)
    big_pending = {"draft": "词" * 160_000}

    with database.session() as session:
        session.add(
            AgentRun(
                id="run-big",
                conversation_id="conv-1",
                user_id="user-1",
                status="waiting_confirmation",
                thread_id="thread-1",
                pending_action_json=big_pending,
                draft_version=1,
            )
        )
        session.add(
            AgentRunEvent(
                id="event-2",
                run_id="run-big",
                conversation_id="conv-1",
                sequence=2,
                event_type="confirmation_required",
                payload_json=big_pending,
                created_at=datetime.now(UTC) + timedelta(seconds=1),
            )
        )
        session.add(
            AgentRunEvent(
                id="event-1",
                run_id="run-big",
                conversation_id="conv-1",
                sequence=1,
                event_type="progress",
                payload_json={"stage": "drafting"},
                created_at=datetime.now(UTC),
            )
        )

    with database.session() as session:
        repository = AgentRepository(session)
        run = repository.get_active_for_user("user-1")
        assert run is not None
        assert run.id == "run-big"
        assert run.pending_action_json == big_pending

        events = repository.list_events("run-big")
        assert [event.id for event in events] == ["event-1", "event-2"]
        assert events[1].payload_json == big_pending
        assert [event.id for event in repository.list_events("run-big", after_sequence=1)] == [
            "event-2"
        ]

    database.dispose()
