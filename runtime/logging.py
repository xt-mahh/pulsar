import json
import os
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from shared.models import AuditLog


class AuditLogger:
    def __init__(self, config: dict = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.output = config.get("output", "file")
        self.path = config.get("path", "./data/logs/audit.log")
        self.log_levels = config.get("log_levels", ["tool_call", "system_event", "auth"])

        if self.enabled and self.output == "file":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _write(self, entry: AuditLog):
        if not self.enabled:
            return
        if entry.event_type not in self.log_levels:
            return
        data = entry.model_dump()
        data["timestamp"] = data["timestamp"].isoformat()
        line = json.dumps(data, ensure_ascii=False)
        if self.output == "file":
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        else:
            logger.info(f"AUDIT: {line}")

    def log_tool_call(
        self, agent: str, action: str, params: dict,
        result: dict = None, duration_ms: int = 0,
        user: str = "system", success: bool = True
    ):
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            event_type="tool_call",
            agent=agent,
            action=action,
            params=params,
            result=result,
            duration_ms=duration_ms,
            user=user,
            success=success,
        )
        self._write(entry)

    def log_system_event(
        self, agent: str, action: str, params: dict = None,
        success: bool = True
    ):
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            event_type="system_event",
            agent=agent,
            action=action,
            params=params or {},
            success=success,
        )
        self._write(entry)

    def log_auth(self, agent: str, action: str, params: dict, success: bool = True):
        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            event_type="auth",
            agent=agent,
            action=action,
            params=params,
            success=success,
        )
        self._write(entry)