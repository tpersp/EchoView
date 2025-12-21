#!/usr/bin/env bash
#
# setup.sh - "It Just Works" for the new PySide6 + Flask EchoView
#
#   1) Installs LightDM (with Xorg), python3, PySide6 deps, etc.
#   2) Creates an isolated virtualenv and installs pip dependencies there
#   3) Disables screen blanking (via raspi-config)
#   3b) Disables Wi-Fi power management
#   4) Prompts for user & paths (unless in --auto-update mode)
#   5) Creates .env in VIEWER_HOME
#   6) (Optional) mounts a CIFS network share or fallback to local "Uploads"
#   7) Creates systemd services for echoview/viewer.py + controller
#   8) Configure Openbox autologin & picom in openbox autostart
#   9) Reboots (unless in --auto-update mode)
#
# Usage:  sudo ./setup.sh  [--auto-update]
#   If you run with --auto-update, it will skip user prompts and final reboot.

# -------------------------------------------------------
# Must be run as root
# -------------------------------------------------------
if [[ $EUID -ne 0 ]]; then
  echo "Please run this script as root (e.g. sudo ./setup.sh)."
  exit 1
fi

# -------------------------------------------------------
# Check if we're in "auto-update" mode
# -------------------------------------------------------
AUTO_UPDATE="false"
if [[ "$1" == "--auto-update" ]]; then
  AUTO_UPDATE="true"
fi

QTWEBENGINE_FLAGS="--no-sandbox --disable-gpu --autoplay-policy=no-user-gesture-required --user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

ensure_chromium_bin() {
  if [ -n "${CHROMIUM_BIN:-}" ]; then
    if command -v "$CHROMIUM_BIN" >/dev/null; then
      CHROMIUM_BIN="$(command -v "$CHROMIUM_BIN")"
      return 0
    fi
  fi
  if command -v chromium >/dev/null; then
    CHROMIUM_BIN="$(command -v chromium)"
    return 0
  elif command -v chromium-browser >/dev/null; then
    CHROMIUM_BIN="$(command -v chromium-browser)"
    return 0
  fi
  echo "ERROR: Chromium not installed (chromium/chromium-browser missing)"
  exit 1
}

persist_env_kv() {
  local key="$1"
  local val="$2"

  if [ -z "${ENV_FILE:-}" ] || [ ! -f "$ENV_FILE" ]; then
    return 0
  fi

  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
  else
    echo "${key}=${val}" >> "$ENV_FILE"
  fi
}

# -------------------------------------------------------
# Display fancy reminder about X11 vs Wayland
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo "***************************************************************"
  echo "*                                                             *"
  echo "*     IMPORTANT: EchoView requires X11 for proper operation   *"
  echo "*                                                             *"
  echo "*  If you are currently using Wayland, please change your     *"
  echo "*  display server to X11 before continuing.                   *"
  echo "*                                                             *"
  echo "***************************************************************"
  echo
  read -p "Have you switched your display server to X11? (y/n): " confirm_x11
  if [[ ! "$confirm_x11" =~ ^[Yy]$ ]]; then
      echo "-------------------------------------------------------------"
      echo "  Please switch to X11 and then rerun this script. Exiting.  "
      echo "                                                             "
      echo "  Please change your display server to X11 by running:       "
      echo "     sudo raspi-config -> advanced -> wayland -> select x11  "
      echo "                                                             "
      echo "  After making the change and rebooting, rerun this script.  "
      echo "-------------------------------------------------------------"
      exit 1
  fi
else
  echo "------------------------------------------------------------------------------"
  echo "WARNING: EchoView requires X11. Ensure that your display server is set to X11."
  echo "------------------------------------------------------------------------------"
fi

