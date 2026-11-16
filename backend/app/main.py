"""FastAPI application factory."""

from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.api.auth_api import router as auth_router
from app.api.authorization import authorize
from app.api.health_router import router as health_router
from app.api.history_api.history_router import router as history_router
from app.api.job_api.job_router import router as job_router
from app.api.resume_api.resume_router import router as resume_router
from app.api.resume_api.workspace_router import router as workspace_router
from app.api.review_api.evaluation_router import router as evaluation_router
from app.api.review_api.review_router import router as review_router
from app.api.schedule_api.schedule_router import router as schedule_router
from app.api.workflow_api.workflow_router import router as workflow_router
from app.core.config import Settings
from app.core.errors import BusinessError
from app.core.lifespan import lifespan
from app.core.logging import error_fields, logger


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    application = FastAPI(
        title=config.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.auth_docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.auth_docs_enabled else None,
    )
    application.state.settings = config

    @application.middleware("http")
    async def request_trace(request: Request, call_next):
        request_id = uuid4().hex
        started = perf_counter()
        with logger.contextualize(request_id=request_id):
            try:
                response = await call_next(request)
            except Exception as exc:
                logger.bind(method=request.method, **error_fields(exc)).error(
                    "http.failed"
                )
                raise
            route = request.scope.get("route")
            logger.bind(
                method=request.method,
                route=getattr(route, "path", "unmatched"),
                http_status=response.status_code,
                duration_ms=round((perf_counter() - started) * 1000, 2),
            ).info("http.completed")
            response.headers["X-Request-ID"] = request_id
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            return response

    @application.middleware("http")
    async def fence_lost_runtime(request: Request, call_next):
        runtime = getattr(request.app.state, "runtime", None)
        if (
            runtime is not None
            and getattr(runtime, "lock_lost", False) is True
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and not request.url.path.startswith("/api/auth/")
        ):
            return JSONResponse(
                status_code=503,
                content={"detail": "后端工作流运行锁已失效，已停止执行，请重启后端"},
            )
        return await call_next(request)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],
        allow_credentials=True,
        expose_headers=["X-Request-ID"],
    )
    application.include_router(health_router)
    application.include_router(auth_router)
    for router in (
        job_router,
        resume_router,
        workspace_router,
        review_router,
        evaluation_router,
        history_router,
        workflow_router,
        schedule_router,
    ):
        application.include_router(router, dependencies=[Depends(authorize)])

    @application.exception_handler(BusinessError)
    async def business_error(request, exc):
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}
        )

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        # Credential values must not be echoed in validation error bodies.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": list(error["loc"]),
                        "msg": error["msg"],
                        "type": error["type"],
                    }
                    for error in exc.errors()
                ]
            },
        )

    @application.exception_handler(IntegrityError)
    async def integrity_error(request, exc):
        return JSONResponse(
            status_code=409, content={"detail": "记录冲突，请刷新后重试"}
        )

    return application


app = create_app()
