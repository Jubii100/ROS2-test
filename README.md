# ROS2 Robot Cell — AI-Powered Motion Planner

A ROS2-based robot cell simulation with a strict architectural boundary between the **LLM "Brain"** (planning, reasoning, replanning) and the **Robot "Nervous System"** (sensing, state management, safety enforcement, actuation). The two domains communicate through a narrow, validated interface — no LLM output ever reaches the robot without passing through a deterministic safety gate.

---

## Test Results — All 4 Tasks Passed

Everything below was produced by a **single command** (`bash run_tests.sh`) that launches the full system from scratch — ROS2 nodes, FastAPI server, Anthropic LLM — runs every test, and tears down on exit. No manual steps, no separate terminals, no pre-existing processes.

```
╔══════════════════════════════════════════════════════════════════════╗
║  ✓  ALL 4 TASKS PASSED — 2026-02-22 15:16:06                      ║
║  LLM: anthropic claude-sonnet-4-20250514 (real API calls)          ║
║  Safety: speed + z-bound constraints verified with real LLM         ║
╚══════════════════════════════════════════════════════════════════════╝
```

| Task | Description | Result |
|------|-------------|--------|
| **Task 1** | ROS2 basics: topics, services, sensor simulation | **PASSED** |
| **Task 2** | FastAPI + ROS2 bridge + Anthropic LLM call | **PASSED** |
| **Task 3** | Multi-agent orchestration + deterministic safety gate | **PASSED** |
| **Task 4** | Docker deployment design + cost/latency monitoring | **PASSED** |

### Task 1 — ROS2 Basics (Nervous System)

```
✓ TASK 1 — ALL CHECKS PASSED
```

Verified live by `run_tests.sh`:

```
Active ROS2 nodes:   /sensor_sim_node, /cell_state_node, /api_bridge_node
Topics:              /perception/object_pose, /cell/state
Services:            /cell/get_state

ros2 service call /cell/get_state std_srvs/srv/Trigger "{}"
→ success=True, message='{"timestamp":"...","object_pose":{"x":0.097715,"y":-0.021253,"z":0.05,...},"frame_id":"world"}'
```

### Task 2 — API + LLM Call (Brain ↔ Nervous System)

```
✓ TASK 2 — ALL CHECKS PASSED
```

```
POST /plan → Anthropic Claude → 7-step pick-and-place plan
  LLM response in 10.32s
  Anthropic usage: tokens_in=446  tokens_out=760  est_cost=$0.012738
```

### Task 3 — Orchestrator + Safety Gate (Brain with Deterministic Guard)

```
✓ TASK 3 — ALL CHECKS PASSED
```

| Test | Constraint | Attempt 1 | Attempt 2 | Result |
|------|-----------|-----------|-----------|--------|
| 3a — generous | max_speed=0.5, z_max=1.0 | PASS | — | `passed_on_attempt: 1` |
| 3b — tight speed | max_speed=0.2, z_max=1.0 | PASS | — | `passed_on_attempt: 1` |
| **3c — z-bound** | **z_max=0.08, goal demands z=0.5** | **REJECTED** | **CORRECTED** | **`passed_on_attempt: 2`** |
| 3d — tight z | z_max=0.03 | PASS | — | `passed_on_attempt: 1` |

### Task 4 — Deployment & Anthropic Cost/Latency Metrics

```
✓ TASK 4 — ALL CHECKS PASSED
```

| Request ID | Latency | Tokens in | Tokens out | Est. Cost |
|------------|---------|-----------|------------|-----------|
| 6f76e2fa | 10.32s | 446 | 760 | $0.0127 |
| c8c6d45c | 9.78s | 446 | 757 | $0.0127 |
| 6fdafb14 | 9.02s | 446 | 756 | $0.0127 |
| 75c23fe2 (plan) | 5.24s | 495 | 285 | $0.0058 |
| 75c23fe2 (replan) | 5.30s | 561 | 281 | $0.0059 |
| f9715f9d | 6.54s | 453 | 405 | $0.0074 |
| **Total (6 calls)** | **~46s** | **2,847** | **3,244** | **$0.057** |