# -------------------------------------------------------
# Display fancy initial banner if not in auto-update mode
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo "==============================================================="
  echo "|                                                             |"
  echo "|         Welcome to the EchoView Setup Script                |"
  echo "|                                                             |"
  echo "|   Simple 'It Just Works' Setup with LightDM + EchoView      |"
  echo "|                      (PySide6)                              |"
  echo "|                                                             |"
  echo "==============================================================="
  echo
  echo "This script will perform the following tasks:"
  echo "  1) Install lightdm (Xorg), python3, etc. plus system python3-pyside6"
  echo "  2) Create a Python virtualenv and install dependencies inside it"
  echo "  3) Disable screen blanking"
  echo "  4) Prompt for user & paths"
  echo "  5) Create .env in VIEWER_HOME"
  echo "  6) (Optional) Mount a network share or fallback to local uploads folder"
  echo "  7) Create systemd services for echoview/viewer.py and the controller"
  echo "  8) Configure Openbox autologin & picom in openbox autostart"
  echo "  9) Reboot the system"
  echo
  read -p "Press [Enter] to continue or Ctrl+C to abort..."
fi

# -------------------------------------------------------
# 1) Install apt packages (including extras for LightDM)
# -------------------------------------------------------
echo
echo "== Step 1: Installing packages (lightdm, Xorg, python3, etc.) =="
apt-get update

apt-get install -y \
  lightdm \
  lightdm-gtk-greeter \
  accountsservice \
  dbus-x11 \
  polkitd \
  pkexec \
  xorg \
  x11-xserver-utils \
  python3 \
  python3-pip \
  python3-venv \
  cifs-utils \
  ffmpeg \
  mpv \
  raspi-config \
  openbox \
  picom \
  conky-all \
  python3-tk \
  git \
  libxcb-cursor0 \
  libxcb-randr0 \
  libxcb-shape0 \
  libxcb-xfixes0 \
  libxcb-xinerama0 \
  libxkbcommon-x11-0\
  libxcb-icccm4\
  libxcb-keysyms1 \
  libgl1 \
  libegl1 \
  libxi6 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libxtst6 \
  libxkbcommon0 \
  libxkbfile1 \
  libasound2 \
  libxslt1.1 \
  libminizip1 \
  libwebp7 \
  libtiff6 \
  libevent-2.1-7 \
  chromium \
  chromium-common \
  chromium-sandbox

if [ $? -ne 0 ]; then
  echo "Error installing packages via apt. Exiting."
  exit 1
fi

ensure_chromium_bin

# -------------------------------------------------------
# Ensure PySide6 WebEngine libraries exist
# -------------------------------------------------------
# Create compatibility symlinks if older versions are missing
for LIB in libwebp.so.6 libtiff.so.5; do
  if ! find /usr/lib -name "$LIB" | grep -q .; then
    TARGET=$(find /usr/lib -name "${LIB%.so.*}.so.*" | head -n1)
    if [ -n "$TARGET" ]; then
      ln -s "$TARGET" "$(dirname "$TARGET")/$LIB"
    fi
  fi
done

# -------------------------------------------------------
# Symlink libminizip.so.1 for PySide6 WebEngine
# -------------------------------------------------------
if [ -f /usr/lib/aarch64-linux-gnu/libminizip.so.1 ] && [ ! -f /usr/lib/libminizip.so.1 ]; then
  ln -s /usr/lib/aarch64-linux-gnu/libminizip.so.1 /usr/lib/libminizip.so.1
fi

# Ensure required runtime libs are installed
ldconfig

# Create /var/lib/lightdm/data so LightDM can store user-data:
mkdir -p /var/lib/lightdm/data
chown lightdm:lightdm /var/lib/lightdm/data

# Make sure accounts-daemon is enabled and running:
systemctl enable accounts-daemon
systemctl start accounts-daemon

# Let raspi-config handle auto-login in desktop:
# B4 => Auto login to Desktop
if command -v raspi-config &>/dev/null; then
  raspi-config nonint do_boot_behaviour B4
else
  echo "Warning: raspi-config not found; skipping auto-login configuration."
fi

# -------------------------------------------------------
# 2) Create virtualenv and install Python deps
# -------------------------------------------------------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV_DIR="$SCRIPT_DIR/.venv"
REQ_FILE="$SCRIPT_DIR/requirements.txt"

