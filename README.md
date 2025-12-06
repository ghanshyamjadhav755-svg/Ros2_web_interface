# AMR WebServer - Developer Documentation

## Project Overview

This project provides a professional web-based remote control interface for ROS2-based Autonomous Mobile Robots (AMRs). It enables real-time control and monitoring of robots through any web browser on the network.

---

## Architecture

### Three-Tier Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Web Browser (Client)                  │
│  - Joystick Control Interface                           │
│  - Real-time Telemetry Display                          │
│  - Laser Scan Visualization                             │
└────────────────┬────────────────────────────────────────┘
                 │ HTTP (Port 8080)
                 │ WebSocket (Port 8765)
                 ▼
┌─────────────────────────────────────────────────────────┐
│              WebSocket Bridge (Python/ROS2)             │
│  - Bidirectional WebSocket Server                       │
│  - ROS2 Topic Publisher/Subscriber                      │
│  - Message Translation (JSON ↔ ROS2)                    │
│  - Safety Features (Deadman Switch)                     │
└────────────────┬────────────────────────────────────────┘
                 │ ROS2 Topics/Services
                 ▼
┌─────────────────────────────────────────────────────────┐
│                    ROS2 AMR System                       │
│  - /cmd_vel (Twist)                                     │
│  - /odom (Odometry)                                     │
│  - /battery_state (BatteryState)                        │
│  - /scan (LaserScan)                                    │
└─────────────────────────────────────────────────────────┘
```

---

## System Flow

### 1. **Initialization Flow**

```
User launches system
    ↓
Launch file starts HTTP Server (port 8080)
    ↓
Launch file starts WebSocket Bridge (port 8765)
    ↓
WebSocket Bridge initializes:
    - ROS2 node
    - Topic publishers/subscribers
    - WebSocket server
    - Telemetry broadcasters
    ↓
System ready for connections
```

### 2. **Client Connection Flow**

```
User opens http://<robot_ip>:8080
    ↓
HTTP Server serves index.html
    ↓
Browser loads JavaScript controller
    ↓
JavaScript initiates WebSocket connection to ws://<robot_ip>:8765
    ↓
WebSocket Bridge accepts connection
    ↓
Connection established - Status indicator turns green
    ↓
Bridge starts broadcasting telemetry at 20Hz
```

### 3. **Control Flow (User moves joystick)**

```
User drags joystick
    ↓
JavaScript calculates velocity (linear, angular)
    ↓
JavaScript sends JSON: {"type": "cmd_vel", "linear": 0.3, "angular": 0.1}
    ↓
WebSocket Bridge receives message
    ↓
Bridge converts to ROS2 Twist message
    ↓
Bridge publishes to /cmd_vel topic
    ↓
AMR receives command and moves
    ↓
AMR publishes odometry to /odom
    ↓
Bridge receives odometry
    ↓
Bridge broadcasts telemetry to all connected clients
    ↓
JavaScript updates UI (velocity display, position)
```

### 4. **Safety Flow (Deadman Switch)**

```
Every 100ms:
    Bridge checks time since last command
        ↓
    If > 500ms and clients connected:
        ↓
    Publish zero velocity (STOP)
    
When WebSocket disconnects:
    ↓
Client removed from active list
    ↓
If no clients remain:
    ↓
Publish zero velocity (STOP)
```

---

## Technology Stack

### Backend
- **Language**: Python 3.10+
- **Framework**: ROS2 Humble
- **WebSocket Library**: websockets 15.x
- **HTTP Server**: aiohttp 3.8+
- **Message Types**: geometry_msgs, nav_msgs, sensor_msgs

### Frontend
- **HTML5** with responsive CSS Grid layout
- **Vanilla JavaScript** (no frameworks)
- **WebSocket API** for real-time communication
- **Canvas API** for laser scan visualization

---

## Project Structure

```
amr_webserver/
├── amr_webserver/                    # Python package
│   ├── __init__.py
│   ├── ros2_websocket_bridge.py     # WebSocket ↔ ROS2 bridge
│   └── http_server.py                # Static file HTTP server
├── launch/
│   ├── webserver.launch.py           # Main launch file
│   └── webserver_debug.launch.py     # Debug version with verbose logging
├── config/
│   └── webserver_params.yaml         # Configuration parameters
├── web/
│   └── index.html                    # Complete web interface
├── resource/
│   └── amr_webserver                 # Resource marker
├── package.xml                       # ROS2 package manifest
├── setup.py                          # Python package setup
└── README.md                         # User documentation
```

---

## Installation & Setup

### Prerequisites

```bash
# ROS2 Humble installation required
# Ubuntu 22.04 recommended

