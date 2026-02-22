"""
FastAPI service that bridges ROS2 cell state with an LLM planner.

Run:
    uvicorn cell_sim.api.app:app --host 0.0.0.0 --port 8000

Logging goes to both stderr and LOG_FILE (default: /tmp/cell_sim_api.log).

Production tracing / metrics notes (see docstrings at module bottom).
"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from cell_sim.api.models import (
    PlanRequest, PlanResponse, PlanStep, Safety,
    OrchestratorRequest, OrchestratorResult,
)
from cell_sim.api.ros2_bridge import ROS2Bridge
from cell_sim.api import llm_client

# ── Logging ──────────────────────────────────────────────────────────────────

LOG_FILE = os.getenv(
    "LOG_FILE",
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "task2_test.log"),
)
LOG_FILE = os.path.abspath(LOG_FILE)

_fmt = logging.Formatter(
    "%(asctime)s  %(levelname)-8s  %(name)-28s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_file_handler = logging.FileHandler(LOG_FILE, mode="w")
_file_handler.setFormatter(_fmt)

_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(_fmt)

logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _stream_handler])
logger = logging.getLogger("cell_sim.api")

# ── ROS2 bridge singleton ───────────────────────────────────────────────────

_bridge: ROS2Bridge | None = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    global _bridge
    logger.info("Starting ROS2 bridge …")
    _bridge = ROS2Bridge()
    logger.info("FastAPI ready — LOG_FILE=%s", LOG_FILE)
    yield
    logger.info("Shutting down ROS2 bridge …")
    _bridge.shutdown()
    _bridge = None


app = FastAPI(
    title="Robot Cell Planner API",
    version="0.1.0",
    lifespan=lifespan,
)


# ── Prompt builder ───────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a robot-cell planning assistant.
Given a user GOAL, CONSTRAINTS, and the current CELL STATE, output a JSON
action plan. Output ONLY valid JSON — no markdown fences, no explanation.

Required JSON schema:
{{
  "plan_id": "<uuid string>",
  "steps": [
    {{
      "type": "MOVE|GRASP|RELEASE|WAIT",
      "target_pose": {{"x":0,"y":0,"z":0,"qx":0,"qy":0,"qz":0,"qw":1}} or null,
      "speed": <float>,
      "notes": "<string>"
    }}
  ],
  "safety": {{
    "assumptions": ["..."],
    "checks": ["..."]
  }}
}}

Rules:
- type must be one of MOVE, GRASP, RELEASE, WAIT.
- target_pose may be null for GRASP, RELEASE, or WAIT.
- speed must respect max_speed from constraints.
- z values in target_pose must stay within allowed_z_min..allowed_z_max.
"""


def _build_prompt(
    goal: str,
    constraints: dict,
    cell_state: dict,
    plan_id: str,
) -> str:
    return (
        f"{_SYSTEM_PROMPT}\n"
        f"GOAL: {goal}\n\n"
        f"CONSTRAINTS: {json.dumps(constraints)}\n\n"
        f"CELL STATE: {json.dumps(cell_state)}\n\n"
        f"Use plan_id = \"{plan_id}\"\n"
    )


def _build_repair_prompt(original_prompt: str, bad_output: str, error: str) -> str:
    return (
        f"{original_prompt}\n\n"
        f"--- YOUR PREVIOUS OUTPUT WAS INVALID ---\n"
        f"Output: {bad_output[:1000]}\n"
        f"Error:  {error}\n\n"
        f"Fix the JSON and output ONLY the corrected JSON.\n"
    )


# ── JSON extraction helper ──────────────────────────────────────────────────

_JSON_BLOCK = re.compile(r"```(?:json)?\s*([\s\S]*?)```")


def _extract_json(raw: str) -> dict:
    """Try to pull a JSON object out of the LLM response text."""
    match = _JSON_BLOCK.search(raw)
    text = match.group(1).strip() if match else raw.strip()
    return json.loads(text)


# ── Endpoint ─────────────────────────────────────────────────────────────────

