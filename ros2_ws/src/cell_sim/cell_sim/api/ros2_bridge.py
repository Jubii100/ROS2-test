"""
In-process ROS2 bridge.

Spins a lightweight rclpy node in a daemon thread so the FastAPI async loop
can fetch the latest cell state without blocking.
"""

from __future__ import annotations

import asyncio
import functools
import json
import logging
import threading
import time

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

logger = logging.getLogger(__name__)


class ROS2Bridge:
    """Thin wrapper that calls /cell/get_state from inside the API process."""

    def __init__(self) -> None:
        rclpy.init()
        self._node = Node("api_bridge_node")
        self._client = self._node.create_client(Trigger, "/cell/get_state")
        self._spin_thread = threading.Thread(target=self._spin, daemon=True)
        self._spin_thread.start()
        logger.info("ROS2 bridge initialised — background spin thread running")

    def _spin(self) -> None:
        try:
            rclpy.spin(self._node)
        except Exception:
            logger.exception("ROS2 spin thread crashed")

    def _fetch_state_blocking(self, timeout_sec: float = 5.0) -> dict:
        if not self._client.wait_for_service(timeout_sec=2.0):
            raise TimeoutError("ROS2 service /cell/get_state not available")

        future = self._client.call_async(Trigger.Request())
        deadline = time.monotonic() + timeout_sec
        while not future.done():
            if time.monotonic() > deadline:
                raise TimeoutError("Service call to /cell/get_state timed out")
            time.sleep(0.01)

        result = future.result()
        if not result.success:
            raise RuntimeError(f"Service returned failure: {result.message}")

        return json.loads(result.message)

    async def get_cell_state(self, timeout_sec: float = 5.0) -> dict:
        """Async wrapper — runs the blocking ROS2 call in a thread-pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, functools.partial(self._fetch_state_blocking, timeout_sec)
        )

    def shutdown(self) -> None:
        self._node.destroy_node()
        rclpy.try_shutdown()
        logger.info("ROS2 bridge shut down")
