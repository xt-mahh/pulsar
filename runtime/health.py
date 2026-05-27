from datetime import datetime, timezone


class AgentHealth:
    def __init__(self, name: str):
        self.name = name
        self.last_heartbeat: datetime | None = None
        self.status: str = "unknown"
        self.consecutive_misses: int = 0
        self.restart_count: int = 0

    def record_heartbeat(self):
        self.last_heartbeat = datetime.now(timezone.utc)
        self.consecutive_misses = 0
        self.status = "healthy"

    def miss_heartbeat(self):
        self.consecutive_misses += 1
        if self.consecutive_misses >= 3:
            self.status = "unhealthy"

    def is_healthy(self) -> bool:
        return self.status == "healthy"


class HealthChecker:
    def __init__(self, max_missed: int = 3):
        self._agents: dict[str, AgentHealth] = {}
        self.max_missed = max_missed

    def register_agent(self, name: str):
        if name not in self._agents:
            self._agents[name] = AgentHealth(name)

    def unregister_agent(self, name: str):
        self._agents.pop(name, None)

    def record_heartbeat(self, name: str):
        if name not in self._agents:
            self.register_agent(name)
        self._agents[name].record_heartbeat()

    def miss_heartbeat(self, name: str):
        if name in self._agents:
            self._agents[name].miss_heartbeat()

    def is_healthy(self, name: str) -> bool:
        agent = self._agents.get(name)
        return agent.is_healthy() if agent else False

    def get_all_status(self) -> dict[str, dict]:
        return {
            name: {
                "status": agent.status,
                "last_heartbeat": agent.last_heartbeat.isoformat() if agent.last_heartbeat else None,
                "consecutive_misses": agent.consecutive_misses,
                "restart_count": agent.restart_count,
            }
            for name, agent in self._agents.items()
        }