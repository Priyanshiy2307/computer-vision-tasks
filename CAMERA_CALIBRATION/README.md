# Intel RealSense D435i — Checkerboard Calibration

Intrinsic calibration for the **Intel RealSense D435i** color camera, built for the **Unitree G1** robot. The workflow uses OpenCV and a physical checkerboard (**9×6 inner corners**, **24 mm** squares).

## Prerequisites

- Intel RealSense D435i on USB 3
- Flat, rigid printed checkerboard (laser print at 100% scale recommended)
- Python 3.8+
- [Intel RealSense SDK](https://github.com/IntelRealSense/librealsense) (required by `pyrealsense2`)

## Installation

```bash
cd camera_calibration
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirement.txt
```

## Quick start

| Goal | Command |
|------|---------|
| Calibrate with a local display | `python d435i_checkerboard_calibration.py` |
| Calibrate on G1 via browser | `python d435i_calibration_G1.py` then open `http://<robot-ip>:5000` |
| Check last run | `python verify_calibration.py` |

Calibration artifacts are written to **`calibration_output/`** (created at runtime; not tracked in git).

## Scripts

### `d435i_checkerboard_calibration.py`

Interactive calibration using an OpenCV window (1280×720 color + depth stream).

| Key | Action |
|-----|--------|
| **SPACE** | Capture frame (checkerboard must be detected) |
| **D** | Remove last capture |
| **C** | Run calibration (minimum 25 captures) |
| **Q** | Quit without saving |

After calibration, shows a side-by-side original vs undistorted preview.

### `d435i_calibration_G1.py`

Headless-friendly server for the robot: live MJPEG stream and a web dashboard on port **5000** (falls back to 5001–5009 if busy). Tries several color resolutions if USB bandwidth is limited. **Auto-capture** every 5 seconds when the board is visible; manual capture and calibration via UI or keyboard (**SPACE**, **D**, **C**, **R**).

### `verify_calibration.py`

Reads `./calibration_output/calibration_report.json`, or falls back to `camera_matrix.yaml`. Prints frame count, resolution, mean reprojection error, and a quality summary. Prints `eureka` when error &lt; 1.0 px and at least 20 frames were used (for automated checks).

## Output files

All paths are under **`calibration_output/`**:

| File | Description |
|------|-------------|
| `camera_matrix.yaml` | OpenCV FileStorage — camera matrix + distortion (use in CV / ROS) |
| `calibration_report.json` | Metrics, factory vs calibrated intrinsics, quality label |
| `calibration_log.yaml` | Plain YAML export (written by the G1 web script only) |

## Capture guidelines

- Collect **25–35** frames: vary **tilt** (pitch/yaw), **distance** (~30–80 cm), and **position** (including image corners).
- Keep the **entire board** in frame; hold still when capturing.
- Board must stay **flat**; warped targets degrade distortion estimates.

## Quality targets (mean reprojection error)

| Error (px) | Interpretation |
|------------|----------------|
| &lt; 0.3 | Excellent |
| 0.3 – 0.5 | Good — suitable for manipulation / pose estimation |
| 0.5 – 1.0 | Marginal — consider recapturing |
| &gt; 1.0 | Poor — recalibrate |

## Repository layout

```
d435i_checkerboard_calibration.py   # Local OpenCV workflow
d435i_calibration_G1.py             # Web UI + auto-capture
verify_calibration.py               # Post-run diagnostic
requirement.txt                     # Python dependencies
calibration_output/                 # Generated locally (gitignored)
```

## Configuration

Both calibration scripts share these defaults (edit at the top of each file if your board differs):

- Inner corners: **9 × 6**
- Square size: **24 mm**
- Minimum captures: **25**; target: **30**
- Default color resolution: **1280×720 @ 30 fps** (G1 script may negotiate lower if needed)
