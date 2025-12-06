from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import ExecuteProcess
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    config_path = os.path.join(
        get_package_share_directory('amr_webserver'),
        'config',
        'webserver_params.yaml'
    )
    
    return LaunchDescription([
        # WebSocket Bridge Node
        Node(
            package='amr_webserver',
            executable='websocket_bridge',
            name='websocket_bridge',
            parameters=[config_path],
            output='screen',
            emulate_tty=True,
        ),
        
        # HTTP Server Process
        ExecuteProcess(
            cmd=['ros2', 'run', 'amr_webserver', 'http_server'],
            output='screen',
        ),
    ])