echo
echo "== Step 2: Creating/updating Python virtualenv =="
if [ ! -d "$VENV_DIR" ]; then
  python3 -m venv "$VENV_DIR"
  if [ $? -ne 0 ]; then
    echo "Error creating virtualenv at $VENV_DIR. Exiting."
    exit 1
  fi
fi

"$VENV_DIR/bin/python3" -m pip install --upgrade pip
if [ $? -ne 0 ]; then
  echo "Failed to upgrade pip inside the virtualenv. Exiting."
  exit 1
fi

if [ -f "$REQ_FILE" ]; then
  echo "Installing dependencies from $REQ_FILE ..."
  "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
else
  echo "requirements.txt not found; installing core dependencies ..."
  "$VENV_DIR/bin/pip" install flask psutil requests spotipy PySide6 Pillow
fi
if [ $? -ne 0 ]; then
  echo "Error installing pip packages inside the virtualenv. Exiting."
  exit 1
fi

# -------------------------------------------------------
# 3) Disable screen blanking and configure Wi-Fi power save (install only)
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
echo
echo "== Step 3: Disabling screen blanking via raspi-config =="
if command -v raspi-config &>/dev/null; then
  raspi-config nonint do_blanking 1
  if [ $? -eq 0 ]; then
    echo "Screen blanking disabled."
  else
    echo "Warning: raspi-config do_blanking failed. You may need to disable blanking manually."
  fi
else
  echo "Warning: raspi-config not found; skipping screen-blanking changes."
fi

# Remove mouse cursor from X sessions
sed -i -- "s/#xserver-command=X/xserver-command=X -nocursor/" /etc/lightdm/lightdm.conf

# -------------------------------------------------------
# 3b) Outcomment conflicting LightDM options in /etc/lightdm/lightdm.conf
# (Comment out greeter-session, user-session, and autologin-session options that may conflict with Openbox autologin)
# -------------------------------------------------------
if [ -f /etc/lightdm/lightdm.conf ]; then
  sed -i 's/^\(greeter-session=.*\)$/#\1/' /etc/lightdm/lightdm.conf
  sed -i 's/^\(user-session=.*\)$/#\1/' /etc/lightdm/lightdm.conf
  sed -i 's/^\(autologin-session=.*\)$/#\1/' /etc/lightdm/lightdm.conf
fi

# -------------------------------------------------------
# 3a) Update boot firmware configuration (enable full KMS + force hotplug)
# -------------------------------------------------------
echo
echo "== Step 3a: Updating boot firmware configuration in /boot/firmware/config.txt =="
if [ -f /boot/firmware/config.txt ]; then
  cp /boot/firmware/config.txt /boot/firmware/config.txt.backup

  # Insert dtoverlay=vc4-kms-v3d if missing (full KMS)
  grep -q '^dtoverlay=vc4-kms-v3d' "/boot/firmware/config.txt" || \
    sed -i '/^# Enable DRM VC4 V3D driver/ a dtoverlay=vc4-kms-v3d' "/boot/firmware/config.txt"

  # Insert max_framebuffers=2 if missing
  grep -q '^max_framebuffers=2' "/boot/firmware/config.txt" || \
    sed -i '/^dtoverlay=vc4-kms-v3d/ a max_framebuffers=2' "/boot/firmware/config.txt"

  # Ensure both HDMI ports are forced hotplug
  for port in 0 1; do
    grep -q "^hdmi_force_hotplug:${port}=1" "/boot/firmware/config.txt" || \
      sed -i "/^max_framebuffers=2/ a hdmi_force_hotplug:${port}=1" "/boot/firmware/config.txt"
  done
fi

# -------------------------------------------------------
# 3c) Disable Wi-Fi power management to avoid disconnects
# -------------------------------------------------------
echo
echo "== Step 3c: Disabling Wi-Fi power management =="
WIFI_IFACE=$(iw dev 2>/dev/null | awk '$1=="Interface"{print $2; exit}')
if [ -n "$WIFI_IFACE" ]; then
  echo "Turning off power management for interface $WIFI_IFACE"
  iwconfig "$WIFI_IFACE" power off || echo "Warning: failed to disable power management on $WIFI_IFACE"
