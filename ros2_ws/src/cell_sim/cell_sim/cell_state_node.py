"""
Cell state aggregator.

Subscribes to the simulated sensor pose, republishes an aggregated JSON state
at 2 Hz, and exposes a Trigger service so callers can pull the latest state
on demand.

QoS: default RELIABLE / KEEP_LAST(10) on both the subscriber and the state
publisher.  At 2–5 Hz there is no bandwidth concern, and reliability ensures
no silent message loss between co-located nodes.
"""

import json

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from std_srvs.srv import Trigger


class CellStateNode(Node):

    def __init__(self):
        super().__init__('cell_state_node')

        self._latest_pose: PoseStamped | None = None

        self._pose_sub = self.create_subscription(
            PoseStamped, '/perception/object_pose', self._on_pose, 10
        )

        self._state_pub = self.create_publisher(String, '/cell/state', 10)
        self._state_timer = self.create_timer(0.5, self._publish_state)  # 2 Hz

        self._srv = self.create_service(
            Trigger, '/cell/get_state', self._handle_get_state
        )

        self.get_logger().info('cell_state_node started  |  state @ 2 Hz  |  service /cell/get_state')

    def _on_pose(self, msg: PoseStamped):
        self._latest_pose = msg

    def _build_state_json(self) -> str | None:
        if self._latest_pose is None:
            return None

        p = self._latest_pose.pose
        stamp = self._latest_pose.header.stamp
        return json.dumps({
            'timestamp': f'{stamp.sec}.{stamp.nanosec:09d}',
            'object_pose': {
                'x': round(p.position.x, 6),
                'y': round(p.position.y, 6),
                'z': round(p.position.z, 6),
                'qx': round(p.orientation.x, 6),
                'qy': round(p.orientation.y, 6),
                'qz': round(p.orientation.z, 6),
                'qw': round(p.orientation.w, 6),
            },
            'frame_id': self._latest_pose.header.frame_id,
        })

    def _publish_state(self):
        state_json = self._build_state_json()
        if state_json is None:
            self.get_logger().warn(
                'No pose received yet — skipping state publish',
                throttle_duration_sec=5.0,
            )
            return

        msg = String()
        msg.data = state_json
        self._state_pub.publish(msg)
        self.get_logger().debug('Published cell state', throttle_duration_sec=5.0)

    def _handle_get_state(self, _request, response):
        state_json = self._build_state_json()
        if state_json is None:
            response.success = False
            response.message = 'No sensor data received yet — state unavailable'
            self.get_logger().warn('get_state called but no data available')
        else:
            response.success = True
            response.message = state_json
            self.get_logger().info('get_state service called — returning latest state')
        return response


def main(args=None):
    rclpy.init(args=args)
    node = CellStateNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
