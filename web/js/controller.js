/**
 * AMR Industrial Control System - Main Controller
 * Handles WebSocket communication, UI updates, and robot control
 */

class AMRIndustrialController {
    constructor() {
        // WebSocket configuration
        this.ws = null;
        this.reconnectInterval = 2000;
        this.reconnecting = false;
        this.pingInterval = null;
        
        // Control parameters
        this.maxLinearVel = 0.5;
        this.maxAngularVel = 1.0;
        this.joystickActive = false;
        
        // State tracking
        this.robotState = 'stopped';
        this.connected = false;
        this.startTime = Date.now();
        
        // Map data
        this.mapData = null;
        this.mapMetadata = null;
        this.mapCanvas = null;
        this.mapCtx = null;
        this.mapScale = 1.0;
        this.mapOffsetX = 0;
        this.mapOffsetY = 0;
        
        // Laser scan
        this.laserCanvas = null;
        this.laserCtx = null;
        
        // Camera
        this.lastCameraUpdate = 0;
        
        // Initialize
        this.init();
    }
    
    init() {
        this.initCanvases();
        this.initJoystick();
        this.initButtons();
        this.initTimers();
        this.connect();
        
        console.log('AMR Industrial Controller initialized');
    }
    
    // ============= WebSocket Connection =============
    
    connect() {
        if (this.reconnecting) return;
        this.reconnecting = true;
        
        const wsUrl = `ws://${window.location.hostname}:8765`;
        console.log('Connecting to:', wsUrl);
        
        try {
            this.ws = new WebSocket(wsUrl);
            
            this.ws.onopen = () => {
                this.onConnected();
            };
            
            this.ws.onclose = (event) => {
                this.onDisconnected();
                setTimeout(() => this.connect(), this.reconnectInterval);
            };
            
            this.ws.onmessage = (event) => {
                this.handleMessage(event.data);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.reconnecting = false;
            };
        } catch (error) {
            console.error('Failed to create WebSocket:', error);
            this.reconnecting = false;
            setTimeout(() => this.connect(), this.reconnectInterval);
        }
    }
    
    onConnected() {
        this.connected = true;
        this.reconnecting = false;
        
        document.getElementById('wsIndicator').classList.add('connected');
        document.getElementById('wsStatus').textContent = 'Connected';
        document.getElementById('loadingOverlay').style.display = 'none';
        
        // Enable robot control buttons
        document.getElementById('startRobotBtn').disabled = false;
        document.getElementById('stopRobotBtn').disabled = false;
        
        this.startPingInterval();
        this.showNotification('Connected to robot', 'success');
        
        console.log('WebSocket connected');
    }
    
    onDisconnected() {
        this.connected = false;
        this.reconnecting = false;
        
        document.getElementById('wsIndicator').classList.remove('connected');
        document.getElementById('wsStatus').textContent = 'Disconnected';
        document.getElementById('loadingOverlay').style.display = 'flex';
        
        // Disable robot control buttons
        document.getElementById('startRobotBtn').disabled = true;
        document.getElementById('stopRobotBtn').disabled = true;
        
        this.stopPingInterval();
        
        console.log('WebSocket disconnected');
    }
    
