"""Launch file to start all robot cell nodes."""

from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    perception_node = Node(
        package='robot_cell',
        executable='perception_node',
        name='perception_node',
        output='screen',
        parameters=[{
            'publish_rate': 5.0,
            'noise_stddev': 0.002,
        }],
    )

    cell_supervisor_node = Node(
        package='robot_cell',
        executable='cell_supervisor_node',
        name='cell_supervisor_node',
        output='screen',
    )

    ai_planner_node = Node(
        package='robot_cell',
        executable='ai_planner_node',
        name='ai_planner_node',
        output='screen',
    )

    return LaunchDescription([
        perception_node,
        cell_supervisor_node,
        ai_planner_node,
    ])
