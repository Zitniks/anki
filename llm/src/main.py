import uuid
import uvicorn

from collections.abc import Awaitable, Callable, Generator
from typing import Any
from contextlib import asynccontextmanager

from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from settings import settings
from logger import startup_logger, set_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to generate and track request IDs for log correlation"""

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Any]]) -> Response:
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        set_request_id(req_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response


@asynccontextmanager
async def lifespan(app: FastAPI) -> Generator[None, None, None]:
    """Lifespan event handler for startup and shutdown"""
    from chat.graph import build_tutor_graph
    from grpc_svc.server import serve_grpc

    app.state.graph = build_tutor_graph()
    grpc_server = None

    if settings.GRPC_ENABLED:
        grpc_server = await serve_grpc(app.state.graph, settings.GRPC_HOST, settings.GRPC_PORT)
        startup_logger.info(f"grpc.ready port={settings.GRPC_PORT}")

    startup_logger.info("app.start")
    try:
        yield
    finally:
        if grpc_server is not None:
            await grpc_server.stop(grace=5)
            startup_logger.info("grpc.stop")


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)

# Add CORS middleware for security
# Note: Permissive since authentication is handled by Caddy reverse proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins since auth is at proxy level
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)


# Health check endpoint
@app.get("/health")
async def health_check() -> dict[str, str | int]:
    """Health check endpoint"""
    return {"status": "healthy"}


# Setup static files
if settings.STATIC_PATH.exists():
    app.mount("/static", StaticFiles(directory=str(settings.STATIC_PATH)), name="static")

if __name__ == "__main__":
    import uvicorn

    startup_logger.info(f"server.start host={settings.APP_HOST} port={settings.APP_PORT}")
    uvicorn.run("main:app",
                host=settings.APP_HOST,
                port=settings.APP_PORT,
                reload=True,
                proxy_headers=True,
                forwarded_allow_ips="*")
