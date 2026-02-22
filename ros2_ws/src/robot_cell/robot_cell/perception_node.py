"""Simulated perception system that publishes detected object poses."""

import math
import random

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, Point, Quaternion
from robot_cell_interfaces.msg import ObjectPose


SIMULATED_OBJECTS = [
    {'id': 'red_cube', 'base_x': 0.5, 'base_y': 0.2, 'base_z': 0.05},
    {'id': 'blue_cylinder', 'base_x': 0.3, 'base_y': -0.1, 'base_z': 0.08},
    {'id': 'green_sphere', 'base_x': 0.6, 'base_y': 0.0, 'base_z': 0.04},
]


class PerceptionNode(Node):
    """Simulates a vision/perception system detecting objects on a worktable."""

    def __init__(self):
        super().__init__('perception_node')

        self.declare_parameter('publish_rate', 5.0)
        self.declare_parameter('noise_stddev', 0.002)

        rate = self.get_parameter('publish_rate').value
        self._noise = self.get_parameter('noise_stddev').value

        self._publisher = self.create_publisher(ObjectPose, '/perception/object_poses', 10)
        self._timer = self.create_timer(1.0 / rate, self._publish_objects)

        self.get_logger().info(
            f'Perception node started — publishing {len(SIMULATED_OBJECTS)} '
            f'objects at {rate} Hz'
        )

    def _add_noise(self, value: float) -> float:
        return value + random.gauss(0.0, self._noise)

    def _publish_objects(self):
        for obj in SIMULATED_OBJECTS:
            msg = ObjectPose()
            msg.object_id = obj['id']
            msg.pose = Pose(
                position=Point(
                    x=self._add_noise(obj['base_x']),
                    y=self._add_noise(obj['base_y']),
                    z=self._add_noise(obj['base_z']),
                ),
                orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
            )
            msg.confidence = min(1.0, max(0.0, random.gauss(0.95, 0.03)))
            msg.stamp = self.get_clock().now().to_msg()

            self._publisher.publish(msg)

        self.get_logger().debug('Published object poses', throttle_duration_sec=5.0)


def main(args=None):
    rclpy.init(args=args)
    node = PerceptionNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
