"""
Simulated perception sensor that publishes a PoseStamped at a configurable rate.

The pose traces a sinusoidal path so downstream consumers see changing data.
QoS: default RELIABLE / KEEP_LAST(10) — suitable for a low-rate sensor where
every message matters and the subscriber is expected to keep up.
"""

import math

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped


class SensorSimNode(Node):

    def __init__(self):
        super().__init__('sensor_sim_node')

        self.declare_parameter('frame_id', 'world')
        self.declare_parameter('amplitude', 0.1)
        self.declare_parameter('publish_rate_hz', 5.0)

        self._frame_id = self.get_parameter('frame_id').value
        self._amplitude = self.get_parameter('amplitude').value
        rate_hz = self.get_parameter('publish_rate_hz').value

        # Default QoS (reliable, keep-last 10) is a sensible choice here:
        # the sensor rate is low (5 Hz) and we want every pose delivered to
        # the subscriber without drops.
        self._pub = self.create_publisher(PoseStamped, '/perception/object_pose', 10)
        self._timer = self.create_timer(1.0 / rate_hz, self._tick)
        self._t = 0.0

        self.get_logger().info(
            f'sensor_sim_node started  |  frame={self._frame_id}  '
            f'amp={self._amplitude}  rate={rate_hz} Hz'
        )

    def _tick(self):
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self._frame_id

        msg.pose.position.x = self._amplitude * math.sin(self._t)
        msg.pose.position.y = self._amplitude * math.cos(self._t)
        msg.pose.position.z = 0.05

        # Fixed orientation (identity quaternion)
        msg.pose.orientation.x = 0.0
        msg.pose.orientation.y = 0.0
        msg.pose.orientation.z = 0.0
        msg.pose.orientation.w = 1.0

        self._pub.publish(msg)
        self._t += 0.1

        self.get_logger().debug(
            f'Published pose  x={msg.pose.position.x:.4f}  '
            f'y={msg.pose.position.y:.4f}',
            throttle_duration_sec=2.0,
        )


def main(args=None):
    rclpy.init(args=args)
    node = SensorSimNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
