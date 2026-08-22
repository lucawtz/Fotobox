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
git clone <repo-url> ~/Fotobox
cd ~/Fotobox
chmod +x install.sh
./install.sh
```

Das Skript erkennt automatisch User und Pfad, installiert alle Abhängigkeiten, legt die Verzeichnisstruktur an und richtet den systemd-Service ein.

### Manuell starten (ohne Autostart)

```bash
cd ~/Fotobox
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

## Konfiguration

Die Konfiguration ist zweigeteilt — das ist wichtig zu verstehen, bevor man
etwas ändert:

* **`config.json`** (nicht in git) enthält nur die Felder aus den ersten beiden
  Tabellen. Alles andere daraus wird beim Speichern **verworfen**.
* **`config.py`** (`_DEFAULTS`, in git) enthält alle übrigen Werte. Die kommen
  per `git pull` aufs Pi und lassen sich nicht über das Admin-Panel ändern.

Diese Tabelle wird aus `config.py` gepflegt — bei Änderungen dort bitte mitziehen.

### Mieter-Felder (Admin-Panel, landen in `config.json`)

| Feld | Beschreibung | Standard |
|---|---|---|
| `wifi_ssid` | Hotspot-Name | `"Fotobox"` |
| `wifi_password` | Hotspot-Passwort (WPA2: 8–63 Zeichen) | `"fotobox123"` |
| `event_name` | Name des Events (Boxschirm + Galerie) | `"Fotobox"` |
| `subtitle` | Untertitel unter dem Event-Namen | `"Drück einen Knopf"` |
| `countdown_duration` | Countdown-Dauer in Sekunden | `3` |
| `logo_path` | Pfad zum Logo auf dem Homescreen | `"Layout/logo.png"` |
| `admin_pin` | PIN für das Admin-Interface (volle Rechte) | `"1234"` |
| `host_pin` | PIN für den Gastgeber (nur laufendes Event; leer = deaktiviert) | `"0000"` |
| `theme` | Farbschema (8 Presets im Admin-Panel wählbar) | `{"bg_top": "#D5BB99", "bg_bottom": "#B…` |

### Box-Felder (Admin-Panel, gerätespezifisch, landen in `config.json`)

| Feld | Beschreibung | Standard |
|---|---|---|
| `print_enabled` | Drucken grundsätzlich erlauben | `true` |
| `printer_name` | CUPS-Druckername (leer = Standarddrucker) | `` |
| `print_copies` | Kopien pro Druckauftrag (1–9) | `1` |
| `print_mode` | `auto` / `cover` (randlos) / `fit` (mit weißem Rand) | `"auto"` |

### Owner-Defaults (nur in `config.py`, per `git pull` aktualisiert)

