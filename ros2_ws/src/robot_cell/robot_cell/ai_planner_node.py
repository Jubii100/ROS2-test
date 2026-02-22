"""AI planner that converts a human goal description into a structured plan."""

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Pose, Point, Quaternion
from robot_cell_interfaces.msg import PlanStep
from robot_cell_interfaces.srv import GeneratePlan, GetCellState


PLAN_TEMPLATES = {
    'pick': [
        {'action': 'MOVE', 'desc': 'Move to object location'},
        {'action': 'PICK', 'desc': 'Close gripper to grasp object'},
    ],
    'place': [
        {'action': 'MOVE', 'desc': 'Move to target placement location'},
        {'action': 'PLACE', 'desc': 'Open gripper to release object'},
    ],
    'pick_and_place': [
        {'action': 'MOVE', 'desc': 'Move to object location'},
        {'action': 'PICK', 'desc': 'Close gripper to grasp object'},
        {'action': 'MOVE', 'desc': 'Move to target placement location'},
        {'action': 'PLACE', 'desc': 'Open gripper to release object'},
    ],
    'inspect': [
        {'action': 'MOVE', 'desc': 'Move to inspection position'},
        {'action': 'INSPECT', 'desc': 'Inspect the object'},
    ],
}

KNOWN_LOCATIONS = {
    'bin_a': Point(x=0.8, y=0.3, z=0.0),
    'bin_b': Point(x=0.8, y=-0.3, z=0.0),
    'inspection_station': Point(x=0.0, y=0.5, z=0.1),
}


class AIPlannerNode(Node):
    """Parses a natural-language goal and returns a sequence of PlanSteps."""

    def __init__(self):
        super().__init__('ai_planner_node')

        self._plan_srv = self.create_service(
            GeneratePlan, '/planner/generate_plan', self._handle_generate_plan
        )

        self._cell_state_client = self.create_client(
            GetCellState, '/cell/get_state'
        )

        self.get_logger().info('AI planner node started')

    def _resolve_object_pose(self, object_id: str, state_response) -> Pose:
        """Look up the latest pose for an object from the cell state."""
        if state_response and state_response.success:
            for obj in state_response.state.detected_objects:
                if obj.object_id == object_id:
                    return obj.pose

        return Pose(
            position=Point(x=0.5, y=0.0, z=0.05),
            orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
        )

    def _parse_goal(self, goal: str) -> tuple[str, str, str | None]:
        """
        Lightweight keyword parser.
        Returns (template_key, target_object_id, destination_name).
        """
        goal_lower = goal.lower()

        target_object = 'red_cube'
        for name in ['red_cube', 'blue_cylinder', 'green_sphere']:
            if name.replace('_', ' ') in goal_lower or name in goal_lower:
                target_object = name
                break

        destination = None
        for loc_name in KNOWN_LOCATIONS:
            if loc_name.replace('_', ' ') in goal_lower or loc_name in goal_lower:
                destination = loc_name
                break

        if 'pick' in goal_lower and 'place' in goal_lower:
            template = 'pick_and_place'
        elif 'pick' in goal_lower or 'grab' in goal_lower or 'grasp' in goal_lower:
            template = 'pick'
        elif 'place' in goal_lower or 'put' in goal_lower:
            template = 'place'
        elif 'inspect' in goal_lower or 'look' in goal_lower or 'check' in goal_lower:
            template = 'inspect'
        else:
            template = 'pick_and_place'

        return template, target_object, destination

    def _handle_generate_plan(self, request, response):
        goal = request.goal_description
        self.get_logger().info(f'Generating plan for goal: "{goal}"')

        cell_state = None
        if self._cell_state_client.service_is_ready():
            future = self._cell_state_client.call_async(GetCellState.Request())
            rclpy.spin_until_future_complete(self, future, timeout_sec=2.0)
            if future.result() is not None:
                cell_state = future.result()

        template_key, target_object, destination = self._parse_goal(goal)
        template = PLAN_TEMPLATES[template_key]

        steps = []
        for i, entry in enumerate(template):
            step = PlanStep()
            step.step_number = i + 1
            step.action = entry['action']
            step.target_object_id = target_object
            step.description = entry['desc']

            if entry['action'] == 'PLACE' and destination and destination in KNOWN_LOCATIONS:
                step.target_pose = Pose(
                    position=KNOWN_LOCATIONS[destination],
                    orientation=Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
                )
            else:
                step.target_pose = self._resolve_object_pose(target_object, cell_state)

            steps.append(step)

        response.steps = steps
        response.success = True
        response.message = (
            f'Generated {len(steps)}-step "{template_key}" plan '
            f'for object "{target_object}"'
        )
        self.get_logger().info(response.message)
        return response


def main(args=None):
    rclpy.init(args=args)
    node = AIPlannerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