---

## Actual Logs — Full Evidence

### Z-Bound Violation → Rejection → Correction (Task 3c)

The LLM was instructed to plan for `z=0.5`, but constraints set `allowed_z_max=0.08`. The safety gate caught it on attempt 1 and the LLM corrected on attempt 2. Extracted from `ros2_ws/api_server.log`:

```
[75c23fe2059c] State → PLANNING  (attempt 0)
[75c23fe2059c] LLM call attempt 1/2  provider=anthropic
  Anthropic usage  model=claude-sonnet-4-20250514  tokens_in=495  tokens_out=285  est_cost=$0.005760
[75c23fe2059c] LLM response in 5.24s  provider=anthropic
[75c23fe2059c] Plan parsed — 2 steps
[75c23fe2059c] State → SAFETY_CHECK  (attempt 1)
  Safety gate found 1 violation(s):
    • Step 1 (MOVE): target z=0.5 above allowed_z_max 0.08          ← CAUGHT
[75c23fe2059c] State → REPLANNING  (attempt 1)
[75c23fe2059c] LLM call attempt 1/2  provider=anthropic
  Anthropic usage  model=claude-sonnet-4-20250514  tokens_in=561  tokens_out=281  est_cost=$0.005898
[75c23fe2059c] LLM response in 5.30s  provider=anthropic
[75c23fe2059c] Replan parsed — 2 steps
[75c23fe2059c] State → SAFETY_CHECK  (attempt 2)
  Safety gate: all checks passed                                     ← FIXED
[75c23fe2059c] State → ACCEPTED  (attempt 2)
[75c23fe2059c] Plan ACCEPTED on attempt 2
Orchestrator done — passed_safety=True  attempt=2
  states=PLANNING → SAFETY_CHECK → REPLANNING → SAFETY_CHECK → ACCEPTED
```

### API Server Startup + Full Call Trace

Complete internal logs from a test run (`ros2_ws/api_server.log`):

```
2026-02-22 15:13:00  INFO   cell_sim.api              Starting ROS2 bridge …
2026-02-22 15:13:00  INFO   cell_sim.api.ros2_bridge   ROS2 bridge initialised — background spin thread running
2026-02-22 15:13:00  INFO   cell_sim.api              FastAPI ready

2026-02-22 15:15:19  INFO   cell_sim.api              [6f76e2fa] POST /plan  goal='Pick the object and place it in bin A'
2026-02-22 15:15:19  INFO   cell_sim.api              [6f76e2fa] Cell state fetched: {"object_pose":{"x":0.087,"y":-0.049,"z":0.05,...}}
2026-02-22 15:15:19  INFO   cell_sim.api.llm_client   [6f76e2fa] LLM call attempt 1/2  provider=anthropic
2026-02-22 15:15:29  INFO   cell_sim.api.llm_client     Anthropic usage  tokens_in=446  tokens_out=760  est_cost=$0.012738
2026-02-22 15:15:29  INFO   cell_sim.api.llm_client   [6f76e2fa] LLM response in 10.32s  provider=anthropic
2026-02-22 15:15:29  INFO   cell_sim.api              [6f76e2fa] Plan validated — 7 steps

2026-02-22 15:15:30  INFO   cell_sim.api              [c8c6d45c] POST /orchestrate — generous constraints
2026-02-22 15:15:40  INFO   cell_sim.api.llm_client     Anthropic usage  tokens_in=446  tokens_out=757  est_cost=$0.012693
2026-02-22 15:15:40  INFO   cell_sim.api.safety        Safety gate: all checks passed
2026-02-22 15:15:40  INFO   cell_sim.api.orchestrator  Plan ACCEPTED on attempt 1

2026-02-22 15:15:40  INFO   cell_sim.api              [6fdafb14] POST /orchestrate — tight speed (max=0.2)
2026-02-22 15:15:49  INFO   cell_sim.api.llm_client     Anthropic usage  tokens_in=446  tokens_out=756  est_cost=$0.012678
2026-02-22 15:15:49  INFO   cell_sim.api.safety        Safety gate: all checks passed
2026-02-22 15:15:49  INFO   cell_sim.api.orchestrator  Plan ACCEPTED on attempt 1

2026-02-22 15:15:49  INFO   cell_sim.api              [75c23fe2] POST /orchestrate — z-bound conflict (z=0.5 vs max=0.08)
2026-02-22 15:15:54  WARNING cell_sim.api.safety        Safety gate found 1 violation(s):
2026-02-22 15:15:54  WARNING cell_sim.api.safety          • Step 1 (MOVE): target z=0.5 above allowed_z_max 0.08
2026-02-22 15:16:00  INFO   cell_sim.api.safety        Safety gate: all checks passed  (after replan)
2026-02-22 15:16:00  INFO   cell_sim.api.orchestrator  Plan ACCEPTED on attempt 2

2026-02-22 15:16:00  INFO   cell_sim.api              [f9715f9d] POST /orchestrate — tight z (max=0.03)
2026-02-22 15:16:06  INFO   cell_sim.api.llm_client     Anthropic usage  tokens_in=453  tokens_out=405  est_cost=$0.007434
2026-02-22 15:16:06  INFO   cell_sim.api.safety        Safety gate: all checks passed
2026-02-22 15:16:06  INFO   cell_sim.api.orchestrator  Plan ACCEPTED on attempt 1
```