| Feld | Beschreibung | Standard |
|---|---|---|
| `max_photos` | Max. Fotos **pro Event** (älteste werden gelöscht) | `500` |
| `gpio_pins` | GPIO-Pins der drei Buttons | `{"left": 17, "trigger": 27, "right": 22}` |
| `idle_timeout` | Sekunden bis zur Slideshow (`0` = aus) | `0` |
| `slide_duration_ms` | Anzeigedauer je Slideshow-Bild | `5000` |
| `gallery_port` | Port des Galerie-Webservers | `80` |
| `hotspot_enabled` | Box als WLAN-Access-Point betreiben | `true` |
| `hotspot_ip` | IP des Pi im Hotspot | `"192.168.4.1"` |
| `hotspot_interface` | WLAN-Interface für den Hotspot | `"wlan0"` |
| `event_session_hours` | Dauer einer Event-Session, bevor ein neuer Ordner beginnt | `18` |
| `picture_dir` | Verzeichnis für Fotos | `"Picture_Box"` |
| `capture_device` | OpenCV-Index der Capture-Card (Live-Vorschau) | `0` |
| `actions` | Buttons auf dem Homescreen | `[{"id": "foto", "label": "Foto", "key"…` |
| `polaroid_frames` | Position/Drehung der drei Polaroid-Rahmen | `[[567, 255, -5], [1098, 256, 5], [1633…` |
| `polaroid_photo_size` | Fotogröße innerhalb eines Polaroid-Rahmens | `[310, 295]` |
| `live_view_rect` | Position und Größe des Live-Vorschaufensters | `[510, 540, 800, 450]` |
| `instagram_url` | Instagram-Handle in der Sidebar + Button in der Galerie | `"https://www.instagram.com/lucawtz"` |
| `instagram_qr_path` | Instagrams eigener QR-Code (in der App exportiert). Leer = Glyph statt Code | `"Layout/instagram_qr.png"` |
| `booking_url` | Buchungs-Link in der Sidebar + Button in der Galerie | `"https://bytebots.de/"` |
| `booking_label` | Erste Zeile der Buchungs-Reihe (Domain kommt automatisch darunter) | `"Fotobox mieten"` |
| `disk_warn_mb` | Speicherwarnung ab X MB frei | `500` |
| `thumbnail_max_age_days` | Thumbnails älter als X Tage aufräumen | `30` |
| `photo_max_age_days` | Fotos nach X Tagen automatisch löschen | `7` |
| `print_media` | CUPS-Medium (`lpoptions -p <drucker> -l`) | `"Postcard"` |
| `print_size_mm` | Papierformat in mm (Querformat, Breite × Höhe) | `[148, 100]` |
| `print_dpi` | Auflösung für die Druckaufbereitung | `300` |
| `print_options` | Zusätzliche rohe `lp -o`-Optionen | `[]` |
| `camera_keepalive_s` | Intervall des Kamera-Watchdogs | `25` |
| `camera_output_mode` | gphoto2-Ausgabemodus der Kamera | `"3"` |

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
http://192.168.4.1/admin         (bei aktivem Hotspot)
http://<pi-ip>/admin             (bei LAN/WLAN-Verbindung)
```

**Funktionen:**
- System-Status (Kamera, Speicher, Foto-Anzahl)
- Event-Name, WLAN-Einstellungen, Countdown-Dauer ändern
- Neues Event starten (trennt Fotos in einen frischen Ordner, löscht nichts)
- Logo hochladen
- Admin-PIN ändern
- Alle Fotos löschen (mit Bestätigung)
- Box für die nächste Vermietung vorbereiten (Wartung → "Box vorbereiten")

**Foto löschen (einzeln):** Foto in der Galerie öffnen → "Löschen" → Admin-PIN eingeben.

**Vermietungswechsel:** Unter **Wartung → Box vorbereiten** lässt sich in einem
Durchgang zurücksetzen, was der letzte Gastgeber hinterlassen hat: Event-Name,
Untertitel, Countdown und Theme, sein Logo, alle Fotos und der Event-Ordner.
Jeder Schritt ist einzeln abwählbar.

WLAN-Zugangsdaten und PINs bleiben dabei **unberührt** — ein Reset würde sie auf
die Auslieferungswerte zurücksetzen, vor denen das Panel zu Recht warnt. Beides
gehört also weiterhin von Hand neu vergeben, sonst kommt der Vormieter in
Funkreichweite wieder ins Admin-Panel.

**Eigenes Logo hinterlegen:** Jeder Upload aus dem Admin-Panel überschreibt
`Layout/logo.png` — das ist der Mieter-Slot. Lege dein eigenes Logo einmalig
zusätzlich als `Layout/logo_default.png` ab: darauf fällt die Box zurück, sobald
der Mieter-Slot leer ist, und ein Upload fasst die Datei nie an.

---

## Hotspot einrichten

Der Hotspot wird über NetworkManager (`nmcli`) gestartet und ist **standardmäßig
aktiv** — die Box ist der Access-Point, sonst erreicht kein Gast die Galerie.
`hotspot_enabled` ist ein Owner-Default in `config.py`; ein Eintrag in der
`config.json` hat **keine** Wirkung (er wird beim Speichern verworfen).

Zum Einrichten per VNC über das Heim-WLAN die Box mit `--no-hotspot` starten —
dann bindet auch der Galerie-Server nur auf `127.0.0.1`:

```bash
sudo systemctl stop fotobox
venv/bin/python main.py --no-hotspot
```

`nmcli` muss verfügbar sein:

```bash
sudo apt install network-manager
```

Standardmäßig wird der **eingebaute Pi-WLAN-Chip** (`wlan0`) verwendet — auch wenn ein USB-WLAN-Stick eingesteckt ist. Falls dein Setup ein anderes Interface braucht, kann es per `hotspot_interface` in der `config.json` überschrieben werden. Verfügbare Interfaces zeigt:

```bash
nmcli device
```

WLAN-Name und Passwort lassen sich im Admin-Panel unter **WLAN** ändern. Die Box
startet den Hotspot danach automatisch neu — alle verbundenen Geräte fliegen
dabei kurz raus, auch das Gerät, von dem aus man die Änderung vornimmt. Am
besten vor dem Event erledigen, nicht mittendrin.

### Warum externe Links über `/go/` laufen

`hotspot.py` schreibt `address=/#/<hotspot_ip>` in die dnsmasq-Config — ein
Captive-Portal-Hijack, der **jede** DNS-Anfrage auf die Box umbiegt. Nur
deshalb landet ein Gast, der irgendeine Adresse eintippt, in der Galerie.

Der Preis: für jeden Gast im Fotobox-WLAN ist damit auch jede externe Seite
unerreichbar. Ein QR-Code mit `https://…` löst auf die Box auf, deren Port 443
niemand bedient — der Gast sieht nur einen Verbindungsfehler.

