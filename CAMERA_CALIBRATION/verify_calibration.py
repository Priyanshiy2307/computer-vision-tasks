#!/usr/bin/env python3
import os
import json
import yaml

REPORT_PATH = "./calibration_output/calibration_report.json"
YAML_PATH = "./calibration_output/camera_matrix.yaml"

def verify():
    # Try loading JSON report first
    data = None
    if os.path.exists(REPORT_PATH):
        try:
            with open(REPORT_PATH, 'r') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error reading JSON report: {e}")

    # Fallback to YAML if JSON fails/missing
    mean_error = None
    num_frames = 0
    
    if data:
        mean_error = data.get("reprojection_error_mean_px")
        num_frames = data.get("num_frames", 0)
        quality = data.get("quality", "Unknown")
        resolution = data.get("resolution", "Unknown")
    elif os.path.exists(YAML_PATH):
        try:
            # Parse YAML manually or via opencv/pyyaml
            with open(YAML_PATH, 'r') as f:
                content = f.read()
                # Basic parsing since it's opencv yaml format
                for line in content.split('\n'):
                    if 'reprojection_error' in line:
                        mean_error = float(line.split(':')[-1].strip())
                    if 'num_frames_used' in line:
                        num_frames = int(line.split(':')[-1].strip())
            quality = "Good" if mean_error < 0.5 else "Acceptable" if mean_error < 1.0 else "Poor"
            resolution = "Resolved from file"
        except Exception as e:
            print(f"Error reading YAML: {e}")
    else:
        print("[!] No calibration output found! Run the calibration first.")
        return

    if mean_error is None:
        print("[!] Calibration files exist but could not extract reprojection error.")
        return

    print("=" * 60)
    print("           CAMERA CALIBRATION DIAGNOSTIC")
    print("=" * 60)
    print(f"  Frames Used:        {num_frames}")
    print(f"  Resolution:         {resolution}")
    print(f"  Reprojection Error: {mean_error:.4f} pixels (mean)")
    
    # Accuracy magnitude explanation
    print("-" * 60)
    print("  Accuracy Evaluation:")
    if mean_error < 0.3:
        status = "EXCELLENT"
        desc = "Extremely accurate. Re-projected grid aligns with sub-pixel precision (< 0.3 px)."
    elif mean_error < 0.5:
        status = "GOOD"
        desc = "High accuracy. Ready for 3D pose estimation and spatial tracking."
    elif mean_error < 1.0:
        status = "ACCEPTABLE"
        desc = "Moderate accuracy. OK for basic applications, but can be improved."
    else:
        status = "POOR / FAILED"
        desc = "High distortion correction error (> 1.0 px). Re-run calibration."
    
    print(f"  Quality Class:      {status}")
    print(f"  Description:        {desc}")
    print("=" * 60)

    # Output eureka if calibration succeeded with good quality
    if mean_error < 1.0 and num_frames >= 20:
        print("\neureka\n")
    else:
        print("\n[!] Calibration accuracy is too poor or not enough frames. Verify board stability.")

if __name__ == "__main__":
    verify()
