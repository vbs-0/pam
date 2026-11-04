import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"ts": round(record.created, 3), "level": record.levelname, "logger": record.name,
                "msg": record.getMessage()}
        data.update(getattr(record, "extra_fields", {}))
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def setup_logging() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h], force=True)


log = logging.getLogger("pam")


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        # accept a caller id only if it is short and safe to echo into logs/headers
        safe = 0 < len(incoming) <= 64 and incoming.replace("-", "").isalnum()
        rid = incoming if safe else uuid.uuid4().hex
        request.state.request_id = rid
        t0 = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info("request", extra={"extra_fields": {
            "rid": rid, "method": request.method, "path": request.url.path,
            "status": response.status_code, "ms": round((time.perf_counter() - t0) * 1000, 1)}})
        return response
