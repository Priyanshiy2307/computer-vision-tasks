"""
=============================================================================
  Intel RealSense D435i — Intrinsic Calibration via Checkerboard
  For: Unitree G1 Robot
=============================================================================

CHECKERBOARD SPECS  (print this before running):
  - Inner corners:  9 x 6  (columns x rows of internal corners)
  - Square size:    24 mm  (each square = 2.4 cm in the real world)
  - Board total:    10 x 7 squares  →  ~240 mm x 168 mm  (A4 landscape fits)

  WHY 9x6?
    - Asymmetric enough that OpenCV can tell orientation unambiguously
    - Not so large that it doesn't fit in frame at close range
    - Widely tested, minimal chance of false corner detection

  HOW TO PRINT:
    - Use a laser printer (inkjet can bleed edges slightly)
    - Print at 100% scale (no "fit to page")
    - Glue or tape flat onto a rigid surface (cardboard, MDF, foam-board)
    - Any curl/warp = bad calibration. Flat is critical.

=============================================================================
  CAPTURE CHECKLIST  (read before you start the script)
=============================================================================

  You need 25–35 good frames spread across these EIGHT positions/orientations.
  The script will tell you live how many you've captured.

  POSITION GUIDE — move the board, keep camera fixed:

    1.  CENTRE, facing straight at camera              ← start here
    2.  CENTRE, tilt top away ~30°  (pitch backward)
    3.  CENTRE, tilt top toward you ~30°  (pitch forward)
    4.  CENTRE, tilt left side away ~30°  (yaw left)
    5.  CENTRE, tilt right side away ~30°  (yaw right)
    6.  TOP-LEFT corner of frame, slight tilt
    7.  TOP-RIGHT corner of frame, slight tilt
    8.  BOTTOM-LEFT corner of frame, slight tilt
    9.  BOTTOM-RIGHT corner of frame, slight tilt
    10. CLOSE RANGE (~30 cm), facing straight
    11. FAR range (~80 cm), facing straight
    12. DIAGONAL tilt (corner of board closest to camera)
    ... repeat with small variations until you hit 25+ captures

  KEY RULES:
    - Hold STILL when pressing SPACE (motion blur kills corners)
    - Board must be FULLY visible in the frame every time
    - Vary distance (30–80 cm range works well)
    - Vary tilt angle (15–45 degrees in multiple axes)
    - Cover all four quadrants of the image
    - DO NOT just translate the board flat — tilt is what constrains distortion

  REPROJECTION ERROR TARGET:
    - < 0.3 px  →  Excellent
    - 0.3–0.5 px  →  Good (acceptable for robot grasping)
    - 0.5–1.0 px  →  Marginal, consider recapturing
    - > 1.0 px  →  Reject, recapture from scratch

=============================================================================
"""

import cv2
import numpy as np
import pyrealsense2 as rs
import os
import json
import time
from datetime import datetime

# ─────────────────────────────────────────────────────────────────────────────
#  CONFIGURATION  — edit these if you change your board or resolution
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

# ─────────────────────────────────────────────────────────────────────────────


def setup_realsense():
    """
    Initialise the D435i pipeline.
    Returns the pipeline and the color stream profile.
    """
    pipeline = rs.pipeline()
    config   = rs.config()

    config.enable_stream(rs.stream.color, CAPTURE_WIDTH, CAPTURE_HEIGHT,
                         rs.format.bgr8, CAPTURE_FPS)

    # Also enable depth so you can visually verify alignment later
    config.enable_stream(rs.stream.depth, 848, 480,
                         rs.format.z16, CAPTURE_FPS)

    profile = pipeline.start(config)

    # Lock auto-exposure after 2 seconds — prevents brightness jumps during capture
    color_sensor = profile.get_device().query_sensors()[1]
    time.sleep(2)
    color_sensor.set_option(rs.option.enable_auto_exposure, 1)

    print("[RealSense] Pipeline started.")
    print(f"[RealSense] Color: {CAPTURE_WIDTH}x{CAPTURE_HEIGHT} @ {CAPTURE_FPS}fps")
    print(f"[RealSense] Factory intrinsics stored inside camera EEPROM (we will override with calibrated values)")

    return pipeline, profile


