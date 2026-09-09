from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import AgentBuildRequest, AgentBuildResult, AgentDesign
from .service import AgentBuilderService


app = FastAPI(title="Monorepo Agent Builder", version="0.1.0")

# Local-development UI origins only. Production deployments should replace this
# with the actual trusted UI origin(s).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


def _find_root() -> Path:
    configured = os.environ.get("MONOREPO_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()

    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "project-registry.yaml").is_file() and (candidate / "agents").is_dir():
            return candidate
    raise RuntimeError("Set MONOREPO_ROOT or start the API from inside the monorepo.")


def _service() -> AgentBuilderService:
    return AgentBuilderService(_find_root())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/agents")
def list_agents() -> dict[str, list[str]]:
    return {"agents": _service().gateway.list_agents()}


@app.post("/v1/agents/preview", response_model=AgentDesign)
def preview_agent(request: AgentBuildRequest) -> AgentDesign:
    try:
        return _service().preview(request)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/agents/build", response_model=AgentBuildResult)
def build_agent(request: AgentBuildRequest) -> AgentBuildResult:
    try:
        return _service().build(request)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
