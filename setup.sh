#!/usr/bin/env bash
set -e

# -------------------------------------------------------
# Friendly EchoView setup script
# -------------------------------------------------------

# Require root
if [[ $EUID -ne 0 ]]; then
  echo "Please run this script as root (e.g. via sudo)." >&2
  exit 1
fi

# Check for non-interactive mode
AUTO_UPDATE="false"
if [[ "$1" == "--auto-update" ]]; then
  AUTO_UPDATE="true"
fi

APP_DIR="$(pwd)"

if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo "========================================================="
  echo "           Welcome to the EchoView setup script           "
  echo "========================================================="
  read -p "Press [Enter] to start or Ctrl+C to cancel..." tmp
fi

echo
echo "== Step 1: Installing required packages =="
apt-get update
apt-get install -y \
  xserver-xorg \
  xinit \
  python3-pip \
  python3-gi \
  gir1.2-webkit2-4.0 \
  cifs-utils \
  git

echo
echo "== Step 2: Installing Python dependencies =="
pip3 install --break-system-packages -r "$APP_DIR/requirements.txt"

# -------------------------------------------------------
# Configuration prompts
# -------------------------------------------------------

DEFAULT_USER="${SUDO_USER:-$(whoami)}"
APP_USER="$DEFAULT_USER"
MEDIA_ROOT="$APP_DIR/media"

if [[ "$AUTO_UPDATE" == "false" ]]; then
  read -p "Run EchoView services as user [$DEFAULT_USER]: " usr
  APP_USER=${usr:-$DEFAULT_USER}

  read -p "Media storage path [$MEDIA_ROOT]: " path
  MEDIA_ROOT=${path:-$MEDIA_ROOT}

  read -p "Use SMB share for media storage? (y/n) " use_smb
else
  use_smb="n"
fi

if id "$APP_USER" &>/dev/null; then
  echo "Using existing user: $APP_USER"
else
  if [[ "$AUTO_UPDATE" == "false" ]]; then
    read -p "User $APP_USER does not exist. Create it? (y/n) " create_u
    if [[ "$create_u" =~ ^[Yy]$ ]]; then
      adduser --gecos "" --disabled-password "$APP_USER"
    else
      echo "Cannot proceed without a valid user." >&2
      exit 1
    fi
  else
    echo "Required user $APP_USER not found in auto-update mode." >&2
    exit 1
  fi
fi

# -------------------------------------------------------
# Optional SMB mounting
# -------------------------------------------------------

if [[ "$use_smb" =~ ^[Yy]$ ]]; then
  read -p "SMB share path (e.g. //server/share): " smb_path
  read -p "Mount point [$MEDIA_ROOT]: " mount_point
  mount_point=${mount_point:-$MEDIA_ROOT}
  read -p "Username: " smb_user
  read -s -p "Password: " smb_pass; echo

  mkdir -p "$mount_point"
  mount -t cifs "$smb_path" "$mount_point" -o username=$smb_user,password=$smb_pass,vers=3.0 || true
  echo "$smb_path $mount_point cifs username=$smb_user,password=$smb_pass,vers=3.0 0 0" >> /etc/fstab
  MEDIA_ROOT="$mount_point"
else
  mkdir -p "$MEDIA_ROOT"
  chown "$APP_USER":"$APP_USER" "$MEDIA_ROOT"
fi

# -------------------------------------------------------
# Create configuration file
# -------------------------------------------------------

mkdir -p "$APP_DIR/config"
python3 - <<PY
import json, os
conf = {'media_root': '$MEDIA_ROOT', 'selected_folders': [], 'current_media': ''}
os.makedirs('config', exist_ok=True)
with open('config/settings.json', 'w') as f:
    json.dump(conf, f)
PY

# -------------------------------------------------------
# Systemd service files
# -------------------------------------------------------

SERVICE_FILE=/etc/systemd/system/echoview.service
cat > "$SERVICE_FILE" <<SERVICE
[Unit]
Description=EchoView server
After=network.target

[Service]
User=$APP_USER
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$(which uvicorn) main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

DISPLAY_SERVICE=/etc/systemd/system/echoview-display.service
cat > "$DISPLAY_SERVICE" <<SERVICE
[Unit]
Description=EchoView viewer
After=echoview.service

[Service]
User=$APP_USER
Type=simple
Environment=DISPLAY=:0
ExecStart=/usr/bin/xinit $(which python3) $APP_DIR/viewer.py -- :0
Restart=always

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
systemctl enable echoview.service echoview-display.service
systemctl start echoview.service echoview-display.service

echo
echo "Setup complete! EchoView should now be running."
echo "Access the web interface at http://<device-ip>:8000"
