# A single step in a robot action plan
int32 step_number
string action                               # e.g. MOVE, PICK, PLACE, INSPECT
string target_object_id
geometry_msgs/Pose target_pose
string description
