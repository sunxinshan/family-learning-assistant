from datetime import UTC, datetime
from typing import Any

from app.core.exceptions import AppError
from app.core.models import new_id
from app.modules.conversation.models import Conversation, ConversationMessage
from app.modules.conversation.repository import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self.repository = repository

    def get_or_create(self, user_id: str) -> Conversation:
        conversation = self.repository.get_for_user(user_id)
        if conversation:
            return conversation
        now = datetime.now(UTC)
        return self.repository.add(
            Conversation(
                id=new_id(),
                user_id=user_id,
                title="学习助手",
                status="active",
                created_at=now,
                updated_at=now,
            )
        )

    def append_message(
        self,
        conversation: Conversation,
        *,
        message_type: str,
        content: dict[str, Any],
        tool_call_id: str | None = None,
        run_id: str | None = None,
    ) -> ConversationMessage:
        sequence = max([message.sequence_no for message in conversation.messages], default=0) + 1
        message = self.repository.add_message(
            ConversationMessage(
                id=new_id(),
                conversation_id=conversation.id,
                sequence_no=sequence,
                message_type=message_type,
                content_json=content,
                tool_call_id=tool_call_id,
                run_id=run_id,
            )
        )
        conversation.messages.append(message)
        conversation.updated_at = datetime.now(UTC)
        return message

    def get_owned(self, conversation_id: str, user_id: str) -> Conversation:
        conversation = self.repository.get_for_user(user_id)
        if not conversation or conversation.id != conversation_id:
            raise AppError("conversation_not_found", "会话不存在", status_code=404)
        return conversation

    def clear(self, user_id: str) -> None:
        conversation = self.get_or_create(user_id)
        self.repository.delete_messages(conversation)
        conversation.updated_at = datetime.now(UTC)
