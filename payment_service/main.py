import atexit, time, yaml
import logging
import logging.config
import logging.handlers
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from payment_service.engine import engine
from payment_service.router import router

from typing import Awaitable, Callable
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("payment_service has started")
    yield
    logger.info("payment_service has stopped")
    await engine.dispose()

def setup_logging():
    with open("payment_service/logger_config.yml") as f:
        config = yaml.safe_load(f)
    logging.config.dictConfig(config)
    queue_handler: logging.handlers.QueueHandler | None = logging.getHandlerByName("queue_handler")
    if queue_handler is not None:
        queue_handler.listener.start()
        atexit.register(queue_handler.listener.stop)

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency",
    ["endpoint"]
)

logger = logging.getLogger("payment_service")

api = FastAPI(lifespan=lifespan)
api.include_router(router)

origins = [
    "http://localhost",
    "http://localhost:3001",
]

api.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.middleware("http")
async def metrics_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    REQUEST_COUNT.labels(
        request.method,
        request.url.path,
        response.status_code
    ).inc()

    REQUEST_LATENCY.labels(request.url.path).observe(duration)
    return response

@api.get('/')
async def index():
    return {"message": "payment service index"}

@api.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
