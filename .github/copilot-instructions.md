# AMR WebServer - AI Agent Instructions

This document guides AI agents working on the **amr_webserver** ROS2-based remote control platform. The system enables real-time web browser control of autonomous mobile robots via WebSocket bridges and ROS2 messaging.

---

## Architecture Overview

### Three-Tier System
1. **Frontend** (`web/index.html`): Vanilla JavaScript with canvas-based joystick and telemetry UI
2. **Backend Bridge** (`ros2_websocket_bridge.py`): Python async WebSocket server translating JSON ↔ ROS2 messages
3. **ROS2 System**: Autonomous robot middleware (odometry, battery, lidar, camera topics)

### Critical Data Flows

**Control Input Path:**
- User drags joystick → JavaScript calculates linear/angular velocity → WebSocket JSON → ROS2 Twist message → `/cmd_vel` topic

**Telemetry Broadcast Path (20Hz loop):**
- ROS2 subscribers collect `/odom`, `/battery_state`, `/scan`, `/camera/image_raw/compressed`
- Bridge constructs telemetry object with position, velocity, battery %, laser ranges
- WebSocket broadcasts JSON to all connected clients simultaneously

**Safety Critical - Deadman Switch:**
- Bridge monitors 500ms timeout since last client command
- If timeout exceeded AND clients still connected: publish zero velocity to `/cmd_vel`
- If all clients disconnect: immediate zero velocity publish + cleanup

---

## Project Structure & Key Files

```
amr_webserver/
├── amr_webserver/
│   ├── ros2_websocket_bridge.py      # Primary: WebSocket server + ROS2 node
│   ├── ros2_websocket_bridge_enhanced.py  # Extended version with URDF/map support
│   ├── http_server.py                # Serves index.html on port 8080
│   └── utils/                        # Helper utilities
├── launch/
│   ├── webserver.launch.py           # Standard launch (use this)
│   └── webserver_enhanced.launch.py  # With URDF/map (experimental)
├── config/
│   └── webserver_params.yaml         # Topic names, ports, velocity limits
├── web/
│   └── index.html                    # Single-file UI (see UI Architecture below)
└── test/                             # Minimal pytest tests
```

---

## Technology Stack & Versioning

| Component | Version/Library | Notes |
|-----------|-----------------|-------|
| **Python** | 3.10+ | ROS2 requirement |
| **ROS2** | Humble | Ubuntu 22.04 target |
| **WebSocket** | websockets 15.x | Async `asyncio`-based |
| **HTTP Server** | aiohttp 3.8+ | Handles static file serving |
| **Frontend** | Vanilla JS, no frameworks | ~800 lines single HTML file |
| **Message Types** | geometry_msgs, sensor_msgs | Standard ROS2 types |

---

## Development Workflows

### Running the System Locally

```bash
# Terminal 1: Start ROS2 robot simulation/actual hardware
ros2 launch <robot_pkg> <launch_file>

# Terminal 2: Start AMR WebServer
cd ~/ros2_ws
colcon build --packages-select amr_webserver
source install/setup.bash
ros2 launch amr_webserver webserver.launch.py

# Terminal 3: Monitor WebSocket activity
ros2 topic echo /cmd_vel
```

### Common Commands

```bash
# Rebuild after Python changes (no rebuilds needed, but required for setup.py changes)
colcon build --packages-select amr_webserver --cmake-args -DCMAKE_BUILD_TYPE=Debug

# Check ROS2 parameter overrides
ros2 param list /websocket_bridge
ros2 param get /websocket_bridge websocket_port

# Test WebSocket connection manually
python3 -c "
import asyncio, websockets, json
async def test():
    async with websockets.connect('ws://localhost:8765') as ws:
        await ws.send(json.dumps({'type': 'ping'}))
        print(await ws.recv())
asyncio.run(test())
"
```

### Debugging Tips

- **WebSocket not connecting?** Check firewall (port 8765), verify bridge running: `ros2 node list | grep websocket`
- **Joystick non-responsive?** Browser console shows errors. Check `/cmd_vel` publishes: `ros2 topic hz /cmd_vel`
- **Telemetry not updating?** Verify topic names match `config/webserver_params.yaml`; check QoS policies align with robot's subscribers

---

## Frontend UI Architecture (`web/index.html`)

### Structure
**Single-file design (2000+ lines):**
- **Inline CSS**: Grid layout (320px sidebar | 1fr center | 400px right panel)
- **Inline JavaScript**: `AMRController` class manages WebSocket + DOM updates
- **Canvas-based Visualization**: Laser scan rendered to `<canvas>` with polar coordinates

