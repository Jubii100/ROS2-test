"""
Multi-provider LLM client.

Provider is selected via the LLM_PROVIDER env-var.
Supports: stub | openai | anthropic | gemini | ollama
API keys are read from LLM_API_KEY (never hardcoded).
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "30"))
_MAX_RETRIES = 2

# Claude Sonnet 4 pricing (per 1M tokens)
_ANTHROPIC_INPUT_COST = 3.0
_ANTHROPIC_OUTPUT_COST = 15.0


def _provider() -> str:
    return os.getenv("LLM_PROVIDER", "stub").lower()


def _api_key() -> str:
    return os.getenv("LLM_API_KEY", "")


# ── Stub provider ────────────────────────────────────────────────────────────

def _stub_generate(prompt: str) -> str:
    """
    Context-aware stub.

    On a normal call the plan intentionally uses speed=0.3 — which is fine for
    the default max_speed=0.5 but will trip a tighter constraint (e.g. 0.2).
    When the prompt contains "SAFETY REJECTION" the stub simulates an LLM
    that understood the feedback and returns a corrected plan with speed=0.15.
    """
    is_repair = "SAFETY REJECTION" in prompt
    label = "corrected" if is_repair else "initial"
    speed = 0.15 if is_repair else 0.3
    logger.info("Stub LLM: generating %s plan (speed=%.2f)", label, speed)

    return json.dumps({
        "plan_id": "STUB",
        "steps": [
            {
                "type": "MOVE",
                "target_pose": {"x": 0.5, "y": 0.0, "z": 0.05,
                                "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
                "speed": speed,
                "notes": "Move to detected object position",
            },
            {
                "type": "GRASP",
                "target_pose": None,
                "speed": min(speed, 0.1),
                "notes": "Close gripper on object",
            },
            {
                "type": "MOVE",
                "target_pose": {"x": 0.8, "y": 0.3, "z": 0.1,
                                "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
                "speed": speed,
                "notes": "Move to target bin A",
            },
            {
                "type": "RELEASE",
                "target_pose": None,
                "speed": 0.0,
                "notes": "Release object into bin",
            },
            {
                "type": "WAIT",
                "target_pose": None,
                "speed": 0.0,
                "notes": "Wait for settle confirmation",
            },
        ],
        "safety": {
            "assumptions": [
                "Object is rigid and graspable",
                "Bin A is within reachable workspace",
                "No humans in the cell during motion",
            ],
            "checks": [
                "Verify gripper force feedback after GRASP",
                "Confirm z stays within allowed range during MOVE",
                "Check collision-free path before execution",
            ],
        },
    })


# ── Real providers ───────────────────────────────────────────────────────────

async def _call_openai(prompt: str) -> str:
    url = "https://api.openai.com/v1/chat/completions"
    model = os.getenv("LLM_MODEL", "gpt-4o")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {_api_key()}"},
            json={
                "model": model,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


async def _call_anthropic(prompt: str) -> str:
    url = "https://api.anthropic.com/v1/messages"
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            headers={
                "x-api-key": _api_key(),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 2048,
                "temperature": 0.0,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        inp = data.get("usage", {}).get("input_tokens", 0)
        out = data.get("usage", {}).get("output_tokens", 0)
        cost = (inp * _ANTHROPIC_INPUT_COST + out * _ANTHROPIC_OUTPUT_COST) / 1_000_000
        logger.info(
            "  Anthropic usage  model=%s  tokens_in=%d  tokens_out=%d  est_cost=$%.6f",
            model, inp, out, cost,
        )
        return data["content"][0]["text"]


async def _call_gemini(prompt: str) -> str:
    model = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={_api_key()}"
    )
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _call_ollama(prompt: str) -> str:
    url = os.getenv("OLLAMA_URL", "http://localhost:11434") + "/api/generate"
    model = os.getenv("LLM_MODEL", "llama3")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            url,
            json={"model": model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["response"]


# ── Dispatcher ───────────────────────────────────────────────────────────────

_PROVIDERS = {
    "openai": _call_openai,
    "anthropic": _call_anthropic,
    "gemini": _call_gemini,
    "ollama": _call_ollama,
}


async def call_llm(prompt: str, request_id: str) -> str:
    """
    Call the configured LLM with retry.
    Returns the raw text response from the model (or stub).
    """
    provider = _provider()

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            logger.info(
                "[%s] LLM call attempt %d/%d  provider=%s",
                request_id, attempt, _MAX_RETRIES, provider,
            )
            t0 = time.monotonic()

            if provider == "stub":
                result = _stub_generate(prompt)
            else:
                handler = _PROVIDERS.get(provider)
                if handler is None:
                    raise ValueError(f"Unknown LLM_PROVIDER: {provider!r}")
                result = await handler(prompt)

            elapsed = time.monotonic() - t0
            logger.info(
                "[%s] LLM response in %.2fs  provider=%s",
                request_id, elapsed, provider,
            )
            return result

        except Exception:
            elapsed = time.monotonic() - t0
            logger.exception(
                "[%s] LLM attempt %d failed after %.2fs",
                request_id, attempt, elapsed,
            )
            if attempt == _MAX_RETRIES:
                raise

    raise RuntimeError("Unreachable")


def deterministic_fallback() -> dict:
    """Last-resort safe plan when LLM + retry both fail."""
    return json.loads(_stub_generate(""))