### Latency per Anthropic Call (from logs)

```
[6f76e2faebcd] LLM response in 10.32s  provider=anthropic
[c8c6d45c5d54] LLM response in  9.78s  provider=anthropic
[6fdafb145f18] LLM response in  9.02s  provider=anthropic
[75c23fe2059c] LLM response in  5.24s  provider=anthropic
[75c23fe2059c] LLM response in  5.30s  provider=anthropic  (replan after rejection)
[f9715f9de5fe] LLM response in  6.54s  provider=anthropic
```

---

## One-Command Launch Sequence

The entire system — Nervous System, Brain, and test suite — boots from a single invocation. Nothing needs to be running beforehand.

```bash
# First-time build (once)
cd ros2_ws && bash build.sh && cd ..

# Launch everything, run all tests, display results, clean up
bash run_tests.sh
```

### What `run_tests.sh` does on instantiation

```
 1. Source ROS2 Jazzy + colcon workspace
 2. Load .env (API keys)
 3. Launch NERVOUS SYSTEM:  ros2 launch cell_sim cell_sim.launch.py  (background)
     → sensor_sim_node starts publishing PoseStamped at 5 Hz
     → cell_state_node starts aggregating + serving /cell/get_state
 4. Launch BRAIN:  uvicorn cell_sim.api.app:app --port 8000  (background)
     → ROS2Bridge spins up a daemon thread, connects to /cell/get_state
     → FastAPI exposes /plan, /orchestrate, /health
 5. Wait for readiness:  poll GET /health until 200 OK
 6. Run TASK 1 tests:  ros2 topic list, echo, service call
 7. Run TASK 2 tests:  curl POST /plan
 8. Run TASK 3 tests:  curl POST /orchestrate (4 scenarios incl. z-bound rejection)
 9. Run TASK 4 tests:  extract cost/latency metrics from api_server.log
10. Write everything to ros2_ws/test_results.log
11. trap EXIT → kill background processes (clean shutdown)
```

### Docker alternative (also single-command)

```bash
cp .env.example .env   # fill in ANTHROPIC_API_KEY
docker compose up --build
# ros2_cell (Nervous System) and planner_api (Brain) start automatically
# curl http://localhost:8000/plan to test
```