else
  echo "No Wi-Fi interface detected; skipping power management tweak."
fi

# -------------------------------------------------------
# 3d) Create systemd service to disable Wi-Fi power management at boot
# -------------------------------------------------------
echo
echo "== Step 3d: Setting up Wi-Fi power management service =="
SERVICE_SCRIPT="/usr/local/sbin/wifi_powersave_off.sh"
SERVICE_FILE="/etc/systemd/system/wifi-powersave-off.service"

cat <<'EOF' > "$SERVICE_SCRIPT"
#!/usr/bin/env bash
WIFI_IFACE=$(iw dev 2>/dev/null | awk '$1=="Interface"{print $2; exit}')
if [ -n "$WIFI_IFACE" ]; then
  /sbin/iwconfig "$WIFI_IFACE" power off
fi
EOF

chmod +x "$SERVICE_SCRIPT"

cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Disable WiFi power management
After=multi-user.target

[Service]
Type=oneshot
ExecStart=$SERVICE_SCRIPT

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable wifi-powersave-off.service
systemctl start wifi-powersave-off.service

fi

# -------------------------------------------------------
# 4) Prompt user for config (skip if AUTO_UPDATE)
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo
  echo "*******************************************************"
  echo "*                                                     *"
  echo "*         EchoView Configuration Setup                *"
  echo "*                                                     *"
  echo "*******************************************************"
  echo
  read -p "Enter the Linux username to run EchoView (default: pi): " VIEWER_USER
  VIEWER_USER=${VIEWER_USER:-pi}

  USER_ID="$(id -u "$VIEWER_USER" 2>/dev/null)"
  if [ -z "$USER_ID" ]; then
    echo "User '$VIEWER_USER' not found. Create user? (y/n)"
    read create_user
    if [[ "$create_user" =~ ^[Yy]$ ]]; then
      adduser --gecos "" --disabled-password "$VIEWER_USER"
      USER_ID="$(id -u "$VIEWER_USER")"
      echo "User '$VIEWER_USER' created with no password."
    else
      echo "Cannot proceed without a valid user. Exiting."
      exit 1
    fi
  fi

  echo
  echo "-------------------------------------------------------"
  echo "  Please specify the installation directories below:"
  echo "-------------------------------------------------------"
  read -p "Enter the path for VIEWER_HOME (default: /home/$VIEWER_USER/EchoView): " input_home
  if [ -z "$input_home" ]; then
    VIEWER_HOME="/home/$VIEWER_USER/EchoView"
  else
    VIEWER_HOME="$input_home"
  fi

  read -p "Enter the path for IMAGE_DIR (default: /mnt/EchoViews): " input_dir
  IMAGE_DIR=${input_dir:-/mnt/EchoViews}
else
  echo
  echo "== Auto-Update Mode: skipping interactive user/path prompts. =="
  VIEWER_USER="pi"
  USER_ID="$(id -u "$VIEWER_USER")"
  if [ -z "$USER_ID" ]; then
    echo "User 'pi' not found. Exiting auto-update."
    exit 1
  fi
  VIEWER_HOME="/home/$VIEWER_USER/EchoView"
  ENV_FILE="$VIEWER_HOME/.env"
  if [ -f "$ENV_FILE" ]; then
    echo "Using existing $ENV_FILE"
    set -a
    source "$ENV_FILE"
    set +a
  else
    IMAGE_DIR="/mnt/EchoViews"
  fi
fi

if [ -n "${QTWEBENGINE_CHROMIUM_FLAGS:-}" ]; then
  QTWEBENGINE_FLAGS="$QTWEBENGINE_CHROMIUM_FLAGS"
fi
ensure_chromium_bin
persist_env_kv CHROMIUM_BIN "$CHROMIUM_BIN"