def get_factory_intrinsics(profile):
    """
    Read the factory-programmed intrinsics from the camera.
    These are our starting reference — we'll compare against our calibrated result.
    """
    color_profile = profile.get_stream(rs.stream.color)
    intr = color_profile.as_video_stream_profile().get_intrinsics()

    print("\n[Factory intrinsics from D435i EEPROM]")
    print(f"  fx={intr.fx:.2f}  fy={intr.fy:.2f}")
    print(f"  cx={intr.ppx:.2f}  cy={intr.ppy:.2f}")
    print(f"  distortion model: {intr.model}")
    print(f"  coeffs: {[round(c,6) for c in intr.coeffs]}")

    return intr


def prepare_object_points():
    """
    Build the 3-D coordinates of the checkerboard corners in the board's
    own coordinate system.

    The board lies flat in the Z=0 plane.
    Corner (0,0,0) is top-left, then X increases right, Y increases down.
    Each step is SQUARE_SIZE_MM millimetres.

    Example for 3x2 board (simplified):
      (0,0,0)  (30,0,0)  (60,0,0)
      (0,30,0) (30,30,0) (60,30,0)
    """
    objp = np.zeros((CHECKERBOARD_ROWS * CHECKERBOARD_COLS, 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD_COLS,
                            0:CHECKERBOARD_ROWS].T.reshape(-1, 2)
    objp *= SQUARE_SIZE_MM   # scale from grid units to millimetres
    return objp


def detect_corners(frame_bgr, objp):
    """
    Try to find the checkerboard corners in one frame.

    Returns:
        found  (bool)  — True if corners were detected
        corners_sub  — subpixel-refined corner locations (Nx1x2 float32)
        frame_draw   — frame with corners drawn on it for visualisation
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    # Fast coarse detection
    flags = (cv2.CALIB_CB_ADAPTIVE_THRESH +
             cv2.CALIB_CB_NORMALIZE_IMAGE +
             cv2.CALIB_CB_FAST_CHECK)

    found, corners = cv2.findChessboardCorners(
        gray,
        (CHECKERBOARD_COLS, CHECKERBOARD_ROWS),
        flags
    )

    frame_draw = frame_bgr.copy()

    if found:
        # Subpixel refinement — moves corners to within ~0.01 px accuracy
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        corners_sub = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)

        # Draw the detected corners
        cv2.drawChessboardCorners(frame_draw,
                                  (CHECKERBOARD_COLS, CHECKERBOARD_ROWS),
                                  corners_sub, found)
        return True, corners_sub, frame_draw

    return False, None, frame_draw


def run_calibration(objpoints_list, imgpoints_list):
    """
    Run OpenCV's calibrateCamera on all accumulated frame pairs.

    objpoints_list : list of (54x3) arrays — 3-D board corners (same for every frame)
    imgpoints_list : list of (54x1x2) arrays — 2-D detected corners per frame

    Returns camera_matrix, dist_coeffs, reprojection_error
    """
    image_size = (CAPTURE_WIDTH, CAPTURE_HEIGHT)

    print(f"\n[Calibration] Running with {len(objpoints_list)} frames...")

    ret, camera_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(
        objpoints_list,
        imgpoints_list,
        image_size,
        None,       # initial camera matrix (None = auto-estimate)
        None        # initial distortion coeffs (None = start from zero)
    )

    # Compute per-frame reprojection error for diagnostics
    per_frame_errors = []
    for i, (objp, imgp) in enumerate(zip(objpoints_list, imgpoints_list)):
        projected, _ = cv2.projectPoints(objp, rvecs[i], tvecs[i],
                                         camera_matrix, dist_coeffs)
        err = cv2.norm(imgp, projected, cv2.NORM_L2) / len(projected)
        per_frame_errors.append(err)

    mean_error = float(np.mean(per_frame_errors))
    max_error  = float(np.max(per_frame_errors))

    return camera_matrix, dist_coeffs, rvecs, tvecs, mean_error, max_error, per_frame_errors


def save_results(camera_matrix, dist_coeffs, mean_error, per_frame_errors,
                 factory_intr, num_frames):
    """
    Save calibration results to disk in multiple formats:
      1. camera_matrix.yaml  — OpenCV FileStorage format (used by most CV code)
      2. calibration_report.json  — human-readable report
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 1. YAML for use in OpenCV / ROS ────────────────────────────────────
    yaml_path = os.path.join(OUTPUT_DIR, "camera_matrix.yaml")
    fs = cv2.FileStorage(yaml_path, cv2.FILE_STORAGE_WRITE)
    fs.write("calibration_date",    ts)
    fs.write("image_width",         CAPTURE_WIDTH)
    fs.write("image_height",        CAPTURE_HEIGHT)
    fs.write("camera_name",         "d435i_color")
    fs.write("camera_matrix",       camera_matrix)
    fs.write("distortion_model",    "plumb_bob")
    fs.write("distortion_coefficients", dist_coeffs)
    fs.write("reprojection_error",  mean_error)
    fs.write("num_frames_used",     num_frames)
    fs.release()

    # ── 2. JSON report ───────────────────────────────────────────────────────
    report = {
        "calibration_date"    : ts,
        "camera"              : "Intel RealSense D435i",
        "resolution"          : f"{CAPTURE_WIDTH}x{CAPTURE_HEIGHT}",
        "checkerboard"        : f"{CHECKERBOARD_COLS}x{CHECKERBOARD_ROWS} inner corners, {SQUARE_SIZE_MM}mm squares",
        "num_frames"          : num_frames,
        "reprojection_error_mean_px": round(mean_error, 4),
        "quality"             : ("Excellent" if mean_error < 0.3 else
                                 "Good"      if mean_error < 0.5 else
                                 "Marginal"  if mean_error < 1.0 else "Poor"),
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
        "factory_intrinsics": {
            "fx": round(factory_intr.fx, 4),
            "fy": round(factory_intr.fy, 4),
            "cx": round(factory_intr.ppx, 4),
            "cy": round(factory_intr.ppy, 4),
        },
        "per_frame_errors_px" : [round(e, 4) for e in per_frame_errors],
    }

    json_path = os.path.join(OUTPUT_DIR, "calibration_report.json")
    with open(json_path, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n[Saved] {yaml_path}")
    print(f"[Saved] {json_path}")
    return yaml_path, json_path


def show_undistorted_preview(pipeline, camera_matrix, dist_coeffs):
    """
    After calibration, show a live side-by-side: original vs undistorted.
    Press Q to quit.
    """
    print("\n[Preview] Showing undistorted preview — press Q to quit")

    # Pre-compute undistortion maps (faster than undistort() per frame)
    map1, map2 = cv2.initUndistortRectifyMap(
        camera_matrix, dist_coeffs, None,
        camera_matrix,
        (CAPTURE_WIDTH, CAPTURE_HEIGHT),
        cv2.CV_16SC2
    )

    while True:
        frames      = pipeline.wait_for_frames()
        color_frame = frames.get_color_frame()
        if not color_frame:
            continue

        img         = np.asanyarray(color_frame.get_data())
        undistorted = cv2.remap(img, map1, map2, cv2.INTER_LINEAR)

        # Resize both to half height for side-by-side display
        h2 = CAPTURE_HEIGHT // 2
        w2 = CAPTURE_WIDTH  // 2
        left  = cv2.resize(img,         (w2, h2))
        right = cv2.resize(undistorted, (w2, h2))

        cv2.putText(left,  "Original",    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 80, 255), 2)
        cv2.putText(right, "Undistorted", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 80), 2)

        combined = np.hstack([left, right])
        cv2.imshow("Calibration result — Q to quit", combined)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cv2.destroyAllWindows()