@app.post("/plan", response_model=PlanResponse)
async def generate_plan(req: PlanRequest):
    request_id = uuid.uuid4().hex[:12]
    plan_id = str(uuid.uuid4())
    logger.info("[%s] POST /plan  goal=%r", request_id, req.goal)

    # 1) Fetch cell state from ROS2
    try:
        cell_state = await _bridge.get_cell_state(timeout_sec=5.0)
        logger.info("[%s] Cell state fetched: %s", request_id, json.dumps(cell_state))
    except Exception as exc:
        logger.error("[%s] ROS2 bridge error: %s", request_id, exc)
        raise HTTPException(status_code=503, detail=f"ROS2 state unavailable: {exc}")

    # 2) Build prompt
    constraints_dict = req.constraints.model_dump()
    prompt = _build_prompt(req.goal, constraints_dict, cell_state, plan_id)
    logger.info("[%s] Prompt built (%d chars)", request_id, len(prompt))

    # 3) Call LLM  →  4) Validate  →  5) Retry / fallback
    raw_output = ""
    for phase in ("initial", "repair"):
        try:
            if phase == "initial":
                raw_output = await llm_client.call_llm(prompt, request_id)
            else:
                repair_prompt = _build_repair_prompt(prompt, raw_output, last_error)
                raw_output = await llm_client.call_llm(repair_prompt, request_id)

            logger.info("[%s] LLM raw (%s): %s", request_id, phase, raw_output[:300])
            parsed = _extract_json(raw_output)
            parsed["plan_id"] = plan_id  # enforce our plan_id
            plan = PlanResponse.model_validate(parsed)
            logger.info(
                "[%s] Plan validated — %d steps, plan_id=%s",
                request_id, len(plan.steps), plan.plan_id,
            )
            return plan

        except Exception as exc:
            last_error = str(exc)
            logger.warning("[%s] Validation failed (%s): %s", request_id, phase, last_error)
            if phase == "repair":
                break

    # 5-b) Deterministic fallback
    logger.warning("[%s] Using deterministic fallback plan", request_id)
    fallback = llm_client.deterministic_fallback()
    fallback["plan_id"] = plan_id
    return PlanResponse.model_validate(fallback)


# ── Orchestrator endpoint ────────────────────────────────────────────────────

@app.post("/orchestrate", response_model=OrchestratorResult)
async def orchestrate(req: OrchestratorRequest):
    from cell_sim.api.orchestrator import run_orchestrator

    request_id = uuid.uuid4().hex[:12]
    logger.info("[%s] POST /orchestrate  goal=%r  constraints=%s",
                request_id, req.goal, req.constraints.model_dump())

    try:
        cell_state = await _bridge.get_cell_state(timeout_sec=5.0)
        logger.info("[%s] Cell state fetched for orchestrator", request_id)
    except Exception as exc:
        logger.error("[%s] ROS2 bridge error: %s", request_id, exc)
        raise HTTPException(status_code=503, detail=f"ROS2 state unavailable: {exc}")

    result = await run_orchestrator(
        goal=req.goal,
        constraints=req.constraints,
        cell_state=cell_state,
        request_id=request_id,
    )
    logger.info(
        "[%s] Orchestrator done — passed_safety=%s  attempt=%d  states=%s",
        request_id, result.passed_safety, result.passed_on_attempt,
        " → ".join(result.states_visited),
    )
    return result


# ── Health endpoint ──────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Programmatic entry-point ─────────────────────────────────────────────────

def start_server():
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    start_server()


# ── Production tracing / metrics guidance ────────────────────────────────────
#
# In a production deployment we would instrument this service at three layers:
#
# 1. REQUEST-LEVEL TRACING  (middleware)
#    - Add an OpenTelemetry / Jaeger middleware to FastAPI so every HTTP
#      request gets a trace-id that propagates through the ROS2 bridge call
#      and the LLM call.  FastAPI: app.add_middleware(TraceMiddleware).
#
# 2. LLM CALL METRICS  (in llm_client.py, around each provider call)
#    - Histogram: llm_latency_seconds  (labels: provider, model, attempt)
#    - Counter:   llm_calls_total       (labels: provider, status)
#    - Counter:   llm_retries_total
#    - These would be exposed via a /metrics endpoint (prometheus_client).
#
# 3. ROS2 BRIDGE METRICS  (in ros2_bridge.py)
#    - Histogram: ros2_service_latency_seconds
#    - Counter:   ros2_service_errors_total
#    - Gauge:     ros2_bridge_connected  (1/0)
#
# Structured JSON logging (e.g. structlog) with request_id / plan_id
# attached to every log line completes the observability stack.
