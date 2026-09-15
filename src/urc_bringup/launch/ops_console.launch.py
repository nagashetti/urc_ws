from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        Node(
            package='urc_rover_sim',
            executable='rover_sim',
            name='rover_sim',
            output='screen',
        ),
        Node(
            package='urc_ops_console',
            executable='ops_console',
            name='ops_console',
            output='screen',
        ),
    ])
