"""
Deterministic safety gate for robot cell plans.

Every check here is hard-coded logic — never delegated to an LLM.
This is the last line of defence before a plan reaches the real robot.
"""

from __future__ import annotations

import logging

from cell_sim.api.models import Constraints, PlanResponse, StepType

logger = logging.getLogger(__name__)


def validate_plan(plan: PlanResponse, constraints: Constraints) -> list[str]:
    """
    Return a list of human-readable violation strings.
    Empty list ⇒ plan is safe.
    """
    violations: list[str] = []

    for idx, step in enumerate(plan.steps, start=1):
        # ── Speed check (applies to every step that specifies speed) ─────
        if step.speed > constraints.max_speed:
            violations.append(
                f"Step {idx} ({step.type.value}): speed {step.speed} "
                f"exceeds max_speed {constraints.max_speed}"
            )

        # ── Z-bound check (applies to every step with a target_pose) ─────
        if step.target_pose is not None:
            z = step.target_pose.z
            if z < constraints.allowed_z_min:
                violations.append(
                    f"Step {idx} ({step.type.value}): target z={z} "
                    f"below allowed_z_min {constraints.allowed_z_min}"
                )
            if z > constraints.allowed_z_max:
                violations.append(
                    f"Step {idx} ({step.type.value}): target z={z} "
                    f"above allowed_z_max {constraints.allowed_z_max}"
                )

        # ── MOVE must have a target_pose ─────────────────────────────────
        if step.type == StepType.MOVE and step.target_pose is None:
            violations.append(
                f"Step {idx} (MOVE): missing target_pose"
            )

    if violations:
        logger.warning("Safety gate found %d violation(s):", len(violations))
        for v in violations:
            logger.warning("  • %s", v)
    else:
        logger.info("Safety gate: all checks passed")

    return violations