echo
echo "Creating $VIEWER_HOME if it doesn't exist..."
mkdir -p "$VIEWER_HOME"
chown "$VIEWER_USER:$VIEWER_USER" "$VIEWER_HOME"

# Ensure the virtualenv is owned by the viewer user so upgrades work later
if [ -d "$VENV_DIR" ]; then
  chown -R "$VIEWER_USER:$VIEWER_USER" "$VENV_DIR"
fi

# -------------------------------------------------------
# 5) Create .env
# -------------------------------------------------------
ENV_FILE="$VIEWER_HOME/.env"
if [[ "$AUTO_UPDATE" == "false" || ! -f "$ENV_FILE" ]]; then
  echo "Creating $ENV_FILE with VIEWER_HOME + IMAGE_DIR + WebEngine defaults..."
  cat <<EOF > "$ENV_FILE"
VIEWER_HOME=$VIEWER_HOME
IMAGE_DIR=$IMAGE_DIR
CHROMIUM_BIN=$CHROMIUM_BIN
QTWEBENGINE_DISABLE_SANDBOX=1
QTWEBENGINE_CHROMIUM_FLAGS="$QTWEBENGINE_FLAGS"
EOF
  chown "$VIEWER_USER:$VIEWER_USER" "$ENV_FILE"
fi

echo
echo "Contents of $ENV_FILE:"
cat "$ENV_FILE"
echo

# -------------------------------------------------------
# 6) (Optional) Configure CIFS/SMB share
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo
  echo "== Step 6: (Optional) Network Share at $IMAGE_DIR =="
  read -p "Mount a network share at $IMAGE_DIR via CIFS? (y/n): " mount_answer
  if [[ "$mount_answer" =~ ^[Yy]$ ]]; then
    read -p "Enter server share path (e.g. //192.168.1.100/MyShare): " SERVER_SHARE
    if [ -z "$SERVER_SHARE" ]; then
      echo "No share path entered. Skipping."
    else
      USER_ID="$(id -u "$VIEWER_USER")"
      read -p "Mount options (e.g. guest,uid=$USER_ID,gid=$USER_ID,vers=3.0) [ENTER for default]: " MOUNT_OPTS
      if [ -z "$MOUNT_OPTS" ]; then
        MOUNT_OPTS="guest,uid=$USER_ID,gid=$USER_ID,vers=3.0"
      fi

      echo "Creating mount dir: $IMAGE_DIR"
      mkdir -p "$IMAGE_DIR"

      FSTAB_LINE="$SERVER_SHARE  $IMAGE_DIR  cifs  $MOUNT_OPTS,x-systemd.automount  0  0"
      if grep -qs "$SERVER_SHARE" /etc/fstab; then
        echo "Share already in /etc/fstab; skipping append."
      else
        echo "Appending to /etc/fstab: $FSTAB_LINE"
        echo "$FSTAB_LINE" >> /etc/fstab
      fi

      echo "Mounting all..."
      mount -a
      if [ $? -ne 0 ]; then
        echo "WARNING: mount -a failed. Check credentials/options."
      else
        echo "Share mounted at $IMAGE_DIR."
      fi
    fi
  else
    echo "No network share chosen. Setting up local uploads folder."
    IMAGE_DIR="$VIEWER_HOME/Uploads"
    mkdir -p "$IMAGE_DIR"
    chown $VIEWER_USER:$VIEWER_USER "$IMAGE_DIR"
    echo "Local uploads folder created at $IMAGE_DIR."
    echo "Updating .env file with new IMAGE_DIR and WebEngine defaults..."
    cat <<EOF > "$ENV_FILE"
VIEWER_HOME=$VIEWER_HOME
IMAGE_DIR=$IMAGE_DIR
CHROMIUM_BIN=$CHROMIUM_BIN
QTWEBENGINE_DISABLE_SANDBOX=1
QTWEBENGINE_CHROMIUM_FLAGS="$QTWEBENGINE_FLAGS"
EOF
    chown "$VIEWER_USER:$VIEWER_USER" "$ENV_FILE"
    echo "Updated .env file:"
    cat "$ENV_FILE"
  fi