def print_summary(camera_matrix, dist_coeffs, mean_error, max_error,
                  per_frame_errors, factory_intr):
    """Print a clean human-readable summary to the terminal."""
    fx, fy = camera_matrix[0, 0], camera_matrix[1, 1]
    cx, cy = camera_matrix[0, 2], camera_matrix[1, 2]

    print("\n" + "=" * 60)
    print("  CALIBRATION COMPLETE")
    print("=" * 60)

    quality = ("✓ EXCELLENT" if mean_error < 0.3 else
               "✓ GOOD"      if mean_error < 0.5 else
               "⚠ MARGINAL"  if mean_error < 1.0 else
               "✗ POOR — recapture recommended")

    print(f"\n  Reprojection error:  {mean_error:.4f} px  (max: {max_error:.4f} px)")
    print(f"  Quality:             {quality}")
    print(f"  Frames used:         {len(per_frame_errors)}")

    print(f"\n  ── Calibrated intrinsics ──────────────────────────")
    print(f"  fx = {fx:>10.4f}   fy = {fy:>10.4f}")
    print(f"  cx = {cx:>10.4f}   cy = {cy:>10.4f}")
    print(f"  k1 = {dist_coeffs[0,0]:>10.6f}   k2 = {dist_coeffs[0,1]:>10.6f}")
    print(f"  p1 = {dist_coeffs[0,2]:>10.6f}   p2 = {dist_coeffs[0,3]:>10.6f}")
    print(f"  k3 = {dist_coeffs[0,4]:>10.6f}")

    print(f"\n  ── Factory intrinsics (EEPROM) ─────────────────────")
    print(f"  fx = {factory_intr.fx:>10.4f}   fy = {factory_intr.fy:>10.4f}")
    print(f"  cx = {factory_intr.ppx:>10.4f}   cy = {factory_intr.ppy:>10.4f}")

    dfx = abs(fx - factory_intr.fx)
    dfy = abs(fy - factory_intr.fy)
    print(f"\n  Δfx = {dfx:.2f} px,  Δfy = {dfy:.2f} px  (difference from factory)")
    if dfx > 20 or dfy > 20:
        print("  ⚠  Large deviation from factory — double-check board flatness")
    else:
        print("  ✓  Within expected range of factory values")

    print("\n  Worst frames (highest reprojection error):")
    sorted_errors = sorted(enumerate(per_frame_errors), key=lambda x: x[1], reverse=True)
    for idx, err in sorted_errors[:3]:
        print(f"     Frame {idx+1:>2d}: {err:.4f} px")

    print("=" * 60)


