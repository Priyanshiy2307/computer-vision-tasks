"""
RealSense D435i Dataset Capture Tool
------------------------------------
Streams live RGB + Depth video from an Intel RealSense D435i.

Press 'c' to capture:
    RGB   -> 0001.png
    Depth -> 0001_depth.png

Press 'q' or ESC to quit.

Requirements:
    pip install pyrealsense2 opencv-python numpy

Usage:
    python d435i_capture_dataset.py

    python d435i_capture_dataset.py --folder my_dataset

    python d435i_capture_dataset.py --width 1280 --height 720 --fps 30
"""

import os
import argparse
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


def get_default_output_dir(folder_name: str) -> Path:
    """Create and return <Downloads>/<folder_name>."""
    downloads = Path.home() / "Downloads"
    out_dir = downloads / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def get_next_index(out_dir: Path) -> int:
    """Find the next available sequential image index."""
    existing = list(out_dir.glob("*.png"))

    if not existing:
        return 1

    max_idx = 0

    for f in existing:
        try:
            idx = int(f.stem)
            max_idx = max(max_idx, idx)
        except ValueError:
            # Ignore files such as 0001_depth.png
            continue

    return max_idx + 1


def main():

    parser = argparse.ArgumentParser(
        description="Intel RealSense D435i RGB + Depth Dataset Capture Tool"
    )

    parser.add_argument(
        "--folder",
        type=str,
        default="d435i_dataset",
        help="Folder name under ~/Downloads"
    )

    parser.add_argument(
        "--width",
        type=int,
        default=640,
        help="Frame width"
    )

    parser.add_argument(
        "--height",
        type=int,
        default=480,
        help="Frame height"
    )

    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Stream FPS"
    )

    args = parser.parse_args()

    # ---------------------------------------------------------
    # Output directory
    # ---------------------------------------------------------

    out_dir = get_default_output_dir(args.folder)

    print(f"[INFO] Saving dataset to:")
    print(f"       {out_dir}")

    # ---------------------------------------------------------
    # RealSense pipeline
    # ---------------------------------------------------------

    pipeline = rs.pipeline()
    config = rs.config()

    # RGB camera
    config.enable_stream(
        rs.stream.color,
        args.width,
        args.height,
        rs.format.bgr8,
        args.fps
    )

    # Depth camera
    config.enable_stream(
        rs.stream.depth,
        args.width,
        args.height,
        rs.format.z16,
        args.fps
    )

    # Start camera
    profile = pipeline.start(config)

    # ---------------------------------------------------------
    # Depth scale
    # ---------------------------------------------------------

    depth_sensor = profile.get_device().first_depth_sensor()
    depth_scale = depth_sensor.get_depth_scale()

    print(f"[INFO] Depth scale: {depth_scale} meters/unit")

    # ---------------------------------------------------------
    # Align depth to RGB
    # ---------------------------------------------------------

    align = rs.align(rs.stream.color)

    # ---------------------------------------------------------
    # Dataset counter
    # ---------------------------------------------------------

    count = get_next_index(out_dir)

    print()
    print("[INFO] D435i streaming started.")
    print("[INFO] Press 'c' to capture.")
    print("[INFO] Press 'q' or ESC to quit.")
    print()

    try:

        while True:

            # -------------------------------------------------
            # Get frames
            # -------------------------------------------------

            frames = pipeline.wait_for_frames()

            # Align depth to color
            aligned_frames = align.process(frames)

            color_frame = aligned_frames.get_color_frame()
            depth_frame = aligned_frames.get_depth_frame()

            if not color_frame or not depth_frame:
                continue

            # -------------------------------------------------
            # Convert frames to NumPy
            # -------------------------------------------------

            color_image = np.asanyarray(
                color_frame.get_data()
            )

            depth_image = np.asanyarray(
                depth_frame.get_data()
            )

            # -------------------------------------------------
            # Create depth visualization
            # -------------------------------------------------

            depth_colormap = cv2.applyColorMap(
                cv2.convertScaleAbs(
                    depth_image,
                    alpha=0.03
                ),
                cv2.COLORMAP_JET
            )

            # -------------------------------------------------
            # Center depth
            # -------------------------------------------------

            h, w = depth_image.shape

            center_x = w // 2
            center_y = h // 2

            center_depth = depth_frame.get_distance(
                center_x,
                center_y
            )

            # -------------------------------------------------
            # RGB display
            # -------------------------------------------------

            rgb_display = color_image.copy()

            cv2.drawMarker(
                rgb_display,
                (center_x, center_y),
                (0, 255, 0),
                markerType=cv2.MARKER_CROSS,
                markerSize=20,
                thickness=2
            )

            cv2.putText(
                rgb_display,
                f"Next save: {count:04d}",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            cv2.putText(
                rgb_display,
                f"Center depth: {center_depth:.3f} m",
                (10, 55),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2
            )

            cv2.putText(
                rgb_display,
                "'c' = capture   'q' = quit",
                (10, 85),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2
            )

            # -------------------------------------------------
            # Depth display
            # -------------------------------------------------

            cv2.drawMarker(
                depth_colormap,
                (center_x, center_y),
                (255, 255, 255),
                markerType=cv2.MARKER_CROSS,
                markerSize=20,
                thickness=2
            )

            cv2.putText(
                depth_colormap,
                f"Depth: {center_depth:.3f} m",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2
            )

            # -------------------------------------------------
            # Show windows
            # -------------------------------------------------

            cv2.imshow(
                "D435i RGB - Press 'c' to capture",
                rgb_display
            )

            cv2.imshow(
                "D435i Depth",
                depth_colormap
            )

            # -------------------------------------------------
            # Keyboard
            # -------------------------------------------------

            key = cv2.waitKey(1) & 0xFF

            # Capture
            if key == ord('c'):

                rgb_filename = out_dir / f"{count:04d}.png"
                depth_filename = out_dir / f"{count:04d}_depth.png"

                # Save RGB
                cv2.imwrite(
                    str(rgb_filename),
                    color_image
                )

                # Save raw 16-bit depth
                cv2.imwrite(
                    str(depth_filename),
                    depth_image
                )

                print(
                    f"[SAVED] RGB   : {rgb_filename}"
                )

                print(
                    f"[SAVED] Depth : {depth_filename}"
                )

                print(
                    f"[INFO] Center depth: {center_depth:.3f} m"
                )

                count += 1

            # Quit
            elif key == ord('q') or key == 27:

                print("[INFO] Exiting.")
                break

    finally:

        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()