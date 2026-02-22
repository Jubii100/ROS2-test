#!/usr/bin/env bash
set -e

source /opt/ros/jazzy/setup.bash
source /ws/install/setup.bash

exec python3 -m uvicorn cell_sim.api.app:app \
    --host 0.0.0.0 --port 8000 \
    --log-level info
