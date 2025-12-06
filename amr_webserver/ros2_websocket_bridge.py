#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState, LaserScan, CompressedImage
from std_srvs.srv import Empty
import cv2
import base64
import numpy as np

import asyncio
import websockets
import json
import threading
from typing import Dict, Set
from dataclasses import dataclass, asdict
import math

@dataclass
class TelemetryData:
    timestamp: float
    position: Dict[str, float]
    velocity: Dict[str, float]
    battery_percentage: float
    battery_voltage: float
    laser_scan_ranges: list
    connection_count: int

class ROS2WebSocketBridge(Node):
    def __init__(self):
        super().__init__('ros2_websocket_bridge')
        
        # Declare parameters
        self.declare_parameter('websocket_port', 8765)
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('odom_topic', '/odom')
        self.declare_parameter('battery_topic', '/battery_state')
        self.declare_parameter('scan_topic', '/scan')
        self.declare_parameter('camera_topic', '/camera/image_raw/compressed')  # Or /image_raw if uncompressed
        self.declare_parameter('max_linear_vel', 0.5)
        self.declare_parameter('max_angular_vel', 1.0)
        
        # Get parameters
        self.ws_port = self.get_parameter('websocket_port').value
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').value
        self.odom_topic = self.get_parameter('odom_topic').value
        self.battery_topic = self.get_parameter('battery_topic').value
        self.scan_topic = self.get_parameter('scan_topic').value
        self.camera_topic = self.get_parameter('camera_topic').value
        self.max_lin_vel = self.get_parameter('max_linear_vel').value
        self.max_ang_vel = self.get_parameter('max_angular_vel').value
        
        # Start time for uptime
        self.start_time = self.get_clock().now()
        
        # QoS profiles
        sensor_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
            depth=10
        )
        
        reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
            depth=10
        )
        
        # Publishers
        self.cmd_vel_pub = self.create_publisher(
            Twist,
            self.cmd_vel_topic,
            reliable_qos
        )
        
        # Subscribers
        self.odom_sub = self.create_subscription(
            Odometry,
            self.odom_topic,
            self.odom_callback,
            sensor_qos
        )
        
        self.battery_sub = self.create_subscription(
            BatteryState,
            self.battery_topic,
            self.battery_callback,
            sensor_qos
        )
        
        self.scan_sub = self.create_subscription(
            LaserScan,
            self.scan_topic,
            self.scan_callback,
            sensor_qos
        )
        
        self.camera_sub = self.create_subscription(
            CompressedImage,
            self.camera_topic,
            self.camera_callback,
            sensor_qos
        )
        
        # Service clients
        self.estop_client = self.create_client(Empty, '/emergency_stop')
        
        # Telemetry data
        self.telemetry = TelemetryData(
            timestamp=0.0,
            position={'x': 0.0, 'y': 0.0, 'theta': 0.0},
            velocity={'linear': 0.0, 'angular': 0.0},
            battery_percentage=0.0,
            battery_voltage=0.0,
            laser_scan_ranges=[],
            connection_count=0
        )
        
        # Camera timer (throttle to 10Hz)
        self.camera_timer = self.create_timer(0.1, self.broadcast_camera)
        self.last_camera_data = None
        
        # WebSocket connections
        self.ws_clients: Set[websockets.WebSocketServerProtocol] = set()
        self.ws_lock = threading.Lock()
        
        # Deadman switch timer
        self.last_cmd_time = self.get_clock().now()
        self.deadman_timeout = 0.5  # seconds
        self.create_timer(0.1, self.deadman_check)
        
        # Telemetry broadcast timer
        self.create_timer(0.05, self.broadcast_telemetry)  # 20Hz
        
        self.get_logger().info(f'ROS2 WebSocket Bridge initialized on port {self.ws_port}')
    
    def quaternion_to_yaw(self, x: float, y: float, z: float, w: float) -> float:
        """Convert quaternion to yaw angle"""
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return yaw
    
    def odom_callback(self, msg: Odometry):
        self.telemetry.position = {
            'x': msg.pose.pose.position.x,
            'y': msg.pose.pose.position.y,
            'theta': self.quaternion_to_yaw(
                msg.pose.pose.orientation.x,
                msg.pose.pose.orientation.y,
                msg.pose.pose.orientation.z,
                msg.pose.pose.orientation.w
            )
        }
        self.telemetry.velocity = {
            'linear': msg.twist.twist.linear.x,
            'angular': msg.twist.twist.angular.z
        }
        self.telemetry.timestamp = self.get_clock().now().nanoseconds / 1e9
    
    def battery_callback(self, msg: BatteryState):
        self.telemetry.battery_percentage = msg.percentage * 100.0 if msg.percentage is not None else 0.0
        self.telemetry.battery_voltage = msg.voltage if msg.voltage is not None else 0.0
    
    def scan_callback(self, msg: LaserScan):
        # Downsample laser scan for web transmission
        step = max(1, len(msg.ranges) // 180)
        # Convert to list and filter out inf/nan values
        self.telemetry.laser_scan_ranges = [
            float(r) if not (math.isinf(r) or math.isnan(r)) else 10.0 
            for r in msg.ranges[::step]
        ]
    
    def camera_callback(self, msg: CompressedImage):
        # Decode compressed image
        np_arr = np.frombuffer(msg.data, np.uint8)
        image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
        if image is not None:
            # Resize if too large (optional, for bandwidth)
            height, width = image.shape[:2]
            if height > 480 or width > 640:
                scale = min(480/height, 640/width)
                new_height, new_width = int(height * scale), int(width * scale)
                image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
            
            # Encode to JPEG base64
            _, buffer = cv2.imencode('.jpg', image, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            self.last_camera_data = base64.b64encode(buffer).decode('utf-8')
    
    def broadcast_camera(self):
        """Broadcast camera feed to all connected clients (throttled)"""
        if not self.last_camera_data or not self.ws_clients:
            return
        
        camera_msg = {
            'type': 'camera',
            'data': self.last_camera_data
        }
        camera_json = json.dumps(camera_msg)
        
        with self.ws_lock:
            clients_copy = list(self.ws_clients)
        
        disconnected = set()
        for client in clients_copy:
            try:
                asyncio.run_coroutine_threadsafe(
                    client.send(camera_json),
                    self.ws_loop
                ).result(timeout=0.1)
            except Exception as e:
                self.get_logger().warn(f'Failed to send camera: {e}')
                disconnected.add(client)
        
        with self.ws_lock:
            self.ws_clients -= disconnected
    
    def deadman_check(self):
        """Stop robot if no command received within timeout"""
        elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
        if elapsed > self.deadman_timeout and len(self.ws_clients) > 0:
            self.publish_cmd_vel(0.0, 0.0)
    
    def publish_cmd_vel(self, linear: float, angular: float):
        """Publish velocity command with safety limits"""
        cmd = Twist()
        cmd.linear.x = max(-self.max_lin_vel, min(self.max_lin_vel, linear))
        cmd.angular.z = max(-self.max_ang_vel, min(self.max_ang_vel, angular))
        self.cmd_vel_pub.publish(cmd)
        self.last_cmd_time = self.get_clock().now()
    
    def broadcast_telemetry(self):
        """Broadcast telemetry to all connected clients"""
        if not self.ws_clients:
            return
        
        now = self.get_clock().now()
        uptime = (now - self.start_time).nanoseconds / 1e9
        
        with self.ws_lock:
            self.telemetry.connection_count = len(self.ws_clients)
            clients_copy = list(self.ws_clients)
        
        # Prepare messages
        status_msg = {
            'type': 'status',
            'battery': float(self.telemetry.battery_percentage),
            'voltage': float(self.telemetry.battery_voltage),
            'uptime': uptime,
            'position': {
                'x': float(self.telemetry.position['x']),
                'y': float(self.telemetry.position['y']),
                'theta': float(self.telemetry.position['theta'])
            },
            'velocity': {
                'linear': float(self.telemetry.velocity['linear']),
                'angular': float(self.telemetry.velocity['angular'])
            }
        }
        
        clients_msg = {
            'type': 'clients',
            'count': int(self.telemetry.connection_count)
        }
        
        lidar_msg = {
            'type': 'lidar',
            'data': [float(d) for d in self.telemetry.laser_scan_ranges]
        }
        
        status_json = json.dumps(status_msg)
        clients_json = json.dumps(clients_msg)
        lidar_json = json.dumps(lidar_msg)
        
        # Send to all clients
        disconnected = set()
        for client in clients_copy:
            try:
                asyncio.run_coroutine_threadsafe(
                    client.send(status_json),
                    self.ws_loop
                ).result(timeout=0.1)
                
                asyncio.run_coroutine_threadsafe(
                    client.send(clients_json),
                    self.ws_loop
                ).result(timeout=0.1)
                
                asyncio.run_coroutine_threadsafe(
                    client.send(lidar_json),
                    self.ws_loop
                ).result(timeout=0.1)
            except Exception as e:
                self.get_logger().warn(f'Failed to send telemetry: {e}')
                disconnected.add(client)
        
        # Remove disconnected clients
        with self.ws_lock:
            self.ws_clients -= disconnected
    
    async def handle_client(self, websocket):
        """Handle WebSocket client connection"""
        with self.ws_lock:
            self.ws_clients.add(websocket)
        
        try:
            client_addr = websocket.remote_address
            self.get_logger().info(f'Client connected: {client_addr}')
        except:
            self.get_logger().info(f'Client connected')
        
        try:
            async for message in websocket:
                await self.process_message(message, websocket)
        except Exception as e:
            self.get_logger().info(f'Client disconnected: {e}')
        finally:
            with self.ws_lock:
                self.ws_clients.discard(websocket)
            # Stop robot when last client disconnects
            with self.ws_lock:
                if not self.ws_clients:
                    self.publish_cmd_vel(0.0, 0.0)
    
    async def process_message(self, message: str, websocket):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')
            
            if msg_type == 'velocity' or msg_type == 'cmd_vel':
                # Explicitly convert to float to ensure type compatibility
                linear = float(data.get('linear', 0.0))
                angular = float(data.get('angular', 0.0))
                self.publish_cmd_vel(linear, angular)
                
            elif msg_type == 'estop' or msg_type == 'emergency_stop':
                self.publish_cmd_vel(0.0, 0.0)
                if self.estop_client.server_is_ready():
                    req = Empty.Request()
                    future = self.estop_client.call_async(req)
                    # Optionally wait for response if needed
                await websocket.send(json.dumps({'type': 'estop_ack'}))
                
            elif msg_type == 'stop':
                self.publish_cmd_vel(0.0, 0.0)
                
            elif msg_type == 'max_speed':
                self.max_lin_vel = float(data.get('value', self.max_lin_vel))
                
            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))
                
        except json.JSONDecodeError:
            self.get_logger().error(f'Invalid JSON: {message}')
        except (ValueError, TypeError) as e:
            self.get_logger().error(f'Invalid data type in message: {e}')
        except Exception as e:
            self.get_logger().error(f'Error processing message: {e}')
    
    async def websocket_server(self):
        """Start WebSocket server"""
        try:
            async with websockets.serve(self.handle_client, '0.0.0.0', self.ws_port):
                self.get_logger().info(f'WebSocket server started on ws://0.0.0.0:{self.ws_port}')
                await asyncio.Future()  # Run forever
        except Exception as e:
            self.get_logger().error(f'WebSocket server error: {e}')
    
    def start_websocket_server(self):
        """Start WebSocket server in separate thread"""
        self.ws_loop = asyncio.new_event_loop()
        
        def run_server():
            asyncio.set_event_loop(self.ws_loop)
            self.ws_loop.run_until_complete(self.websocket_server())
        
        ws_thread = threading.Thread(target=run_server, daemon=True)
        ws_thread.start()

