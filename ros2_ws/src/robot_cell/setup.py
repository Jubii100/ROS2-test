from setuptools import find_packages, setup

package_name = 'robot_cell'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/robot_cell.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='mohammed',
    maintainer_email='mohammedjelsiddig@gmail.com',
    description='Generic robot cell simulation for ROS2 test',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'perception_node = robot_cell.perception_node:main',
            'cell_supervisor_node = robot_cell.cell_supervisor_node:main',
            'ai_planner_node = robot_cell.ai_planner_node:main',
        ],
    },
)
