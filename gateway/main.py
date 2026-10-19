"""AURA gateway entrypoint."""
import logging

from app.app import create_app
from app.config import load_settings


def run() -> None:
    """Load settings, build the app, serve via uvicorn."""
    settings = load_settings()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("aura.gateway")
    logger.info("starting AURA gateway on %s:%s", settings.gateway_host, settings.gateway_port)
    import uvicorn

    app = create_app(settings)
    uvicorn.run(app, host=settings.gateway_host, port=settings.gateway_port,
                log_level="info")


if __name__ == "__main__":
    run()