def main(args=None):
    rclpy.init(args=args)
    
    bridge = ROS2WebSocketBridge()
    bridge.start_websocket_server()
    
    try:
        rclpy.spin(bridge)
    except KeyboardInterrupt:
        pass
    finally:
        bridge.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()


    
# #!/usr/bin/env python3

# import rclpy
# from rclpy.node import Node
# from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
# from geometry_msgs.msg import Twist
# from nav_msgs.msg import Odometry
# from sensor_msgs.msg import BatteryState, LaserScan
# from std_srvs.srv import Empty

# import asyncio
# import websockets
# import json
# import threading
# from typing import Dict, Set
# from dataclasses import dataclass, asdict

# @dataclass
# class TelemetryData:
#     timestamp: float
#     position: Dict[str, float]
#     velocity: Dict[str, float]
#     battery_percentage: float
#     battery_voltage: float
#     laser_scan_ranges: list
#     connection_count: int

# class ROS2WebSocketBridge(Node):
#     def __init__(self):
#         super().__init__('ros2_websocket_bridge')
        
#         # Declare parameters
#         self.declare_parameter('websocket_port', 8765)
#         self.declare_parameter('cmd_vel_topic', '/cmd_vel')
#         self.declare_parameter('odom_topic', '/odom')
#         self.declare_parameter('battery_topic', '/battery_state')
#         self.declare_parameter('scan_topic', '/scan')
#         self.declare_parameter('max_linear_vel', 0.5)
#         self.declare_parameter('max_angular_vel', 1.0)
        