else
  echo
  echo "== Auto-Update Mode: skipping CIFS prompt. =="
fi

# -------------------------------------------------------
# 7) Create systemd services for viewer + controller
# -------------------------------------------------------
echo
echo "== Step 7: Creating systemd service files =="

ECHOVIEW_SERVICE="/etc/systemd/system/echoview.service"
echo "Creating $ECHOVIEW_SERVICE ..."
cat <<EOF > "$ECHOVIEW_SERVICE"
[Unit]
Description=EchoView PySide6 Slideshow + Overlay
After=lightdm.service
Wants=lightdm.service

[Service]
User=$VIEWER_USER
Group=$VIEWER_USER
WorkingDirectory=$VIEWER_HOME
EnvironmentFile=$ENV_FILE
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/$VIEWER_USER/.Xauthority"
Environment="QTWEBENGINE_DISABLE_SANDBOX=1"
Environment="QTWEBENGINE_CHROMIUM_FLAGS=$QTWEBENGINE_FLAGS"
Environment="PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"
ExecStartPre=/bin/sleep 5
ExecStart=$VENV_DIR/bin/python3 -m echoview.viewer

Restart=always
RestartSec=5
Type=simple

[Install]
WantedBy=graphical.target
EOF

CONTROLLER_SERVICE="/etc/systemd/system/controller.service"
echo "Creating $CONTROLLER_SERVICE ..."
cat <<EOF > "$CONTROLLER_SERVICE"
[Unit]
Description=EchoView Flask Web Controller
After=network-online.target
Wants=network-online.target

[Service]
User=$VIEWER_USER
Group=$VIEWER_USER
WorkingDirectory=$VIEWER_HOME
EnvironmentFile=$ENV_FILE
Environment="DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$USER_ID/bus"
Environment="XDG_RUNTIME_DIR=/run/user/$USER_ID"
Environment="DISPLAY=:0"
Environment="XAUTHORITY=/home/$VIEWER_USER/.Xauthority"
Environment="PATH=$VENV_DIR/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
Environment="PYTHONUNBUFFERED=1"

ExecStart=$VENV_DIR/bin/python3 -m echoview.web.app
Restart=always
RestartSec=5
Type=simple

[Install]
WantedBy=multi-user.target
EOF


echo "Reloading systemd..."
systemctl daemon-reload
systemctl enable echoview.service
systemctl enable controller.service
systemctl start echoview.service
systemctl start controller.service

# -------------------------------------------------------
# 8) Configure Openbox autologin & picom in openbox autostart
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
echo
echo "== Step 8: Configure Openbox autologin, picom, and autostart =="

# Configure LightDM for Openbox autologin
mkdir -p /etc/lightdm/lightdm.conf.d
cat <<EOF >/etc/lightdm/lightdm.conf.d/99-openbox-autologin.conf
[Seat:*]
greeter-session=lightdm-gtk-greeter
user-session=openbox
autologin-user=$VIEWER_USER
autologin-user-timeout=0
autologin-session=openbox
EOF

# Configure Openbox autostart to launch picom
OPENBOX_CONF_DIR="/home/$VIEWER_USER/.config/openbox"
mkdir -p "$OPENBOX_CONF_DIR"
AUTOSTART_FILE="$OPENBOX_CONF_DIR/autostart"

cat <<EOF > "$AUTOSTART_FILE"
#!/usr/bin/env bash
# Minimal openbox autostart
# Start picom after X is ready

# Set a black root just in case
xsetroot -solid black

# Start picom in background quietly
picom >/dev/null 2>&1 &
EOF

# Set permissions on Openbox autostart
chown -R "$VIEWER_USER:$VIEWER_USER" "/home/$VIEWER_USER/.config/openbox"
chmod +x "$AUTOSTART_FILE"

