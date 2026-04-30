# Fotobox

Vollständige Fotobox-App für den Raspberry Pi (Bookworm) mit DSLR-Kamera, Galerie-Webserver und Admin-Interface.

## Hardware-Anforderungen

| Komponente | Details |
|---|---|
| Raspberry Pi | 4B oder 5 (4 GB RAM empfohlen) |
| DSLR-Kamera | USB-kompatibel (gphoto2-Support) |
| HDMI-Capture-Card | Für die Live-Vorschau im Countdown |
| Monitor | Beliebig, kein Touchscreen nötig |
| GPIO-Buttons | 3× Taster mit Pull-up |

### GPIO-Pinbelegung

| Funktion | GPIO-Pin | Tastatur-Fallback |
|---|---|---|
| Links / Zurück | 17 | Q |
| Auslösen / Bestätigen | 27 | Space |
| Rechts / Collage / Drucken | 22 | E |

Buttons werden an GND und den jeweiligen GPIO-Pin angeschlossen (Pull-up intern aktiviert).

---

## Installation

```bash
git clone <repo-url> /home/pi/fotobox
cd /home/pi/fotobox
chmod +x install.sh
./install.sh
```

Das Skript installiert alle Abhängigkeiten, legt die Verzeichnisstruktur an und richtet den systemd-Service ein.

### Manuell starten (ohne Autostart)

```bash
cd /home/pi/fotobox
source venv/bin/activate
python3 main.py
```

### Autostart verwalten

```bash
sudo systemctl start fotobox     # starten
sudo systemctl stop fotobox      # stoppen
sudo systemctl restart fotobox   # neu starten
sudo systemctl status fotobox    # Status anzeigen
tail -f logs/fotobox.log         # Logs live anzeigen
```

---

## Konfiguration (config.json)

| Feld | Beschreibung | Standard |
|---|---|---|
| `event_name` | Name des Events (auf Screen + Galerie) | `"Fotobox"` |
| `countdown_duration` | Countdown-Dauer in Sekunden | `3` |
| `max_photos` | Max. Anzahl gespeicherter Fotos (älteste werden gelöscht) | `500` |
| `idle_timeout` | Sekunden bis Slideshow startet | `60` |
| `admin_pin` | PIN für Admin-Interface und Foto-Löschen | `"1234"` |
| `logo_path` | Pfad zum Logo (wird auf Homescreen angezeigt) | `"Layout/logo.png"` |
| `picture_dir` | Verzeichnis für Fotos | `"Picture_Box"` |
| `hotspot_enabled` | WLAN-Hotspot aktivieren | `false` |
| `wifi_ssid` | Hotspot-Name | `"Fotobox"` |
| `wifi_password` | Hotspot-Passwort | `"fotobox123"` |
| `hotspot_ip` | IP-Adresse des Pi im Hotspot | `"192.168.4.1"` |
| `gallery_port` | Port des Galerie-Webservers | `5000` |
| `gpio_pins.left` | GPIO-Pin für Links-Button | `17` |
| `gpio_pins.trigger` | GPIO-Pin für Auslöser-Button | `27` |
| `gpio_pins.right` | GPIO-Pin für Rechts-Button | `22` |
| `capture_device` | OpenCV-Index der Capture-Card (Live-Vorschau) | `0` |
| `disk_warn_mb` | Speicherwarnung ab X MB frei | `500` |

---

## Screen-Flow

```
Homescreen
  │
  ├─[Space]─→ Einzelfoto-Countdown → Result-Screen → (zurück)
  │
  └─[E]─────→ Collage (4× Countdown) → Result-Screen → (zurück)
                                              │
                                    [Q] Zurück / [Space] Nochmal / [E] Drucken
```

**Slideshow** startet automatisch nach `idle_timeout` Sekunden ohne Eingabe. Jeder Button bricht sie ab.

---

## Admin-Interface

Erreichbar per Browser (Handy/Laptop im gleichen Netzwerk):

```
http://192.168.4.1:5000/admin    (bei aktivem Hotspot)
http://<pi-ip>:5000/admin        (bei LAN/WLAN-Verbindung)
```

**Funktionen:**
- System-Status (Kamera, Speicher, Foto-Anzahl)
- Event-Name, WLAN-Einstellungen, Countdown-Dauer ändern
- Logo hochladen
- Admin-PIN ändern
- Alle Fotos löschen (mit Bestätigung)

**Foto löschen (einzeln):** Foto in der Galerie öffnen → "Löschen" → Admin-PIN eingeben.

---

## Hotspot einrichten

Der Hotspot wird über NetworkManager (`nmcli`) gestartet. `hotspot_enabled: true` in config.json setzen und sicherstellen, dass `nmcli` verfügbar ist:

```bash
sudo apt install network-manager
```

Nach Änderung des WLAN-Namens oder Passworts: `sudo systemctl restart fotobox`.

---

## Troubleshooting

### Kamera nicht erkannt
1. USB-Kabel prüfen
2. `gphoto2 --auto-detect` im Terminal ausführen
3. Kamera-Modus auf "PTP" / "MTP" stellen (nicht "Massenspecher")
4. Watchdog versucht automatisch alle 10 Sekunden eine Neuverbindung

### Galerie nicht erreichbar
- Pi-IP mit `ip a` prüfen
- Firewall: `sudo ufw allow 5000`
- Log: `tail -f logs/gallery.log`

### Live-Vorschau fehlt (Countdown schwarz)
- Capture-Card-Index prüfen: `v4l2-ctl --list-devices`
- `capture_device` in config.json ggf. auf `1` oder `2` stellen

### Speicherwarnung
- Fotos auf anderem Gerät sichern
- `max_photos` in config.json reduzieren
- Admin-Interface: "Alle Fotos löschen"

### Logs lesen
```bash
tail -f /home/pi/fotobox/logs/fotobox.log   # Haupt-App
tail -f /home/pi/fotobox/logs/gallery.log   # Webserver
```

---

## Verzeichnisstruktur

```
fotobox/
├── main.py              # Einstiegspunkt
├── config.py            # Konfigurationsloader
├── config.json          # Nutzerkonfiguration (bearbeiten!)
├── camera.py            # gphoto2-Wrapper + Watchdog
├── hardware.py          # GPIO-Buttons (3×)
├── ui.py                # Pygame-GUI (State-Machine)
├── gallery_server.py    # Flask-Webserver (Galerie + Admin)
├── collage.py           # 2×2-Collage-Generator
├── disk_monitor.py      # Speicherüberwachung
├── hotspot.py           # WLAN-Hotspot (nmcli)
├── Layout/              # Overlay-Bilder, Logo
├── Picture_Box/         # Gespeicherte Fotos
├── thumbnails/          # Thumbnail-Cache
├── logs/                # Log-Dateien
├── templates/           # HTML-Templates (Galerie, Admin)
├── fotobox.service      # systemd-Unit
├── install.sh           # Installations-Skript
└── requirements.txt     # Python-Abhängigkeiten
```
