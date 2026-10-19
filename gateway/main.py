import asyncio
import logging

from litestar import Litestar
from litestar.config import Config

from app.app import create_app
from app.config import Settings, load_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run() -> None:
    """Run the AURA gateway server."""
    # Load settings
    settings = load_settings()
    
    # Create app
    app = create_app(settings)
    
    # Run uvicorn programmatically
    import uvicorn
    
    uvicorn.run(
        app,
        host=settings.host or "0.0.0.0",
        port=settings.port or 8000,
        reload=settings.debug or False,
        log_level=logging.getLevelName(settings.log_level or "INFO"),
    )


if __name__ == "__main__":
    run()