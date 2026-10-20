"""AURA gateway entrypoint: structured logs, dependency checks, graceful
shutdown (uvicorn handles SIGTERM/SIGINT; ProviderService holds no blocking
calls outside request scope)."""
import json
import logging
import os
from datetime import datetime, timezone

from app.app import create_app
from app.config import load_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        handlers=[handler], force=True)


def run() -> None:
    """Load settings, build the app, serve via uvicorn."""
    settings = load_settings()
    _configure_logging(settings.log_level)
    logger = logging.getLogger("aura.gateway")

    data_dir = settings.gateway_data_dir
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("gateway_data_dir %s unusable: %s", data_dir, exc)

    if not settings.device_auth_token:
        logger.warning("DEVICE_AUTH_TOKEN empty: gateway runs open on the LAN "
                       "(development only)")
    for problem in settings.problems():
        logger.warning("config: %s", problem)

    logger.info("starting AURA gateway on %s:%s (pid %s, provider %s)",
                settings.gateway_host, settings.gateway_port, os.getpid(),
                settings.ai_provider)
    import uvicorn

    app = create_app(settings)
    uvicorn.run(app, host=settings.gateway_host, port=settings.gateway_port,
                log_level=settings.log_level.lower())


if __name__ == "__main__":
    run()