# Install Python dependencies
pip3 install websockets aiohttp
```

### Step-by-Step Installation

1. **Create/Navigate to ROS2 Workspace**
   ```bash
   mkdir -p ~/ros2_ws/src
   cd ~/ros2_ws/src
   ```

2. **Clone or Create Package**
   ```bash
   # If cloning from repository
   git clone <repository_url> amr_webserver
   
   # OR create from scratch
   ros2 pkg create amr_webserver --build-type ament_python \
       --dependencies rclpy geometry_msgs nav_msgs sensor_msgs std_srvs
   ```

3. **Copy Source Files**
   - Place all Python files in `amr_webserver/amr_webserver/`
   - Place launch files in `amr_webserver/launch/`
   - Place config files in `amr_webserver/config/`
   - Place web files in `amr_webserver/web/`

4. **Build the Package**
   ```bash
   cd ~/ros2_ws
   colcon build --packages-select amr_webserver --symlink-install
   source install/setup.bash
   ```

5. **Configure Firewall** (if enabled)
   ```bash
   sudo ufw allow 8080/tcp   # HTTP
   sudo ufw allow 8765/tcp   # WebSocket
   ```

---

## Configuration

### webserver_params.yaml

```yaml
/**:
  ros__parameters:
    # Network
    websocket_port: 8765
    
    # ROS2 Topics
    cmd_vel_topic: '/cmd_vel'        # Command velocity output
    odom_topic: '/odom'              # Odometry input
    battery_topic: '/battery_state'  # Battery status input
    scan_topic: '/scan'              # Laser scan input
    
    # Safety Limits
    max_linear_vel: 0.5              # m/s
    max_angular_vel: 1.0             # rad/s
    
    # Deadman Switch
    deadman_timeout: 0.5             # seconds
```

### Customizing for Your Robot

1. **Topic Names**: Modify topic names to match your robot's namespace
   ```yaml
   cmd_vel_topic: '/robot_name/cmd_vel'
   odom_topic: '/robot_name/odom'
   ```

2. **Velocity Limits**: Adjust based on your robot's capabilities
   ```yaml
   max_linear_vel: 1.0   # Faster robot
   max_angular_vel: 2.0  # More agile turning
   ```

3. **Safety Timeout**: Increase for higher latency networks
   ```yaml
   deadman_timeout: 1.0  # More lenient timeout
   ```

---

## Running the System

### Basic Usage

```bash
# Terminal 1: Launch the web server
cd ~/ros2_ws
source install/setup.bash
ros2 launch amr_webserver webserver.launch.py
```

Access the interface at: `http://<robot_ip>:8080`

### With Debug Logging

```bash
ros2 launch amr_webserver webserver_debug.launch.py
```

### Running Components Separately

```bash
# Terminal 1: WebSocket Bridge only
ros2 run amr_webserver websocket_bridge

# Terminal 2: HTTP Server only
ros2 run amr_webserver http_server
```

### Testing with TurtleSim

```bash
# Terminal 1: Start TurtleSim
ros2 run turtlesim turtlesim_node

# Terminal 2: Launch web server
cd ~/ros2_ws
source install/setup.bash
ros2 launch amr_webserver webserver.launch.py

# Terminal 3: Monitor commands (optional)
ros2 topic echo /cmd_vel
```

Open browser → `http://localhost:8080` → Control the turtle with joystick!

---

## Development Workflow

### Code Organization

**ros2_websocket_bridge.py**
- `ROS2WebSocketBridge` class: Main bridge node
- `handle_client()`: WebSocket connection handler
- `process_message()`: Parse and route incoming JSON commands
- `publish_cmd_vel()`: Publish velocity with safety limits
- `broadcast_telemetry()`: Send robot state to all clients
- `deadman_check()`: Safety timeout monitoring

**http_server.py**
- `HTTPServer` class: Static file server
- `get_web_directory()`: Locate web files
- `index_handler()`: Serve index.html
- Fallback HTML if files missing

**index.html**
- `AMRController` class: Main JavaScript controller
- `connect()`: WebSocket connection management
- `initJoystick()`: Touch/mouse joystick controls
- `sendCommand()`: Send velocity to robot
- `updateTelemetry()`: Update UI from robot data
- `drawLaserScan()`: Visualize laser data

### Adding New Features

#### Example: Add Camera Stream

1. **Backend (ros2_websocket_bridge.py)**
   ```python
   from sensor_msgs.msg import CompressedImage
   import base64
   
   def __init__(self):
       # ... existing code ...
       self.image_sub = self.create_subscription(
           CompressedImage,
           '/camera/image_raw/compressed',
           self.image_callback,
           sensor_qos
       )
   
   def image_callback(self, msg: CompressedImage):
       img_b64 = base64.b64encode(msg.data).decode('utf-8')
       telemetry_data = {
           'type': 'camera',
           'data': img_b64,
           'format': msg.format
       }
       # Broadcast to clients
   ```

2. **Frontend (index.html)**
   ```javascript
   // Add to updateTelemetry()
   if (msg.type === 'camera') {
       const img = document.getElementById('cameraFeed');
       img.src = 'data:image/jpeg;base64,' + msg.data;
   }
   ```

---

## API Reference

### WebSocket Protocol

#### Client → Server Messages

**Velocity Command**
```json
{
    "type": "cmd_vel",
    "linear": 0.5,    // m/s
    "angular": 0.3    // rad/s
}
```

**Emergency Stop**
```json
{
    "type": "emergency_stop"
}
```

**Ping (Keepalive)**
```json
{
    "type": "ping"
}
```

#### Server → Client Messages

**Telemetry Data** (20Hz)
```json
{
    "type": "telemetry",
    "data": {
        "timestamp": 1234567890.123,
        "position": {
            "x": 1.5,
            "y": 2.3,
            "z": 0.0
        },
        "velocity": {
            "linear": 0.2,
            "angular": 0.1
        },
        "battery_percentage": 85.5,
        "battery_voltage": 24.3,
        "laser_scan_ranges": [1.2, 1.5, 2.0, ...],
        "connection_count": 2
    }
}
```

**Emergency Stop Acknowledgment**
```json
{
    "type": "estop_ack"
}
```

**Pong (Keepalive Response)**
```json
{
    "type": "pong"
}
```

---

## Troubleshooting

### Port Already in Use

```bash
# Find process using port
sudo lsof -i :8080
sudo lsof -i :8765

# Kill process
sudo lsof -ti:8080 | xargs kill -9
```

### WebSocket Connection Failed

1. **Check firewall**
   ```bash
   sudo ufw status
   sudo ufw allow 8765/tcp
   ```

2. **Verify WebSocket server is running**
   ```bash
   sudo netstat -tulpn | grep 8765
   ```

3. **Check browser console** (F12 → Console tab)

### Blank Web Page

1. **Verify index.html exists**
   ```bash
   ls -la ~/ros2_ws/src/amr_webserver/web/index.html
   ls -la ~/ros2_ws/install/amr_webserver/share/amr_webserver/web/
   ```

2. **Check file size** (should be ~17KB)
   ```bash
   ls -lh ~/ros2_ws/src/amr_webserver/web/index.html
   ```

3. **Test with curl**
   ```bash
   curl http://localhost:8080 | head -50
   ```

### Type Errors in Messages

Ensure explicit type conversion:
```python
linear = float(data.get('linear', 0.0))
angular = float(data.get('angular', 0.0))
```

### Topics Not Publishing

```bash
# Check if topics exist
ros2 topic list

# Monitor specific topic
ros2 topic echo /cmd_vel

# Check topic info
ros2 topic info /cmd_vel
```

---

## Performance Considerations

### Telemetry Rate
- Default: 20Hz (50ms interval)
- Configurable in `broadcast_telemetry()` timer
- Balance between responsiveness and network load

### Laser Scan Downsampling
- Full scans can be 360+ points
- Downsampled to ~180 points for web transmission
- Adjustable in `scan_callback()`

### Connection Limits
- No hard limit on concurrent connections
- Each connection receives full telemetry stream
- Monitor system resources with many clients

---

## Security Considerations

### Production Deployment

1. **SSL/TLS for WebSocket**
   ```python
   import ssl
   ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
   ssl_context.load_cert_chain('cert.pem', 'key.pem')
   
   async with websockets.serve(
       self.handle_client, 
       '0.0.0.0', 
       self.ws_port,
       ssl=ssl_context
   ):
   ```

2. **Authentication**
   - Add token-based authentication
   - Implement user session management
   - Add login page before control interface

3. **Rate Limiting**
   - Limit command frequency per client
   - Prevent DoS attacks

4. **Input Validation**
   - Already implemented: velocity limits
   - Add additional bounds checking
   - Sanitize all user inputs

---

## Testing

### Unit Testing

```bash
# Run package tests
cd ~/ros2_ws
colcon test --packages-select amr_webserver
colcon test-result --verbose
```

### Manual Testing Checklist

- [ ] HTTP server starts successfully
- [ ] WebSocket server starts successfully
- [ ] Web page loads correctly
- [ ] Status indicator turns green (connected)
- [ ] Joystick responds to input
- [ ] Velocity values update in real-time
- [ ] Stop button halts motion
- [ ] Emergency stop works
- [ ] Telemetry updates continuously
- [ ] Multiple clients can connect
- [ ] Deadman switch stops robot
- [ ] Connection loss stops robot

### Network Testing

```bash
# Test from another machine
curl http://<robot_ip>:8080

# WebSocket test with wscat
npm install -g wscat
wscat -c ws://<robot_ip>:8765
```

---

## Future Enhancements

### Planned Features
- [ ] Authentication system
- [ ] Multi-robot control
- [ ] Camera stream integration
- [ ] Path planning visualization
- [ ] Mission waypoint editor
- [ ] Data logging and playback
- [ ] Mobile app wrapper (React Native)
- [ ] Voice control integration
- [ ] Gamepad/controller support
- [ ] Augmented reality view

### Contributing

When contributing:
1. Follow PEP 8 for Python code
2. Use meaningful commit messages
3. Test on both localhost and network
4. Update documentation
5. Maintain backward compatibility

---

## Support & Contact

For issues, questions, or contributions:
- GitHub Issues: [repository_url]/issues
- ROS Discourse: discourse.ros.org
- Email: your_email@example.com

---

## License

Apache 2.0 - See LICENSE file for details

---

## Acknowledgments

Built for professional robotics applications with:
- ROS2 Humble
- Python websockets library
- Modern web standards (ES6+)

Designed for production use in industrial, research, and educational robotics.
