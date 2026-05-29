"""AuditLogger — structured JSON Lines logging with rotation and field redaction."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _redact_value(value: Any, mask: str = "***REDACTED***") -> Any:
    """Return the redaction mask for any sensitive value."""
    return mask


def _redact_dict(
    data: dict[str, Any],
    redact_fields: list[str],
    mask: str = "***REDACTED***",
    _prefix: str = "",
) -> dict[str, Any]:
    """Recursively redact sensitive fields in a dict.

    Supports dot-notation paths like ``credentials.api_key``.
    """
    result: dict[str, Any] = {}
    for key, value in data.items():
        full_path = f"{_prefix}.{key}" if _prefix else key
        if full_path in redact_fields:
            result[key] = _redact_value(value, mask)
        elif isinstance(value, dict):
            result[key] = _redact_dict(value, redact_fields, mask, full_path)
        elif isinstance(value, list):
            result[key] = [
                _redact_dict(item, redact_fields, mask, full_path) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            result[key] = value
    return result


class AuditLogger:
    """Structured audit logger writing JSON Lines to a file.

    Features:
    - JSON Lines format (one event per line)
    - File rotation by size
    - Configurable retention (max backups, max age)
    - Sensitive field redaction
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        cfg = config or {}

        self._enabled = cfg.get("enabled", True)
        self._file_path = Path(cfg.get("file_path", "./data/audit/audit.log"))
        self._max_file_size = cfg.get("max_file_size_mb", 100) * 1024 * 1024
        self._max_backups = cfg.get("max_backups", 7)
        self._max_age_days = cfg.get("max_age_days", 30)
        self._compress = cfg.get("compress", True)
        self._format = cfg.get("format", "json")
        self._filter_ops = cfg.get("filter_operations", [])

        # Redaction config
        redact_cfg = cfg.get("redact_fields", {})
        self._redact_enabled = redact_cfg.get("enabled", True)
        self._redact_fields = redact_cfg.get("fields", [
            "api_key", "api_secret", "app_secret", "access_token",
            "token", "password", "secret", "authorization",
        ])
        self._redact_mask = redact_cfg.get("mask", "***REDACTED***")

        self._file_handle: Any = None
        self._bytes_written: int = 0
        self._rotation_index: int = 0

    # ── public API ────────────────────────────────────────────────────────

    def log(
        self,
        event_type: str,
        agent: str = "",
        action: str = "",
        params: dict[str, Any] | None = None,
        result: Any = None,
        duration_ms: float = 0.0,
        user: str = "",
        success: bool = True,
        **extra: Any,
    ) -> None:
        """Write a structured audit event."""
        if not self._enabled:
            return

        if self._filter_ops and event_type not in self._filter_ops:
            return

        now = datetime.now(timezone.utc)
        entry: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "event_type": event_type,
            "agent": agent,
            "action": action,
            "duration_ms": round(duration_ms, 2),
            "user": user,
            "success": success,
        }

        if params is not None:
            entry["params"] = self._maybe_redact(params)
        if result is not None:
            entry["result"] = self._maybe_redact(result)
        entry.update(extra)

        self._write_entry(entry)

    def log_event(
        self,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Shortcut for logging a simple event without all optional fields."""
        self.log(event_type=event_type, **(data or {}))

    # ── lifecycle ─────────────────────────────────────────────────────────

    def open(self) -> None:
        """Open the log file (called by runtime on init)."""
        if not self._enabled:
            return
        self._ensure_dir()
        self._file_handle = open(self._file_path, "a", encoding="utf-8")
        self._bytes_written = self._file_handle.tell()
        logger.info("Audit log opened: %s", self._file_path)

    def close(self) -> None:
        """Flush and close the log file."""
        if self._file_handle:
            self._file_handle.flush()
            self._file_handle.close()
            self._file_handle = None
            logger.info("Audit log closed")

    def flush(self) -> None:
        if self._file_handle:
            self._file_handle.flush()

    # ── internals ─────────────────────────────────────────────────────────

    def _ensure_dir(self) -> None:
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    def _write_entry(self, entry: dict[str, Any]) -> None:
        if self._format == "json":
            line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
        else:
            line = f"[{entry['timestamp']}] {entry['event_type']} | {entry.get('agent','')} | {entry.get('action','')}\n"

        if self._file_handle:
            self._file_handle.write(line)
            self._bytes_written += len(line.encode("utf-8"))
            self._file_handle.flush()

            if self._bytes_written >= self._max_file_size:
                self._rotate()
        else:
            # Fallback to stderr if file not opened
            import sys
            sys.stderr.write(line)

    def _rotate(self) -> None:
        """Rotate the log file by size."""
        if not self._file_handle:
            return
        self._file_handle.close()

        # Shift existing backups
        for i in range(self._max_backups - 1, 0, -1):
            src = self._file_path.with_suffix(f".log.{i}")
            dst = self._file_path.with_suffix(f".log.{i + 1}")
            if src.exists():
                dst.write_bytes(src.read_bytes())
                src.unlink()

        # Rename current
        rotated = self._file_path.with_suffix(".log.1")
        self._file_path.rename(rotated)

        # Open new
        self._file_handle = open(self._file_path, "w", encoding="utf-8")
        self._bytes_written = 0
        self._rotation_index += 1

        # Clean old backups
        self._clean_old_backups()

    def _clean_old_backups(self) -> None:
        """Remove backups beyond max_backups."""
        for i in range(self._max_backups + 1, 100):
            backup = self._file_path.with_suffix(f".log.{i}")
            if backup.exists():
                backup.unlink()
            else:
                break

    def _maybe_redact(self, data: Any) -> Any:
        if not self._redact_enabled or not isinstance(data, dict):
            return data
        return _redact_dict(data, self._redact_fields, self._redact_mask)
