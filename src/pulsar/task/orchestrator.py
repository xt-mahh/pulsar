"""Orchestrator — multi-step DAG workflow execution with compensation rollback.

Receives ActionPlan (a set of steps with dependencies), builds a DAG,
executes steps in topological order (parallel where possible), and
performs rollback compensation on failure.
"""

import asyncio
import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# Data models
# ══════════════════════════════════════════════════════════════════════

class StepStatus(Enum):
    """State machine for individual step execution."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    COMPENSATE = "compensate"
    ROLLBACK = "rollback"
    COMPENSATED = "compensated"


class WorkflowStatus(Enum):
    """Overall workflow status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"


@dataclass
class ActionStep:
    """A single step in an ActionPlan workflow."""

    id: str                                 # Step unique ID
    tool: str                               # Tool name to execute
    params: dict = field(default_factory=dict)  # Step parameters
    depends_on: list[str] = field(default_factory=list)  # Step IDs this depends on
    compensation: Optional["ActionStep"] = None  # Compensation action (undo)


@dataclass
class ActionPlan:
    """A complete workflow plan with multiple steps."""

    workflow_id: str                        # Workflow unique ID
    steps: list[ActionStep] = field(default_factory=list)  # All steps
    user_intent: str = ""                   # User intent description
    confidence: float = 1.0                 # Intent confidence (0.0~1.0)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class StepResult:
    """Execution result for a single step."""

    step_id: str
    status: StepStatus = StepStatus.PENDING
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


@dataclass
class CompensationAction:
    """Record of a compensation action that was executed."""

    step_id: str                            # Original step ID
    action: str                             # Compensation action/tool
    params: dict = field(default_factory=dict)  # Compensation params
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None


@dataclass
class Workflow:
    """Aggregate workflow result."""

    workflow_id: str
    plan: ActionPlan
    step_results: dict[str, StepResult] = field(default_factory=dict)
    compensation_results: dict[str, CompensationAction] = field(default_factory=dict)
    status: WorkflowStatus = WorkflowStatus.PENDING
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════
# Orchestrator
# ══════════════════════════════════════════════════════════════════════

