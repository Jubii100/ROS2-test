# ROS2 Robot Cell — AI-Powered Motion Planner

A ROS2-based robot cell simulation with LLM-powered motion planning, a deterministic safety gate, and a FastAPI HTTP bridge. The system simulates a perception sensor and cell state aggregator, exposes them as ROS2 topics/services, and connects to Anthropic's Claude to generate structured pick-and-place plans that are validated against safety constraints before execution.

---

## Architecture

```
┌──────────────────────────── Edge Device ─────────────────────────────────┐
│                                                                          │
│   sensor_sim_node ──(PoseStamped 5 Hz)──▶ cell_state_node               │
│                                              │       │                   │
│                                     (String 2 Hz)  (Trigger svc)        │
│                                      /cell/state   /cell/get_state      │
│                                                        ▲                 │
└────────────────────────────────────────────────────────┼─────────────────┘
                                                         │
                        ┌────────────────────────────────┘
                        │
┌───────────────── Planner API (FastAPI :8000) ────────────────────────────┐
│                                                                          │
│   POST /plan ──▶ ROS2Bridge ──▶ Build Prompt ──▶ LLM Client ──▶ Parse   │
│                                                      │                   │
│   POST /orchestrate ──▶ State Machine                │                   │
│        │                    │                         │                   │
│        │              PLANNING ──▶ SAFETY_CHECK       │                   │
│        │                │              │              │                   │
│        │           REPLANNING    ACCEPTED/REJECTED    │                   │
│        │                                              │                   │
│        └──────── safety.py (deterministic)            │                   │
│                                                       │                   │
└───────────────────────────────────────────────────────┼─────────────────┘
                                                        │ HTTPS
                                                        ▼
                                              ┌─────────────────┐
                                              │  Anthropic API  │
                                              │  Claude Sonnet  │
                                              └─────────────────┘
```

---

## Quick Start (One Command)

```bash
# 1. Set your API key
export ANTHROPIC_API_KEY=sk-ant-...
#    (or put it in .env — the script auto-loads it)

# 2. Build the workspace (first time only)
cd ros2_ws && bash build.sh && cd ..

# 3. Run all tests (launches nodes, API, runs Tasks 1–4, shows results)
bash run_tests.sh
```

The script:
1. Starts both ROS2 nodes (sensor + cell state) in the background
2. Starts the FastAPI server with the Anthropic provider
3. Waits for all services to be healthy
4. Executes every test from Tasks 1–4
5. Writes the full log to `ros2_ws/test_results.log`
6. Cleans up all background processes on exit

---

## Docker Deployment

```bash
# Copy and fill in your API key
cp .env.example .env
# edit .env → set ANTHROPIC_API_KEY

# Build and launch
docker compose up --build

# In another terminal, test:
curl -s http://localhost:8000/health
curl -s -X POST http://localhost:8000/plan \
  -H "Content-Type: application/json" \
  -d '{"goal":"Pick the cube and place it in bin A"}'
```

### Docker Services

| Service | Image Base | Purpose | Port |
|---------|-----------|---------|------|
| `ros2_cell` | `ros:jazzy-ros-base` | Sensor simulation + cell state (edge) | — |
| `planner_api` | `ros:jazzy-ros-base` + FastAPI | HTTP API + ROS2 bridge + LLM client | 8000 |

### Connectivity & Safety (Edge → Inference)

| Concern | Implementation |
|---------|---------------|
| **Protocol** | HTTP/REST — FastAPI on port 8000. In production, gRPC with protobuf would reduce serialization overhead |
| **Network failure** | 5-second timeout on ROS2 service calls; 30-second timeout on Anthropic API. Both configurable via env vars |
| **Inference timeout** | If the LLM doesn't respond within `LLM_TIMEOUT`, the call is retried once, then falls back to a deterministic safe-stop plan |
| **Fallback strategy** | `deterministic_fallback()` in `llm_client.py` returns a hardcoded safe plan. The REJECTED state in the orchestrator also clamps all values to respect constraints |
| **Safe-stop plan** | On total failure: WAIT step with speed=0 — robot holds position, no motion commanded |

### GPU / Cloud Inference Notes

Since we use Anthropic's hosted Claude API (not local GPU inference):

| Topic | Details |
|-------|---------|
| **GPU access** | Not applicable — Anthropic manages GPU infrastructure. For local LLM (Ollama), you'd add `runtime: nvidia` + `deploy.resources.reservations.devices` in docker-compose |
| **Metrics to monitor** | API latency (measured), token usage (measured), cost per call (measured), error rate, queue depth on the FastAPI side |
| **Cost/latency tradeoffs** | Claude Sonnet 4: $3/M input, $15/M output. Average call: ~$0.01. For lower latency: use Claude Haiku. For lower cost at scale: batch requests, cache common plans, use a fine-tuned local model for common scenarios |

---

## File Structure

