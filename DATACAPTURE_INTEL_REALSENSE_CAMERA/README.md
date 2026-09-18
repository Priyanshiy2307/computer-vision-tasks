# INTEL REALSENSE DATASET CAPTURE

This folder contains dataset-capture scripts for three Intel RealSense cameras:

1. Intel RealSense D405
2. Intel RealSense D435i
3. Intel RealSense D455i

==================================================

1. INTEL REALSENSE SOFTWARE INSTALLATION
   ==================================================

The Intel RealSense SDK 2.0 is required to access and work with
Intel RealSense cameras.

The main components used in this project are:

* librealsense
* RealSense Viewer
* rs-enumerate-devices
* pyrealsense2

---

## 1.1 INSTALL SYSTEM DEPENDENCIES

Update the package list:

```
sudo apt update
```

Install basic dependencies:

```
sudo apt install -y \
    git \
    cmake \
    build-essential \
    libssl-dev \
    libusb-1.0-0-dev \
    pkg-config \
    libgtk-3-dev \
    libglfw3-dev \
    libgl1-mesa-dev \
    libglu1-mesa-dev
```

---

## 1.2 INSTALL INTEL REALSENSE SDK

The recommended method is to install Intel RealSense
librealsense from the official Intel RealSense repository.

After installation, verify that the RealSense command-line
tools are available:

```
rs-enumerate-devices
```

If the command is available, the SDK installation is working.

---

## 1.3 PYTHON REALSENSE SUPPORT

For Python-based dataset capture, install the RealSense Python
wrapper:

```
pip install pyrealsense2
```

Verify the installation:

```
python -c "import pyrealsense2 as rs; print(rs.__version__)"
```

If a version number is displayed, pyrealsense2 is installed.

==================================================
2. CONNECTING THE REALSENSE CAMERA
==================================

Connect the RealSense camera to the computer using a USB cable.

For best performance, use a USB 3.x port when supported by the
camera and computer.

After connecting the camera, verify that Linux detects the USB
device:

```
lsusb
```

RealSense devices should appear in the output.

==================================================
3. CHECKING THE CAMERA FROM TERMINAL
====================================

The primary command used to identify an Intel RealSense camera
is:

```
rs-enumerate-devices
```

Run:

```
rs-enumerate-devices
```

This displays information such as:

* Camera model
* Serial number
* Firmware version
* USB connection
* RGB sensor
* Depth sensor
* Infrared sensor
* Supported resolutions
* Supported frame rates
* Sensor profiles

For example, the output should identify the connected camera
as something similar to:

```
Intel RealSense D405
```

or:

```
Intel RealSense D435I
```

or:

```
Intel RealSense D455
```

==================================================
4. CHECK USB CONNECTION
=======================

To check whether the camera is detected by Linux:

```
lsusb
```

For more detailed USB information:

```
lsusb -t
```

To check RealSense video devices:

```
ls /dev/video*
```

RealSense cameras may expose multiple video devices such as:

```
/dev/video0
/dev/video1
/dev/video2
```

The exact device numbers may change depending on the other
USB cameras connected to the computer.

==================================================
5. REALSENSE VIEWER
===================

RealSense Viewer provides a graphical interface for testing
and configuring RealSense cameras.

Launch it from the terminal using:

```
realsense-viewer
```

The viewer can be used to check:

* RGB stream
* Depth stream
* Infrared stream
* Camera resolution
* FPS
* Exposure
* Gain
* Depth range
* Device information
* Firmware information
* Advanced camera settings

Before running a dataset capture script, it is recommended to
verify that the camera works correctly in RealSense Viewer.

==================================================
6. ACCESSING THE CAMERA FROM PYTHON
===================================

The Python scripts in this repository use:

```
pyrealsense2
```

Basic Python import:

```
import pyrealsense2 as rs
```

A RealSense pipeline is normally created using:

```
pipeline = rs.pipeline()
```

The pipeline is then configured and started to access the
camera streams.

==================================================
7. CAMERA DATASET CAPTURE SCRIPTS
=================================

This directory contains three capture scripts:

```
d405_capture_dataset.py
d435i_capture_dataset.py
d455i_capture_dataset.py
```

---

## 7.1 D405

Script:

```
d405_capture_dataset.py
```

Purpose:

Capture RGB images from the Intel RealSense D405 for computer
vision dataset creation.

Typical usage:

```
python d405_capture_dataset.py --folder <folder_name>
```

Example:

```
python d405_capture_dataset.py --folder lid_dataset
```

---

## 7.2 D435i

Script:

```
d435i_capture_dataset.py
```

Purpose:

Capture images from the Intel RealSense D435i for computer
vision and robotics perception datasets.

The D435i provides:

* RGB
* Stereo depth
* Infrared
* IMU

