"""Cell supervisor that aggregates perception data and exposes cell state."""

import rclpy
from rclpy.node import Node
from robot_cell_interfaces.msg import ObjectPose, CellState
from robot_cell_interfaces.srv import GetCellState, ExecuteStep


class CellSupervisorNode(Node):
    """Maintains the latest cell state and provides services to query/act on it."""

    def __init__(self):
        super().__init__('cell_supervisor_node')

        self._detected_objects: dict[str, ObjectPose] = {}
        self._robot_status = 'READY'
        self._gripper_state = 'OPEN'
        self._cell_status = 'IDLE'

        self._pose_sub = self.create_subscription(
            ObjectPose, '/perception/object_poses', self._on_object_pose, 10
        )

        self._state_pub = self.create_publisher(CellState, '/cell/state', 10)
        self._state_timer = self.create_timer(1.0, self._publish_state)

        self._get_state_srv = self.create_service(
            GetCellState, '/cell/get_state', self._handle_get_state
        )
        self._execute_step_srv = self.create_service(
            ExecuteStep, '/cell/execute_step', self._handle_execute_step
        )

        self.get_logger().info('Cell supervisor node started')

    def _on_object_pose(self, msg: ObjectPose):
        self._detected_objects[msg.object_id] = msg

    def _build_state(self) -> CellState:
        state = CellState()
        state.cell_status = self._cell_status
        state.robot_status = self._robot_status
        state.gripper_state = self._gripper_state
        state.detected_objects = list(self._detected_objects.values())
        state.stamp = self.get_clock().now().to_msg()
        return state

    def _publish_state(self):
        self._state_pub.publish(self._build_state())
        self.get_logger().debug(
            f'State published — {len(self._detected_objects)} objects tracked',
            throttle_duration_sec=5.0,
        )

    def _handle_get_state(self, _request, response):
        response.state = self._build_state()
        response.success = True
        response.message = 'Current cell state retrieved'
        self.get_logger().info('GetCellState service called')
        return response

    def _handle_execute_step(self, request, response):
        step = request.step
        self.get_logger().info(
            f'Executing step {step.step_number}: '
            f'{step.action} on {step.target_object_id} — {step.description}'
        )

        self._cell_status = 'BUSY'

        if step.action == 'MOVE':
            self._robot_status = 'MOVING'
        elif step.action == 'PICK':
            self._robot_status = 'HOLDING'
            self._gripper_state = 'CLOSED'
        elif step.action == 'PLACE':
            self._robot_status = 'READY'
            self._gripper_state = 'OPEN'
        elif step.action == 'INSPECT':
            self._robot_status = 'READY'
        else:
            response.success = False
            response.message = f'Unknown action: {step.action}'
            response.resulting_robot_status = self._robot_status
            response.resulting_gripper_state = self._gripper_state
            self._cell_status = 'ERROR'
            return response

        self._cell_status = 'IDLE'

        response.success = True
        response.message = f'Step {step.step_number} executed successfully'
        response.resulting_robot_status = self._robot_status
        response.resulting_gripper_state = self._gripper_state
        return response


def main(args=None):
    rclpy.init(args=args)
    node = CellSupervisorNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
