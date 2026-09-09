from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class RuntimeConfig(BaseModel):
    provider: Literal["codex", "openai-agents"] = "codex"
    model: str | None = None
    sandbox: Literal["read-only", "workspace-write", "full-access"] = "workspace-write"
    workspace: str = "agents"


class PermissionConfig(BaseModel):
    filesystem_read: list[str] = Field(default_factory=lambda: ["agents"])
    filesystem_write: list[str] = Field(default_factory=list)
    shell: bool = True
    network: Literal["controlled", "disabled", "allowed"] = "controlled"


class AgentSpec(BaseModel):
    id: str
    disabled: bool = False
    version: str = "0.1.0"
    description: str
    purpose: str
    instructions_file: str = "AGENT.md"
    skills_file: str = "skills.yaml"
    evals_file: str = "evals.yaml"
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    permissions: PermissionConfig = Field(default_factory=PermissionConfig)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        if not value.startswith("agent-"):
            raise ValueError("Agent id must start with 'agent-'.")
        allowed = set("abcdefghijklmnopqrstuvwxyz0123456789-")
        if not value or any(char not in allowed for char in value):
            raise ValueError("Agent id may contain lowercase letters, digits, and hyphens only.")
        return value


class LoadedAgent(BaseModel):
    spec: AgentSpec
    root: Path
    instructions: str
    skills: list[str] = Field(default_factory=list)
    evaluations: dict = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class AgentRunResult(BaseModel):
    run_id: str
    agent_id: str
    session_id: str | None = None
    status: Literal["completed", "failed"]
    final_response: str = ""
    token_usage: dict | None = None
    error: str | None = None