---

## Brain vs. Nervous System — Architectural Separation

This project enforces a hard boundary between two process domains, analogous to the LangGraph "agentic graph" pattern versus real-time robot control:

```
  ╔══════════════════════════════════════════════════════════════════════════╗
  ║                                                                        ║
  ║   "BRAIN" — LLM Graph Processes (Agentic / LangGraph-style)           ║
  ║                                                                        ║
  ║   ┌────────────┐      ┌──────────────┐      ┌────────────────┐        ║
  ║   │  PLANNING  │─────▶│ SAFETY_CHECK │─────▶│   ACCEPTED     │        ║
  ║   │            │      │ (gate node)  │      │                │        ║
  ║   │ LLM call   │      │ deterministic│      │ validated plan │        ║
  ║   │ prompt eng │      │ hard-coded   │      │ ready to exec  │        ║
  ║   └────────────┘      └──────┬───────┘      └────────────────┘        ║
  ║                               │ FAIL                                   ║
  ║                               ▼                                        ║
  ║                        ┌──────────────┐                                ║
  ║                        │ REPLANNING   │ ← rejection reason fed back    ║
  ║                        │ (max 1 retry)│   to LLM as context            ║
  ║                        └──────────────┘                                ║
  ║                                                                        ║
  ║   Components:                                                          ║
  ║     • orchestrator.py  — state machine (plan → check → replan)         ║
  ║     • llm_client.py    — Anthropic/OpenAI/Gemini/Ollama/stub           ║
  ║     • safety.py        — deterministic constraint validator            ║
  ║     • app.py           — FastAPI HTTP interface                        ║
  ║     • models.py        — Pydantic schemas (strict typing)              ║
  ║                                                                        ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║                                                                        ║
  ║          ▲ validated plan (Pydantic PlanResponse)                       ║
  ║          │                                                             ║
  ║          │  Narrow contract: only schema-validated, safety-checked     ║
  ║          │  plans cross this boundary. Raw LLM text NEVER passes.     ║
  ║          │                                                             ║
  ║          ▼ cell state JSON (from /cell/get_state Trigger service)      ║
  ║                                                                        ║
  ╠══════════════════════════════════════════════════════════════════════════╣
  ║                                                                        ║
  ║   "NERVOUS SYSTEM" — Robot Cell Processes (ROS2 / Real-Time)          ║
  ║                                                                        ║
  ║   ┌─────────────────┐    5 Hz     ┌──────────────────┐                ║
  ║   │ sensor_sim_node │────────────▶│ cell_state_node  │                ║
  ║   │                 │ PoseStamped │                  │                ║
  ║   │ simulated       │             │ aggregates state │                ║
  ║   │ perception      │             │ publishes JSON   │                ║
  ║   └─────────────────┘             │ serves /cell/    │                ║
  ║                                   │   get_state      │                ║
  ║                                   └──────────────────┘                ║
  ║                                                                        ║
  ║   Components:                                                          ║
  ║     • sensor_sim_node.py  — PoseStamped at 5 Hz (sinusoidal motion)    ║
  ║     • cell_state_node.py  — JSON state at 2 Hz + Trigger service       ║
  ║     • ros2_bridge.py      — in-process rclpy client (daemon thread)    ║
  ║                                                                        ║
  ╚══════════════════════════════════════════════════════════════════════════╝
```

### Why This Separation Matters

| Principle | Brain (LLM) | Nervous System (ROS2) |
|-----------|-------------|----------------------|
| **Determinism** | Non-deterministic — LLM output varies per call | Fully deterministic — same input, same output |
| **Latency** | 5–10 seconds per Anthropic call | Sub-millisecond ROS2 pub/sub |
| **Failure mode** | May produce invalid JSON, hallucinate poses, ignore constraints | Sensor noise is bounded and predictable |
| **Trust level** | Zero trust — every output is validated before use | High trust — hard-coded physics simulation |
| **Safety enforcement** | Never — LLM is never given control authority | Always — `safety.py` runs deterministic checks |
| **Update cycle** | Model swapped via env var, no robot restart needed | Firmware-like — changes require rebuild + test |