### Key UI Components

**Joystick Logic** (`initJoystick` method):
- Circular base (280px diameter), draggable stick (100px diameter)
- Constraints: stick limited to 90px radius from center
- Velocity calculation: `-y/maxDist * maxLinearVel` for forward, `-x/maxDist * maxAngularVel` for rotation
- Touch + mouse events both supported

**Laser Scan Visualization** (`drawLidar` method):
- Uses polar coordinate transform: `x = centerX + cos(angle) * radius`
- Grid lines at 0.5m intervals up to 5m max range
- **Robot orientation awareness**: Canvas rotated by `robotTheta` from odometry
- Obstacle highlighting: red arrows for points < 1m distance

**Telemetry Updates** (`handleMessage` method):
- Subscribes to 6 message types: `status`, `clients`, `camera`, `lidar`, `pong`
- Battery visualization: green (>50%) → orange (20-50%) → red (<20%)
- Position display: X, Y, Theta updated from `/odom`

### WebSocket Message Protocol

**Client → Server (JavaScript sends):**
```json
{"type": "velocity", "linear": 0.3, "angular": 0.1}
{"type": "max_speed", "value": 0.5}
{"type": "estop"}
{"type": "stop"}
{"type": "ping"}
```

**Server → Client (Bridge broadcasts):**
```json
{"type": "status", "battery": 75, "voltage": 24.5, "uptime": 3600, "position": {"x": 1.2, "y": 0.5, "theta": 0.785}, "velocity": {"linear": 0.2, "angular": 0.1}}
{"type": "camera", "data": "base64_jpeg_string"}
{"type": "lidar", "data": [0.5, 0.52, 0.51, ...]}
{"type": "clients", "count": 2}
```

---

## Backend Bridge Architecture (`ros2_websocket_bridge.py`)

### ROS2 Node Structure

**Initialization:**
1. Declares 8 parameters (ports, topic names, velocity limits)
2. Creates 4 subscribers (odom, battery, scan, camera) with `BEST_EFFORT` QoS
3. Creates 1 publisher (`cmd_vel`) with `RELIABLE` QoS
4. Spawns async WebSocket server on port 8765

**Callback Pattern:**
- Each ROS2 callback (`odom_callback`, `battery_callback`, etc.) stores latest data in class attributes
- `broadcast_telemetry()` packs all current data into single JSON, sends to all connected clients every 50ms (20Hz)

**WebSocket Message Handling:**
- `handle_client()` runs async loop for each connection
- Validates message type; routes to velocity handler, estop handler, etc.
- **Deadman switch**: Background task checks `time.time() - last_cmd_time > 0.5` every 100ms

### Critical Parameters (config/webserver_params.yaml)

| Parameter | Default | Notes |
|-----------|---------|-------|
| `websocket_port` | 8765 | Must match JavaScript URL |
| `max_linear_vel` | 0.5 m/s | Hard limit applied server-side |
| `max_angular_vel` | 1.0 rad/s | Hard limit applied server-side |
| `deadman_timeout` | 0.5 s | Defines safety timeout |
| `camera_quality` | 30 | JPEG compression (1-100) |
| `camera_rate` | 5 Hz | Image publish rate |

**Topic Names Must Match Robot Setup:**
- `/cmd_vel` - Input to robot motion controller
- `/odom` - From robot localization (odometry)
- `/battery_state` - From robot power system
- `/scan` - From robot lidar sensor
- `/camera/image_raw/compressed` - From robot camera (compressed preferred for bandwidth)

---

## Common Development Patterns

### Adding a New Telemetry Field

1. **Backend**: In `ros2_websocket_bridge.py`, update `TelemetryData` dataclass
   ```python
   @dataclass
   class TelemetryData:
       # ... existing fields ...
       imu_data: Dict[str, float]  # Add new field
   ```

2. **Update broadcast**: In `broadcast_telemetry()`, include new field from latest subscriber data
   ```python
   'imu_data': {'pitch': self.latest_imu.linear_acceleration.y, ...}
   ```

3. **Frontend**: In `handleMessage()` case `'status'`, extract and display:
   ```javascript
   if (msg.imu_data) {
       document.getElementById('pitchValue').textContent = msg.imu_data.pitch.toFixed(2);
   }
   ```

### Customizing Velocity Limits

