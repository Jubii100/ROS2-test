#!/usr/bin/env bash
# Build the entire workspace in the correct order.
# Usage:  cd ros2_ws && bash build.sh
set -euo pipefail
cd "$(dirname "$0")"

# Ensure anaconda doesn't shadow system Python (needed for CMake msg gen)
export PATH="/usr/bin:$(echo "$PATH" | tr ':' '\n' | grep -v anaconda | tr '\n' ':')"

source /opt/ros/jazzy/setup.bash

echo "── Building robot_cell_interfaces (CMake) ──────────────────"
colcon build --packages-select robot_cell_interfaces \
    --cmake-args -DPython3_EXECUTABLE=/usr/bin/python3

source install/setup.bash

echo "── Building cell_sim + robot_cell (Python) ─────────────────"
colcon build --packages-select cell_sim robot_cell

source install/setup.bash
echo ""
echo "Build complete.  Run:"
echo "  ros2 launch cell_sim cell_sim.launch.py"
echo "  # then in another terminal:"
echo "  bash run_tests.sh"
