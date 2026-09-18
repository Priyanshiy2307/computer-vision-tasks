#!/usr/bin/env python3
"""
=============================================================================
  Intel RealSense D435i — Web-Based Checkerboard Calibration
  For: Unitree G1 Robot (Headless Remote Setup)
=============================================================================

  This script starts a local web server on port 5000.
  Open http://<robot_ip>:5000 in your browser (laptop, phone, tablet)
  to view the live feed and control the calibration process.

  Web UI Hotkeys (when browser tab is focused):
    - SPACE  : Capture current frame
    - D      : Delete last captured frame
    - C      : Trigger calibration (needs 25+ frames)
    - R      : Reset all captures
"""

import cv2
import numpy as np
import pyrealsense2 as rs
import os
import json
import yaml
import time
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────
CHECKERBOARD_COLS   = 9       # inner corners along the long edge
CHECKERBOARD_ROWS   = 6       # inner corners along the short edge
SQUARE_SIZE_MM      = 24.0    # physical size of each square in millimetres (2.4 cm)

CAPTURE_WIDTH       = 1280    # RealSense color stream width
CAPTURE_HEIGHT      = 720     # RealSense color stream height
CAPTURE_FPS         = 30

MIN_CAPTURES        = 25      # minimum good frames before calibration runs
TARGET_CAPTURES     = 30      # aim for this many

OUTPUT_DIR          = "./calibration_output"   # where results are saved
PORT                = 5000