The **safety gate** (`safety.py`) is the critical boundary enforcer. It is pure deterministic code, never an LLM call:
- All MOVE steps must have `speed <= max_speed`
- All `target_pose.z` must be within `[allowed_z_min, allowed_z_max]`
- All MOVE steps must have a `target_pose`

If the Brain violates any constraint, the orchestrator sends a **SAFETY REJECTION** with the exact violation list back to the LLM for one retry. If the retry also fails, a deterministic fallback plan (with clamped values) is returned — the Nervous System never receives an unsafe command.

---

## Deployment & Build

### Docker Compose (preferred)

```bash
cp .env.example .env   # set ANTHROPIC_API_KEY
docker compose up --build
```

| Container | Role | Image Base | What it runs |
|-----------|------|-----------|--------------|
| `ros2_cell` | **Nervous System** | `ros:jazzy-ros-base` | `sensor_sim_node` + `cell_state_node` (edge device) |
| `planner_api` | **Brain** | `ros:jazzy-ros-base` + FastAPI | FastAPI + ROS2 bridge + LLM orchestrator |

Both containers share `ROS_DOMAIN_ID=42` on a Docker bridge network so the Brain's `ros2_bridge.py` can call the Nervous System's `/cell/get_state` service across containers.

### Connectivity & Safety (Brain ↔ Nervous System)

| Concern | Implementation |
|---------|---------------|
| **Protocol** | HTTP/REST between user and Brain (port 8000). ROS2 DDS between Brain's bridge and Nervous System |
| **Network failure** | 5s timeout on ROS2 service calls; 30s timeout on Anthropic API. Configurable via env vars |
| **Inference timeout** | If the LLM doesn't respond within `LLM_TIMEOUT`, retried once, then falls back to deterministic safe-stop plan |
| **Fallback strategy** | `deterministic_fallback()` returns a hardcoded safe plan. The REJECTED state clamps all values to guarantee constraint compliance |
| **Safe-stop plan** | On total Brain failure: WAIT step with speed=0 — Nervous System holds position, no motion commanded |

### GPU / Cloud Inference Notes

Since we use Anthropic's hosted Claude API (not local GPU inference):

| Topic | Details |
|-------|---------|
| **GPU access** | Not applicable — Anthropic manages GPU infrastructure. For local LLM (Ollama), add `runtime: nvidia` + `deploy.resources.reservations.devices` in docker-compose |
| **Metrics monitored** | API latency (measured per call), token usage (measured), cost per call (measured), safety violations caught (logged) |
| **Cost/latency tradeoffs** | Claude Sonnet 4: $3/M input, $15/M output. Avg call ~$0.01. For lower latency: Claude Haiku. For lower cost at scale: batch requests, cache common plans, fine-tune a local model |

---

## File Structure

```
playground/
├── README.md                              ← you are here
├── .env                                   ← API keys (git-ignored)
├── .gitignore
├── docker-compose.yml                     ← Docker deployment
├── run_tests.sh                           ← ONE COMMAND: launch + test + log
├── docker/
│   ├── Dockerfile.ros2_cell               ← Nervous System container
│   ├── Dockerfile.planner_api             ← Brain container
│   └── entrypoint_api.sh
└── ros2_ws/
    ├── build.sh                           ← workspace build script
    ├── test_results.log                   ← latest full test output
    ├── api_server.log                     ← API internal logs (cost/latency)
    └── src/
        ├── cell_sim/                      ← main package
        │   ├── cell_sim/
        │   │   ├── sensor_sim_node.py         NERVOUS SYSTEM: perception (5 Hz)
        │   │   ├── cell_state_node.py         NERVOUS SYSTEM: state + service
        │   │   └── api/
        │   │       ├── app.py                 BRAIN: FastAPI endpoints
        │   │       ├── models.py              BRAIN: Pydantic schemas
        │   │       ├── ros2_bridge.py         BRIDGE: in-process rclpy client
        │   │       ├── llm_client.py          BRAIN: multi-provider LLM + metrics
        │   │       ├── safety.py              GATE: deterministic validator
        │   │       └── orchestrator.py        BRAIN: state machine orchestrator
        │   ├── launch/
        │   │   └── cell_sim.launch.py
        │   └── setup.py
        ├── robot_cell/                    ← extended ROS2 nodes
        └── robot_cell_interfaces/         ← custom .msg/.srv definitions
```

