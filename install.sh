#!/usr/bin/env bash
# Fotobox Installations-Skript – Raspberry Pi OS Bookworm
set -e

INSTALL_DIR="/home/pi/fotobox"
SERVICE_FILE="/etc/systemd/system/fotobox.service"

echo "=== Fotobox Installation ==="

# 1. System-Pakete
echo "→ System-Pakete installieren..."
sudo apt-get update -qq
sudo apt-get install -y \
    gphoto2 \
    hostapd \
    python3-pip \
    python3-venv \
    libatlas-base-dev \
    libjpeg-dev \
    libopencv-dev \
    cups \
    cups-bsd

# 2. Fotobox-Verzeichnis anlegen (falls noch nicht vorhanden)
echo "→ Verzeichnisstruktur anlegen..."
mkdir -p "$INSTALL_DIR/Picture_Box"
mkdir -p "$INSTALL_DIR/thumbnails"
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/Layout"

# 3. Dateien kopieren (wenn Skript aus dem Quellverzeichnis ausgeführt wird)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ "$SCRIPT_DIR" != "$INSTALL_DIR" ]; then
    echo "→ Dateien nach $INSTALL_DIR kopieren..."
    cp -r "$SCRIPT_DIR"/. "$INSTALL_DIR/"
fi

# 4. Python-Umgebung (venv)
echo "→ Python-Umgebung einrichten..."
cd "$INSTALL_DIR"
python3 -m venv venv --system-site-packages
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q

# 5. config.json anlegen (falls noch nicht vorhanden)
if [ ! -f "$INSTALL_DIR/config.json" ]; then
    echo "→ Beispiel-Konfiguration kopieren..."
    cp "$INSTALL_DIR/config.json.example" "$INSTALL_DIR/config.json"
    echo "   ⚠  Bitte config.json anpassen (Admin-PIN, Event-Name etc.)"
fi

# 6. Berechtigungen
chown -R pi:pi "$INSTALL_DIR"

# 7. systemd-Service in fotobox.service Python-Pfad anpassen
echo "→ systemd-Service einrichten..."
sed "s|/usr/bin/python3|$INSTALL_DIR/venv/bin/python3|g" \
    "$INSTALL_DIR/fotobox.service" | sudo tee "$SERVICE_FILE" > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable fotobox.service

# 8. Drucker-Gruppe (für lp-Befehl)
sudo usermod -aG lpadmin pi 2>/dev/null || true

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. config.json anpassen: nano $INSTALL_DIR/config.json"
echo "  2. Fotobox starten:      sudo systemctl start fotobox"
echo "  3. Logs:                 tail -f $INSTALL_DIR/logs/fotobox.log"
echo "  4. Admin-Interface:      http://192.168.4.1:5000/admin  (wenn Hotspot aktiv)"
echo ""
echo "Für Hotspot-Konfiguration → siehe README.md"
