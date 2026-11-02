from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.database import get_session

router = APIRouter(prefix="/health", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: str
    version: str


@router.get("/live", response_model=HealthResponse)
def live(request: Request) -> HealthResponse:
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )


@router.get("/ready", response_model=HealthResponse)
def ready(
    request: Request,
    session: Session = Depends(get_session),
) -> HealthResponse:
    session.execute(text("SELECT 1"))
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        environment=settings.environment,
        version=settings.app_version,
    )