    startPingInterval() {
        this.pingInterval = setInterval(() => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.send({ type: 'ping' });
            }
        }, 15000);
    }
    
    stopPingInterval() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }
    
    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        }
    }
    
    // ============= Message Handling =============
    
    handleMessage(data) {
        try {
            const msg = JSON.parse(data);
            
            switch (msg.type) {
                case 'telemetry':
                    this.updateTelemetry(msg.data);
                    break;
                case 'map':
                    this.updateMap(msg.metadata, msg.data);
                    break;
                case 'camera':
                    this.updateCamera(msg.data, msg.format);
                    break;
                case 'urdf':
                    this.updateURDF(msg.data);
                    break;
                case 'robot_state':
                    this.updateRobotState(msg.state);
                    break;
                case 'robot_control_response':
                    this.handleRobotControlResponse(msg);
                    break;
                case 'pong':
                    // Keepalive response
                    break;
                default:
                    console.log('Unknown message type:', msg.type);
            }
        } catch (e) {
            console.error('Error parsing message:', e);
        }
    }
    
    // ============= Telemetry Updates =============
    
    updateTelemetry(data) {
        // Battery
        const batteryPercent = data.battery_percentage.toFixed(1);
        document.getElementById('batteryPercent').textContent = `${batteryPercent}%`;
        document.getElementById('batteryVoltage').textContent = `${data.battery_voltage.toFixed(2)}V`;
        
        const batteryFill = document.getElementById('batteryFill');
        batteryFill.style.width = `${data.battery_percentage}%`;
        batteryFill.textContent = `${Math.round(data.battery_percentage)}%`;
        
        batteryFill.className = 'battery-fill';
        if (data.battery_percentage < 20) {
            batteryFill.classList.add('low');
        } else if (data.battery_percentage < 50) {
            batteryFill.classList.add('medium');
        }
        
        // Position
        document.getElementById('posX').textContent = data.position.x.toFixed(2);
        document.getElementById('posY').textContent = data.position.y.toFixed(2);
        
        // Calculate yaw from quaternion
        const yaw = this.quaternionToYaw(data.orientation);
        document.getElementById('posTheta').textContent = `${(yaw * 180 / Math.PI).toFixed(1)}°`;
        
        // Map position overlay
        document.getElementById('mapPosition').textContent = 
            `X: ${data.position.x.toFixed(2)} Y: ${data.position.y.toFixed(2)}`;
        
        // Connection count
        document.getElementById('connectionCount').textContent = data.connection_count;
        
        // Robot state
        if (data.robot_state) {
            this.updateRobotState(data.robot_state);
        }
        
        // Draw robot on map
        if (this.mapData) {
            this.drawMap();
            this.drawRobotOnMap(data.position, data.orientation);
        }
        
        // Draw laser scan
        if (data.laser_scan_ranges && data.laser_scan_ranges.length > 0) {
            this.drawLaserScan(data.laser_scan_ranges);
        }
    }
    
    quaternionToYaw(q) {
        // Convert quaternion to yaw angle
        const siny_cosp = 2 * (q.w * q.z + q.x * q.y);
        const cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z);
        return Math.atan2(siny_cosp, cosy_cosp);
    }
    
    updateRobotState(state) {
        this.robotState = state;
        const stateElement = document.getElementById('robotState');
        
        if (state === 'running') {
            stateElement.textContent = 'RUNNING';
            stateElement.style.background = 'var(--accent-green)';
            document.getElementById('startRobotBtn').disabled = true;
            document.getElementById('stopRobotBtn').disabled = false;
        } else {
            stateElement.textContent = 'STOPPED';
            stateElement.style.background = 'var(--accent-red)';
            document.getElementById('startRobotBtn').disabled = false;
            document.getElementById('stopRobotBtn').disabled = true;
        }
    }
    
    // ============= Map Rendering =============
    
    updateMap(metadata, data) {
        this.mapMetadata = metadata;
        this.mapData = data;
        
        console.log(`Map received: ${metadata.width}x${metadata.height}, resolution: ${metadata.resolution}`);
        
        // Initialize map display
        this.initMapCanvas();
        this.drawMap();
        
        this.showNotification('Map loaded', 'success');
    }
    
    initMapCanvas() {
        if (!this.mapMetadata) return;
        
        this.mapCanvas.width = this.mapMetadata.width;
        this.mapCanvas.height = this.mapMetadata.height;
        
        // Center map
        const containerWidth = this.mapCanvas.parentElement.clientWidth;
        const containerHeight = this.mapCanvas.parentElement.clientHeight;
        
        this.mapScale = Math.min(
            containerWidth / this.mapMetadata.width,
            containerHeight / this.mapMetadata.height
        ) * 0.9;
        
        this.mapOffsetX = (containerWidth - this.mapMetadata.width * this.mapScale) / 2;
        this.mapOffsetY = (containerHeight - this.mapMetadata.height * this.mapScale) / 2;
    }
    
    drawMap() {
        if (!this.mapData || !this.mapMetadata) return;
        
        const ctx = this.mapCtx;
        const width = this.mapMetadata.width;
        const height = this.mapMetadata.height;
        
        // Clear canvas
        ctx.clearRect(0, 0, this.mapCanvas.width, this.mapCanvas.height);
        
        // Create image data
        const imageData = ctx.createImageData(width, height);
        
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const i = (y * width + x);
                const value = this.mapData[i];
                
                let color;
                if (value === -1) {
                    // Unknown
                    color = [50, 50, 50];
                } else if (value === 0) {
                    // Free space
                    color = [240, 240, 240];
                } else {
                    // Occupied
                    const intensity = 255 - (value * 2.55);
                    color = [intensity, intensity, intensity];
                }
                
                const pixelIndex = ((height - 1 - y) * width + x) * 4;
                imageData.data[pixelIndex] = color[0];
                imageData.data[pixelIndex + 1] = color[1];
                imageData.data[pixelIndex + 2] = color[2];
                imageData.data[pixelIndex + 3] = 255;
            }
        }
        
        ctx.putImageData(imageData, 0, 0);
    }
    
    drawRobotOnMap(position, orientation) {
        if (!this.mapMetadata) return;
        
        const ctx = this.mapCtx;
        const resolution = this.mapMetadata.resolution;
        const origin = this.mapMetadata.origin;
        
        // Convert world coordinates to map coordinates
        const mapX = (position.x - origin.x) / resolution;
        const mapY = this.mapMetadata.height - (position.y - origin.y) / resolution;
        
        // Draw robot
        ctx.save();
        ctx.translate(mapX, mapY);
        
        const yaw = this.quaternionToYaw(orientation);
        ctx.rotate(-yaw);
        
        // Robot body
        ctx.fillStyle = 'rgba(52, 152, 219, 0.8)';
        ctx.beginPath();
        ctx.arc(0, 0, 8, 0, 2 * Math.PI);
        ctx.fill();
        
        // Direction indicator
        ctx.strokeStyle = 'rgba(231, 76, 60, 0.9)';
        ctx.lineWidth = 3;
        ctx.beginPath();
        ctx.moveTo(0, 0);
        ctx.lineTo(12, 0);
        ctx.stroke();
        
        ctx.restore();
    }
    
    // ============= Laser Scan Rendering =============
    
    drawLaserScan(ranges) {
        const ctx = this.laserCtx;
        const width = this.laserCanvas.width;
        const height = this.laserCanvas.height;
        const centerX = width / 2;
        const centerY = height / 2;
        
        ctx.clearRect(0, 0, width, height);
        
        // Draw range circle
        ctx.strokeStyle = '#2c3e50';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.arc(centerX, centerY, Math.min(width, height) * 0.4, 0, 2 * Math.PI);
        ctx.stroke();
        
        if (!ranges || ranges.length === 0) return;
        
        const scale = Math.min(width, height) * 0.08;
        const angleStep = Math.PI / (ranges.length - 1);
        
        // Draw scan points
        ctx.fillStyle = '#3498db';
        for (let i = 0; i < ranges.length; i++) {
            const angle = -Math.PI / 2 + i * angleStep;
            const range = Math.min(ranges[i], 10) * scale;
            const x = centerX + range * Math.cos(angle);
            const y = centerY + range * Math.sin(angle);
            
            ctx.beginPath();
            ctx.arc(x, y, 2, 0, 2 * Math.PI);
            ctx.fill();
        }
        
        // Draw robot center
        ctx.fillStyle = '#e74c3c';
        ctx.beginPath();
        ctx.arc(centerX, centerY, 5, 0, 2 * Math.PI);
        ctx.fill();
    }
    
    // ============= Camera Feed =============
    
    updateCamera(data, format) {
        const now = Date.now();
        if (now - this.lastCameraUpdate < 100) return; // Max 10Hz display
        this.lastCameraUpdate = now;
        
        const img = document.getElementById('cameraImage');
        const noCamera = document.getElementById('noCamera');
        
        img.src = `data:image/jpeg;base64,${data}`;
        img.style.display = 'block';
        noCamera.style.display = 'none';
    }
    
    // ============= URDF Visualization =============
    
    updateURDF(urdfData) {
        console.log('URDF data received, length:', urdfData.length);
        // URDF visualization will be added in future enhancement
        // For now, just log it
        this.showNotification('URDF loaded', 'success');
    }
    
    // ============= Joystick Control =============
    
    initJoystick() {
        const stick = document.getElementById('joystick');
        const base = stick.parentElement;
        
        let isDragging = false;
        let centerX, centerY, maxRadius;
        
        const updateGeometry = () => {
            const rect = base.getBoundingClientRect();
            centerX = rect.width / 2;
            centerY = rect.height / 2;
            maxRadius = (rect.width / 2) - 45;
        };
        
        updateGeometry();
        window.addEventListener('resize', updateGeometry);
        
        const handleMove = (clientX, clientY) => {
            const rect = base.getBoundingClientRect();
            let x = clientX - rect.left - centerX;
            let y = clientY - rect.top - centerY;
            
            const distance = Math.sqrt(x * x + y * y);
            if (distance > maxRadius) {
                const angle = Math.atan2(y, x);
                x = Math.cos(angle) * maxRadius;
                y = Math.sin(angle) * maxRadius;
            }
            
            stick.style.transform = `translate(calc(-50% + ${x}px), calc(-50% + ${y}px))`;
            
            const linear = -(y / maxRadius) * this.maxLinearVel;
            const angular = -(x / maxRadius) * this.maxAngularVel;
            
            document.getElementById('linearVel').textContent = linear.toFixed(2);
            document.getElementById('angularVel').textContent = angular.toFixed(2);
            
            this.sendCommand(linear, angular);
        };
        
        const resetStick = () => {
            stick.style.transform = 'translate(-50%, -50%)';
            document.getElementById('linearVel').textContent = '0.00';
            document.getElementById('angularVel').textContent = '0.00';
            this.sendCommand(0, 0);
            isDragging = false;
        };
        
        // Mouse events
        stick.addEventListener('mousedown', (e) => {
            isDragging = true;
            e.preventDefault();
        });
        
        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                handleMove(e.clientX, e.clientY);
            }
        });
        
        document.addEventListener('mouseup', resetStick);
        
        // Touch events
        stick.addEventListener('touchstart', (e) => {
            isDragging = true;
            e.preventDefault();
        });
        
        document.addEventListener('touchmove', (e) => {
            if (isDragging) {
                const touch = e.touches[0];
                handleMove(touch.clientX, touch.clientY);
            }
        });
        
        document.addEventListener('touchend', resetStick);
    }
    
    sendCommand(linear, angular) {
        this.send({
            type: 'cmd_vel',
            linear: linear,
            angular: angular
        });
    }
    
    // ============= Button Controls =============
    
    initButtons() {
        // Start Robot
        document.getElementById('startRobotBtn').addEventListener('click', () => {
            this.send({ type: 'start_robot' });
            this.showNotification('Starting robot...', 'success');
        });
        
        // Stop Robot
        document.getElementById('stopRobotBtn').addEventListener('click', () => {
            this.send({ type: 'stop_robot' });
            this.showNotification('Stopping robot...', 'success');
        });
        
        // Emergency Stop
        document.getElementById('estopBtn').addEventListener('click', () => {
            this.send({ type: 'emergency_stop' });
            this.sendCommand(0, 0);
            this.showNotification('EMERGENCY STOP ACTIVATED', 'error');
        });
        
        // Brake
        document.getElementById('brakeBtn').addEventListener('click', () => {
            this.sendCommand(0, 0);
        });
    }
    
    handleRobotControlResponse(msg) {
        if (msg.success) {
            this.showNotification(msg.message, 'success');
        } else {
            this.showNotification(msg.message, 'error');
        }
    }
    
    // ============= Canvas Initialization =============
    
    initCanvases() {
        // Map canvas
        this.mapCanvas = document.getElementById('mapCanvas');
        this.mapCtx = this.mapCanvas.getContext('2d');
        
        const container = this.mapCanvas.parentElement;
        this.mapCanvas.width = container.clientWidth;
        this.mapCanvas.height = container.clientHeight;
        
        // Laser canvas
        this.laserCanvas = document.getElementById('laserCanvas');
        this.laserCtx = this.laserCanvas.getContext('2d');
        this.laserCanvas.width = this.laserCanvas.offsetWidth;
        this.laserCanvas.height = 250;
        
        // Handle window resize
        window.addEventListener('resize', () => {
            this.mapCanvas.width = container.clientWidth;
            this.mapCanvas.height = container.clientHeight;
            if (this.mapData) {
                this.initMapCanvas();
                this.drawMap();
            }
        });
    }
    
    // ============= Timers =============
    
    initTimers() {
        // Uptime counter
        setInterval(() => {
            const elapsed = Date.now() - this.startTime;
            const hours = Math.floor(elapsed / 3600000);
            const minutes = Math.floor((elapsed % 3600000) / 60000);
            const seconds = Math.floor((elapsed % 60000) / 1000);
            
            document.getElementById('uptime').textContent = 
                `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
        }, 1000);
    }
    
    // ============= Notifications =============
    
    showNotification(message, type = 'success') {
        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.textContent = message;
        
        document.body.appendChild(notification);
        
        setTimeout(() => {
            notification.style.animation = 'slideIn 0.3s ease reverse';
            setTimeout(() => {
                document.body.removeChild(notification);
            }, 300);
        }, 3000);
    }
}

// Initialize controller when page loads
window.addEventListener('DOMContentLoaded', () => {
    window.controller = new AMRIndustrialController();
    console.log('AMR Industrial Control System loaded');
});