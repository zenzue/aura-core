"""Local time plugin with zoneinfo."""

from datetime import datetime
import zoneinfo
from typing import Any, Dict

from app.config import Settings
from app.tools.registry import BaseTool


class LocalTimePlugin(BaseTool):
    name = "get_local_time"

    def __init__(self, settings: Settings):
        super().__init__()
        self.settings = settings

    def spec(self) -> Dict[str, Any]:
        return {
            "description": "Get current local time in a timezone",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone (e.g. Asia/Bangkok). Default from settings.",
                    },
                },
                "required": [],
            },
        }

    async def call(self, args: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
        tz_name = args.get("timezone", self.settings.pet_timezone)
        try:
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz)
            return {
                "ok": True,
                "iso": now.isoformat(),
                "human": now.strftime("%Y-%m-%d %H:%M:%S %Z"),
            }
        except zoneinfo.ZoneInfoNotFoundError:
            return {"ok": False, "error": f"Timezone not found: {tz_name}"}