# ─────────────────────────────────────────────────────────────────────────────
#  HTML TEMPLATE FOR DETAILED WEB UI
# ─────────────────────────────────────────────────────────────────────────────
HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RealSense D435i Calibration Dashboard</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-dark: #0a0b10;
            --bg-card: rgba(20, 22, 35, 0.65);
            --border-color: rgba(255, 255, 255, 0.08);
            --accent-cyan: #00f2fe;
            --accent-blue: #4facfe;
            --accent-purple: #8a2be2;
            --accent-purple-glow: rgba(138, 43, 226, 0.3);
            --color-success: #00e676;
            --color-error: #ff1744;
            --color-warning: #ffb300;
            --text-main: #f5f6fa;
            --text-muted: #8f92a1;
        }

        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }

        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-dark);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            overflow-x: hidden;
            background-image: 
                radial-gradient(circle at 10% 20%, rgba(138, 43, 226, 0.15) 0%, transparent 40%),
                radial-gradient(circle at 90% 80%, rgba(0, 242, 254, 0.1) 0%, transparent 45%);
            background-attachment: fixed;
        }

        header {
            padding: 20px 40px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            background: rgba(10, 11, 16, 0.8);
            backdrop-filter: blur(10px);
            z-index: 10;
        }

        .logo-section h1 {
            font-size: 1.5rem;
            font-weight: 700;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-purple));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .logo-section p {
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-top: 2px;
        }

        .connection-badge {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.05);
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid var(--border-color);
            font-size: 0.85rem;
        }

        .dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background-color: var(--color-success);
            box-shadow: 0 0 10px var(--color-success);
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 230, 118, 0.7); }
            70% { transform: scale(1); box-shadow: 0 0 0 8px rgba(0, 230, 118, 0); }
            100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(0, 230, 118, 0); }
        }

        .container {
            display: grid;
            grid-template-columns: 1fr 400px;
            gap: 30px;
            padding: 30px 40px;
            flex-grow: 1;
            max-width: 1800px;
            margin: 0 auto;
            width: 100%;
        }

        .main-panel {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .video-card {
            background: var(--bg-card);
            border-radius: 20px;
            border: 1px solid var(--border-color);
            overflow: hidden;
            box-shadow: 0 12px 40px rgba(0, 0, 0, 0.4);
            position: relative;
            aspect-ratio: 16/9;
            backdrop-filter: blur(12px);
            display: flex;
            justify-content: center;
            align-items: center;
            transition: border-color 0.3s ease;
        }

        .video-card.board-found {
            border-color: rgba(0, 230, 118, 0.4);
            box-shadow: 0 12px 40px rgba(0, 230, 118, 0.08);
        }

        .video-stream {
            width: 100%;
            height: 100%;
            object-fit: contain;
            display: block;
        }

        .sidebar {
            display: flex;
            flex-direction: column;
            gap: 24px;
        }

        .card {
            background: var(--bg-card);
            border-radius: 20px;
            border: 1px solid var(--border-color);
            padding: 24px;
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
            backdrop-filter: blur(12px);
        }

        .card-title {
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 18px;
            color: var(--text-main);
            display: flex;
            justify-content: space-between;
            align-items: center;
            letter-spacing: 0.5px;
        }

        .status-indicator {
            padding: 6px 14px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 0.85rem;
            text-align: center;
            text-transform: uppercase;
        }

        .status-searching {
            background: rgba(255, 23, 68, 0.1);
            color: var(--color-error);
            border: 1px solid rgba(255, 23, 68, 0.2);
        }

        .status-found {
            background: rgba(0, 230, 118, 0.1);
            color: var(--color-success);
            border: 1px solid rgba(0, 230, 118, 0.2);
        }

        .progress-section {
            margin-top: 15px;
        }

        .progress-labels {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: var(--text-muted);
            margin-bottom: 8px;
        }

        .progress-bar-container {
            height: 10px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 5px;
            overflow: hidden;
            border: 1px solid rgba(255, 255, 255, 0.02);
        }

        .progress-bar {
            height: 100%;
            background: linear-gradient(90deg, var(--accent-blue), var(--accent-cyan));
            width: 0%;
            transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 0 10px var(--accent-cyan);
        }

        .btn {
            width: 100%;
            padding: 14px;
            border-radius: 12px;
            font-size: 0.95rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 10px;
            font-family: inherit;
        }

        .btn-capture {
            background: linear-gradient(135deg, var(--accent-blue), var(--accent-cyan));
            color: #050508;
            border: none;
            box-shadow: 0 4px 20px rgba(0, 242, 254, 0.25);
        }

        .btn-capture:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(0, 242, 254, 0.4);
        }

        .btn-capture:active {
            transform: translateY(0);
        }

        .btn-capture:disabled {
            opacity: 0.4;
            cursor: not-allowed;
            box-shadow: none;
        }

        .btn-group-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
            margin-top: 12px;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid var(--border-color);
            color: var(--text-main);
        }

        .btn-secondary:hover:not(:disabled) {
            background: rgba(255, 255, 255, 0.08);
            border-color: rgba(255, 255, 255, 0.15);
        }

        .btn-danger {
            background: rgba(255, 23, 68, 0.05);
            border: 1px solid rgba(255, 23, 68, 0.2);
            color: #ff5252;
        }

        .btn-danger:hover:not(:disabled) {
            background: rgba(255, 23, 68, 0.15);
            border-color: rgba(255, 23, 68, 0.4);
        }

        .btn-calibrate {
            background: linear-gradient(135deg, var(--accent-purple), #b030b0);
            color: white;
            border: none;
            box-shadow: 0 4px 20px var(--accent-purple-glow);
            margin-top: 15px;
        }

        .btn-calibrate:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(138, 43, 226, 0.5);
        }

        .btn-calibrate:disabled {
            opacity: 0.3;
            cursor: not-allowed;
            box-shadow: none;
        }

        .terminal-panel {
            background: #05060a;
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 20px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.8rem;
            color: #a4b0be;
            min-height: 150px;
            max-height: 250px;
            overflow-y: auto;
            flex-grow: 1;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
        }

        .terminal-line {
            margin-bottom: 6px;
            line-height: 1.4;
        }

        .terminal-line.info { color: var(--accent-cyan); }
        .terminal-line.success { color: var(--color-success); }
        .terminal-line.error { color: var(--color-error); }
        .terminal-line.warning { color: var(--color-warning); }

        .results-panel {
            display: none;
            animation: fadeIn 0.4s ease forwards;
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .results-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
            margin-top: 12px;
        }

        .result-item {
            background: rgba(255, 255, 255, 0.02);
            padding: 10px 14px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.04);
        }

        .result-label {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-bottom: 2px;
        }

        .result-value {
            font-size: 1.05rem;
            font-weight: 700;
        }

        .keyboard-shortcuts {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid var(--border-color);
        }

        kbd {
            background: rgba(255, 255, 255, 0.1);
            color: var(--text-main);
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-family: inherit;
            border: 1px solid rgba(255, 255, 255, 0.1);
            font-weight: bold;
        }

        .shortcut-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.75rem;
            color: var(--text-muted);
        }

        /* Responsive */
        @media (max-width: 1100px) {
            .container {
                grid-template-columns: 1fr;
            }
            .sidebar {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <header>
        <div class="logo-section">
            <h1>RealSense D435i Intrinsic Calibration</h1>
            <p>Checkerboard Method (9x6 Corners, 24mm squares)</p>
        </div>
        <div class="connection-badge">
            <div class="dot"></div>
            <span>Camera Active</span>
        </div>
    </header>

    <div class="container">
        <div class="main-panel">
            <div class="video-card" id="videoContainer">
                <img src="/video_feed" class="video-stream" alt="RealSense Live Stream">
            </div>
            
            <div class="card" style="display: flex; flex-direction: column; flex-grow: 1;">
                <div class="card-title">System Logs / Output Console</div>
                <div class="terminal-panel" id="terminal">
                    <div class="terminal-line info">[System] Web interface initialized. Connecting to camera stream...</div>
                </div>
            </div>
        </div>

        <div class="sidebar">
            <div class="card">
                <div class="card-title">
                    <span>Calibration Controller</span>
                    <span class="status-indicator status-searching" id="detectionStatus">Searching...</span>
                </div>

                <div class="progress-section">
                    <div class="progress-labels">
                        <span>Calibration Frames</span>
                        <span id="captureCountLabel">0 / 30</span>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" id="progressBar"></div>
                    </div>
                </div>

                <div style="margin-top: 24px;">
                    <button class="btn btn-capture" id="btnCapture" onclick="triggerAction('capture')">
                        Capture Frame
                    </button>
                    <div class="btn-group-grid">
                        <button class="btn btn-danger" onclick="triggerAction('delete')">Delete Last</button>
                        <button class="btn btn-secondary" onclick="triggerAction('reset')">Reset All</button>
                    </div>
                    <button class="btn btn-calibrate" id="btnCalibrate" onclick="triggerAction('calibrate')" disabled>
                        Run Calibration
                    </button>
                </div>

                <div class="keyboard-shortcuts">
                    <div class="shortcut-item"><kbd>SPACE</kbd> Capture</div>
                    <div class="shortcut-item"><kbd>D</kbd> Delete</div>
                    <div class="shortcut-item"><kbd>C</kbd> Calibrate</div>
                    <div class="shortcut-item"><kbd>R</kbd> Reset</div>
                </div>
            </div>

            <div class="card results-panel" id="resultsPanel">
                <div class="card-title">
                    <span>Calibration Metrics</span>
                    <span class="status-indicator status-found" id="qualityLabel">Excellent</span>
                </div>
                
                <div class="results-grid">
                    <div class="result-item">
                        <div class="result-label">Reprojection Error</div>
                        <div class="result-value" id="resErr">0.241 px</div>
                    </div>
                    <div class="result-item">
                        <div class="result-label">Frames Used</div>
                        <div class="result-value" id="resFrames">28</div>
                    </div>
                    <div class="result-item">
                        <div class="result-label">Focal Length (fx)</div>
                        <div class="result-value" id="resFx">912.4</div>
                    </div>
                    <div class="result-item">
                        <div class="result-label">Focal Length (fy)</div>
                        <div class="result-value" id="resFy">910.8</div>
                    </div>
                    <div class="result-item" style="grid-column: span 2;">
                        <div class="result-label">Principal Point (cx, cy)</div>
                        <div class="result-value" id="resCenter">641.2, 362.4</div>
                    </div>
                </div>
                <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 14px; text-align: center; font-family: monospace;">
                    YAML matrix saved to output directory.
                </div>
            </div>
        </div>
    </div>

    <script>
        const progressBar = document.getElementById('progressBar');
        const captureCountLabel = document.getElementById('captureCountLabel');
        const detectionStatus = document.getElementById('detectionStatus');
        const videoContainer = document.getElementById('videoContainer');
        const btnCapture = document.getElementById('btnCapture');
        const btnCalibrate = document.getElementById('btnCalibrate');
        const terminal = document.getElementById('terminal');
        const resultsPanel = document.getElementById('resultsPanel');

        let lastLogs = [];

        function updateStatus() {
            fetch('/api/status')
                .then(res => res.json())
                .then(data => {
                    // Update board detection status
                    if (data.board_detected) {
                        detectionStatus.textContent = "Board Detected";
                        detectionStatus.className = "status-indicator status-found";
                        videoContainer.classList.add('board-found');
                        btnCapture.disabled = false;
                    } else {
                        detectionStatus.textContent = "Searching...";
                        detectionStatus.className = "status-indicator status-searching";
                        videoContainer.classList.remove('board-found');
                        btnCapture.disabled = true;
                    }

                    // Update frame count
                    const count = data.captured_count;
                    const target = data.target_captures;
                    const min = data.min_captures;
                    captureCountLabel.textContent = `${count} / ${target}`;
                    progressBar.style.width = `${Math.min(100, (count / target) * 100)}%`;

                    if (count >= min) {
                        btnCalibrate.disabled = false;
                    } else {
                        btnCalibrate.disabled = true;
                    }

                    // Update logs
                    if (data.logs && data.logs.length > 0) {
                        let newLogs = data.logs.filter(l => !lastLogs.includes(l));
                        if (newLogs.length > 0) {
                            newLogs.forEach(log => {
                                const line = document.createElement('div');
                                line.className = 'terminal-line';
                                if (log.includes('error') || log.includes('failed') || log.includes('[!]')) {
                                    line.classList.add('error');
                                } else if (log.includes('success') || log.includes('[+]') || log.includes('complete')) {
                                    line.classList.add('success');
                                } else if (log.includes('warning') || log.includes('⚠')) {
                                    line.classList.add('warning');
                                } else {
                                    line.classList.add('info');
                                }
                                line.textContent = log;
                                terminal.appendChild(line);
                            });
                            terminal.scrollTop = terminal.scrollHeight;
                            lastLogs = data.logs;
                        }
                    }

                    // Update calibration results
                    if (data.calibrated && data.calibration_result) {
                        const res = data.calibration_result;
                        document.getElementById('resErr').textContent = `${res.reprojection_error_mean_px} px`;
                        document.getElementById('resFrames').textContent = res.num_frames;
                        document.getElementById('resFx').textContent = res.calibrated_intrinsics.fx;
                        document.getElementById('resFy').textContent = res.calibrated_intrinsics.fy;
                        document.getElementById('resCenter').textContent = `${res.calibrated_intrinsics.cx}, ${res.calibrated_intrinsics.cy}`;
                        
                        const qLabel = document.getElementById('qualityLabel');
                        qLabel.textContent = res.quality;
                        if (res.quality === 'Excellent' || res.quality === 'Good') {
                            qLabel.className = 'status-indicator status-found';
                        } else {
                            qLabel.className = 'status-indicator status-searching';
                        }
                        
                        resultsPanel.style.display = 'block';
                    } else {
                        resultsPanel.style.display = 'none';
                    }
                })
                .catch(err => console.error("Error fetching status:", err));
        }

        function triggerAction(action) {
            fetch(`/api/${action}`, { method: 'POST' })
                .then(res => res.json())
                .then(data => {
                    const line = document.createElement('div');
                    line.className = 'terminal-line';
                    if (data.success) {
                        line.classList.add('success');
                        line.textContent = `[Action] ${data.message}`;
                    } else {
                        line.classList.add('error');
                        line.textContent = `[Action Error] ${data.message}`;
                    }
                    terminal.appendChild(line);
                    terminal.scrollTop = terminal.scrollHeight;
                    updateStatus();
                });
        }

        // Listen for Keyboard Shortcuts
        document.addEventListener('keydown', (e) => {
            if (e.key === ' ' || e.code === 'Space') {
                e.preventDefault();
                if (!btnCapture.disabled) {
                    triggerAction('capture');
                }
            } else if (e.key === 'd' || e.key === 'D') {
                triggerAction('delete');
            } else if (e.key === 'c' || e.key === 'C') {
                if (!btnCalibrate.disabled) {
                    triggerAction('calibrate');
                }
            } else if (e.key === 'r' || e.key === 'R') {
                triggerAction('reset');
            }
        });

        // Poll status every 200ms for responsiveness
        setInterval(updateStatus, 200);
        updateStatus();
    </script>
</body>
</html>
"""

# ─────────────────────────────────────────────────────────────────────────────
#  WEB SERVER INFRASTRUCTURE
# ─────────────────────────────────────────────────────────────────────────────

class CameraManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.pipeline = None
        self.profile = None
        self.factory_intr = None
        self.objp = None
        self.objpoints = []
        self.imgpoints = []
        self.latest_raw_frame = None
        self.latest_display_frame = None
        self.latest_corners = None
        self.is_board_detected = False
        self.logs = []
        self.calibrated = False
        self.calibration_result = None
        self.is_running = False
        self.last_capture_time = 0
        self.capture_interval = 1.0  # seconds
        self.frame_id = 0
        
        # Auto-capture settings
        self.auto_capture_enabled = True   # ON by default
        self.auto_capture_interval = 5.0   # seconds between captures
        self.auto_capture_last_time = 0
        
        self.prepare_object_points()

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        print(formatted)
        with self.lock:
            self.logs.append(formatted)
            if len(self.logs) > 80:
                self.logs.pop(0)

    def prepare_object_points(self):
        objp = np.zeros((CHECKERBOARD_ROWS * CHECKERBOARD_COLS, 3), np.float32)
        objp[:, :2] = np.mgrid[0:CHECKERBOARD_COLS,
                                0:CHECKERBOARD_ROWS].T.reshape(-1, 2)
        objp *= SQUARE_SIZE_MM
        self.objp = objp

    def start_camera(self):
        self.log("Initializing RealSense pipeline...")
        
        # Configurations to try in order of preference (color-only to save USB bandwidth)
        configs_to_try = [
            {"width": 1280, "height": 720, "fps": 30},
            {"width": 1280, "height": 720, "fps": 15},
            {"width": 1280, "height": 720, "fps": 6},
            {"width": 848,  "height": 480, "fps": 30},
            {"width": 848,  "height": 480, "fps": 15},
            {"width": 640,  "height": 480, "fps": 30},
            {"width": 640,  "height": 480, "fps": 15},
            {"width": 640,  "height": 480, "fps": 6},
            {"width": 424,  "height": 240, "fps": 30},
            {"width": 424,  "height": 240, "fps": 15},
        ]
        
        success = False
        for c in configs_to_try:
            self.pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, c["width"], c["height"], rs.format.bgr8, c["fps"])
            try:
                self.profile = self.pipeline.start(config)
                self.log(f"Trying {c['width']}x{c['height']}@{c['fps']}fps ... negotiated OK, verifying frames...")
                
                # CRITICAL: Verify that frames ACTUALLY arrive (USB bandwidth check)
                frames_ok = False
                for attempt in range(3):
                    try:
                        frames = self.pipeline.wait_for_frames(3000)  # 3 sec timeout
                        color_frame = frames.get_color_frame()
                        if color_frame:
                            frames_ok = True
                            break
                    except Exception:
                        pass
                
                if frames_ok:
                    global CAPTURE_WIDTH, CAPTURE_HEIGHT, CAPTURE_FPS
                    CAPTURE_WIDTH = c["width"]
                    CAPTURE_HEIGHT = c["height"]
                    CAPTURE_FPS = c["fps"]
                    success = True
                    self.log(f"✓ Frames verified! Using {CAPTURE_WIDTH}x{CAPTURE_HEIGHT} @ {CAPTURE_FPS}fps")
                    break
                else:
                    self.log(f"✗ {c['width']}x{c['height']}@{c['fps']}fps: negotiated but no frames arrived (USB bandwidth). Trying next...")
                    self.pipeline.stop()
                    time.sleep(0.5)
                    
            except Exception as e:
                self.log(f"✗ {c['width']}x{c['height']}@{c['fps']}fps rejected: {str(e)}")
                try:
                    self.pipeline.stop()
                except Exception:
                    pass
                time.sleep(0.3)
                
        if not success:
            # Last resort: let RealSense pick whatever it can
            try:
                self.log("All explicit configs failed. Trying auto-detect...")
                self.pipeline = rs.pipeline()
                config = rs.config()
                config.enable_stream(rs.stream.color)
                self.profile = self.pipeline.start(config)
                
                # Verify frames arrive
                frames = self.pipeline.wait_for_frames(5000)
                color_frame = frames.get_color_frame()
                if not color_frame:
                    self.log("Auto-detect started but no frames. Giving up.")
                    return False
                    
                color_profile = self.profile.get_stream(rs.stream.color)
                intr = color_profile.as_video_stream_profile().get_intrinsics()
                CAPTURE_WIDTH = intr.width
                CAPTURE_HEIGHT = intr.height
                CAPTURE_FPS = 30
                self.log(f"✓ Auto-detect succeeded: {CAPTURE_WIDTH}x{CAPTURE_HEIGHT}")
                success = True
            except Exception as e:
                self.log(f"Auto-detect camera config failed: {str(e)}")
                return False
                
        try:
            # Allow auto-exposure to settle
            color_sensor = self.profile.get_device().query_sensors()[1]
            time.sleep(1)
            color_sensor.set_option(rs.option.enable_auto_exposure, 1)
            
            # Fetch factory intrinsic parameters
            color_profile = self.profile.get_stream(rs.stream.color)
            intr = color_profile.as_video_stream_profile().get_intrinsics()
            self.factory_intr = {
                "fx": round(intr.fx, 2), "fy": round(intr.fy, 2),
                "cx": round(intr.ppx, 2), "cy": round(intr.ppy, 2),
                "model": str(intr.model),
                "coeffs": [round(float(c), 6) for c in intr.coeffs]
            }
            
            self.log("RealSense D435i camera streams online.")
            self.log(f"Factory Intrinsics: fx={intr.fx:.1f}, fy={intr.fy:.1f}, cx={intr.ppx:.1f}, cy={intr.ppy:.1f}")
            self.is_running = True
            
            # Launch capture background loop
            threading.Thread(target=self.capture_loop, daemon=True).start()
            return True
        except Exception as e:
            self.log(f"Error configuring RealSense sensors: {str(e)}")
            return False

    def capture_loop(self):
        self.log("=" * 50)
        self.log("AUTO-CAPTURE IS ON (every 5 seconds)")
        self.log("Just hold/move the checkerboard in front of the camera.")
        self.log("Frames will be captured automatically when the board is detected.")
        self.log("=" * 50)
        
        while self.is_running:
            start_time = time.time()
            try:
                frames = self.pipeline.wait_for_frames()
                color_frame = frames.get_color_frame()
                if not color_frame:
                    continue
                
                img = np.asanyarray(color_frame.get_data())
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                flags = (cv2.CALIB_CB_ADAPTIVE_THRESH +
                         cv2.CALIB_CB_NORMALIZE_IMAGE +
                         cv2.CALIB_CB_FAST_CHECK)
                
                found, corners = cv2.findChessboardCorners(
                    gray, (CHECKERBOARD_COLS, CHECKERBOARD_ROWS), flags
                )
                
                display_img = img.copy()
                corners_sub = None
                
                if found:
                    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
                    corners_sub = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                    cv2.drawChessboardCorners(
                        display_img, (CHECKERBOARD_COLS, CHECKERBOARD_ROWS), corners_sub, found
                    )
                
                with self.lock:
                    self.latest_raw_frame = img
                    self.latest_display_frame = display_img
                    self.latest_corners = corners_sub
                    self.is_board_detected = found
                    self.frame_id += 1
                
                # ── AUTO-CAPTURE LOGIC ──
                now = time.time()
                with self.lock:
                    should_auto = (
                        self.auto_capture_enabled
                        and found
                        and corners_sub is not None
                        and not self.calibrated
                        and len(self.objpoints) < TARGET_CAPTURES
                        and (now - self.auto_capture_last_time) >= self.auto_capture_interval
                    )
                
                if should_auto:
                    with self.lock:
                        self.objpoints.append(self.objp)
                        self.imgpoints.append(corners_sub)
                        self.auto_capture_last_time = now
                        count = len(self.objpoints)
                    self.log(f"📸 AUTO-CAPTURED frame {count}/{TARGET_CAPTURES} — move the board to a new position!")
                    
                    # Auto-trigger calibration once we reach enough frames
                    if count >= TARGET_CAPTURES:
                        self.log(f"🎯 Reached {TARGET_CAPTURES} frames! Auto-running calibration...")
                        self.calibrate()
                    
            except Exception as e:
                self.log(f"Capture thread loop error: {str(e)}")
                
            # Throttle loop to ~12 FPS to prevent CPU starvation and stream lag
            elapsed = time.time() - start_time
            sleep_time = max(0.01, 0.08 - elapsed)
            time.sleep(sleep_time)

    def get_jpeg_frame(self):
        with self.lock:
            if self.latest_display_frame is None:
                # Placeholder frame
                blank = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
                cv2.putText(blank, "Initializing camera stream...", (CAPTURE_WIDTH // 4, CAPTURE_HEIGHT // 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (100, 100, 150), 2)
                _, jpeg = cv2.imencode('.jpg', blank)
                return jpeg.tobytes()
            
            _, jpeg = cv2.imencode('.jpg', self.latest_display_frame)
            return jpeg.tobytes()

    def get_latest_frame_with_id(self):
        with self.lock:
            if self.latest_display_frame is None:
                return None, 0
            
            _, jpeg = cv2.imencode('.jpg', self.latest_display_frame)
            return jpeg.tobytes(), self.frame_id

    def capture_frame(self):
        now = time.time()
        should_calibrate = False
        with self.lock:
            if not self.is_board_detected:
                self.log("Capture rejected: Checkerboard not detected.")
                return False, "Checkerboard not detected."
            if now - self.last_capture_time < self.capture_interval:
                return False, "Please wait a moment between captures."
            
            self.objpoints.append(self.objp)
            self.imgpoints.append(self.latest_corners)
            self.last_capture_time = now
            count = len(self.objpoints)
            self.log(f"[+] Captured frame {count}/{TARGET_CAPTURES}")
            
            if count >= TARGET_CAPTURES and not self.calibrated:
                should_calibrate = True
                
        if should_calibrate:
            self.log(f"🎯 Reached {TARGET_CAPTURES} frames! Auto-running calibration...")
            threading.Thread(target=self.calibrate, daemon=True).start()
            return True, f"Captured frame {count}. Auto-running calibration..."
            
        return True, f"Captured frame {count}."

    def delete_last(self):
        with self.lock:
            if len(self.objpoints) > 0:
                self.objpoints.pop()
                self.imgpoints.pop()
                count = len(self.objpoints)
                self.log(f"[-] Deleted last capture. Total frames: {count}")
                return True, f"Deleted last frame. Total left: {count}"
            else:
                self.log("Delete failed: Frame buffer is empty.")
                return False, "No frames to delete."

    def reset(self):
        with self.lock:
            self.objpoints = []
            self.imgpoints = []
            self.calibrated = False
            self.calibration_result = None
            self.log("Resetting calibration state. Frame count cleared.")
            return True, "Calibration state reset."

    def calibrate(self):
        with self.lock:
            if len(self.objpoints) < MIN_CAPTURES:
                msg = f"Insufficient captures: Need at least {MIN_CAPTURES} (have {len(self.objpoints)})"
                self.log(msg)
                return False, msg
            
            self.log("Initiating OpenCV calibration algorithms...")
            obj_pts = list(self.objpoints)
            img_pts = list(self.imgpoints)
            
        try:
            image_size = (CAPTURE_WIDTH, CAPTURE_HEIGHT)
            
            # Execute calibration (CPU bound, done without lock)
            ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
                obj_pts, img_pts, image_size, None, None
            )
            
            # Reprojection error computation
            per_frame_errors = []
            for i, (objp_val, imgp_val) in enumerate(zip(obj_pts, img_pts)):
                projected, _ = cv2.projectPoints(objp_val, rvecs[i], tvecs[i], camera_matrix, dist_coeffs)
                err = cv2.norm(imgp_val, projected, cv2.NORM_L2) / len(projected)
                per_frame_errors.append(err)
                
            mean_error = float(np.mean(per_frame_errors))
            max_error = float(np.max(per_frame_errors))
            
            # Save matrix and calibration info
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # Write camera_matrix.yaml
            yaml_path = os.path.join(OUTPUT_DIR, "camera_matrix.yaml")
            fs = cv2.FileStorage(yaml_path, cv2.FILE_STORAGE_WRITE)
            fs.write("calibration_date", ts)
            fs.write("image_width", CAPTURE_WIDTH)
            fs.write("image_height", CAPTURE_HEIGHT)
            fs.write("camera_name", "d435i_color")
            fs.write("camera_matrix", camera_matrix)
            fs.write("distortion_model", "plumb_bob")
            fs.write("distortion_coefficients", dist_coeffs)
            fs.write("reprojection_error", mean_error)
            fs.write("num_frames_used", len(obj_pts))
            fs.release()
            
            quality = ("Excellent" if mean_error < 0.3 else
                       "Good" if mean_error < 0.5 else
                       "Marginal" if mean_error < 1.0 else "Poor")
            
            result = {
                "calibration_date": ts,
                "camera": "Intel RealSense D435i",
                "resolution": f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
                "num_frames": len(obj_pts),
                "reprojection_error_mean_px": round(mean_error, 4),
                "reprojection_error_max_px": round(max_error, 4),
                "quality": quality,
                "calibrated_intrinsics": {
                    "fx": round(float(camera_matrix[0, 0]), 4),
                    "fy": round(float(camera_matrix[1, 1]), 4),
                    "cx": round(float(camera_matrix[0, 2]), 4),
                    "cy": round(float(camera_matrix[1, 2]), 4),
                    "k1": round(float(dist_coeffs[0, 0]), 6),
                    "k2": round(float(dist_coeffs[0, 1]), 6),
                    "p1": round(float(dist_coeffs[0, 2]), 6),
                    "p2": round(float(dist_coeffs[0, 3]), 6),
                    "k3": round(float(dist_coeffs[0, 4]), 6),
                },
                "factory_intrinsics": self.factory_intr
            }
            
            json_path = os.path.join(OUTPUT_DIR, "calibration_report.json")
            with open(json_path, "w") as f:
                json.dump(result, f, indent=2)
                
            clean_yaml_path = os.path.join(OUTPUT_DIR, "calibration_log.yaml")
            yaml_data = {
                "calibration_date": ts,
                "camera_name": "d435i_color",
                "image_width": int(CAPTURE_WIDTH),
                "image_height": int(CAPTURE_HEIGHT),
                "num_frames_used": int(len(obj_pts)),
                "reprojection_error": float(mean_error),
                "distortion_model": "plumb_bob",
                "camera_matrix": camera_matrix.tolist() if hasattr(camera_matrix, "tolist") else camera_matrix,
                "distortion_coefficients": dist_coeffs.flatten().tolist() if hasattr(dist_coeffs, "flatten") else dist_coeffs,
                "calibrated_intrinsics": {
                    "fx": round(float(camera_matrix[0, 0]), 4),
                    "fy": round(float(camera_matrix[1, 1]), 4),
                    "cx": round(float(camera_matrix[0, 2]), 4),
                    "cy": round(float(camera_matrix[1, 2]), 4),
                    "k1": round(float(dist_coeffs[0, 0]), 6),
                    "k2": round(float(dist_coeffs[0, 1]), 6),
                    "p1": round(float(dist_coeffs[0, 2]), 6),
                    "p2": round(float(dist_coeffs[0, 3]), 6),
                    "k3": round(float(dist_coeffs[0, 4]), 6),
                }
            }
            with open(clean_yaml_path, "w") as f:
                yaml.safe_dump(yaml_data, f, default_flow_style=False, sort_keys=False)
                
            with self.lock:
                self.calibrated = True
                self.calibration_result = result
            
            self.log("✓ Calibration finished successfully!")
            self.log(f"  Reprojection Error: {mean_error:.4f} px (Max: {max_error:.4f} px)")
            self.log(f"  Quality Grade: {quality}")
            self.log(f"  Calibrated Parameters Saved: {yaml_path}")
            self.log(f"  Standard YAML Log Saved: {clean_yaml_path}")
            
            return True, "Calibration successful!"
            
        except Exception as e:
            self.log(f"Error during calibration calculation: {str(e)}")
            return False, f"Calibration calculation error: {str(e)}"

    def stop(self):
        self.is_running = False
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass


camera_manager = CameraManager()

# ─────────────────────────────────────────────────────────────────────────────
#  HTTP ROUTER
# ─────────────────────────────────────────────────────────────────────────────

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class CalibrationRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Silence standard HTTP access logging to avoid cluttering stdout
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            
        elif self.path == '/video_feed':
            self.send_response(200)
            self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
            self.end_headers()
            try:
                last_frame_id = -1
                while camera_manager.is_running:
                    frame, frame_id = camera_manager.get_latest_frame_with_id()
                    if frame is not None and frame_id != last_frame_id:
                        last_frame_id = frame_id
                        self.wfile.write(b'--frame\r\n')
                        self.wfile.write(b'Content-Type: image/jpeg\r\n')
                        self.wfile.write(f'Content-Length: {len(frame)}\r\n\r\n'.encode('utf-8'))
                        self.wfile.write(frame)
                        self.wfile.write(b'\r\n')
                    else:
                        time.sleep(0.02)  # Check for new frame quickly (50Hz)
            except Exception:
                pass
                
        elif self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            with camera_manager.lock:
                status = {
                    "board_detected": camera_manager.is_board_detected,
                    "captured_count": len(camera_manager.objpoints),
                    "min_captures": MIN_CAPTURES,
                    "target_captures": TARGET_CAPTURES,
                    "logs": list(camera_manager.logs),
                    "calibrated": camera_manager.calibrated,
                    "calibration_result": camera_manager.calibration_result,
                    "auto_capture": camera_manager.auto_capture_enabled
                }
            self.wfile.write(json.dumps(status).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def do_POST(self):
        response = {"success": False, "message": "Method not recognized"}
        
        if self.path == '/api/capture':
            success, msg = camera_manager.capture_frame()
            response = {"success": success, "message": msg}
        elif self.path == '/api/delete':
            success, msg = camera_manager.delete_last()
            response = {"success": success, "message": msg}
        elif self.path == '/api/reset':
            success, msg = camera_manager.reset()
            response = {"success": success, "message": msg}
        elif self.path == '/api/calibrate':
            success, msg = camera_manager.calibrate()
            response = {"success": success, "message": msg}
        elif self.path == '/api/auto_start':
            with camera_manager.lock:
                camera_manager.auto_capture_enabled = True
            camera_manager.log("Auto-capture ENABLED")
            response = {"success": True, "message": "Auto-capture enabled"}
        elif self.path == '/api/auto_stop':
            with camera_manager.lock:
                camera_manager.auto_capture_enabled = False
            camera_manager.log("Auto-capture PAUSED")
            response = {"success": True, "message": "Auto-capture paused"}
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

# ─────────────────────────────────────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    if not camera_manager.start_camera():
        print("[!] Camera initialization failed. Exiting.")
        return

    # Start HTTP server
    port = PORT
    httpd = None
    while port < PORT + 10:
        try:
            server_address = ('', port)
            httpd = ThreadedHTTPServer(server_address, CalibrationRequestHandler)
            break
        except OSError as e:
            if e.errno == 98:  # Address already in use
                print(f"[!] Port {port} is in use, trying port {port + 1}...")
                port += 1
            else:
                raise e

    if httpd is None:
        print("[!] Could not bind to any port in range 5000-5010. Exiting.")
        camera_manager.stop()
        return
    
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Get primary local IP address to print for the user
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = 'localhost'
    finally:
        s.close()
        
    print("\n" + "=" * 65)
    print(f"  REAL-TIME CALIBRATION DASHBOARD RUNNING")
    print(f"  Local Access:      http://localhost:{port}")
    print(f"  Network Access:    http://{local_ip}:{port}")
    print("=" * 65)
    print("  Use the web interface on your laptop/phone to align the")
    print("  checkerboard. Press Ctrl+C in this terminal to terminate.")
    print("=" * 65 + "\n")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[Terminating] Stopping server and camera stream...")
    finally:
        camera_manager.stop()
        httpd.server_close()
        print("[Done] Safe shutdown completed.")

if __name__ == "__main__":
    main()
