"""Launch both cell_sim nodes with default parameters."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    sensor_node = Node(
        package='cell_sim',
        executable='sensor_sim_node',
        name='sensor_sim_node',
        output='screen',
        parameters=[{
            'frame_id': 'world',
            'amplitude': 0.1,
            'publish_rate_hz': 5.0,
        }],
    )

    state_node = Node(
        package='cell_sim',
        executable='cell_state_node',
        name='cell_state_node',
        output='screen',
    )

    return LaunchDescription([sensor_node, state_node])
