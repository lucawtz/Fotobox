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
    # Immer installieren, nicht nur beim ersten Mal: nach einem git pull mit
    # neuen Dependencies existiert node_modules laengst, ein "nur wenn fehlt"-Check
    # haette die neuen Pakete uebersprungen und der Build waere an einem
    # unaufloesbaren Import gescheitert. npm ci baut exakt nach
    # package-lock.json auf und raeumt veraltete Pakete mit weg; npm install
    # faengt den Fall ab, dass Lockfile und package.json auseinanderlaufen.
    npm ci --silent || npm install --silent
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
# IP kommt aus den Owner-Defaults in config.py (NICHT aus config.json —
# dort landen nur Mieter-Felder, hotspot_ip wird beim Speichern verworfen).
# Die Datei wird dem Service-User übergeben — hotspot.py passt sie zur
# Laufzeit auf die echte Interface-IP an, falls NetworkManager im
# 'shared mode' von ipv4.addresses abweicht.
echo "→ Captive-Portal-DNS einrichten..."
HOTSPOT_IP=$(cd "$INSTALL_DIR" && python3 -c "import config; print(config.cfg['hotspot_ip'])" 2>/dev/null || echo "192.168.4.1")
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

# 9. Log-Rotation — logs/fotobox.log waechst sonst unbegrenzt, weil systemd
# mit StandardOutput=append: dranhaengt. copytruncate, weil systemd den
# Filedeskriptor offen haelt (Details in scripts/logrotate-fotobox).
echo "→ Log-Rotation einrichten..."
if [ -f "$INSTALL_DIR/scripts/logrotate-fotobox" ]; then
    sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
        -e "s|__USER__|$INSTALL_USER|g" \
        "$INSTALL_DIR/scripts/logrotate-fotobox" \
        | sudo tee /etc/logrotate.d/fotobox > /dev/null
    # Syntaxpruefung: ein kaputter Eintrag legt die Rotation ALLER Logs auf
    # dem System lahm, nicht nur unsere.
    if sudo logrotate --debug /etc/logrotate.d/fotobox > /dev/null 2>&1; then
        echo "  ✓ /etc/logrotate.d/fotobox"
    else
        echo "  ⚠ logrotate-Konfiguration fehlerhaft — wird entfernt"
        sudo rm -f /etc/logrotate.d/fotobox
    fi
else
    echo "  ⚠ scripts/logrotate-fotobox fehlt — uebersprungen"
fi

# 10. Bildschirmschoner/DPMS aus. Ohne das wird der Monitor mitten im Event
# schwarz und der naechste Gast denkt, die Box ist aus. Beide Display-Stacks
# abdecken: X11 (xset) und Wayland/labwc+wayfire (kein Blanking konfigurierbar,
# daher zusaetzlich die Konsolen-Variante).
echo "→ Bildschirmschoner deaktivieren..."
AUTOSTART_DIR="$INSTALL_HOME/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cat > "$AUTOSTART_DIR/fotobox-no-blank.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Fotobox: Bildschirmschoner aus
Exec=sh -c "xset s off; xset -dpms; xset s noblank"
X-GNOME-Autostart-enabled=true
NoDisplay=true
EOF
# Konsolen-Blanking (greift auch ohne X/Wayland-Session)
if ! grep -q "consoleblank=0" /boot/firmware/cmdline.txt 2>/dev/null \
   && [ -f /boot/firmware/cmdline.txt ]; then
    echo "  Hinweis: für vollständiges Blanking-Aus 'consoleblank=0' in"
    echo "           /boot/firmware/cmdline.txt ergänzen (manuell, ein Reboot nötig)."
fi
echo "  ✓ $AUTOSTART_DIR/fotobox-no-blank.desktop"

# 11. Boot-Target pruefen. Der Service haengt an graphical.target und braucht
# eine laufende Desktop-Session — bootet der Pi in die Konsole, ist der
# Service zwar aktiviert, startet aber nie erfolgreich.
echo "→ Boot-Target prüfen..."
CURRENT_TARGET=$(systemctl get-default 2>/dev/null || echo "unbekannt")
if [ "$CURRENT_TARGET" = "graphical.target" ]; then
    echo "  ✓ Boot-Target ist graphical.target"
else
    echo "  ⚠ Boot-Target ist '$CURRENT_TARGET', nicht graphical.target."
    echo "    Die Fotobox-UI braucht eine Desktop-Session. Umstellen mit:"
    echo "      sudo raspi-config nonint do_boot_behaviour B4   # Autologin Desktop"
    echo "      sudo systemctl set-default graphical.target"
fi

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