#         # Get parameters
#         self.ws_port = self.get_parameter('websocket_port').value
#         self.max_lin_vel = self.get_parameter('max_linear_vel').value
#         self.max_ang_vel = self.get_parameter('max_angular_vel').value
        
#         # QoS profiles
#         sensor_qos = QoSProfile(
#             reliability=ReliabilityPolicy.BEST_EFFORT,
#             durability=DurabilityPolicy.VOLATILE,
#             depth=10
#         )
        
#         reliable_qos = QoSProfile(
#             reliability=ReliabilityPolicy.RELIABLE,
#             durability=DurabilityPolicy.VOLATILE,
#             depth=10
#         )
        
#         # Publishers
#         self.cmd_vel_pub = self.create_publisher(
#             Twist,
#             self.get_parameter('cmd_vel_topic').value,
#             reliable_qos
#         )
        
#         # Subscribers
#         self.odom_sub = self.create_subscription(
#             Odometry,
#             self.get_parameter('odom_topic').value,
#             self.odom_callback,
#             sensor_qos
#         )
        
#         self.battery_sub = self.create_subscription(
#             BatteryState,
#             self.get_parameter('battery_topic').value,
#             self.battery_callback,
#             sensor_qos
#         )
        
#         self.scan_sub = self.create_subscription(
#             LaserScan,
#             self.get_parameter('scan_topic').value,
#             self.scan_callback,
#             sensor_qos
#         )
        
