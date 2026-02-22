"""Pydantic models for the /plan endpoint request and response."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ── Request ──────────────────────────────────────────────────────────────────

class Constraints(BaseModel):
    max_speed: float = 0.5
    allowed_z_min: float = 0.0
    allowed_z_max: float = 1.0


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, examples=["Pick the object and place it in bin A"])
    constraints: Constraints = Field(default_factory=Constraints)


# ── Response ─────────────────────────────────────────────────────────────────

class StepType(str, Enum):
    MOVE = "MOVE"
    GRASP = "GRASP"
    RELEASE = "RELEASE"
    WAIT = "WAIT"


class Pose(BaseModel):
    x: float
    y: float
    z: float
    qx: float = 0.0
    qy: float = 0.0
    qz: float = 0.0
    qw: float = 1.0


class PlanStep(BaseModel):
    type: StepType
    target_pose: Optional[Pose] = None
    speed: float = 0.0
    notes: str = ""


class Safety(BaseModel):
    assumptions: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)


class PlanResponse(BaseModel):
    plan_id: str
    steps: list[PlanStep] = Field(..., min_length=1)
    safety: Safety = Field(default_factory=Safety)


# ── Orchestrator ─────────────────────────────────────────────────────────────

class AttemptDetail(BaseModel):
    attempt: int
    violations: list[str] = Field(default_factory=list)
    passed: bool


class OrchestratorRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    constraints: Constraints = Field(default_factory=Constraints)


class OrchestratorResult(BaseModel):
    plan: PlanResponse
    passed_safety: bool
    passed_on_attempt: int = Field(
        ..., description="1 or 2 if accepted, 0 if both attempts failed"
    )
    attempts: list[AttemptDetail]
    states_visited: list[str]
