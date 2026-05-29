"""Configuration manager with YAML loading, env var interpolation, Pydantic validation,
and optional hot-reload via file polling."""

from __future__ import annotations

import os
import re
import time
import logging
from pathlib import Path
from typing import Any, Callable

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

ENV_VAR_RE = re.compile(r"\$\{([^}]+)\}")

# ── Pydantic models for validation ────────────────────────────────────────


class SystemConfig(BaseModel):
    name: str = "pulsar"
    env: str = "development"
    debug: bool = False
    data_dir: str = "./data"
    timezone: str = "UTC"
    pid_file: str = "/tmp/pulsar.pid"


class GatewayProviderConfig(BaseModel):
    type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.95
    timeout: float = 60.0
    retry: dict[str, Any] = Field(default_factory=lambda: {"max_retries": 3, "base_delay_ms": 1000, "max_delay_ms": 30000})


class GatewayConfig(BaseModel):
    default_provider: str = "deepseek"
    providers: dict[str, GatewayProviderConfig] = Field(default_factory=dict)
    timeout: float = 30.0
    max_retries: int = 3
    retry_delay: float = 2.0


class RuntimeConfig(BaseModel):
    max_concurrency: int = 10
    shutdown_timeout: int = 15
    health_check_interval: int = 30
    task_timeout: int = 120
    limits: dict[str, Any] = Field(default_factory=lambda: {"max_open_files": 1024, "max_memory_mb": 512, "max_tool_output_bytes": 10485760})


class AuditRedactFields(BaseModel):
    enabled: bool = True
    fields: list[str] = Field(default_factory=lambda: ["api_key", "api_secret", "app_secret", "access_token", "token", "password", "secret", "authorization"])
    mask: str = "***REDACTED***"


class AuditConfig(BaseModel):
    enabled: bool = True
    level: str = "info"
    output: str = "file"
    file_path: str = "./data/audit/audit.log"
    max_file_size_mb: int = 100
    max_backups: int = 7
    max_age_days: int = 30
    compress: bool = True
    format: str = "json"
    filter_operations: list[str] = Field(default_factory=list)
    redact_fields: AuditRedactFields = Field(default_factory=AuditRedactFields)


class PulsarConfig(BaseModel):
    system: SystemConfig = Field(default_factory=SystemConfig)
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    audit: AuditConfig = Field(default_factory=AuditConfig)
    raw: dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"


class ConfigManager:
    """Loads, validates, and watches pulsar config files.

    Supports:
    - YAML loading
    - Environment variable interpolation (``${VAR_NAME}`` or ``${VAR_NAME:-default}``)
    - Pydantic validation
    - Optional file-polling hot-reload
    """

    def __init__(
        self,
        config_path: str | Path = "config.yaml",
        auto_reload: bool = False,
        reload_callback: Callable[[PulsarConfig], None] | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self._config_path = Path(config_path)
        self._auto_reload = auto_reload
        self._reload_callback = reload_callback
        self._poll_interval = poll_interval
        self._config: PulsarConfig | None = None
        self._last_mtime: float = 0.0
        self._running = False

    # ── public API ────────────────────────────────────────────────────────

    @property
    def config(self) -> PulsarConfig:
        """Return the validated config.  Raises if not yet loaded."""
        if self._config is None:
            raise RuntimeError("Config not loaded — call load() first")
        return self._config

    def load(self) -> PulsarConfig:
        """Load config from the YAML path, interpolate env vars, validate."""
        path = self._resolve_path()
        logger.info("Loading config from %s", path)

        raw = self._load_yaml(path)
        interpolated = self._interpolate_env(raw)
        validated = PulsarConfig(**interpolated)
        validated.raw = raw

        self._config = validated
        self._last_mtime = path.stat().st_mtime
        logger.info("Config loaded (env=%s, debug=%s)", validated.system.env, validated.system.debug)
        return validated

    def reload(self) -> PulsarConfig | None:
        """Check for file modification and reload if changed.  Returns new config or None."""
        path = self._resolve_path()
        try:
            current_mtime = path.stat().st_mtime
        except OSError:
            return None

        if current_mtime <= self._last_mtime:
            return None

        logger.info("Config file changed, reloading…")
        cfg = self.load()
        if self._reload_callback:
            self._reload_callback(cfg)
        return cfg

    def get(self, key: str, default: Any = None) -> Any:
        """Dot-notation access into the validated config, e.g. ``gateway.default_provider``."""
        if self._config is None:
            return default
        parts = key.split(".")
        obj: Any = self._config
        for part in parts:
            if isinstance(obj, BaseModel):
                obj = getattr(obj, part, None)
            elif isinstance(obj, dict):
                obj = obj.get(part)
            else:
                return default
            if obj is None:
                return default
        return obj

    # ── hot-reload loop ───────────────────────────────────────────────────

    async def watch(self) -> None:
        """Poll the config file for changes (simple async loop)."""
        if not self._auto_reload:
            return
        self._running = True
        import asyncio
        while self._running:
            await asyncio.sleep(self._poll_interval)
            try:
                self.reload()
            except Exception:
                logger.exception("Config reload failed")

    def stop_watch(self) -> None:
        self._running = False

    # ── internals ─────────────────────────────────────────────────────────

    def _resolve_path(self) -> Path:
        path = self._config_path
        if not path.is_absolute():
            # Try relative to CWD first, then fallback
            cwd = Path.cwd()
            candidate = cwd / path
            if candidate.exists():
                return candidate
        return path

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            logger.warning("Config file %s not found, using defaults", path)
            return {}
        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
        return data if isinstance(data, dict) else {}

    def _interpolate_env(self, obj: Any) -> Any:
        """Recursively replace ``${VAR_NAME}`` and ``${VAR_NAME:-default}`` placeholders."""
        if isinstance(obj, str):
            return ENV_VAR_RE.sub(self._replace_env_var, obj)
        if isinstance(obj, dict):
            return {k: self._interpolate_env(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._interpolate_env(item) for item in obj]
        return obj

    @staticmethod
    def _replace_env_var(match: re.Match) -> str:
        expression = match.group(1)
        if ":-" in expression:
            var_name, default = expression.split(":-", 1)
        else:
            var_name, default = expression, ""
        return os.environ.get(var_name, default)