#         # Service clients
#         self.estop_client = self.create_client(Empty, '/emergency_stop')
        
#         # Telemetry data
#         self.telemetry = TelemetryData(
#             timestamp=0.0,
#             position={'x': 0.0, 'y': 0.0, 'z': 0.0},
#             velocity={'linear': 0.0, 'angular': 0.0},
#             battery_percentage=0.0,
#             battery_voltage=0.0,
#             laser_scan_ranges=[],
#             connection_count=0
#         )
        
#         # WebSocket connections
#         self.ws_clients: Set[websockets.WebSocketServerProtocol] = set()
#         self.ws_lock = threading.Lock()
        
#         # Deadman switch timer
#         self.last_cmd_time = self.get_clock().now()
#         self.deadman_timeout = 0.5  # seconds
#         self.create_timer(0.1, self.deadman_check)
        
#         # Telemetry broadcast timer
#         self.create_timer(0.05, self.broadcast_telemetry)  # 20Hz
        
#         self.get_logger().info(f'ROS2 WebSocket Bridge initialized on port {self.ws_port}')
    
#     def odom_callback(self, msg: Odometry):
#         self.telemetry.position = {
#             'x': msg.pose.pose.position.x,
#             'y': msg.pose.pose.position.y,
#             'z': msg.pose.pose.position.z
#         }
#         self.telemetry.velocity = {
#             'linear': msg.twist.twist.linear.x,
#             'angular': msg.twist.twist.angular.z
#         }
#         self.telemetry.timestamp = self.get_clock().now().nanoseconds / 1e9
    
#     def battery_callback(self, msg: BatteryState):
#         self.telemetry.battery_percentage = msg.percentage * 100.0
#         self.telemetry.battery_voltage = msg.voltage
    
#     def scan_callback(self, msg: LaserScan):
#         # Downsample laser scan for web transmission
#         step = max(1, len(msg.ranges) // 180)
#         # Convert to list and filter out inf/nan values
#         self.telemetry.laser_scan_ranges = [
#             float(r) if not (r == float('inf') or r != r) else 10.0 
#             for r in msg.ranges[::step]
#         ]
    
#     def deadman_check(self):
#         """Stop robot if no command received within timeout"""
#         elapsed = (self.get_clock().now() - self.last_cmd_time).nanoseconds / 1e9
#         if elapsed > self.deadman_timeout and len(self.ws_clients) > 0:
#             self.publish_cmd_vel(0.0, 0.0)
    
#     def publish_cmd_vel(self, linear: float, angular: float):
#         """Publish velocity command with safety limits"""
#         cmd = Twist()
#         cmd.linear.x = max(-self.max_lin_vel, min(self.max_lin_vel, linear))
#         cmd.angular.z = max(-self.max_ang_vel, min(self.max_ang_vel, angular))
#         self.cmd_vel_pub.publish(cmd)
#         self.last_cmd_time = self.get_clock().now()
    
#     def broadcast_telemetry(self):
#         """Broadcast telemetry to all connected clients"""
#         if not self.ws_clients:
#             return
        
