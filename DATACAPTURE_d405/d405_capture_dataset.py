"""
RealSense D405 Dataset Capture Tool
------------------------------------
Streams live RGB video from an Intel RealSense D405 camera.
Press 'c' to capture and save the current frame as a sequentially
numbered image (0001.png, 0002.png, ...).
Press 'q' or ESC to quit.

Requirements:
    pip install pyrealsense2 opencv-python

Usage:
    python d405_capture_dataset.py
    python d405_capture_dataset.py --folder my_dataset
    python d405_capture_dataset.py --width 1280 --height 720 --fps 30
"""

import os
import argparse
from pathlib import Path

import cv2
import numpy as np
import pyrealsense2 as rs


def get_default_output_dir(folder_name: str) -> Path:
    """Create (if needed) and return <Downloads>/<folder_name>."""
    downloads = Path.home() / "Downloads"
    out_dir = downloads / folder_name
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def get_next_index(out_dir: Path) -> int:
    """Find the next available sequential index based on existing files."""
    existing = list(out_dir.glob("*.png"))
    if not existing:
        return 1
    max_idx = 0
    for f in existing:
        try:
            idx = int(f.stem)
            max_idx = max(max_idx, idx)
        except ValueError:
            continue
    return max_idx + 1


def main():
    parser = argparse.ArgumentParser(description="D405 dataset capture tool")
    parser.add_argument("--folder", type=str, default="d405_dataset",
                         help="Folder name to create under ~/Downloads (default: d405_dataset)")
    parser.add_argument("--width", type=int, default=640, help="Frame width")
    parser.add_argument("--height", type=int, default=480, help="Frame height")
    parser.add_argument("--fps", type=int, default=30, help="Stream FPS")
    args = parser.parse_args()

    out_dir = get_default_output_dir(args.folder)
    print(f"[INFO] Saving captures to: {out_dir}")

    # ---- RealSense pipeline setup (D405 supports color stream) ----
    pipeline = rs.pipeline()
    config = rs.config()
    config.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)

    profile = pipeline.start(config)
    print("[INFO] Streaming started. Press 'c' to capture, 'q'/ESC to quit.")

    count = get_next_index(out_dir)

    try:
        while True:
            frames = pipeline.wait_for_frames()
            color_frame = frames.get_color_frame()
            if not color_frame:
                continue

            color_image = np.asanyarray(color_frame.get_data())

            display = color_image.copy()
            cv2.putText(display, f"Next save: {count:04d}.png  |  'c'=capture  'q'=quit",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
            cv2.imshow("D405 Feed - press 'c' to capture", display)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('c'):
                filename = out_dir / f"{count:04d}.png"
                cv2.imwrite(str(filename), color_image)
                print(f"[SAVED] {filename}")
                count += 1
            elif key == ord('q') or key == 27:  # 'q' or ESC
                print("[INFO] Exiting.")
                break

    finally:
        pipeline.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
