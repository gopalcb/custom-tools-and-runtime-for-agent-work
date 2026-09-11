"""Run ownership and workflow execution."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from agents_internal_messaging.bus import MessageBus
from .codex_client import CodexAppServerClient, CodexProtocolError
from .events import EventHub, RuntimeEvent
from .memory.service import MemoryService
from .planned_tasks import (
    extract_structured_plan,
    persist_planned_tasks,
    render_planned_task_handoff,
    update_planned_tasks_from_report,
)
from .post_completion import post_completion
from .registry import AgentDefinition, Registry
from .resolver import Resolver, ResolvedRunSpec, collect_project_context, compact_context
from .strategy_feedback import StrategyFeedbackCoordinator, build_memory_source, fallback_analysis
from .system_health import run_monorepo_system_health
from .workflow import WorkflowCancelled, WorkflowEngine
from .workflows.workflow_resolver import resolve_planned_workflow


logger = logging.getLogger(__name__)
ERROR_EVENT_TYPES = frozenset({"error", "tool.failed", "background.failed", "run.failed"})


@dataclass(slots=True)
class RunContext:
    run_id: str
    session_id: str
    prompt: str
    resolved: ResolvedRunSpec
    project_root: Path
    agent_id: str
    conditions: Mapping[str, bool]
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    artifacts: list[Path] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    background_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)
    event_hub: EventHub | None = None
    memory_service: MemoryService | None = None


class AgentRuntime:
    """Own resolution, workflow execution, Codex turns, and finalization."""

    def __init__(
        self,
        project_root: str | Path,
        registry: Registry,
        resolver: Resolver,
        events: EventHub,
        memory: MemoryService,
        workflow: WorkflowEngine,
        codex_client: CodexAppServerClient,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.registry = registry
        self.resolver = resolver
        self.events = events
        self.memory = memory
        self.workflow = workflow
        self.codex = codex_client
        self.messaging = MessageBus(self.registry.messaging_root)
        self.strategy_feedback = StrategyFeedbackCoordinator(
            self.project_root,
            self.registry,
            self.codex,
            self.memory,
        )
        self._runs: dict[str, RunContext] = {}
        logger.info("AgentRuntime initialized", extra={"project_root": str(self.project_root)})

    async def run(
        self,
        prompt: str,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        resume: bool = False,
    ) -> AsyncIterator[RuntimeEvent]:
        """Resolve and execute a prompt while streaming durable events."""
        run_id = run_id or f"run-{uuid4().hex[:12]}"
        logger.info(
            "Runtime run requested",
            extra={"run_id": run_id, "session_id": session_id, "agent_id": agent_id, "resume": resume},
        )
        if resume and session_id is None:
            session_id = self._latest_session_id()
            if session_id is None:
                raise ValueError("No previous session is available to resume")
        session_id = session_id or f"session-{uuid4().hex[:12]}"
        queue = self.events.subscribe(run_id)
        task = asyncio.create_task(
            self._execute(run_id, session_id, prompt, agent_id=agent_id, resume=resume)
        )
        try:
            while not task.done() or not queue.empty():
                try:
                    yield await asyncio.wait_for(queue.get(), 0.1)
                except asyncio.TimeoutError:
                    continue
            await task
        finally:
            self.events.unsubscribe(queue)

    async def cancel(self, run_id: str) -> bool:
        """Cancel an active run and report whether it was found."""
        context = self._runs.get(run_id)
        if context is None:
            logger.info("Cancel requested for unknown run", extra={"run_id": run_id})
            return False
        context.cancel_event.set()
        for task in context.background_tasks.values():
            task.cancel()
        await self.codex.interrupt()
        logger.info("Runtime run cancellation requested", extra={"run_id": run_id})
        return True

    async def respond_to_approval(self, request_id: int, decision: str) -> None:
        """Forward an application approval decision to the active Codex client."""
        await self.codex.respond_to_approval(request_id, decision)

    async def run_command(self, command: str) -> dict[str, Any]:
        """Run a Codex slash command without routing it through a workflow."""
        return await self.codex.run_command(command)

    async def close(self) -> None:
        """Close the Codex client and release runtime resources."""
        await self.codex.close()
        logger.info("AgentRuntime closed")

    def _latest_session_id(self) -> str | None:
        candidates = sorted(
            self.events.sessions_root.glob("*/session.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return candidates[0].parent.name if candidates else None

    async def _execute(
        self,
        run_id: str,
        session_id: str,
        prompt: str,
        *,
        agent_id: str | None,
        resume: bool,
    ) -> None:
        await self.events.emit(
            self.events.new_event(
                "run.started",
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                status="running",
                message=prompt,
                payload={"workflow_projection": True},
            )
        )
        try:
            resolved = self.resolver.resolve(prompt, agent_id=agent_id)
        except Exception as exc:
            logger.exception("Run resolution failed", extra={"run_id": run_id, "agent_id": agent_id})
            for event_type in ("error", "run.failed"):
                event = await self.events.emit(
                    self.events.new_event(
                        event_type,
                        run_id=run_id,
                        session_id=session_id,
                        agent_id=agent_id,
                        status="failed",
                        message=str(exc),
                        payload={"exception": type(exc).__name__} if event_type == "error" else {},
                    )
                )
                self._record_error_alert(event)
            self.events.write_session(
                session_id,
                {
                    "status": "failed",
                    "last_run_id": run_id,
                    "agent_id": agent_id,
                    "error": str(exc),
                },
            )
            await post_completion(
                SimpleNamespace(
                    run_id=run_id,
                    session_id=session_id,
                    event_hub=self.events,
                    memory_service=self.memory,
                )
            )
            return
        logger.info(
            "Run resolved",
            extra={"run_id": run_id, "agent_id": resolved.agent_id, "workflow_id": resolved.workflow_id},
        )
        context = RunContext(
            run_id=run_id,
            session_id=session_id,
            prompt=prompt,
            resolved=resolved,
            project_root=self.project_root,
            agent_id=resolved.agent_id,
            conditions=resolved.conditions,
            event_hub=self.events,
            memory_service=self.memory,
        )
        previous_session = self.events.load_session(session_id) if resume else None
        context.data["resume"] = resume
        if previous_session and previous_session.get("codex_thread_id"):
            context.data["codex_thread_id"] = previous_session["codex_thread_id"]
        self._runs[run_id] = context
        self._write_session(context, "active")
        try:
            await self._ensure_pre_work_health(context)
            await self._emit(
                context,
                "resolver.completed",
                status="completed",
                payload={
                    "agent_id": resolved.agent_id,
                    "workflow_id": resolved.workflow_id,
                    "planning_workflow_id": resolved.planning_workflow_id,
                    "skills": list(resolved.skills),
                    "tools": list(resolved.tools),
                    "conditions": dict(resolved.conditions),
                    "validation_commands": list(resolved.validation_commands),
                },
            )
            handlers = {
                "agent": self._agent_step,
                "tool": self._tool_step,
                "shell": self._shell_step,
                "hook": self._hook_step,
            }
            if resolved.planning_workflow_id is not None:
                logger.info(
                    "Planning workflow starting",
                    extra={"run_id": run_id, "workflow_id": resolved.planning_workflow_id},
                )
                planning_result = await self.workflow.execute(
                    self.registry.get_workflow(resolved.planning_workflow_id), context, handlers
                )
                plan_output = planning_result.outputs.get("plan", {})
                planner_response = plan_output.get("response", "") if isinstance(plan_output, dict) else ""
                try:
                    structured_plan = extract_structured_plan(planner_response)
                    if structured_plan and structured_plan.get("tasks"):
                        task_manifest = persist_planned_tasks(
                            self.project_root,
                            structured_plan,
                            run_id=run_id,
                            session_id=session_id,
                        )
                        context.data["planned_tasks_manifest"] = str(task_manifest)
                        context.data["planned_tasks_plan_id"] = str(structured_plan.get("title", ""))
                        context.data["planned_tasks_handoff"] = render_planned_task_handoff(structured_plan, task_manifest)
                        await self._emit(
                            context,
                            "artifact.created",
                            step_id="plan",
                            status="completed",
                            message="Planned tasks persisted for controller visibility.",
                            payload={"path": str(task_manifest), "kind": "planned-tasks"},
                        )
                except Exception as exc:
                    logger.warning(
                        "Planner task persistence failed; continuing workflow",
                        extra={"run_id": run_id, "session_id": session_id, "error": str(exc)},
                    )
                    await self._emit(
                        context,
                        "error",
                        step_id="plan",
                        status="need rework",
                        message=f"Planned task persistence failed; continuing workflow: {exc}",
                        payload={"exception": type(exc).__name__, "non_blocking": True},
                    )
                selection = resolve_planned_workflow(
                    planner_response,
                    self.registry.execution_workflow_ids(),
                    resolved.workflow_id,
                )
                context.data["workflow_selection"] = selection.workflow_id
                context.data["planning_complete"] = True
                await self._emit(
                    context,
                    "workflow.resolved",
                    status="completed",
                    message=selection.workflow_id,
                    payload={"workflow_id": selection.workflow_id, "source": selection.source},
                )
                definition = self.registry.get_workflow(selection.workflow_id)
            else:
                definition = self.registry.get_workflow(resolved.workflow_id)
            logger.info(
                "Execution workflow starting",
                extra={"run_id": run_id, "workflow_id": definition.get("id", resolved.workflow_id)},
            )
            await self.workflow.execute(definition, context, handlers)
            await self._emit(context, "run.completed", status="completed", message="Run completed")
            self._write_session(context, "completed")
            await post_completion(context)
            logger.info("Run completed", extra={"run_id": run_id, "session_id": session_id})
        except (WorkflowCancelled, asyncio.CancelledError):
            await self._emit(context, "run.cancelled", status="cancelled", message="Run cancelled")
            self._write_session(context, "cancelled")
            await post_completion(context)
            logger.info("Run cancelled", extra={"run_id": run_id, "session_id": session_id})
        except Exception as exc:
            logger.exception("Run failed", extra={"run_id": run_id, "session_id": session_id})
            if not context.data.get("strategy_feedback_completed"):
                try:
                    await self._hook_step(
                        {
                            "id": "store-strategy-memory",
                            "name": "Collect feedback and update strategy memory",
                            "hook": "strategy_memory_feedback",
                        },
                        context,
                    )
                except Exception as feedback_error:
                    await self._emit(
                        context,
                        "error",
                        step_id="store-strategy-memory",
                        status="failed",
                        message=f"Strategy feedback failed after run error: {feedback_error}",
                        payload={
                            "exception": type(feedback_error).__name__,
                            "non_blocking": True,
                        },
                    )
            await self._emit(
                context,
                "error",
                status="failed",
                message=str(exc),
                payload={"exception": type(exc).__name__},
            )
            await self._emit(context, "run.failed", status="failed", message=str(exc))
            self._write_session(context, "failed", error=str(exc))
            await post_completion(context)
        finally:
            self._runs.pop(run_id, None)

    async def _agent_step(self, step: dict[str, Any], context: RunContext) -> dict[str, Any]:
        configured = step.get("agent")
        target_id = context.agent_id if configured == "$resolved_agent" else configured
        if not isinstance(target_id, str):
            raise ValueError(f"Agent step '{step['id']}' has no valid agent")
        agent = self.registry.get_agent(target_id)
        instructions = self._assembled_instructions(agent, context)
        prompt = self._step_prompt(step, context)
        await self._emit(context, "agent.started", agent_id=target_id, step_id=step["id"], status="running")
        logger.info(
            "Agent step started",
            extra={"run_id": context.run_id, "agent_id": target_id, "step_id": step["id"]},
        )
        final_parts: list[str] = []
        resume_id: str | None = None
        if context.data.get("resume") and target_id == context.agent_id:
            resume_id = context.data.get("codex_thread_id")
        codex_options = self.registry.codex_options_for_profile(agent.model_profile)
        async for raw in self.codex.stream_turn(
            prompt,
            developer_instructions=instructions,
            model=codex_options["model"],
            effort=codex_options["effort"],
            thread_id=resume_id,
        ):
            if raw.get("method") == "client/thread":
                context.data["codex_thread_id"] = raw["params"]["threadId"]
                continue
            for event_type, message, payload in self._normalize_codex(raw):
                if event_type == "agent.message.delta" and message:
                    final_parts.append(message)
                await self._emit(
                    context,
                    event_type,
                    agent_id=target_id,
                    step_id=step["id"],
                    message=message,
                    payload=payload,
                )
        final = "".join(final_parts)
        await self._emit(
            context,
            "agent.completed",
            agent_id=target_id,
            step_id=step["id"],
            status="completed",
            message=final[-2000:] if final else None,
        )
        if step.get("id") != "plan" and context.data.get("planned_tasks_plan_id") and final:
            try:
                count = update_planned_tasks_from_report(
                    self.project_root,
                    str(context.data["planned_tasks_plan_id"]),
                    final,
                    context.run_id,
                    context.session_id,
                )
                if count:
                    await self._emit(
                        context,
                        "artifact.created",
                        agent_id=target_id,
                        step_id=step["id"],
                        status="completed",
                        message=f"Updated {count} planned-task status entries.",
                        payload={
                            "path": str(context.data.get("planned_tasks_manifest", "")),
                            "kind": "planned-tasks-status",
                            "count": count,
                        },
                    )
            except Exception as exc:
                logger.warning(
                    "Planned task status report could not be applied; continuing workflow",
                    extra={"run_id": context.run_id, "step_id": step["id"], "error": str(exc)},
                )
        logger.info(
            "Agent step completed",
            extra={"run_id": context.run_id, "agent_id": target_id, "step_id": step["id"]},
        )
        return {"agent_id": target_id, "response": final}

    async def _tool_step(self, step: dict[str, Any], context: RunContext) -> Any:
        tool = step.get("tool")
        permitted = tool in context.resolved.tools or (
            tool == "project_context" and "repo" in context.resolved.tools
        )
        if not permitted:
            raise PermissionError(f"Tool '{tool}' is not permitted for {context.agent_id}")
        await self._emit(context, "tool.started", step_id=step["id"], payload={"tool": tool})
        logger.info(
            "Runtime tool step started",
            extra={"run_id": context.run_id, "tool": tool, "step_id": step["id"]},
        )
        try:
            if tool in {"project_context", "repo"}:
                items = await collect_project_context(
                    self.project_root,
                    context.resolved.context_queries,
                )
                value = compact_context(items)
                context.data["project_context"] = value
                result: Any = {"files": [item.path for item in items], "characters": len(value)}
            elif tool == "web_search":
                result = await self._agent_step(
                    {
                        "id": step["id"],
                        "name": "Research current external sources required by the request",
                        "agent": step.get("agent", "$resolved_agent"),
                    },
                    context,
                )
                context.data["web_research"] = result
            elif tool == "agent_messaging":
                pending = self.messaging.pending(context.agent_id)
                result = {
                    "root": str(self.messaging.root),
                    "agent_id": context.agent_id,
                    "pending_count": len(pending),
                    "pending_paths": [str(path) for path in pending],
                }
                context.data["agent_messaging"] = result
            else:
                raise ValueError(f"Unknown runtime tool: {tool}")
        except Exception as exc:
            logger.exception(
                "Runtime tool step failed",
                extra={"run_id": context.run_id, "tool": tool, "step_id": step["id"]},
            )
            await self._emit(
                context,
                "tool.failed",
                step_id=step["id"],
                message=str(exc),
                payload={"tool": tool},
            )
            raise
        await self._emit(
            context,
            "tool.completed",
            step_id=step["id"],
            status="completed",
            payload={"tool": tool, "result": result},
        )
        logger.info(
            "Runtime tool step completed",
            extra={"run_id": context.run_id, "tool": tool, "step_id": step["id"]},
        )
        return result

    async def _shell_step(self, step: dict[str, Any], context: RunContext) -> dict[str, Any]:
        command = self._resolve_command(step.get("command"), context)
        logger.info(
            "Validation shell step started",
            extra={"run_id": context.run_id, "step_id": step["id"], "command": command},
        )
        await self._emit(
            context,
            "tool.started",
            step_id=step["id"],
            payload={"tool": "shell", "command": command, "validation": True},
        )
        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self.project_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        result = {
            "command": command,
            "exit_code": process.returncode,
            "stdout": stdout.decode(errors="replace")[-8000:],
            "stderr": stderr.decode(errors="replace")[-8000:],
            "validation": True,
        }
        if process.returncode:
            logger.error(
                "Validation shell step failed",
                extra={"run_id": context.run_id, "step_id": step["id"], "exit_code": process.returncode},
            )
            await self._emit(
                context,
                "tool.failed",
                step_id=step["id"],
                message=f"Validation command failed: {command}",
                payload={"tool": "shell", **result},
            )
            raise RuntimeError(f"Validation command failed ({process.returncode}): {command}")
        await self._emit(
            context,
            "tool.completed",
            step_id=step["id"],
            status="completed",
            payload={"tool": "shell", **result},
        )
        logger.info(
            "Validation shell step completed",
            extra={"run_id": context.run_id, "step_id": step["id"]},
        )
        return result

    async def _ensure_pre_work_health(
        self,
        context: RunContext,
        *,
        step_id: str = "pre-work-health",
    ) -> dict[str, Any]:
        """Run the mandatory pre-work health check once per runtime run."""
        cached = context.data.get("pre_work_health")
        if isinstance(cached, dict) and cached.get("status") == "healthy":
            return {**cached, "cached": True}
        health = run_monorepo_system_health(
            self.project_root,
            state_root=self.registry.state_root,
            messaging_root=self.registry.messaging_root,
            memory_root=self.memory.retriever.memory_root,
        )
        context.data["pre_work_health"] = health
        await self._emit(
            context,
            "health.checked",
            step_id=step_id,
            status=health["status"],
            message=f"Monorepo system health is {health['status']}.",
            payload=health,
        )
        if health["status"] != "healthy":
            raise RuntimeError("Monorepo system health check failed")
        return health

    async def _hook_step(self, step: dict[str, Any], context: RunContext) -> dict[str, str]:
        hook = step.get("hook")
        if hook == "analyze_query":
            return {"hook": hook, "status": "completed"}
        if hook == "pre_work_health_check":
            health = await self._ensure_pre_work_health(context, step_id=step["id"])
            if health.get("cached"):
                return {"hook": hook, "status": "cached"}
            return {"hook": hook, "status": "completed"}
        if hook == "strategy_memory_feedback":
            if not self.strategy_feedback.enabled():
                context.data["strategy_feedback_completed"] = True
                return {"hook": hook, "status": "skipped"}
            settings = self.strategy_feedback.settings()
            max_cycles = max(1, min(5, int(settings["max_rework_cycles"])))
            cycles: list[dict[str, Any]] = []
            for cycle in range(1, max_cycles + 1):
                await self._emit(
                    context,
                    "feedback.started",
                    step_id=step["id"],
                    status="running",
                    message="Waiting for post-work feedback.",
                    payload={"cycle": cycle},
                )
                feedback = await self.strategy_feedback.collect_feedback(context)
                feedback_status = str(feedback.get("status") or "cancelled")
                cycles.append({"cycle": cycle, "status": feedback_status})
                artifact_path = feedback.get("artifact_path")
                if artifact_path:
                    await self._emit(
                        context,
                        "artifact.created",
                        step_id=step["id"],
                        status="completed",
                        message="Strategy feedback artifact written.",
                        payload={"path": str(artifact_path), "kind": "strategy-feedback"},
                    )
                if feedback_status != "submitted":
                    await self._emit(
                        context,
                        "feedback.cancelled",
                        step_id=step["id"],
                        status=feedback_status,
                        message=str(feedback.get("reason") or feedback_status),
                        payload={"cycle": cycle, "feedback": feedback},
                    )
                    break
                await self._emit(
                    context,
                    "feedback.submitted",
                    step_id=step["id"],
                    status="completed",
                    message="Post-work feedback submitted.",
                    payload={
                        "cycle": cycle,
                        "store_work_memory": bool(feedback.get("store_work_memory", True)),
                        "has_requested_change": bool(str(feedback.get("requested_change") or "").strip()),
                    },
                )
                try:
                    analysis = await self.strategy_feedback.analyze_feedback(context, feedback)
                except Exception as exc:
                    analysis = {"feedback_type": "no_action", "rework": {"needed": False}, "memory_actions": []}
                    await self._emit(
                        context,
                        "error",
                        step_id=step["id"],
                        status="failed",
                        message=f"Strategy feedback analysis failed: {exc}",
                        payload={"exception": type(exc).__name__, "non_blocking": True},
                    )
                await self._emit(
                    context,
                    "feedback.analyzed",
                    step_id=step["id"],
                    status="completed",
                    message=str(analysis.get("feedback_type") or "no_action"),
                    payload={"cycle": cycle, "analysis": analysis},
                )
                if bool(feedback.get("store_work_memory", True)):
                    memory_source = build_memory_source(context, feedback)
                    memory_actions = analysis.get("memory_actions", [])
                    if not isinstance(memory_actions, list):
                        memory_actions = []
                    memory_result = context.memory_service.apply_strategy_memory_actions(
                        memory_actions,
                        memory_source,
                    )
                    if memory_result.get("stored", 0) == 0 and not memory_actions:
                        fallback = fallback_analysis(feedback)
                        fallback_actions = fallback.get("memory_actions", [])
                        if isinstance(fallback_actions, list) and fallback_actions:
                            fallback_result = context.memory_service.apply_strategy_memory_actions(
                                fallback_actions,
                                memory_source,
                            )
                            memory_result = {
                                **memory_result,
                                "stored": int(memory_result.get("stored", 0))
                                + int(fallback_result.get("stored", 0)),
                                "results": [
                                    *memory_result.get("results", []),
                                    *fallback_result.get("results", []),
                                ],
                                "fallback_used": True,
                            }
                    context.data.setdefault("strategy_memory_updates", []).append(memory_result)
                    await self._emit(
                        context,
                        "memory.updated",
                        step_id=step["id"],
                        status="completed",
                        message=f"Stored {memory_result.get('stored', 0)} strategy memory records.",
                        payload={"cycle": cycle, "result": memory_result},
                    )
                else:
                    await self._emit(
                        context,
                        "memory.updated",
                        step_id=step["id"],
                        status="skipped",
                        message="User unchecked durable strategy-memory storage.",
                        payload={"cycle": cycle},
                    )
                rework = analysis.get("rework") if isinstance(analysis.get("rework"), dict) else {}
                rework_prompt = str(rework.get("prompt") or "").strip()
                if not bool(rework.get("needed")) or not rework_prompt:
                    break
                await self._emit(
                    context,
                    "feedback.rework_requested",
                    step_id=step["id"],
                    status="running",
                    message=rework_prompt[:2000],
                    payload={"cycle": cycle},
                )
                context.data["strategy_rework_prompt"] = rework_prompt
                await self._agent_step(
                    {
                        "id": f"strategy-rework-{cycle}",
                        "name": "Apply feedback rework",
                        "agent": "$resolved_agent",
                    },
                    context,
                )
            context.data["feedback_cycles"] = cycles
            context.data["strategy_feedback_completed"] = True
            return {"hook": hook, "status": "completed"}
        if hook != "post_completion":
            raise ValueError(f"Unknown hook: {hook}")
        # Actual finalization follows the terminal run event so metrics and run.json
        # see the authoritative final state.
        return {"hook": hook, "status": "deferred-until-terminal-event"}

    def _assembled_instructions(self, agent: AgentDefinition, context: RunContext) -> str:
        skill_sections: list[str] = []
        for skill_id, path in zip(agent.skills, agent.skill_paths):
            if skill_id in context.resolved.skills:
                skill_sections.append(f"## Skill: {skill_id}\n{path.read_text(encoding='utf-8').strip()}")
        allowed = list(context.resolved.tools)
        if context.data.get("planning_complete"):
            allowed = [tool for tool in allowed if tool != "web_search"]
        allowed_tools = ", ".join(allowed) or "none"
        validations = "\n".join(f"- {item}" for item in context.resolved.validation_commands) or "- none"
        project_context = context.data.get("project_context", "No project context was collected yet.")
        memory_context = (
            context.memory_service.retrieve_context(context.prompt)
            if context.memory_service is not None
            else ""
        )
        memory_context = memory_context or "No relevant project memory was retrieved."
        messaging = self.messaging.pending(context.agent_id)
        messaging_contract = (
            "Messaging is available through agent-msg. Use `agent-msg send --sender "
            f"{context.agent_id} --recipient <agent-id> --type <message-type> "
            "--payload-json '<json>'`; all messages are durable under "
            f"{self.messaging.root}. Pending inbox files: {len(messaging)}."
        )
        research_contract = ""
        if context.resolved.needs_web_search and not context.data.get("planning_complete"):
            research_contract = (
                "\n\n# External research contract\n"
                "Use current external sources when needed, prefer primary sources, "
                "include source URLs, and label uncertainty or inference clearly."
            )
        research_results = ""
        if agent.id == "agent-implementation-planner" and context.data.get("web_research"):
            research_results = f"\n\n# Planning research results\n{context.data['web_research']}"
        return (
            f"{agent.instructions.strip()}\n\n"
            f"# Runtime contract\nAllowed tools: {allowed_tools}\n"
            f"Validation commands:\n{validations}\n\n"
            f"# Selected project context\n{project_context}\n\n"
            f"# Retrieved project memory\n{memory_context}\n\n"
            f"# Agent messaging\n{messaging_contract}\n\n"
            + "\n\n".join(skill_sections)
            + research_contract
            + research_results
        )

    def _model_for_profile(self, profile: str | None) -> str | None:
        """Return the configured model for legacy runtime callers."""
        return self.registry.codex_options_for_profile(profile)["model"]

    def _step_prompt(self, step: Mapping[str, Any], context: RunContext) -> str:
        prompt = (
            f"User request:\n{context.prompt}\n\n"
            f"Current workflow step: {step.get('name', step.get('id'))}\n"
            "Complete this step within the runtime contract. Report created or changed file paths clearly."
        )
        if step.get("id") == "plan":
            prompt += (
                "\n\nReturn a JSON object matching "
                "`agent-config/agents/agent-implementation-planner/plan.schema.json`. "
                "Choose the most suitable execution workflow in the `workflow_id` field. "
                "Available execution workflows: "
                + ", ".join(sorted(self.registry.execution_workflow_ids()))
            )
        elif context.data.get("planned_tasks_handoff"):
            prompt += "\n\n" + str(context.data["planned_tasks_handoff"])
        if str(step.get("id", "")).startswith("strategy-rework"):
            prompt += (
                "\n\nPost-work feedback rework request:\n"
                + str(context.data.get("strategy_rework_prompt", "")).strip()
            )
        return prompt

    def _resolve_command(self, raw: Any, context: RunContext) -> str:
        if not isinstance(raw, str) or not raw:
            raise ValueError("Shell step command must be a non-empty string")
        validation = self.registry.project_config.get("validation", {})
        if raw.startswith("$validation."):
            key = raw.removeprefix("$validation.")
            value = validation.get(key) if isinstance(validation, dict) else None
            if not isinstance(value, str) or not value:
                raise ValueError(f"Missing validation command: {key}")
            if value not in context.resolved.validation_commands:
                raise PermissionError(f"Validation command '{key}' was not resolved for this run")
            return value
        if raw not in context.resolved.validation_commands:
            raise PermissionError("Workflow shell commands must come from resolved validation policy")
        return raw

    @staticmethod
    def _normalize_codex(raw: Mapping[str, Any]) -> list[tuple[str, str | None, dict[str, Any]]]:
        """Translate App Server notifications into the runtime's stable event schema.

        Raw App Server objects deliberately stop here. Consumers only see the
        small, flat fields below, which lets the protocol evolve independently
        from the event log and client state model.
        """
        method = str(raw.get("method", ""))
        params = dict(raw.get("params") or {})
        item = params.get("item") if isinstance(params.get("item"), dict) else {}
        item_type = str(item.get("type", ""))
        if method == "item/agentMessage/delta":
            delta = str(params.get("delta", ""))
            return [("agent.message.delta", delta, {"delta": delta})]
        if method == "item/completed" and item_type == "agentMessage":
            text = item.get("text") or item.get("content")
            content = str(text) if text else ""
            return [("agent.message.completed", content or None, {
                "item_id": str(item.get("id", "")),
                "text": content,
            })]
        if method == "item/started" and item_type == "commandExecution":
            return [("tool.started", None, AgentRuntime._command_payload(item))]
        if method == "item/commandExecution/outputDelta":
            output = str(params.get("delta", ""))
            return [("tool.progress", output or None, {
                "tool": "shell",
                "tool_id": str(params.get("itemId", "")),
                "output": output,
            })]
        if method == "item/completed" and item_type == "commandExecution":
            failed = item.get("status") == "failed" or item.get("exitCode") not in (None, 0)
            payload = AgentRuntime._command_payload(item)
            payload.update(
                output=str(item.get("aggregatedOutput") or ""),
                exit_code=item.get("exitCode"),
                duration_ms=item.get("durationMs"),
            )
            return [("tool.failed" if failed else "tool.completed", None, payload)]
        if method == "item/started" and item_type == "mcpToolCall":
            return [("tool.started", None, AgentRuntime._mcp_payload(item))]
        if method == "item/mcpToolCall/progress":
            message = str(params.get("message", ""))
            return [("tool.progress", message or None, {
                "tool": "mcp",
                "tool_id": str(params.get("itemId", "")),
                "message": message,
            })]
        if method == "item/completed" and item_type == "mcpToolCall":
            payload = AgentRuntime._mcp_payload(item)
            failed = item.get("status") == "failed" or bool(item.get("error"))
            error = item.get("error")
            if isinstance(error, Mapping):
                payload["error"] = str(error.get("message", ""))
            result = item.get("result")
            if isinstance(result, Mapping):
                payload["output"] = str(result.get("structuredContent") or result.get("content") or "")
            return [("tool.failed" if failed else "tool.completed", payload.get("error"), payload)]
        if method == "item/fileChange/outputDelta":
            output = str(params.get("delta", ""))
            return [("file.changed", output or None, {
                "file_id": str(params.get("itemId", "")),
                "output": output,
            })]
        if method == "item/fileChange/patchUpdated":
            diff = str(params.get("patch") or params.get("diff") or params.get("delta") or "")
            return [("file.changed", None, {
                "file_id": str(params.get("itemId", "")),
                "path": str(params.get("path", "")),
                "diff": diff,
            })]
        if method == "item/completed" and item_type == "fileChange":
            changes = item.get("changes") or [item]
            events: list[tuple[str, str | None, dict[str, Any]]] = []
            for change in changes:
                if not isinstance(change, dict):
                    continue
                path = str(change.get("path", "unknown"))
                kind = str(change.get("kind") or item.get("kind") or "file")
                payload = {
                    "file_id": str(item.get("id", "")),
                    "path": path,
                    "kind": kind,
                    "diff": str(change.get("diff") or ""),
                }
                events.append(("file.changed", None, payload))
                if kind.casefold() in {
                    "add",
                    "added",
                    "create",
                    "created",
                    "generate",
                    "generated",
                }:
                    events.append(
                        (
                            "artifact.created",
                            None,
                            {"path": path, "kind": kind},
                        )
                    )
            return events
        if method == "turn/diff/updated":
            return [("artifact.created", None, {
                "path": "turn.diff",
                "kind": "diff",
                "diff": str(params.get("diff", "")),
            })]
        if method == "thread/tokenUsage/updated":
            usage = params.get("tokenUsage") if isinstance(params.get("tokenUsage"), Mapping) else {}
            total = usage.get("total") if isinstance(usage.get("total"), Mapping) else {}
            last = usage.get("last") if isinstance(usage.get("last"), Mapping) else {}
            fields = {
                "input_tokens": "inputTokens",
                "cached_input_tokens": "cachedInputTokens",
                "cache_write_input_tokens": "cacheWriteInputTokens",
                "output_tokens": "outputTokens",
                "reasoning_output_tokens": "reasoningOutputTokens",
                "total_tokens": "totalTokens",
            }
            payload = {stable: total.get(protocol, 0) for stable, protocol in fields.items()}
            payload.update({f"last_{stable}": last.get(protocol, 0) for stable, protocol in fields.items()})
            payload["context_window"] = usage.get("modelContextWindow")
            return [("agent.usage.updated", None, payload)]
        if method == "turn/completed":
            turn = params.get("turn") or {}
            status = turn.get("status")
            if status == "failed":
                error = turn.get("error") if isinstance(turn.get("error"), Mapping) else {}
                message = str(error.get("message", "Codex turn failed"))
                return [("error", message, {"turn_id": str(turn.get("id", "")), "error": message})]
            return []
        if "approval" in method.casefold():
            approval_status = str(params.get("status") or "pending")
            policy = str(params.get("approvalPolicy") or "")
            message = (
                "Approval automatically accepted by local policy"
                if approval_status == "accepted"
                else "Approval decision required"
            )
            return [(
                "tool.started",
                message,
                {
                    "tool": "approval",
                    "status": approval_status,
                    "approval_policy": policy,
                    "request_id": params.get("requestId"),
                    "request_method": str(params.get("requestMethod") or ""),
                },
            )]
        return []

    @staticmethod
    def _command_payload(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "tool": "shell",
            "tool_id": str(item.get("id", "")),
            "command": str(item.get("command", "")),
            "cwd": str(item.get("cwd", "")),
            "status": str(item.get("status", "")),
        }

    @staticmethod
    def _mcp_payload(item: Mapping[str, Any]) -> dict[str, Any]:
        server = str(item.get("server", ""))
        name = str(item.get("tool", ""))
        return {
            "tool": "mcp",
            "tool_id": str(item.get("id", "")),
            "name": f"{server}/{name}" if server and name else name or server,
            "status": str(item.get("status", "")),
            "duration_ms": item.get("durationMs"),
        }

    def _write_session(
        self,
        context: RunContext,
        status: str,
        *,
        error: str | None = None,
    ) -> None:
        metadata: dict[str, Any] = {
            "status": status,
            "last_run_id": context.run_id,
            "agent_id": context.agent_id,
        }
        thread_id = context.data.get("codex_thread_id")
        if thread_id:
            metadata["codex_thread_id"] = thread_id
        if error:
            metadata["error"] = error
        self.events.write_session(context.session_id, metadata)

    async def _emit(
        self,
        context: RunContext,
        event_type: str,
        *,
        agent_id: str | None = None,
        step_id: str | None = None,
        status: str | None = None,
        message: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = await self.events.emit(
            self.events.new_event(
                event_type,
                run_id=context.run_id,
                session_id=context.session_id,
                agent_id=agent_id or context.agent_id,
                step_id=step_id,
                status=status,
                message=message,
                payload=dict(payload or {}),
            )
        )
        self._record_error_alert(event)
        return event

    def _record_error_alert(self, event: RuntimeEvent) -> None:
        """Mirror runtime errors into the messaging error tracker."""
        if event.type not in ERROR_EVENT_TYPES:
            return
        try:
            self.messaging.record_error(event.to_dict())
        except Exception as error:
            logger.warning("Could not record runtime error alert: %s", error)
