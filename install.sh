#!/usr/bin/env bash
# Fotobox Installations-Skript – Raspberry Pi OS Bookworm
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$SCRIPT_DIR"
INSTALL_USER="$(id -un)"
INSTALL_HOME="$HOME"
SERVICE_FILE="/etc/systemd/system/fotobox.service"

echo "=== Fotobox Installation ==="
echo "User:        $INSTALL_USER"
echo "Install-Dir: $INSTALL_DIR"
echo ""

# 1. System-Pakete
echo "→ System-Pakete installieren..."
sudo apt-get update -qq
sudo apt-get install -y \
    gphoto2 \
    hostapd \
    network-manager \
    python3-pip \
    python3-venv \
    libjpeg-dev \
    cups \
    cups-bsd \
    nodejs \
    npm
# libatlas-base-dev und libopencv-dev sind auf Bookworm/Trixie nicht mehr
# nötig — opencv-python kommt als Binary-Wheel mit allen Libs.

# 2. Verzeichnisstruktur
echo "→ Verzeichnisstruktur anlegen..."
mkdir -p "$INSTALL_DIR/Picture_Box"
mkdir -p "$INSTALL_DIR/thumbnails"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/Layout"

# 3. Python-Umgebung
echo "→ Python-Umgebung einrichten..."
cd "$INSTALL_DIR"
if [ ! -d venv ]; then
    python3 -m venv venv --system-site-packages
fi
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
PYTHON_BIN="$INSTALL_DIR/venv/bin/python3"

# 4. config.json anlegen
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    echo "→ Beispiel-Konfiguration kopieren..."
    cp "$INSTALL_DIR/config.json.example" "$INSTALL_DIR/config.json"
    echo "   ⚠  Bitte config.json anpassen (Admin-PIN, Event-Name etc.)"
fi

# 4b. React-SPA bauen (Galerie + Admin-Interface)
if [ -d "$INSTALL_DIR/frontend" ]; then
    echo "→ Frontend (React-SPA) bauen..."
    cd "$INSTALL_DIR/frontend"
    if [ ! -d node_modules ]; then
        npm install --silent
    fi
    npm run build --silent
    cd "$INSTALL_DIR"
fi

# 5. systemd-Service mit aktuellen Pfaden installieren
echo "→ systemd-Service einrichten..."
sed -e "s|__PYTHON__|$PYTHON_BIN|g" \
    -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__USER__|$INSTALL_USER|g" \
    -e "s|__HOME__|$INSTALL_HOME|g" \
    "$INSTALL_DIR/fotobox.service" | sudo tee "$SERVICE_FILE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable fotobox.service

# 6. USB-Auto-Export — udev-Regel installieren
# Wenn ein USB-Stick eingesteckt wird, startet der Pi via udev
# scripts/usb_export.py und kopiert alle Fotos rüber.
echo "→ USB-Auto-Export einrichten..."
chmod +x "$INSTALL_DIR/scripts/usb_export.py"
sed "s|/home/pi/Fotobox|$INSTALL_DIR|g" \
    "$INSTALL_DIR/scripts/99-fotobox-usb.rules" \
    | sudo tee /etc/udev/rules.d/99-fotobox-usb.rules > /dev/null
sudo udevadm control --reload-rules
sudo mkdir -p /run/fotobox
sudo chown "$INSTALL_USER":"$INSTALL_USER" /run/fotobox 2>/dev/null || true

# 7. Drucker-Gruppe
sudo usermod -aG lpadmin "$INSTALL_USER" 2>/dev/null || true

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. config.json anpassen: nano $INSTALL_DIR/config.json"
echo "  2. Fotobox starten:      sudo systemctl start fotobox"
echo "  3. Logs:                 tail -f $INSTALL_DIR/logs/fotobox.log"
echo "  4. Admin-Interface:      http://192.168.4.1:5000/admin  (wenn Hotspot aktiv)"
echo ""