Deshalb zeigen die Instagram- und Buchungs-Buttons in der Galerie auf
`/go/instagram` bzw. `/go/termin`. Diese Route liegt lokal, ist ohne DNS und
ohne Internet erreichbar, prüft im Browser ob das Handy überhaupt nach draußen
kommt und leitet dann selbst weiter. Klappt das nicht, erklärt sie stattdessen
den Weg (WLAN trennen / mobile Daten an), statt den Gast im Fehler stehen zu
lassen.

### Instagram-QR

`instagram_qr_path` nimmt den Code, den Instagram im eigenen Profil zum Export
anbietet — direkt so, wie die App ihn ausgibt. `ui.py` schneidet den Rand und
den Handle-Schriftzug darunter selbst weg und macht das Weiss transparent,
damit der Code auf der Cremekachel der Sidebar sitzt statt in einem weissen
Rechteck darauf. Das Weiss wird bewusst durch die *helle* Kachel ersetzt und
nicht durch das Sidebar-Braun: ein QR-Code braucht dunkle Module auf hellem
Grund, invertiert scheitern viele Scanner.

Instagrams Code hat 41 Module gegenüber 25 beim Galerie-Code, ist also
deutlich dichter. Er wird deshalb mit 130 px gerendert (~3,2 px pro Modul) —
kleiner als der Galerie-Code, aber gross genug zum Scannen. Ohne hinterlegte
Datei zeichnet die Sidebar wie vorher das Instagram-Glyph.

### Nur ein selbst erzeugter Code

Am Boxbildschirm gibt es aus demselben Grund **nur einen** selbst erzeugten
QR-Code, den der Galerie. Wer den Buchungs-Link scannen würde, hängt ohnehin schon im
Fotobox-WLAN und damit in der Galerie, wo der Button steht — ein zweiter Code
gewinnt dort nichts und nimmt dem Galerie-Code die Führung. Instagram und
Buchung stehen deshalb als Text darunter, die Buchung mit ihrer Domain als
zweiter Zeile.

---

## Drucker einrichten (Canon Selphy)

`install.sh` installiert CUPS und nimmt den Service-User in die Gruppe
`lpadmin` auf, richtet aber **keinen Drucker ein** — das ist geräteabhängig und
muss einmalig von Hand passieren.

```bash
# 1. Selphy per USB anschliessen und einschalten, dann suchen lassen:
lpinfo -v                      # zeigt z.B. usb://Canon/SELPHY%20CP1500?serial=...

# 2. Passenden Treiber finden (Gutenprint deckt die CP-Serie ab):
sudo apt install printer-driver-gutenprint
lpinfo -m | grep -i selphy

# 3. Drucker anlegen (Name frei waehlbar, hier "Selphy"):
sudo lpadmin -p Selphy \
     -v "usb://Canon/SELPHY%20CP1500?serial=XXXX" \
     -m "gutenprint.5.3://canon-selphy-cp1500/expert" \
     -o media=Postcard -E

# 4. Als Standard setzen und pruefen:
sudo lpoptions -d Selphy
lpstat -p                      # muss "is idle. enabled" melden
```

Danach im Admin-Panel unter **Drucken** das Zielgerät auswählen. Solange CUPS
keinen bereiten Drucker meldet, blendet die Box den „Drucken"-Knopf aus.

**Welche Optionen der Treiber akzeptiert**, zeigt:

```bash
lpoptions -p Selphy -l
```

Passende Werte dann in `config.py` unter `print_media`, `print_size_mm` und
`print_options` eintragen (z.&nbsp;B. `print_options: ["StpBorderless=True"]`
für randlosen Druck).

**Testdruck ohne die Box:**

```bash
lp -d Selphy -o media=Postcard /pfad/zum/foto.jpg
lpstat -o                      # Warteschlange ansehen
cancel -a Selphy               # Warteschlange leeren
```

Die Box rechnet das Foto vor dem Druck selbst auf das Papierformat
(`printing.prepare`): Einzelfotos randlos, die 2×2-Collage vollständig mit
weißem Rand — ein quadratisches Bild randlos auf Postkarte gedruckt würde die
obere und untere Fotoreihe abschneiden.

---

## Troubleshooting

### Kamera nicht erkannt
1. USB-Kabel prüfen
2. `gphoto2 --auto-detect` im Terminal ausführen
3. Kamera-Modus auf "PTP" / "MTP" stellen (nicht "Massenspecher")
4. Watchdog versucht automatisch alle 10 Sekunden eine Neuverbindung

### Galerie nicht erreichbar
- Pi-IP mit `ip a` prüfen
- Firewall: `sudo ufw allow 80`
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
├── Layout/              # Logo
├── Picture_Box/         # Gespeicherte Fotos
├── thumbnails/          # Thumbnail-Cache
├── logs/                # Log-Dateien
├── frontend/            # React-SPA (Galerie + Admin)
├── fotobox.service      # systemd-Unit
├── install.sh           # Installations-Skript
└── requirements.txt     # Python-Abhängigkeiten
```
