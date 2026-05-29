"""审计日志系统 — 结构化日志记录与查询"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from shared.models import AuditLog

logger = logging.getLogger("pulsar.audit")


class AuditLogger:
    """审计日志记录器

    将所有关键操作记录为结构化 JSON Lines 日志。
    Phase 1 写入本地文件，后续可对接 ELK / Loki。
    """

    def __init__(self, config: dict[str, Any] | None = None):
        config = config or {}
        self.enabled = config.get("enabled", True)
        self.output = config.get("output", "file")
        self.path = config.get("path", "data/logs/audit.log")
        self.log_levels = config.get("log_levels", ["tool_call", "system_event", "auth"])

        if self.enabled and self.output == "file":
            log_path = Path(self.path)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(log_path, "a", encoding="utf-8")
        else:
            self._file = None

    def log(
        self,
        event_type: str,
        agent: str,
        action: str,
        params: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        duration_ms: int = 0,
        user: str = "system",
        success: bool = True,
    ) -> None:
        """记录一条审计日志

        Args:
            event_type: 事件类型 (tool_call, system_event, auth)
            agent: 执行 Agent 名称
            action: 执行的操作
            params: 操作参数
            result: 操作结果
            duration_ms: 耗时(毫秒)
            user: 操作用户
            success: 是否成功
        """
        if not self.enabled:
            return

        if event_type not in self.log_levels:
            return

        entry = AuditLog(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            agent=agent,
            action=action,
            params=params or {},
            result=result,
            duration_ms=duration_ms,
            user=user,
            success=success,
        )

        self._write_entry(entry)

    def _write_entry(self, entry: AuditLog) -> None:
        """写入日志条目"""
        try:
            line = entry.model_dump_json() + "\n"

            if self._file:
                self._file.write(line)
                self._file.flush()
            else:
                # stdout 模式
                print(f"[AUDIT] {line.strip()}")
        except Exception as e:
            logger.error(f"写入审计日志失败: {e}")

    def query(
        self,
        event_type: str | None = None,
        agent: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        """查询审计日志（从文件读取）

        Args:
            event_type: 按事件类型过滤
            agent: 按 Agent 过滤
            action: 按操作过滤
            limit: 返回条数上限

        Returns:
            匹配的审计日志列表（按时间倒序）
        """
        if not self.path:
            return []

        log_path = Path(self.path)
        if not log_path.exists():
            return []

        results: list[AuditLog] = []
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = AuditLog.model_validate_json(line)
                    except Exception:
                        continue

                    # 过滤
                    if event_type and entry.event_type != event_type:
                        continue
                    if agent and entry.agent != agent:
                        continue
                    if action and entry.action != action:
                        continue

                    results.append(entry)
        except Exception as e:
            logger.error(f"读取审计日志失败: {e}")

        # 按时间倒序排列
        results.sort(key=lambda x: x.timestamp, reverse=True)
        return results[:limit]

    def close(self) -> None:
        """关闭日志文件"""
        if self._file:
            self._file.close()
            self._file = None