#         with self.ws_lock:
#             self.telemetry.connection_count = len(self.ws_clients)
            
#             # Create telemetry dict with proper type conversion
#             telemetry_dict = {
#                 'timestamp': float(self.telemetry.timestamp),
#                 'position': {
#                     'x': float(self.telemetry.position['x']),
#                     'y': float(self.telemetry.position['y']),
#                     'z': float(self.telemetry.position['z'])
#                 },
#                 'velocity': {
#                     'linear': float(self.telemetry.velocity['linear']),
#                     'angular': float(self.telemetry.velocity['angular'])
#                 },
#                 'battery_percentage': float(self.telemetry.battery_percentage),
#                 'battery_voltage': float(self.telemetry.battery_voltage),
#                 'laser_scan_ranges': list(self.telemetry.laser_scan_ranges),  # Ensure it's a list
#                 'connection_count': int(self.telemetry.connection_count)
#             }
            
#             telemetry_json = json.dumps({
#                 'type': 'telemetry',
#                 'data': telemetry_dict
#             })
            
#             # Send to all clients
#             disconnected = set()
#             for client in self.ws_clients:
#                 try:
#                     asyncio.run_coroutine_threadsafe(
#                         client.send(telemetry_json),
#                         self.ws_loop
#                     )
#                 except Exception as e:
#                     self.get_logger().warn(f'Failed to send telemetry: {e}')
#                     disconnected.add(client)
            
#             # Remove disconnected clients
#             self.ws_clients -= disconnected
    
#     async def handle_client(self, websocket):
#         """Handle WebSocket client connection"""
#         with self.ws_lock:
#             self.ws_clients.add(websocket)
        
#         try:
#             client_addr = websocket.remote_address
#             self.get_logger().info(f'Client connected: {client_addr}')
#         except:
#             self.get_logger().info(f'Client connected')
        
#         try:
#             async for message in websocket:
#                 await self.process_message(message, websocket)
#         except Exception as e:
#             self.get_logger().info(f'Client disconnected: {e}')
#         finally:
#             with self.ws_lock:
#                 self.ws_clients.discard(websocket)
#             # Stop robot when last client disconnects
#             if not self.ws_clients:
#                 self.publish_cmd_vel(0.0, 0.0)
    
#     async def process_message(self, message: str, websocket):
#         """Process incoming WebSocket message"""
#         try:
#             data = json.loads(message)
#             msg_type = data.get('type')
            
#             if msg_type == 'cmd_vel':
#                 # Explicitly convert to float to ensure type compatibility
#                 linear = float(data.get('linear', 0.0))
#                 angular = float(data.get('angular', 0.0))
#                 self.publish_cmd_vel(linear, angular)
                
#             elif msg_type == 'emergency_stop':
#                 self.publish_cmd_vel(0.0, 0.0)
#                 if self.estop_client.service_is_ready():
#                     req = Empty.Request()
#                     self.estop_client.call_async(req)
#                 await websocket.send(json.dumps({'type': 'estop_ack'}))
                
#             elif msg_type == 'ping':
#                 await websocket.send(json.dumps({'type': 'pong'}))
                
#         except json.JSONDecodeError:
#             self.get_logger().error(f'Invalid JSON: {message}')
#         except (ValueError, TypeError) as e:
#             self.get_logger().error(f'Invalid data type in message: {e}')
#         except Exception as e:
#             self.get_logger().error(f'Error processing message: {e}')
    
#     async def websocket_server(self):
#         """Start WebSocket server"""
#         try:
#             async with websockets.serve(self.handle_client, '0.0.0.0', self.ws_port):
#                 self.get_logger().info(f'WebSocket server started on ws://0.0.0.0:{self.ws_port}')
#                 await asyncio.Future()  # Run forever
#         except Exception as e:
#             self.get_logger().error(f'WebSocket server error: {e}')
    
#     def start_websocket_server(self):
#         """Start WebSocket server in separate thread"""
#         self.ws_loop = asyncio.new_event_loop()
        
#         def run_server():
#             asyncio.set_event_loop(self.ws_loop)
#             self.ws_loop.run_until_complete(self.websocket_server())
        
#         ws_thread = threading.Thread(target=run_server, daemon=True)
#         ws_thread.start()

# def main(args=None):
#     rclpy.init(args=args)
    
#     bridge = ROS2WebSocketBridge()
#     bridge.start_websocket_server()
    
#     try:
#         rclpy.spin(bridge)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         bridge.destroy_node()
#         rclpy.shutdown()

# if __name__ == '__main__':
#     main()