import pytest
import tempfile
import os
from runtime.config import load_config


class TestConfig:
    def test_load_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")

    def test_load_config_success(self):
        content = """
system:
  name: "Pulsar"
  version: "0.1.0"
runtime:
  heartbeat_interval: 15
audit:
  enabled: true
  output: "file"
  path: "./data/logs/audit.log"
  log_levels: ["tool_call"]
"""
        import yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name

        try:
            cfg = load_config(tmp_path)
            assert cfg.system["name"] == "Pulsar"
            assert cfg.runtime["heartbeat_interval"] == 15
        finally:
            os.unlink(tmp_path)

    def test_env_var_substitution(self):
        os.environ["TEST_VAR"] = "test_value"
        content = """
system:
  name: "${TEST_VAR}"
"""
        import yaml
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write(content)
            tmp_path = f.name

        try:
            cfg = load_config(tmp_path)
            assert cfg.system["name"] == "test_value"
        finally:
            os.unlink(tmp_path)
            del os.environ["TEST_VAR"]