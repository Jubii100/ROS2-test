from setuptools import find_packages, setup

package_name = 'cell_sim'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/cell_sim.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='mohammed',
    maintainer_email='mohammedjelsiddig@gmail.com',
    description='Simulated robot cell: perception + state aggregation',
    license='TODO: License declaration',
    extras_require={
        'test': [
            'pytest',
        ],
    },
    entry_points={
        'console_scripts': [
            'sensor_sim_node = cell_sim.sensor_sim_node:main',
            'cell_state_node = cell_sim.cell_state_node:main',
            'api_server = cell_sim.api.app:start_server',
        ],
    },
)
