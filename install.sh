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

# 7. Privilegierte Ports — venv-Python darf Port 80 binden, damit
# Gäste nur 'http://192.168.4.1' eingeben müssen statt ':5000'.
# setcap wirkt nur für genau diese Python-Binary, kein System-Risiko.
#
# Real-Python hinter dem venv-Symlink berechtigen — setcap auf einem
# Symlink wirkt nicht, der Kernel checkt nur die echte Binary.
echo "→ venv-Python für Port 80 berechtigen..."
PYTHON_REAL="$(readlink -f "$PYTHON_BIN")"
if sudo setcap 'cap_net_bind_service=+ep' "$PYTHON_REAL"; then
    # Verifizieren dass die Capability auch wirklich gesetzt ist
    if sudo getcap "$PYTHON_REAL" 2>/dev/null | grep -q "cap_net_bind_service"; then
        echo "  ✓ Port 80 ist jetzt für $PYTHON_REAL freigegeben"
    else
        echo "  ⚠  setcap meldete Erfolg, aber getcap zeigt keine Capability"
        echo "     → Galerie wird auf Port 5000 ausweichen"
        echo "     → iOS-Captive-Portal kann mit Non-Standard-Ports stolpern"
    fi
else
    echo "  ⚠  setcap fehlgeschlagen — Filesystem unterstützt evtl. keine"
    echo "     extended attributes (ungewöhnlich auf Bookworm)"
    echo "     → Galerie startet auf Port 5000 statt 80"
fi

# 7b. Captive-Portal: dnsmasq alle DNS-Anfragen auf die Hotspot-IP
# auflösen lassen. Damit kommen iOS/Android-Probe-URLs (apple.com,
# gstatic.com etc.) bei uns an, der Server schickt 302-Redirect zur
# Galerie — Phone öffnet automatisch das "Anmelden"-Popup.
#
# IP wird aus config.json gelesen, und die Datei wird dem Service-User
# übergeben — hotspot.py passt sie zur Laufzeit auf die echte Interface-
# IP an, falls NetworkManager im 'shared mode' von ipv4.addresses abweicht.
echo "→ Captive-Portal-DNS einrichten..."
HOTSPOT_IP=$(python3 -c "import json,sys; print(json.load(open('$INSTALL_DIR/config.json')).get('hotspot_ip','192.168.4.1'))" 2>/dev/null || echo "192.168.4.1")
sudo mkdir -p /etc/NetworkManager/dnsmasq-shared.d
sudo tee /etc/NetworkManager/dnsmasq-shared.d/captive.conf > /dev/null <<EOF
# Fotobox Captive-Portal: alle DNS-Anfragen auf Hotspot-IP umleiten
# Wird zur Laufzeit von hotspot.py auf die echte Interface-IP angepasst.
address=/#/$HOTSPOT_IP
EOF
sudo chown "$INSTALL_USER":"$INSTALL_USER" /etc/NetworkManager/dnsmasq-shared.d/captive.conf

# 7c. Sudoers-Fallback: falls der chown später mal verloren geht (Reinstall
# als anderer User, manuelle Edits etc.), darf hotspot.py die captive.conf
# trotzdem ohne Passwort via 'sudo tee' schreiben. Eng begrenzt auf genau
# diesen Pfad — kein generelles NOPASSWD.
echo "→ Sudoers-Eintrag für captive.conf-Update einrichten..."
sudo tee /etc/sudoers.d/fotobox-captive > /dev/null <<EOF
$INSTALL_USER ALL=(root) NOPASSWD: /usr/bin/tee /etc/NetworkManager/dnsmasq-shared.d/captive.conf
EOF
sudo chmod 440 /etc/sudoers.d/fotobox-captive
sudo visudo -cf /etc/sudoers.d/fotobox-captive >/dev/null || {
    echo "  ⚠  Sudoers-Eintrag fehlerhaft, wird entfernt"
    sudo rm -f /etc/sudoers.d/fotobox-captive
}

# 7d. Polkit-Regel: Service-User darf NetworkManager-Connections verwalten
# (nmcli connection add/delete/up/down für Hotspot ohne sudo)
echo "→ Polkit-Regel für NetworkManager einrichten..."
sudo tee /etc/polkit-1/rules.d/50-fotobox-nm.rules > /dev/null <<EOF
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.NetworkManager.") === 0 &&
        subject.user === "$INSTALL_USER") {
        return polkit.Result.YES;
    }
});
EOF

# 8. Drucker-Gruppe
sudo usermod -aG lpadmin "$INSTALL_USER" 2>/dev/null || true

echo ""
echo "=== Installation abgeschlossen ==="
echo ""
echo "Nächste Schritte:"
echo "  1. config.json anpassen: nano $INSTALL_DIR/config.json"
echo "  2. Fotobox starten:      sudo systemctl start fotobox"
echo "  3. Logs:                 tail -f $INSTALL_DIR/logs/fotobox.log"
echo "  4. Galerie:              http://192.168.4.1   (Port 80 ist Default)"
echo "  5. Admin-Interface:      http://192.168.4.1/admin"
echo ""