- Edit `config/webserver_params.yaml`: change `max_linear_vel`, `max_angular_vel`
- Server validates: `linear_vel = min(abs(received_vel), max_linear_vel) * sign(received_vel)`
- Frontend slider range automatically set from server capability (can query via handshake message)

### Monitoring Network Performance

- Add console logging in `broadcast_telemetry()`: track message size, client count, publish latency
- Frontend can measure round-trip with `ping` message and `pong` response
- Current design targets 20Hz updates; increasing beyond 50Hz risks WebSocket buffer overflow

---

## Safety & Constraints

### Hard Limits (Cannot Override)
- Server enforces max velocity limits on `/cmd_vel` publish
- Deadman switch terminates motion if client silent > 500ms
- E-STOP button sends dedicated message triggering all-stop logic

### Soft Limits (Configurable)
- Client-side joystick range (set by `maxLinearVel`, `maxAngularVel`)
- Camera JPEG quality (trades latency for image quality)
- Telemetry broadcast rate (default 20Hz)

### QoS Policy Matching
- **Subscribers** use `BEST_EFFORT` (sensor data, no retry)
- **Publishers** use `RELIABLE` (motion commands, guaranteed delivery)
- If robot uses different QoS: update `sensor_qos`/`reliable_qos` objects in bridge constructor

---

## Testing Strategy

### Unit Tests
Minimal test suite in `test/test_flake8.py` — only linting, no functional tests.

### Integration Testing
**Manual procedure:**
1. Run fake robot: `ros2 run turtlesim turtlesim_node` (for testing without hardware)
2. Create fake publishers for battery/scan: Use test utility node or `ros2 pub` directly
3. Open `http://localhost:8080` → verify joystick drives turtle
4. Check bridge logs for message throughput, no errors

### Deployment Checklist
- [ ] Topic names in `config/webserver_params.yaml` match robot's actual topics
- [ ] WebSocket port (8765) and HTTP port (8080) not firewalled
- [ ] Python 3.10+, websockets 15.x, aiohttp 3.8+ installed
- [ ] Robot publishes to `/odom`, `/battery_state`, `/scan` in expected format
- [ ] Max velocity limits appropriate for robot (test manually first)

---

## Edge Cases & Known Limitations

| Issue | Cause | Mitigation |
|-------|-------|-----------|
| Joystick "sticks" mid-movement | Browser tab loses focus; touchend not fired | Clicking any button triggers reset; add blur listener to force release |
| Camera feed delays/freezes | Network bandwidth, JPEG compression, subscription lag | Reduce `camera_quality`, lower `camera_rate`, or disable camera in config |
| Lidar visualization jumpy | Poll-based drawing not synced with subscription callbacks | Implement frame-rate capping in `drawLidar()` or use requestAnimationFrame |
| WebSocket reconnection loops | Network hiccup; bridge crashes | Frontend retries every 2s indefinitely; add max-retry limit if needed |
| Multiple clients fighting for control | No arbitration; last command wins | Document as "single operator" system; add UI warning if 2+ clients detected |

---

## References & Runbooks

### Launch Configuration
- Standard: `ros2 launch amr_webserver webserver.launch.py`
- With debugging: Modify launch file to set `output='screen'`, `emulate_tty=True`

### Extending the System
- **New sensor**: Subscribe in bridge, add to `TelemetryData`, broadcast in telemetry loop, handle in frontend JS
- **New control mode**: Create new message type (e.g., `type: 'waypoint'`), handle in `handle_client()`, execute in ROS2 action
- **Enhanced UI**: Frontend is single HTML; all CSS/JS inline; rebuild involves only redeploying `web/index.html`

### Troubleshooting Commands
```bash
# Verify bridge running and publishing
ros2 node list | grep websocket_bridge
ros2 topic list | grep cmd_vel

# Monitor actual commands sent to robot
ros2 topic echo /cmd_vel

# Check bridge is receiving sensor data
ros2 topic echo /scan --once
ros2 topic echo /battery_state --once

# Manually test WebSocket with curl (requires websocat tool)
websocat ws://localhost:8765
# Type: {"type": "ping"}
```

---

## Version History & Future Work

- **Current**: v2.0.0 - Stable single-operator system with deadman switch
- **Enhanced**: Experimental `ros2_websocket_bridge_enhanced.py` adds URDF visualization, map rendering (not fully integrated)
- **Future Improvements**:
  - Multi-operator queueing (named control requests)
  - ROS2 action support (multi-step missions)
  - Real-time latency visualization
  - Automatic topic discovery (don't require manual config)

