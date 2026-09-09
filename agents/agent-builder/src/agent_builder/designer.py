from __future__ import annotations

import re

from .models import AgentBuildRequest, AgentDesign


_NON_SLUG = re.compile(r"[^a-z0-9]+")


def normalize_agent_id(name: str) -> str:
    normalized = _NON_SLUG.sub("-", name.lower()).strip("-")
    while normalized.startswith("agent-agent-"):
        normalized = normalized[len("agent-"):]
    if not normalized.startswith("agent-"):
        normalized = f"agent-{normalized}"
    return normalized


class AgentDesigner:
    """Deterministic V1 designer.

    This gives the project a working baseline without requiring a nested LLM call.
    A future `CodexDesignEnhancer` can refine this structured object while keeping
    validation and filesystem writes unchanged.
    """

    def design(self, request: AgentBuildRequest) -> AgentDesign:
        agent_id = normalize_agent_id(request.name)
        responsibilities = request.responsibilities or [
            f"Own tasks directly related to: {request.purpose.rstrip('.')}",
            "Inspect existing implementation and reusable shared capabilities before creating new abstractions.",
            "Validate changes before reporting task completion.",
        ]

        workflow = [
            "Understand the request and identify the minimum required scope.",
            "Load only relevant project context, skills, and files.",
            "Inspect existing implementation and decide whether reuse is possible.",
            "Implement the smallest complete change.",
            "Run available validation/tests or clearly report why validation could not run.",
            "Summarize changes, evidence, and any remaining risk.",
        ]
        if request.preferred_workflow:
            workflow.insert(1, f"Honor this preferred workflow when compatible: {request.preferred_workflow}")

        skills = list(dict.fromkeys(["repository-navigation", "safe-file-editing", *request.required_skills]))
        restrictions = list(dict.fromkeys([
            "Do not modify unrelated projects or agents unless explicitly required by the task.",
            "Do not duplicate shared Agent Gateway behavior inside this agent.",
            *request.restrictions,
        ]))

        return AgentDesign(
            agent_id=agent_id,
            purpose=request.purpose,
            description=f"Dedicated monorepo agent for {request.purpose.rstrip('.').lower()}.",
            context=request.context,
            responsibilities=responsibilities,
            workflow_steps=workflow,
            skills=skills,
            restrictions=restrictions,
            filesystem_read=["."],
            filesystem_write=["."],
            shell=True,
            network="controlled",
            evaluation_requirements=[
                "task_completed",
                "scope_respected",
                "validation_attempted",
                "no_unnecessary_changes",
                "existing_patterns_reused_when_appropriate",
            ],
        )