---

## API Endpoints

| Endpoint | Method | Domain | Description |
|----------|--------|--------|-------------|
| `/health` | GET | Brain | Returns `{"status": "ok"}` |
| `/plan` | POST | Brain | Single LLM call → Pydantic validation → plan |
| `/orchestrate` | POST | Brain | Full state-machine: plan → safety check → replan |

### Request Schema

```json
{
  "goal": "Pick the object and place it in bin A",
  "constraints": {
    "max_speed": 0.5,
    "allowed_z_min": 0.0,
    "allowed_z_max": 1.0
  }
}
```

### Response Schema

```json
{
  "plan_id": "uuid",
  "steps": [
    {
      "type": "MOVE|GRASP|RELEASE|WAIT",
      "target_pose": {"x":0,"y":0,"z":0,"qx":0,"qy":0,"qz":0,"qw":1},
      "speed": 0.3,
      "notes": "Move to object"
    }
  ],
  "safety": {
    "assumptions": ["Object is graspable"],
    "checks": ["Verify gripper force after GRASP"]
  }
}
```

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Brain / Nervous System separation** | The LLM produces *intent*; the safety gate and ROS2 nodes handle *execution*. No raw LLM text crosses the boundary — only Pydantic-validated plans |
| **Deterministic safety gate** | Safety-critical checks must never be delegated to an LLM. Hard-coded bounds in `safety.py` are predictable, auditable, and testable |
| **Closed-loop replanning** | If the Brain violates constraints, the safety gate sends structured rejection feedback for one retry. Bounded to 2 attempts to guarantee termination |
| **Multi-provider LLM client** | Env-var driven provider selection (`stub`/`openai`/`anthropic`/`gemini`/`ollama`). Swap the Brain's model without touching the Nervous System |
| **In-process ROS2 bridge** | `rclpy` runs in a daemon thread inside FastAPI. The Brain calls the Nervous System's `/cell/get_state` via DDS, avoiding subprocess or HTTP overhead |
| **Cost/latency instrumentation** | Every Anthropic call logs tokens, cost estimate, and wall-clock latency. Essential for production budget monitoring |
| **Safe-stop fallback** | On total Brain failure (LLM down, 2 failed attempts): return WAIT with speed=0. The Nervous System holds position — no unsafe motion |

---

## What I'd Improve for Production

1. **LangGraph for the Brain** — replace the hand-rolled state machine with a LangGraph `StateGraph` for visual debugging and built-in checkpointing
2. **gRPC instead of REST** between user and Brain for lower latency + strong typing
3. **OpenTelemetry tracing** with trace-id propagation across Nervous System → Brain → Anthropic
4. **Prometheus `/metrics` endpoint** for Grafana dashboards (latency histograms, cost counters, safety rejection rate)
5. **Plan caching** — hash (goal + constraints + discretized state) → skip LLM for repeated requests
6. **Circuit breaker** on the Anthropic client to fail fast during outages
7. **Local fallback model** (Ollama with quantized LLaMA) as a secondary Brain when cloud API is unavailable
8. **ROS2 action server** instead of services for long-running plan execution with progress feedback
9. **Integration tests** with a simulated robot (MoveIt + Gazebo) to validate plans in physics before real execution