# Create Picom configuration optimized for Raspberry Pi
PICOM_CONF_DIR="/home/$VIEWER_USER/.config/picom"
mkdir -p "$PICOM_CONF_DIR"
PICOM_CONF_FILE="$PICOM_CONF_DIR/picom.conf"

cat <<EOF > "$PICOM_CONF_FILE"
backend = "xrender";

fade = true;
fade-delta = 4;

fade-in-step = 0.03;
fade-out-step = 0.03;

use-damage = false;
EOF

# Set permissions on Picom configuration
chown -R "$VIEWER_USER:$VIEWER_USER" "$PICOM_CONF_DIR"

echo "Done configuring Openbox autologin, Picom configuration, and autostart."
fi

# -------------------------------------------------------
# 8b) Set up systemd-based network watchdog timer
# -------------------------------------------------------
cleanup_legacy_watchdog_cron() {
  local existing filtered
  existing=$(crontab -l 2>/dev/null || true)
  if [ -n "$existing" ] && echo "$existing" | grep -q "Network fail, rebooting."; then
    filtered=$(echo "$existing" | grep -v "Network fail, rebooting.")
    printf "%s\n" "$filtered" | crontab -
    echo "Removed legacy cron-based network watchdog entry."
  fi
}

detect_watchdog_default_target() {
  local gateway addr ip o1 o2 o3
  gateway=$(ip -4 route show default 2>/dev/null | awk '$1=="default"{print $3; exit}')
  if [ -n "$gateway" ]; then
    echo "$gateway"
    return
  fi

  addr=$(ip -4 addr show scope global up 2>/dev/null | awk '/inet /{print $2; exit}')
  if [ -n "$addr" ]; then
    ip=${addr%%/*}
    IFS='.' read -r o1 o2 o3 _ <<< "$ip"
    if [ -n "${o1:-}" ] && [ -n "${o2:-}" ] && [ -n "${o3:-}" ]; then
      echo "${o1}.${o2}.${o3}.1"
      return
    fi
  fi

  echo "1.1.1.1"
}

install_network_watchdog() {
  local target="$1"
  local attempts="$2"
  local threshold="$3"
  local watchdog_dir="$VIEWER_HOME/bin"
  local watchdog_script="$watchdog_dir/network-watchdog.sh"
  local watchdog_conf="$VIEWER_HOME/network-watchdog.conf"
  local watchdog_service="/etc/systemd/system/network-watchdog.service"
  local watchdog_timer="/etc/systemd/system/network-watchdog.timer"
  local log_path="$VIEWER_HOME/viewer.log"
  local user_id group_id

  if [[ ! "$attempts" =~ ^[1-9][0-9]*$ ]]; then
    attempts=5
  fi
  if [[ ! "$threshold" =~ ^[1-9][0-9]*$ ]]; then
    threshold=3
  fi
  if (( threshold > attempts )); then
    threshold="$attempts"
  fi

  user_id="$(id -u "$VIEWER_USER")"
  group_id="$(id -g "$VIEWER_USER")"

  mkdir -p "$watchdog_dir"
  /usr/bin/install -m 0755 "$SCRIPT_DIR/network-watchdog.sh" "$watchdog_script"
  chown "$VIEWER_USER:$VIEWER_USER" "$watchdog_script"

  touch "$log_path"
  chown "$VIEWER_USER:$VIEWER_USER" "$log_path"

  cat <<EOF > "$watchdog_conf"
WATCHDOG_USER=$VIEWER_USER
WATCHDOG_UID=$user_id
WATCHDOG_GID=$group_id
WATCHDOG_LOG=$log_path
WATCHDOG_TARGET=$target
WATCHDOG_ATTEMPTS=$attempts
WATCHDOG_FAIL_THRESHOLD=$threshold
EOF
  chown "$VIEWER_USER:$VIEWER_USER" "$watchdog_conf"
  chmod 644 "$watchdog_conf"

  cat <<EOF > "$watchdog_service"
[Unit]
Description=EchoView Network Watchdog
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=$watchdog_script
EnvironmentFile=-$watchdog_conf
User=root
Group=root
WorkingDirectory=$VIEWER_HOME
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
# The watchdog script and config live under $VIEWER_HOME (e.g. /home/pi/EchoView),
# so ProtectHome must be disabled to avoid 203/EXEC failures.
ProtectHome=false
ReadWritePaths=$VIEWER_HOME
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=multi-user.target
EOF

  cat <<EOF > "$watchdog_timer"
[Unit]
Description=Run EchoView Network Watchdog periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
AccuracySec=1min
RandomizedDelaySec=30s
Persistent=true
Unit=network-watchdog.service

[Install]
WantedBy=timers.target
EOF

  systemctl daemon-reload
  systemctl enable --now network-watchdog.timer
  systemctl restart network-watchdog.service

  echo "Network watchdog installed (target=$target, attempts=$attempts, threshold=$threshold)."
  echo "Configuration file: $watchdog_conf"
}

cleanup_legacy_watchdog_cron

if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo
  echo "== Optional: Network Watchdog (systemd timer) =="
  echo "This replaces the old cron-based reboot on single ping failure."
  read -p "Enable network watchdog timer? (y/n): " setup_watchdog

  if [[ "$setup_watchdog" =~ ^[Yy]$ ]]; then
    default_target="$(detect_watchdog_default_target)"
    read -p "Enter the host/IP to ping (default: $default_target): " PING_TARGET_INPUT
    PING_TARGET=${PING_TARGET_INPUT:-$default_target}

    read -p "Attempts per run (default: 5): " WATCHDOG_ATTEMPTS_INPUT
    WATCHDOG_ATTEMPTS=${WATCHDOG_ATTEMPTS_INPUT:-5}

    read -p "Consecutive failures before reboot (default: 3): " WATCHDOG_FAIL_THRESHOLD_INPUT
    WATCHDOG_FAIL_THRESHOLD=${WATCHDOG_FAIL_THRESHOLD_INPUT:-3}

    install_network_watchdog "$PING_TARGET" "$WATCHDOG_ATTEMPTS" "$WATCHDOG_FAIL_THRESHOLD"
  else
    echo "Skipping watchdog setup."
  fi
else
  echo
  echo "== Auto-Update Mode: systemd network watchdog =="
  WATCHDOG_CONF_FILE="$VIEWER_HOME/network-watchdog.conf"

  if systemctl list-unit-files | grep -q '^network-watchdog.timer'; then
    echo "Refreshing watchdog script and units..."
    default_target="$(detect_watchdog_default_target)"
    existing_target="$default_target"
    attempts=5
    threshold=3

    if [ -f "$WATCHDOG_CONF_FILE" ]; then
      source "$WATCHDOG_CONF_FILE"
      existing_target="${WATCHDOG_TARGET:-$default_target}"
      attempts="${WATCHDOG_ATTEMPTS:-$attempts}"
      threshold="${WATCHDOG_FAIL_THRESHOLD:-$threshold}"
    fi

    install_network_watchdog "$existing_target" "$attempts" "$threshold"
  else
    echo "Timer not previously enabled; skipping watchdog install."
  fi
fi

# -------------------------------------------------------
# 9) Reboot (skip if AUTO_UPDATE)
# -------------------------------------------------------
if [[ "$AUTO_UPDATE" == "false" ]]; then
  echo
  echo "==============================================================="
  echo "   Setup is complete! Your Pi will now reboot.                 "
  echo "                                                               "
  echo "   Upon reboot, you will see:                                  "
  echo "    - LightDM auto-logging into X/Openbox (DISPLAY=:0)         "
  echo "    - openbox/autostart launching picom                        "
  echo "    - echoview.service running echoview/viewer.py              "
  echo "    - controller.service running Flask at http://<Pi-IP>:8080  "
  echo "==============================================================="
  echo
  echo "Rebooting in 5 seconds..."
  sleep 5
  reboot
else
  echo
  echo "== Auto-Update Mode: skipping final reboot. =="
fi
