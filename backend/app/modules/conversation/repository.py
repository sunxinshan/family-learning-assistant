from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.modules.conversation.models import Conversation, ConversationMessage


class ConversationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_for_user(self, user_id: str) -> Conversation | None:
        return self.session.scalar(
            select(Conversation)
            .options(selectinload(Conversation.messages))
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.created_at)
        )

    def add(self, conversation: Conversation) -> Conversation:
        self.session.add(conversation)
        self.session.flush()
        return conversation

    def add_message(self, message: ConversationMessage) -> ConversationMessage:
        self.session.add(message)
        self.session.flush()
        return message

    def delete_messages(self, conversation: Conversation) -> None:
        for message in list(conversation.messages):
            self.session.delete(message)
        self.session.flush()