```
playground/
├── README.md                       ← you are here
├── .env                            ← API keys (git-ignored)
├── .gitignore
├── docker-compose.yml              ← Task 4: deployment config
├── docker/
│   ├── Dockerfile.ros2_cell        ← ROS2 edge container
│   ├── Dockerfile.planner_api      ← API + LLM container
│   └── entrypoint_api.sh
├── run_tests.sh                    ← one-shot test runner (Tasks 1–4)
└── ros2_ws/
    ├── build.sh                    ← workspace build script
    ├── test_results.log            ← latest test output
    ├── api_server.log              ← API internal logs
    └── src/
        ├── cell_sim/               ← main Python package
        │   ├── cell_sim/
        │   │   ├── sensor_sim_node.py      Task 1: PoseStamped publisher (5 Hz)
        │   │   ├── cell_state_node.py      Task 1: JSON state + Trigger service
        │   │   └── api/
        │   │       ├── app.py              Task 2: FastAPI endpoints
        │   │       ├── models.py           Pydantic request/response schemas
        │   │       ├── ros2_bridge.py      In-process rclpy client
        │   │       ├── llm_client.py       Multi-provider LLM + cost tracking
        │   │       ├── safety.py           Task 3: deterministic constraint validator
        │   │       └── orchestrator.py     Task 3: state machine (plan→check→replan)
        │   ├── launch/
        │   │   └── cell_sim.launch.py
        │   └── setup.py
        ├── robot_cell/             ← extended ROS2 package (custom msgs)
        └── robot_cell_interfaces/  ← custom .msg/.srv definitions
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Returns `{"status": "ok"}` |
| `/plan` | POST | Generate a motion plan (single LLM call + Pydantic validation) |
| `/orchestrate` | POST | Full state-machine: plan → safety check → replan if needed |

### Request Schema (`/plan` and `/orchestrate`)

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

## Safety Gate (Deterministic — Never LLM)

The safety validator in `safety.py` enforces:

1. **Speed check**: Every step's `speed` must be ≤ `constraints.max_speed`
2. **Z-bound check**: Every `target_pose.z` must be within `[allowed_z_min, allowed_z_max]`
3. **MOVE completeness**: Every MOVE step must have a `target_pose`

If any check fails, the orchestrator sends a **SAFETY REJECTION** prompt back to the LLM with the exact violation list. If the second attempt also fails, a deterministic fallback plan (with clamped values) is returned.

---

## Test Results (Latest Run — Anthropic Claude Sonnet 4)

### Task Pass/Fail Summary

| Task | Description | Result |
|------|-------------|--------|
| **Task 1** | ROS2 basics: topics, services, sensor simulation | **PASSED** |
| **Task 2** | FastAPI + ROS2 bridge + LLM call | **PASSED** |
| **Task 3** | Multi-agent orchestration + safety gate | **PASSED** |
| **Task 4** | Docker deployment design + cost/latency monitoring | **PASSED** |

### Anthropic LLM Call Metrics (from actual test run)

| Test | LLM Calls | Latency | Tokens (in/out) | Est. Cost | Safety |
|------|-----------|---------|-----------------|-----------|--------|
| Task 2 — `/plan` | 1 | 10.32s | 446 / 760 | $0.0127 | n/a |
| Task 3a — generous | 1 | 9.78s | 446 / 757 | $0.0127 | PASS attempt 1 |
| Task 3b — tight speed | 1 | 9.02s | 446 / 756 | $0.0127 | PASS attempt 1 |
| Task 3c — z-bound reject | 2 | 5.24s + 5.30s | 495+561 / 285+281 | $0.0117 | **REJECT → PASS attempt 2** |
| Task 3d — tight z-bound | 1 | 6.54s | 453 / 405 | $0.0074 | PASS attempt 1 |
| **Total** | **6 calls** | **~46s** | **2847 / 3244** | **~$0.057** | |

### Z-Bound Violation Evidence (Task 3c)

```
Safety gate found 1 violation(s):
  • Step 1 (MOVE): target z=0.5 above allowed_z_max 0.08
```

The LLM was given a goal demanding `z=0.5` but the constraint said `allowed_z_max=0.08`. The safety gate caught the violation on attempt 1, sent the rejection back to Claude, and Claude corrected to `z=0.08` on attempt 2.

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Separate LLM planner from robot executor** | The planner produces intent; the safety gate and executor validate and act. No LLM output ever reaches the robot without deterministic validation |
| **Deterministic safety gate** | Safety-critical checks must never be delegated to an LLM. Hard-coded bounds are predictable and auditable |
| **Closed-loop replanning** | If the LLM violates constraints, it gets one retry with explicit feedback. Bounded to 2 attempts to guarantee termination |
| **Multi-provider LLM client** | Env-var driven provider selection (stub/openai/anthropic/gemini/ollama). Swap models without code changes |
| **In-process ROS2 bridge** | rclpy runs in a daemon thread inside the FastAPI process. Avoids IPC overhead and subprocess management |
| **Cost/latency logging** | Every Anthropic call logs tokens, cost estimate, and wall-clock latency. Essential for production cost monitoring |

---

## What I'd Improve for Production

1. **gRPC instead of REST** between edge and planner for lower latency + strong typing
2. **OpenTelemetry tracing** with trace-id propagation across ROS2 → API → LLM
3. **Prometheus metrics endpoint** (`/metrics`) for Grafana dashboards
4. **Plan caching** — hash (goal + constraints + discretized state) → skip LLM for repeated requests
5. **Circuit breaker** on the Anthropic client to fail fast during outages
6. **Local fallback model** (e.g. Ollama with a quantized model) when cloud API is unavailable
7. **ROS2 action server** instead of services for long-running plan execution with progress feedback
8. **Integration tests** with a simulated robot (MoveIt + Gazebo) to validate plans in physics
