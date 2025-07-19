#!/bin/bash
set -e

echo "=== EchoView Setup ==="
echo "Installing display dependencies..."
sudo apt-get update
sudo apt-get install -y xserver-xorg xinit python3-pip
echo "Installing Python dependencies..."
pip3 install --break-system-packages -r requirements.txt
MEDIA_ROOT="$(pwd)/media"
read -p "Use SMB share? (y/n) " use_smb
if [ "$use_smb" = "y" ]; then
    read -p "SMB path (e.g. //server/share): " smb_path
    read -p "Mount point [/mnt/echoview]: " mount_point
    mount_point=${mount_point:-/mnt/echoview}
    read -p "Username: " smb_user
    read -s -p "Password: " smb_pass
    echo
    sudo mkdir -p "$mount_point"
    sudo mount -t cifs "$smb_path" "$mount_point" -o username=$smb_user,password=$smb_pass,vers=3.0 || true
    MEDIA_ROOT="$mount_point"
    echo "$smb_path $mount_point cifs username=$smb_user,password=$smb_pass,vers=3.0 0 0" | sudo tee -a /etc/fstab >/dev/null
else
    mkdir -p media
fi

mkdir -p config
python3 - <<PY
import json
import os
conf={'media_root': '$MEDIA_ROOT','selected_folders': [],'current_media': ''}
os.makedirs('config', exist_ok=True)
with open('config/settings.json','w') as f:
    json.dump(conf,f)
PY

SERVICE_FILE=/etc/systemd/system/echoview.service
sudo bash -c "cat > $SERVICE_FILE" <<SERVICE
[Unit]
Description=EchoView server
After=network.target

[Service]
Type=simple
WorkingDirectory=$(pwd)
ExecStart=$(which uvicorn) main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE


sudo systemctl enable echoview
sudo systemctl start echoview

DISPLAY_SERVICE=/etc/systemd/system/echoview-display.service
sudo bash -c "cat > $DISPLAY_SERVICE" <<SERVICE
[Unit]
Description=EchoView kiosk display
After=echoview.service

[Service]
Type=simple
Environment=DISPLAY=:0
ExecStart=/usr/bin/xinit $(which python3) $(pwd)/viewer.py -- :0
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable echoview-display
sudo systemctl start echoview-display

echo "Setup complete!"