Typical usage:

```
python d435i_capture_dataset.py
```

Check the script help first:

```
python d435i_capture_dataset.py --help
```

---

## 7.3 D455i

Script:

```
d455i_capture_dataset.py
```

Purpose:

Capture images from the Intel RealSense D455i for computer
vision and robotics perception datasets.

The D455i provides:

* RGB
* Stereo depth
* Infrared
* IMU

Typical usage:

```
python d455i_capture_dataset.py
```

Check available options:

```
python d455i_capture_dataset.py --help
```

==================================================
8. CAPTURE CONTROLS
===================

The capture scripts use keyboard controls.

Typical controls:

```
c
    Capture an image

q
    Quit the application

ESC
    Quit the application
```

Captured images are saved sequentially, for example:

```
0001.png
0002.png
0003.png
0004.png
```

This makes the captured dataset easy to organize and annotate.

==================================================
9. RECOMMENDED CAMERA CHECK WORKFLOW
====================================

Before collecting a dataset, follow these steps:

## STEP 1

Connect the RealSense camera.

## STEP 2

Check USB detection:

```
lsusb
```

## STEP 3

Check RealSense detection:

```
rs-enumerate-devices
```

## STEP 4

Open RealSense Viewer:

```
realsense-viewer
```

## STEP 5

Verify the required streams.

## STEP 6

Run the appropriate capture script.

For D405:

```
python d405_capture_dataset.py --help
```

For D435i:

```
python d435i_capture_dataset.py --help
```

For D455i:

```
python d455i_capture_dataset.py --help
```

## STEP 7

Capture the required dataset images.

## STEP 8

Review the images before annotation.

==================================================
10. TROUBLESHOOTING
===================

If:

```
rs-enumerate-devices
```

does not detect the camera:

1. Check the USB cable.

2. Try another USB port.

3. Prefer a USB 3.x port when supported.

4. Run:

   ```
   lsusb
   ```

5. Check whether the RealSense device appears.

6. Close RealSense Viewer if another application is
   already using the camera.

7. Disconnect and reconnect the camera.

8. Run:

   ```
   rs-enumerate-devices
   ```

again.

If Python cannot import pyrealsense2:

```
python -c "import pyrealsense2"
```

Install it using:

```
pip install pyrealsense2
```

If the camera is detected but the Python capture script
cannot access it, make sure another application such as
RealSense Viewer is not currently using the camera.

==================================================
11. IMPORTANT NOTE ABOUT CAMERA ACCESS
======================================

Only one application should normally control the camera
stream at a time.

For example, if RealSense Viewer is actively streaming the
camera, a Python capture script may fail to access the same
camera.

Recommended workflow:

```
Close RealSense Viewer
        |
        v
Run the Python capture script
        |
        v
Capture dataset
        |
        v
Close the Python script
        |
        v
Open RealSense Viewer if inspection is required
```

==================================================
12. DATASET WORKFLOW
====================

General computer vision dataset workflow:

```
Camera
  |
  v
Image Capture
  |
  v
Dataset Folder
  |
  v
Image Review
  |
  v
Annotation
  |
  v
Train / Valid / Test Split
  |
  v
Model Training
  |
  v
Model Testing
  |
  v
Deployment
```

The captured images can be used for:

* Object detection
* Instance segmentation
* Object tracking
* Robotics perception
* Depth-based object selection
* Roboflow datasets
* YOLO training

==================================================
13. CAMERA IDENTIFICATION SUMMARY
=================================

## D405

Script:

```
d405_capture_dataset.py
```

Primary use:

```
Close-range depth and RGB perception.
```

## D435i

Script:

```
d435i_capture_dataset.py
```

Primary use:

```
RGB + depth + infrared + IMU perception.
```

## D455i

Script:

```
d455i_capture_dataset.py
```

Primary use:

```
RGB + depth + infrared + IMU perception.
```

==================================================
14. USEFUL TERMINAL COMMANDS
============================

Check Linux USB devices:

```
lsusb
```

Check USB topology:

```
lsusb -t
```

Check RealSense devices:

```
rs-enumerate-devices
```

Open RealSense Viewer:

```
realsense-viewer
```

Check video devices:

```
ls /dev/video*
```

Check Python RealSense installation:

```
python -c "import pyrealsense2 as rs; print(rs.__version__)"
```

Check capture-script options:

```
python d405_capture_dataset.py --help

python d435i_capture_dataset.py --help

python d455i_capture_dataset.py --help
```

================================
The expected directory structure is:

computer-vision-tasks/
|
└── DATACAPTURE_INTEL_REALSENSE_CAMERA/
    |
    ├── d405_capture_dataset.py
    ├── d435i_capture_dataset.py
    ├── d455i_capture_dataset.py
    └── README.txt
