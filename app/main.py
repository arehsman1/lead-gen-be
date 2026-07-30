import logging
import time
import uuid

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import activity, api_keys, audits, businesses, dashboard, emails, geography, pdfs, search, settings
from app.core.config import get_settings

class RequestIdDefaultFilter(logging.Filter):
    """Ensures every log record has a request_id, even ones logged by
    third-party libraries (httpx, uvicorn) that never set `extra`."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
)
for handler in logging.getLogger().handlers:
    handler.addFilter(RequestIdDefaultFilter())
logger = logging.getLogger("caleb.api")

settings_obj = get_settings()
limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings_obj.rate_limit_per_minute}/minute"])

app = FastAPI(
    title="CALEBREVIEW Lead Gen API",
    version="0.1.0",
    description="Lead search, website auditing, PDF reports, and outreach email for CALEBREVIEW Lead Gen.",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings_obj.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    extra = {"request_id": request_id}

    logger.info(f"{request.method} {request.url.path} started", extra=extra)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(f"{request.method} {request.url.path} failed", extra=extra)
        raise

    duration_ms = round((time.perf_counter() - start) * 1000, 1)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        f"{request.method} {request.url.path} completed status={response.status_code} duration_ms={duration_ms}",
        extra=extra,
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


@app.get("/health")
def health_check():
    return {"status": "ok"}


api_prefix = settings_obj.api_prefix
app.include_router(dashboard.router, prefix=api_prefix)
app.include_router(search.router, prefix=api_prefix)
app.include_router(businesses.router, prefix=api_prefix)
app.include_router(audits.router, prefix=api_prefix)
app.include_router(emails.router, prefix=api_prefix)
app.include_router(pdfs.router, prefix=api_prefix)
app.include_router(settings.router, prefix=api_prefix)
app.include_router(activity.router, prefix=api_prefix)
app.include_router(geography.router, prefix=api_prefix)
app.include_router(api_keys.router, prefix=api_prefix)
