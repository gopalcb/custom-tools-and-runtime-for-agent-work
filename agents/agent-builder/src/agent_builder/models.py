from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AgentBuildRequest(BaseModel):
    name: str
    purpose: str
    context: str = ""
    preferred_workflow: str | None = None
    responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    restrictions: list[str] = Field(default_factory=list)
    overwrite: bool = False

    @field_validator("name", "purpose")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be blank.")
        return value.strip()


class AgentDesign(BaseModel):
    agent_id: str
    purpose: str
    description: str
    context: str = ""
    responsibilities: list[str]
    workflow_steps: list[str]
    skills: list[str]
    restrictions: list[str]
    filesystem_read: list[str]
    filesystem_write: list[str]
    shell: bool = True
    network: str = "controlled"
    evaluation_requirements: list[str]


class AgentBuildResult(BaseModel):
    agent_id: str
    path: str
    created_files: list[str]
    message: str
