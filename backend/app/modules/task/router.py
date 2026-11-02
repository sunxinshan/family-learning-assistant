from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_session
from app.core.security import RuntimeContext, get_runtime_context
from app.modules.task.repository import TaskRepository
from app.modules.task.schemas import TaskCreate, TaskOut, TaskUpdate
from app.modules.task.service import TaskService

router = APIRouter(tags=["task"])


def get_task_service(session: Session = Depends(get_session)) -> TaskService:
    return TaskService(TaskRepository(session), session)


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    include_snapshot: bool = Query(True),
    context: RuntimeContext = Depends(get_runtime_context),
    service: TaskService = Depends(get_task_service),
) -> list[TaskOut]:
    return service.list(context.user_id, include_snapshot)


@router.post("/tasks", response_model=TaskOut, status_code=201)
def create_task(
    payload: TaskCreate,
    context: RuntimeContext = Depends(get_runtime_context),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    return service.create(context.user_id, context.role, payload)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def get_task(
    task_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    return service.get(task_id, context.user_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
def update_task(
    task_id: str,
    payload: TaskUpdate,
    context: RuntimeContext = Depends(get_runtime_context),
    service: TaskService = Depends(get_task_service),
) -> TaskOut:
    return service.update(task_id, context.user_id, payload)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(
    task_id: str,
    context: RuntimeContext = Depends(get_runtime_context),
    service: TaskService = Depends(get_task_service),
) -> Response:
    service.delete(task_id, context.user_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
