"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.health_router import router as health_router
from app.api.job_api.job_router import router as job_router
from app.api.resume_api.resume_router import router as resume_router
from app.api.review_api.review_router import router as review_router
from app.api.schedule_api.schedule_router import router as schedule_router
from app.api.workflow_api.workflow_router import router as workflow_router
from app.core.config import Settings
from app.core.errors import BusinessError
from app.core.lifespan import lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    application = FastAPI(title=config.app_name, version="0.1.0", lifespan=lifespan)
    application.state.settings = config
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    application.include_router(health_router)
    for router in (
        job_router,
        resume_router,
        review_router,
        workflow_router,
        schedule_router,
    ):
        application.include_router(router)

    @application.exception_handler(BusinessError)
    async def business_error(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    @application.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(
            status_code=409, content={"detail": "记录冲突，请刷新后重试"}
        )

    return application


app = create_app()
