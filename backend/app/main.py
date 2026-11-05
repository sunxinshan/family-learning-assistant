import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

import app.core.model_registry  # noqa: F401
from app.api.routes.health import router as health_router
from app.core.config import Settings, get_settings
from app.core.database import Database
from app.core.exceptions import (
    AppError,
    app_error_handler,
    http_error_handler,
    unhandled_error_handler,
    validation_error_handler,
)
from app.core.logging import configure_logging
from app.core.middleware import RequestContextMiddleware
from app.infrastructure.checkpoint import CheckpointerManager
from app.modules.admin.router import router as admin_router
from app.modules.agent.llm import LLMAdapter, create_llm_adapter
from app.modules.agent.router import router as agent_router
from app.modules.agent.runtime import AgentRuntime
from app.modules.content.router import router as content_router
from app.modules.conversation.router import router as conversation_router
from app.modules.learning.router import router as learning_router
from app.modules.material.router import router as material_router
from app.modules.practice.router import router as practice_router
from app.modules.seeder import seed_bootstrap_admins, seed_demo
from app.modules.task.router import router as task_router
from app.modules.user.router import router as user_router
from app.modules.vocabulary.router import router as vocabulary_router


def create_app(settings: Settings | None = None, llm: LLMAdapter | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings.log_level, resolved_settings.log_format)
    logger = logging.getLogger("app")
    database = Database(resolved_settings)
    checkpointer_manager = CheckpointerManager(resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        logger.info(
            "application starting",
            extra={"environment": resolved_settings.environment},
        )
        with checkpointer_manager as checkpointer:
            if resolved_settings.seed_demo_data:
                seed_demo(database)
            seed_bootstrap_admins(database)
            application.state.agent_runtime = AgentRuntime(
                database=database,
                checkpointer=checkpointer,
                settings=resolved_settings,
                llm=llm or create_llm_adapter(resolved_settings),
            )
            try:
                yield
            finally:
                database.dispose()
                logger.info("application stopped")

    application = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.logger = logger

    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    application.add_middleware(RequestContextMiddleware)

    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(RequestValidationError, validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, http_error_handler)
    application.add_exception_handler(Exception, unhandled_error_handler)

    prefix = resolved_settings.api_v1_prefix
    application.include_router(health_router, prefix=prefix)
    application.include_router(user_router, prefix=prefix)
    application.include_router(content_router, prefix=prefix)
    application.include_router(vocabulary_router, prefix=prefix)
    application.include_router(material_router, prefix=prefix)
    application.include_router(task_router, prefix=prefix)
    application.include_router(practice_router, prefix=prefix)
    application.include_router(learning_router, prefix=prefix)
    application.include_router(conversation_router, prefix=prefix)
    application.include_router(agent_router, prefix=prefix)
    application.include_router(admin_router, prefix=prefix)

    @application.get("/", include_in_schema=False)
    def root() -> JSONResponse:
        return JSONResponse(
            {
                "name": resolved_settings.app_name,
                "version": resolved_settings.app_version,
                "docs": "/docs",
            }
        )

    return application


app = create_app()