# ─────────────────────────────────────────────────────────────────────────────
#  MAIN CAPTURE LOOP
# ─────────────────────────────────────────────────────────────────────────────

def main():
    print(__doc__)  # Print the capture guide at startup

    # ── Setup ────────────────────────────────────────────────────────────────
    pipeline, profile   = setup_realsense()
    factory_intr        = get_factory_intrinsics(profile)
    objp                = prepare_object_points()

    objpoints = []   # accumulated 3-D board corners  (grows with each capture)
    imgpoints = []   # accumulated 2-D detected corners

    last_capture_time   = 0
    MIN_CAPTURE_INTERVAL = 1.0   # seconds between captures (prevents duplicates)
    camera_matrix        = None
    dist_coeffs          = None

    print("\n" + "=" * 60)
    print("  LIVE CAPTURE")
    print("=" * 60)
    print("  SPACE  — capture this frame")
    print("  C      — run calibration now  (available after 25 captures)")
    print("  D      — delete last capture  (if it looked bad)")
    print("  Q      — quit without saving")
    print("=" * 60 + "\n")

    try:
        while True:
            frames      = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue

            img = np.asanyarray(color_frame.get_data())

            # Try to detect corners in every live frame (for the overlay)
            found, corners, display_img = detect_corners(img, objp)

            n = len(objpoints)

            # ── Status bar overlaid on frame ──────────────────────────────
            bar_color  = (0, 180, 0) if found else (0, 60, 200)
            status_txt = f"Captured: {n}/{TARGET_CAPTURES}  |  {'BOARD DETECTED — press SPACE' if found else 'Searching for board...'}"
            cv2.rectangle(display_img, (0, 0), (CAPTURE_WIDTH, 44), (20, 20, 20), -1)
            cv2.putText(display_img, status_txt, (14, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, bar_color, 2)

            if n >= MIN_CAPTURES:
                cv2.putText(display_img, "C = calibrate", (CAPTURE_WIDTH - 210, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 230, 200), 2)

            # ── Hint messages ─────────────────────────────────────────────
            hints = [
                "Tilt board in all directions",
                "Cover corners of the frame",
                "Vary distance 30-80 cm",
                "Hold still before pressing SPACE",
            ]
            hint = hints[min(n // 7, len(hints) - 1)]
            cv2.putText(display_img, f"Tip: {hint}",
                        (14, CAPTURE_HEIGHT - 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (200, 200, 100), 1)

            cv2.imshow("D435i Checkerboard Calibration", display_img)
            key = cv2.waitKey(1) & 0xFF

            # ── Key: SPACE — capture ──────────────────────────────────────
            if key == ord(' '):
                now = time.time()
                if not found:
                    print("  [!] No board detected — move the board into frame")
                elif now - last_capture_time < MIN_CAPTURE_INTERVAL:
                    print("  [!] Too fast — hold still and wait a moment")
                else:
                    objpoints.append(objp)
                    imgpoints.append(corners)
                    last_capture_time = now
                    n = len(objpoints)
                    print(f"  [+] Captured frame {n:>2d}/{TARGET_CAPTURES}", end="")
                    if n < 10:
                        print(f"  — try some tilt now")
                    elif n < 18:
                        print(f"  — cover the corners of the image")
                    elif n < MIN_CAPTURES:
                        print(f"  — almost there, {MIN_CAPTURES - n} more needed")
                    else:
                        print(f"  — looking good! press C when ready to calibrate")

                    # Flash green border to confirm capture
                    flash = img.copy()
                    cv2.rectangle(flash, (0, 0), (CAPTURE_WIDTH, CAPTURE_HEIGHT),
                                  (0, 255, 80), 12)
                    cv2.imshow("D435i Checkerboard Calibration", flash)
                    cv2.waitKey(200)

            # ── Key: D — delete last ──────────────────────────────────────
            elif key == ord('d') and len(objpoints) > 0:
                objpoints.pop()
                imgpoints.pop()
                print(f"  [-] Deleted last capture. Remaining: {len(objpoints)}")

            # ── Key: C — calibrate ────────────────────────────────────────
            elif key == ord('c'):
                if len(objpoints) < MIN_CAPTURES:
                    print(f"  [!] Need at least {MIN_CAPTURES} captures (have {len(objpoints)})")
                else:
                    cv2.destroyAllWindows()
                    (camera_matrix, dist_coeffs,
                     rvecs, tvecs,
                     mean_error, max_error,
                     per_frame_errors) = run_calibration(objpoints, imgpoints)

                    print_summary(camera_matrix, dist_coeffs, mean_error, max_error,
                                  per_frame_errors, factory_intr)

                    save_results(camera_matrix, dist_coeffs, mean_error,
                                 per_frame_errors, factory_intr, len(objpoints))

                    # Show undistorted preview
                    show_undistorted_preview(pipeline, camera_matrix, dist_coeffs)
                    break

            # ── Key: Q — quit ─────────────────────────────────────────────
            elif key == ord('q'):
                print("  [Quit] Exiting without saving.")
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()
        print("\n[Done]")


if __name__ == "__main__":
    main()
