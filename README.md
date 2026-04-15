# MotionSense Pi

MotionSense Pi is a first-pass smart room monitor for a Raspberry Pi 3 B with a Pi Camera v2.1 and Sense HAT.

## MVP goals

- Capture on-demand snapshots with the Pi camera
- Support both the Pi camera and a connected USB webcam
- Trigger full-resolution captures when motion is detected
- Show the latest snapshot in a local web UI
- Show recent motion events in the dashboard
- Report camera availability and basic device status
- Report Sense HAT environmental data when available, with temperature in Fahrenheit and pressure in inHg
- Degrade cleanly when the Sense HAT stack is not installed yet

## Stack

- Python 3.11
- Flask for the local dashboard
- `rpicam-still` for snapshot capture on Raspberry Pi OS Bookworm
- `v4l2-ctl` for lightweight USB webcam still capture
- Pillow for lightweight frame-difference motion detection
- `sense-hat` Python package for sensor and LED matrix access

## Project layout

```text
app/
  camera.py
  motion.py
  monitor.py
  sensehat.py
  web.py
  static/
  templates/
deploy/
  install_on_pi.sh
tests/
main.py
requirements.txt
```

## Local run

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The app listens on `http://127.0.0.1:8080` by default.

## Pi install

Copy the project to the Pi, then run:

```bash
cd /opt/motionsense-pi
./deploy/install_on_pi.sh
```

The installer:

- installs Python and Sense HAT dependencies
- enables I2C when `raspi-config` is available
- creates a virtual environment
- installs Python requirements
- writes a `motionsense-pi` systemd service
- starts the dashboard on port `8080`

After install, open:

```text
http://<pi-ip>:8080
```

## Notes

- Motion detection runs as a background loop that compares low-resolution probe frames and captures a full snapshot when the score crosses the configured threshold.
- The active camera source can be switched between the Pi camera and a compatible USB webcam from the dashboard.
- The Sense HAT LED matrix uses a low-risk idle screensaver, flashes blue on successful captures, and stays red on camera faults.
- Live view is intentionally deferred until snapshot capture and motion events are stable.
- If the Sense HAT still reports unavailable after install, reboot the Pi so the I2C change takes effect.