class Orchestrator:
    """Multi-step DAG workflow orchestrator with compensation rollback.

    Usage:
        orchestrator = Orchestrator(execute_handler=my_exec_func)
        workflow = await orchestrator.execute_plan(action_plan)
        print(workflow.status)
    """

    def __init__(
        self,
        execute_handler: Optional[Callable] = None,
    ):
        """
        Args:
            execute_handler: Async callable that takes (tool_name: str, params: dict)
                             and returns the result. If None, _default_execute is used.
        """
        self._handler = execute_handler
        self.active_workflows: dict[str, Workflow] = {}

    # ── Public API ──────────────────────────────────────────────────

    async def execute_plan(self, plan: ActionPlan) -> Workflow:
        """Execute a complete ActionPlan workflow.

        Builds a DAG from steps, topologically sorts them, executes in
        parallel batches, and handles compensation on failure.

        Args:
            plan: The ActionPlan to execute.

        Returns:
            Workflow object with all step results.
        """
        now = datetime.now(timezone.utc).isoformat()
        workflow = Workflow(
            workflow_id=plan.workflow_id,
            plan=plan,
            status=WorkflowStatus.RUNNING,
            created_at=now,
        )
        self.active_workflows[plan.workflow_id] = workflow

        # Initialize step results
        for step in plan.steps:
            workflow.step_results[step.id] = StepResult(
                step_id=step.id,
                status=StepStatus.PENDING,
            )

        try:
            # Build DAG and get execution order (batches of parallel steps)
            dag = self._build_dag(plan.steps)
            execution_batches = self._topological_sort(dag)

            # Execute each batch in order, steps within a batch in parallel
            for batch in execution_batches:
                tasks = []
                for step_id in batch:
                    step = self._find_step(plan.steps, step_id)
                    if step:
                        tasks.append(self._run_step(step, workflow))

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Check for failures
                for result in results:
                    if isinstance(result, Exception):
                        # Find which step failed
                        failed_step_id = self._identify_failed_step(workflow)
                        if failed_step_id:
                            logger.error(
                                "Step '%s' failed, starting compensation...",
                                failed_step_id,
                            )
                            await self._compensate(workflow, failed_step_id)
                            workflow.status = WorkflowStatus.COMPENSATED
                            workflow.completed_at = datetime.now(timezone.utc).isoformat()
                            return workflow

            # All steps completed successfully
            workflow.status = WorkflowStatus.COMPLETED

        except Exception as e:
            logger.error("Workflow execution error: %s", e)
            workflow.status = WorkflowStatus.FAILED

        workflow.completed_at = datetime.now(timezone.utc).isoformat()
        return workflow

    async def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID."""
        return self.active_workflows.get(workflow_id)

    # ── Step execution ──────────────────────────────────────────────

    async def _run_step(self, step: ActionStep, workflow: Workflow) -> StepResult:
        """Execute a single step and record the result."""
        result = workflow.step_results[step.id]
        result.status = StepStatus.RUNNING
        result.started_at = datetime.now(timezone.utc).isoformat()

        try:
            output = await self._execute_tool(step.tool, step.params)
            result.status = StepStatus.SUCCESS
            result.output = output
            logger.debug("Step '%s' completed successfully", step.id)
        except Exception as e:
            result.status = StepStatus.FAILED
            result.error = str(e)
            logger.warning("Step '%s' failed: %s", step.id, e)
            raise  # Re-raise so the caller can detect failure

        finally:
            result.completed_at = datetime.now(timezone.utc).isoformat()

        return result

    async def _execute_tool(self, tool: str, params: dict) -> Any:
        """Execute a tool via the registered handler or default executor."""
        if self._handler:
            if asyncio.iscoroutinefunction(self._handler):
                return await self._handler(tool, params)
            else:
                return self._handler(tool, params)
        else:
            return await self._default_execute(tool, params)

    async def _default_execute(self, tool: str, params: dict) -> Any:
        """Default tool execution — delegates to the global ToolRegistry."""
        from pulsar.execution.tools.registry import get_registry
        registry = get_registry()
        return await registry.execute(tool, **params)

    # ── Compensation ────────────────────────────────────────────────

    async def _compensate(self, workflow: Workflow, failed_step_id: str) -> None:
        """Execute compensation for all successfully completed steps in reverse order.

        Iterates through steps in reverse dependency order and executes
        defined compensation actions for successful steps.
        """
        logger.info(
            "Starting compensation for workflow '%s' (failed step: %s)",
            workflow.workflow_id,
            failed_step_id,
        )

        reversed_steps = self._reverse_dependency_order(workflow.plan.steps)

        for step in reversed_steps:
            if step.id == failed_step_id:
                continue  # Don't compensate the failed step itself

            step_result = workflow.step_results.get(step.id)
            if step_result and step_result.status == StepStatus.SUCCESS and step.compensation:
                comp = CompensationAction(
                    step_id=step.id,
                    action=step.compensation.tool,
                    params=step.compensation.params,
                    status=StepStatus.ROLLBACK,
                )

                try:
                    comp_result = await self._execute_tool(
                        step.compensation.tool,
                        step.compensation.params,
                    )
                    comp.status = StepStatus.COMPENSATED
                    logger.info(
                        "Compensation for step '%s' succeeded: %s",
                        step.id,
                        comp_result,
                    )
                except Exception as e:
                    comp.status = StepStatus.FAILED
                    comp.error = str(e)
                    logger.error(
                        "Compensation for step '%s' failed: %s",
                        step.id,
                        e,
                    )
                    # Continue compensating other steps

                workflow.compensation_results[step.id] = comp

    # ── DAG construction and sorting ─────────────────────────────────

    def _build_dag(self, steps: list[ActionStep]) -> dict[str, list[str]]:
        """Build an adjacency list (DAG) from steps.

        Returns:
            dict mapping step_id -> list of successor step_ids.
        """
        dag: dict[str, list[str]] = {s.id: [] for s in steps}
        step_ids = {s.id for s in steps}

        for step in steps:
            for dep_id in step.depends_on:
                if dep_id in step_ids:
                    dag.setdefault(dep_id, []).append(step.id)

        return dag

    def _topological_sort(self, dag: dict[str, list[str]]) -> list[list[str]]:
        """Kahn's algorithm for topological sort, grouped by parallel batches.

        Returns:
            List of batches. Each batch is a list of step IDs that can run in parallel.
            Batches must be executed sequentially (outer list order).
        """
        # Calculate in-degrees
        in_degree: dict[str, int] = {node: 0 for node in dag}
        for node, successors in dag.items():
            for succ in successors:
                in_degree[succ] = in_degree.get(succ, 0) + 1

        # Ensure all nodes are in in_degree
        for node in dag:
            in_degree.setdefault(node, 0)

        queue = deque([node for node, degree in in_degree.items() if degree == 0])
        batches: list[list[str]] = []

        while queue:
            batch = list(queue)
            batches.append(batch)
            queue.clear()

            for node in batch:
                for succ in dag.get(node, []):
                    in_degree[succ] -= 1
                    if in_degree[succ] == 0:
                        queue.append(succ)

        return batches

    def _reverse_dependency_order(self, steps: list[ActionStep]) -> list[ActionStep]:
        """Return steps in reverse dependency order (for compensation)."""
        dag = self._build_dag(steps)
        batches = self._topological_sort(dag)

        # Flatten batches, reverse them
        flat_order: list[str] = []
        for batch in reversed(batches):
            flat_order.extend(reversed(batch))

        # Map back to ActionStep objects, preserving found order
        step_map = {s.id: s for s in steps}
        return [step_map[sid] for sid in flat_order if sid in step_map]

    @staticmethod
    def _find_step(steps: list[ActionStep], step_id: str) -> Optional[ActionStep]:
        """Find a step by ID."""
        for step in steps:
            if step.id == step_id:
                return step
        return None

    @staticmethod
    def _identify_failed_step(workflow: Workflow) -> Optional[str]:
        """Identify the first step with FAILED status."""
        for step_id, result in workflow.step_results.items():
            if result.status == StepStatus.FAILED:
                return step_id
        return None
