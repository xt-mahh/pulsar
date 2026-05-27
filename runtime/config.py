import os
import re
import yaml
from pathlib import Path
from shared.models import PulsarConfig


_env_var_pattern = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_vars(value):
    if isinstance(value, str):
        def _replace(match):
            env_var = match.group(1)
            return os.environ.get(env_var, match.group(0))
        return _env_var_pattern.sub(_replace, value)
    if isinstance(value, dict):
        return {k: _resolve_env_vars(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_env_vars(v) for v in value]
    return value


def load_config(config_path: str = "config.yaml") -> PulsarConfig:
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    resolved = _resolve_env_vars(raw)
    return PulsarConfig(**resolved)


class ConfigWatcher:
    def __init__(self, config_path: str = "config.yaml", poll_interval: int = 30):
        self.config_path = config_path
        self.poll_interval = poll_interval
        self._last_mtime = 0
        self._current_config = None

    def get_config(self) -> PulsarConfig:
        if self._current_config is None:
            self._current_config = load_config(self.config_path)
            self._last_mtime = Path(self.config_path).stat().st_mtime
        return self._current_config

    def check_reload(self) -> bool:
        try:
            mtime = Path(self.config_path).stat().st_mtime
            if mtime > self._last_mtime:
                self._current_config = load_config(self.config_path)
                self._last_mtime = mtime
                return True
        except OSError:
            pass
        return False

    def reload(self) -> PulsarConfig:
        self._current_config = load_config(self.config_path)
        self._last_mtime = Path(self.config_path).stat().st_mtime
        return self._current_config