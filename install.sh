#!/bin/bash
# EchoView Install Script
# This script installs dependencies and guides the user through setup on a Linux system (e.g., Raspberry Pi)

set -e

# 0. Confirm X11 is enabled (required for display app)
echo "\n---"
echo "EchoView Display requires X11 (graphical desktop) to run."
read -p "Is X11 (Desktop GUI) enabled on this system? (y/n): " x11_choice
if [[ "$x11_choice" =~ ^[Yy]$ ]]; then
    echo "Proceeding with installation..."
else
    echo "X11 is required for the display app. Exiting installation."
    exit 1
fi

# 1. Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "Python 3 is not installed. Please install Python 3 and rerun this script."
    exit 1
fi

# 2. Check for pip
if ! command -v pip3 &> /dev/null; then
    echo "pip3 is not installed. Installing pip3..."
    sudo apt-get update && sudo apt-get install -y python3-pip
fi

# 3. Install system dependencies
sudo apt-get update
sudo apt-get install -y libxcb-cursor0 libxcb-xinerama0 libxcb-xinput0 ffmpeg

# 4. Install Python dependencies
pip3 install --upgrade pip
pip3 install -r requirements.txt

# 5. Create and activate Python virtual environment automatically
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 6. Mount network share (optional, default: skip)
echo "\n---"
echo "Optional: Mount a network share for media storage (e.g., SMB/CIFS)"
default_mount_choice="n"
read -p "Do you want to mount a network share? (y/n) [${default_mount_choice}]: " mount_choice
mount_choice=${mount_choice:-$default_mount_choice}
if [[ "$mount_choice" =~ ^[Yy]$ ]]; then
    default_share_path="//server/share"
    read -p "Enter the network share path (e.g., //10.10.10.54/PiViewers) [${default_share_path}]: " share_path
    share_path=${share_path:-$default_share_path}
    default_mount_point="/mnt/piviewers"
    read -p "Enter the local mount point [${default_mount_point}]: " mount_point
    mount_point=${mount_point:-$default_mount_point}
    sudo mkdir -p "$mount_point"
    default_share_user="guest"
    read -p "Enter username for the share [${default_share_user}]: " share_user
    share_user=${share_user:-$default_share_user}
    if [[ "$share_user" == "guest" ]]; then
        sudo mount -t cifs "$share_path" "$mount_point" -o guest,uid=$(id -u),gid=$(id -g)
    else
        read -s -p "Enter password for the share: " share_pass
        echo
        sudo mount -t cifs "$share_path" "$mount_point" -o username="$share_user",password="$share_pass",uid=$(id -u),gid=$(id -g)
    fi
    echo "Share mounted at $mount_point. To make this permanent, add an entry to /etc/fstab."
else
    echo "Skipping network share mount. Media will be stored locally."
fi

# 7. Guide for systemd setup
cat << EOF

---
Systemd Integration:
1. Edit the ExecStart and WorkingDirectory paths in systemd/*.service files to match your installation.
2. Copy the service files to /etc/systemd/system/:
   sudo cp systemd/echoview-*.service /etc/systemd/system/
3. Reload systemd:
   sudo systemctl daemon-reload
4. Enable and start the services:
   sudo systemctl enable echoview-display.service
   sudo systemctl start echoview-display.service
   sudo systemctl enable echoview-web.service
   sudo systemctl start echoview-web.service

---

To run the web server manually:
  uvicorn web.main:app --reload

To run the display app manually:
  python display/main.py

For more info, see README.md
EOF

# 8. Optional: Install and start systemd services
read -p "Do you want to install and start EchoView system services? (y/n): " sysd_choice
if [[ "$sysd_choice" =~ ^[Yy]$ ]]; then
    sudo cp systemd/echoviewer-display.service /etc/systemd/system/echoview-display.service
    sudo cp systemd/echoviewer-web.service /etc/systemd/system/echoview-web.service
    # Update ExecStart in service files to use venv python/uvicorn
    sudo sed -i 's|ExecStart=.*display/main.py|ExecStart=/home/pi/EchoView/.venv/bin/python /home/pi/EchoView/display/main.py|' /etc/systemd/system/echoview-display.service
    sudo sed -i 's|ExecStart=.*uvicorn web.main:app.*|ExecStart=/home/pi/EchoView/.venv/bin/uvicorn web.main:app --host 0.0.0.0 --port 8000|' /etc/systemd/system/echoview-web.service
    sudo systemctl daemon-reload
    sudo systemctl enable echoview-display.service
    sudo systemctl start echoview-display.service
    sudo systemctl enable echoview-web.service
    sudo systemctl start echoview-web.service
    echo "EchoView system services installed and started."
else
    echo "Skipping systemd service installation."
fi

echo "\nInstallation complete!"
