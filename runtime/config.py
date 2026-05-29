"""配置加载与校验 — 支持 YAML 读取、环境变量替换、热加载"""

import os
import re
from pathlib import Path
from typing import Any

import yaml

from shared.errors import ConfigError


def _replace_env_vars(value: Any) -> Any:
    """递归替换字符串中的 ${VAR} 环境变量占位符"""
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            default = match.group(2)
            env_val = os.environ.get(var_name)
            if env_val is not None:
                return env_val
            if default is not None:
                return default
            raise ConfigError(f"环境变量 {var_name} 未设置且无默认值")
        return re.sub(r"\$\{(\w+)(?::([^}]*))?\}", _replace, value)
    elif isinstance(value, dict):
        return {k: _replace_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_replace_env_vars(item) for item in value]
    return value


def load_config(path: str = "config.yaml") -> dict[str, Any]:
    """加载并校验配置文件

    Args:
        path: 配置文件路径，默认 "config.yaml"

    Returns:
        解析后的配置字典（环境变量已替换）

    Raises:
        ConfigError: 文件不存在或格式错误
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"配置文件不存在: {path}")

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"YAML 解析失败: {e}")

    if not isinstance(raw_config, dict):
        raise ConfigError("配置文件根节点必须为字典")

    # 环境变量替换
    config = _replace_env_vars(raw_config)

    # 基础校验
    _validate_config(config)

    return config


def _validate_config(config: dict[str, Any]) -> None:
    """基础配置校验"""
    if "system" not in config:
        raise ConfigError("缺少 system 配置段")
    if "runtime" not in config:
        raise ConfigError("缺少 runtime 配置段")
    if "gateway" not in config:
        raise ConfigError("缺少 gateway 配置段")

    system = config["system"]
    if "name" not in system:
        raise ConfigError("system.name 不能为空")
    if "data_dir" not in system:
        raise ConfigError("system.data_dir 不能为空")


def watch_config(path: str = "config.yaml", callback=None):
    """监听配置文件变更（简化版：轮询模式）

    Args:
        path: 配置文件路径
        callback: 配置变更后的回调函数 callback(new_config)
    """
    import time
    from pathlib import Path

    config_path = Path(path)
    last_mtime = config_path.stat().st_mtime if config_path.exists() else 0

    def _watcher():
        nonlocal last_mtime
        while True:
            time.sleep(5)
            if config_path.exists():
                current_mtime = config_path.stat().st_mtime
                if current_mtime > last_mtime:
                    last_mtime = current_mtime
                    try:
                        new_config = load_config(path)
                        if callback:
                            callback(new_config)
                    except ConfigError as e:
                        # 配置错误时仅记录，不中断 watcher
                        import logging
                        logging.error(f"配置热加载失败: {e}")

    import threading
    t = threading.Thread(target=_watcher, daemon=True)
    t.start()
    return t