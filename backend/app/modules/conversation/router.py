from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.conversation.models import Conversation
from app.modules.conversation.repository import ConversationRepository
from app.modules.conversation.schemas import ConversationOut, MessageAppend
from app.modules.conversation.service import ConversationService

router = APIRouter(tags=["conversation"])


def get_conversation_service(session: Session = Depends(get_session)) -> ConversationService:
    return ConversationService(ConversationRepository(session))


def conversation_to_out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        user_id=conversation.user_id,
        title=conversation.title,
        status=conversation.status,
        messages=[message.content_json for message in conversation.messages],
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/conversations/current", response_model=ConversationOut)
def current_conversation(
    context: RuntimeContext = Depends(get_runtime_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationOut:
    return conversation_to_out(service.get_or_create(context.user_id))


@router.post("/conversations/current/messages", response_model=ConversationOut, status_code=201)
def append_message(
    payload: MessageAppend,
    context: RuntimeContext = Depends(get_runtime_context),
    service: ConversationService = Depends(get_conversation_service),
) -> ConversationOut:
    conversation = service.get_or_create(context.user_id)
    service.append_message(
        conversation,
        message_type=str(payload.message.get("role", "assistant")),
        content=payload.message,
    )
    return conversation_to_out(conversation)


@router.delete("/conversations/current/messages", status_code=status.HTTP_204_NO_CONTENT)
def clear_conversation(
    context: RuntimeContext = Depends(get_runtime_context),
    service: ConversationService = Depends(get_conversation_service),
) -> Response:
    service.clear(context.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
