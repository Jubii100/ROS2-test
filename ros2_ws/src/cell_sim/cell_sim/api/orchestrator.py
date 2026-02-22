"""
Multi-step orchestrator with an explicit state machine.

States
------
PLANNING       → call LLM to produce a plan
SAFETY_CHECK   → run deterministic constraint validation
REPLANNING     → re-call LLM with rejection reasons appended
ACCEPTED       → plan passed safety
REJECTED       → both attempts failed; deterministic fallback used

Transitions
-----------
PLANNING  ──▶  SAFETY_CHECK
SAFETY_CHECK ──(pass)──▶ ACCEPTED
SAFETY_CHECK ──(fail, attempt 1)──▶ REPLANNING
SAFETY_CHECK ──(fail, attempt 2)──▶ REJECTED
REPLANNING ──▶ SAFETY_CHECK
"""

from __future__ import annotations

import json
import logging
import uuid
from enum import Enum

from cell_sim.api.models import (
    Constraints,
    PlanResponse,
    OrchestratorResult,
    AttemptDetail,
)
from cell_sim.api.safety import validate_plan
from cell_sim.api import llm_client
from cell_sim.api.app import _build_prompt, _extract_json

logger = logging.getLogger(__name__)


class State(str, Enum):
    PLANNING = "PLANNING"
    SAFETY_CHECK = "SAFETY_CHECK"
    REPLANNING = "REPLANNING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


def _build_replan_prompt(
    base_prompt: str,
    violations: list[str],
) -> str:
    block = "\n".join(f"  • {v}" for v in violations)
    return (
        f"{base_prompt}\n\n"
        f"--- SAFETY REJECTION (your previous plan was rejected) ---\n"
        f"Violations found:\n{block}\n\n"
        f"Generate a CORRECTED plan that fixes every violation.\n"
        f"Output ONLY valid JSON.\n"
    )


async def run_orchestrator(
    goal: str,
    constraints: Constraints,
    cell_state: dict,
    request_id: str,
) -> OrchestratorResult:
    """Execute the plan → check → replan state machine."""

    plan_id = str(uuid.uuid4())
    constraints_dict = constraints.model_dump()
    base_prompt = _build_prompt(goal, constraints_dict, cell_state, plan_id)

    state = State.PLANNING
    attempt = 0
    current_plan: PlanResponse | None = None
    attempts: list[AttemptDetail] = []
    states_visited: list[str] = []

    while True:
        states_visited.append(state.value)
        logger.info("[%s] State → %s  (attempt %d)", request_id, state.value, attempt)

        # ── PLANNING ─────────────────────────────────────────────────────
        if state == State.PLANNING:
            attempt = 1
            try:
                raw = await llm_client.call_llm(base_prompt, request_id)
                parsed = _extract_json(raw)
                parsed["plan_id"] = plan_id
                current_plan = PlanResponse.model_validate(parsed)
                logger.info("[%s] Plan parsed — %d steps", request_id, len(current_plan.steps))
            except Exception as exc:
                logger.error("[%s] Planning failed: %s", request_id, exc)
                current_plan = PlanResponse.model_validate(
                    {**llm_client.deterministic_fallback(), "plan_id": plan_id}
                )
            state = State.SAFETY_CHECK

        # ── SAFETY_CHECK ─────────────────────────────────────────────────
        elif state == State.SAFETY_CHECK:
            violations = validate_plan(current_plan, constraints)
            attempts.append(AttemptDetail(
                attempt=attempt,
                violations=violations,
                passed=len(violations) == 0,
            ))

            if not violations:
                state = State.ACCEPTED
            elif attempt >= 2:
                state = State.REJECTED
            else:
                state = State.REPLANNING

        # ── REPLANNING ───────────────────────────────────────────────────
        elif state == State.REPLANNING:
            attempt = 2
            replan_prompt = _build_replan_prompt(base_prompt, violations)
            try:
                raw = await llm_client.call_llm(replan_prompt, request_id)
                parsed = _extract_json(raw)
                parsed["plan_id"] = plan_id
                current_plan = PlanResponse.model_validate(parsed)
                logger.info("[%s] Replan parsed — %d steps", request_id, len(current_plan.steps))
            except Exception as exc:
                logger.error("[%s] Replanning failed: %s", request_id, exc)
                current_plan = PlanResponse.model_validate(
                    {**llm_client.deterministic_fallback(), "plan_id": plan_id}
                )
            state = State.SAFETY_CHECK

        # ── ACCEPTED ─────────────────────────────────────────────────────
        elif state == State.ACCEPTED:
            states_visited.append(state.value)
            logger.info(
                "[%s] Plan ACCEPTED on attempt %d", request_id, attempt
            )
            return OrchestratorResult(
                plan=current_plan,
                passed_safety=True,
                passed_on_attempt=attempt,
                attempts=attempts,
                states_visited=states_visited,
            )

        # ── REJECTED ─────────────────────────────────────────────────────
        elif state == State.REJECTED:
            states_visited.append(state.value)
            logger.warning(
                "[%s] Plan REJECTED after %d attempts — using safe fallback",
                request_id, attempt,
            )
            fallback = llm_client.deterministic_fallback()
            fallback["plan_id"] = plan_id
            # Clamp fallback speeds to guarantee safety
            for step in fallback["steps"]:
                if step["speed"] > constraints.max_speed:
                    step["speed"] = constraints.max_speed
                if step.get("target_pose") and step["target_pose"] is not None:
                    z = step["target_pose"]["z"]
                    step["target_pose"]["z"] = max(
                        constraints.allowed_z_min,
                        min(z, constraints.allowed_z_max),
                    )
            safe_plan = PlanResponse.model_validate(fallback)
            return OrchestratorResult(
                plan=safe_plan,
                passed_safety=False,
                passed_on_attempt=0,
                attempts=attempts,
                states_visited=states_visited,
            )
