# Fotobox — Hardware-Bestand

Was in dieser Box wirklich steckt, ausgelesen am **26.08.2026** vom laufenden
Gerät. Nicht die Anforderungen aus dem README (*„Pi 4B oder 5", „3× Taster"*),
sondern der Ist-Zustand.

Seriennummern und MAC-Adressen sind gekürzt — die Befehle zum Auslesen stehen
jeweils dabei. PINs und WLAN-Passwort stehen hier bewusst gar nicht; die leben
in `config.json` und gehören nicht ins Repo.

---

## Raspberry Pi

| | |
|---|---|
| Modell | Raspberry Pi 4 Model B **Rev 1.4** |
| Seriennummer | `1000…c89d` — `tr -d '\0' < /proc/device-tree/serial-number` |
| Hostname | `FotoboxRaspberry` |
| Service-User | `fotoboxpi` (uid 1000) |
| Gruppen | u.a. `sudo`, `video`, `gpio`, `lp`, `lpadmin`, `render`, `input` |
| OS | Debian GNU/Linux **13 (trixie)** |
| Kernel | `6.12.47+rpt-rpi-v8`, aarch64 |
| Python | **3.13.5** — System und venv identisch |
| CPU / RAM | 4 Kerne · **7,6 GiB** |
| Installation | `/home/fotoboxpi/Fotobox` |

**Wichtig für `requirements.txt`:** Python 3.13 ist der Grund für den
numpy-Pin auf `~=2.1.3`. Für 2.0.x gibt es keine cp313-Wheels, pip baut die
dann 20 Minuten lang aus dem Quelltext.

### Speicher

| | |
|---|---|
| SD-Karte | 58,3 GB (`/dev/mmcblk0`) |
| `/` | 57 GB, davon **44 GB frei** (21 % belegt) |
| `/boot/firmware` | 510 MB, 87 MB belegt |

### Temperatur — Achtung

```
temp=79.8'C     throttled=0x80000
```

`0x80000` ist Bit 19: **die weiche Temperaturgrenze wurde seit dem Boot schon
erreicht.** Aktuell wird nicht gedrosselt (Bits 0–3 sind leer), aber bei
79,8 °C im Leerlauf ist kaum Luft. Der Pi taktet ab 80 °C herunter.

Ein Event bedeutet stundenlangen Dauerbetrieb mit laufendem Live-Bild
(Videodecoding), Hotspot und Druckaufbereitung — alles gleichzeitig und alles
CPU-nah. Kühlkörper oder Lüfter gehört auf die Liste vor der Generalprobe.

Prüfen: `vcgencmd measure_temp` und `vcgencmd get_throttled`.

---

## Kamera

| | |
|---|---|
| Modell | **Canon EOS 700D** |
| Firmware | `3-1.1.3` |
| Seriennummer | `61dd…cca6` — `gphoto2 --summary` |
| USB-ID | `04a9:3272` |
| Treiber | `usbfs` (gphoto2 spricht direkt mit dem Gerät) |
| Aufnahmeformate | **nur JPEG** |
| Akku | 100 % (bei der Messung) |

### Eingestellt

| Einstellung | Wert | Bedeutung für die Box |
|---|---|---|
| `output` | **TFT + PC** (Index 3 von 0–7) | Bild geht aufs Kameradisplay *und* über HDMI |
| `viewfinder` | `0` im Ruhezustand | schaltet der Halte-Prozess auf `1` |
| `afmethod` | **Live** (Index 2) | kleines festes AF-Feld in der Bildmitte |
| `focusmode` | **Manual** | AF ist am Objektiv abgeschaltet |
| `imageformat` | Large Fine JPEG | kein RAW — sonst zwei Dateien pro `--filename` |
| `capturetarget` | **Internal RAM** | Fotos gehen *nicht* auf die SD-Karte der Kamera |
| Belichtung | M · 1/125 · f/5,6 · ISO Auto | |

`focusmode: Manual` ist für eine Fotobox richtig: bei festem Abstand einmal
scharfstellen, danach gibt es keine Fehlfokussierung im Countdown. Es heißt
aber auch, dass die gemessene Auslöseverzögerung **nicht** vom Autofokus
kommt.

`capturetarget: Internal RAM` erklärt, warum `--capture-image-and-download`
funktioniert, ohne dass eine SD-Karte in der Kamera nötig wäre.

### Uhr

Die Kamerauhr geht **3602 s (1 h 0 min 2 s) nach**. Wichtig bei jeder
EXIF-Messung — ohne Korrektur landen alle Zeitrechnungen eine Stunde daneben.

Auslesen: `gphoto2 --get-config datetime` gegen `date` auf dem Pi.

### Gemessene Zeiten

Über 29 Aufnahmen aus den `Aufnahme-Zeiten`-Zeilen im Log, ergänzt um
EXIF-Messungen des echten Auslösemoments:

| Abschnitt | Zeit |
|---|---|
| Anfrage → USB-Gerät frei (Halte-Prozess beendet) | Ø **1,24 s** (0,80–1,88) |
| dort friert das Live-Bild ein | |
| Gerät frei → Belichtung | Ø **2,0 s** |
| **Anfrage → Belichtung** | Ø **3,25 s** (gemessen 3,45 s im Einzelfall) |
| Belichtung → gphoto2-Marker `New file is in location` | **0,34–0,49 s** |
| Anfrage → Bild geladen | Ø 4,24 s |

**Der Marker ist nicht der Verschluss.** Er meldet die fertige Datei auf der
Kamera und liegt rund 0,4 s danach. Wer `capture_lead_s` neu kalibriert, muss
das abziehen oder gegen EXIF messen — siehe Kommentar in `config.py`.

Nachgemessen am 26.08. mit den aktuellen Werten: Verschluss **+0,35 s** nach
„Lächeln!".

### Bekannte Zustände

**„Beschäftigt…bitte warten."** Die Kamera kann sich in einen Zustand
verklemmen, in dem sie Lesezugriffe beantwortet, aber jeden Schreibzugriff mit
`PTP Device Busy (0x2019)` und `I/O in progress (-110)` ablehnt. Beobachtet am
26.08. nach mehreren mitten in der Sitzung abgebrochenen gphoto2-Aufrufen.

Was **nicht** hilft: USB-Reset (`USBDEVFS_RESET`), Neustart des Dienstes, der
Ein/Aus-Schalter. Eine EOS im Busy-Zustand verzögert das Ausschalten — der Pi
sieht dann kein `USB disconnect`, und die Kamera bleibt hängen.

Was hilft: **Akku entnehmen.** Danach meldet sie sich neu am Bus an, und
`output`/`viewfinder` lassen sich wieder setzen.

Kontrolle: `dmesg | grep "usb 1-1.4"` muss ein `USB disconnect` gefolgt von
einer **neuen** Gerätenummer zeigen. Bleibt die Nummer gleich, war die Kamera
nicht wirklich aus.

---

## Bildschirm

| | |
|---|---|
| Anschluss | `card1-HDMI-A-1` **connected** (HDMI-A-2 unbenutzt) |
| Compositor | **labwc** (Wayland), Session-Typ `tty` |
| SDL-Treiber | `wayland` |

### Auflösung — der Monitor kann kein Full HD

Vom Kernel gemeldete Modi:

```
1024x768     ← Maximum
800x600
848x480
640x480
```

Die Box rendert intern fest auf **1920×1080** (`ui.W, ui.H`) und lässt SDL
herunterskalieren:

```
Display: 1920x1080 ist kein nativer Modus (verfuegbar: [(1024, 768), …]) — SCALED aktiv
Display: SDL-Treiber 'wayland' aktiv (1920x1080, skaliert)
```

Das funktioniert, hat aber zwei Folgen:

1. **Alles ist weicher als entworfen.** Schrift, QR-Codes und Live-Bild
   verlieren beim Herunterrechnen auf 1024×768 mehr als die Hälfte der Pixel.
2. **Das Seitenverhältnis passt nicht.** 1920×1080 ist 16:9, 1024×768 ist 4:3.

Die QR-Codes sind davon am stärksten betroffen: der Galerie-Code wird mit
125×125 px gezeichnet und landet auf dem Panel bei rund 67×67 px. Ob er in
dieser Größe noch zuverlässig scannt, ist **nicht geprüft** und gehört auf die
Generalprobe.

Die Dauer-Warnung *„Sidebar zu eng für 3 Codes"* hat damit **nichts** zu tun
— das hatte ich zuerst vermutet und beim Nachlesen widerlegt. Sie rechnet in
der logischen 1920×1080-Fläche gegen `SIDEBAR_W = 320` und meldet fehlende
**Höhe** (`605 px gebraucht, 547 px verfügbar`). Der Buchungs-Code fällt
deshalb auf Glyph und Text zurück, unabhängig davon, was der Monitor kann.

### Bildschirmschoner

`~/.config/autostart/fotobox-no-blank.desktop`:

```
Exec=sh -c "xset s off; xset -dpms; xset s noblank"
```

**Vermutlich wirkungslos.** `xset` ist ein X11-Werkzeug, die Session läuft
unter labwc/Wayland. Es erreicht damit höchstens XWayland, nicht den
Compositor. ROADMAP-Punkt P1-6 gilt damit weiterhin als offen — ob der Monitor
über Stunden anbleibt, hat noch niemand nachgewiesen.

---

## HDMI-Capture-Card

| | |
|---|---|
| Modell | **MacroSilicon USB3.0 Capture** |
| USB-ID | `534d:2109` |
| Geräte | `/dev/video0` (Capture), `/dev/video1` (Metadaten) |
| Schnittstellen | 2× Video (`uvcvideo`), 2× Audio (`snd-usb-audio`), 1× HID |
| Betrieb | **480 Mbit auf Bus 001** — also USB 2.0, nicht 3.0 |

### Auflösung muss angefordert werden

Ohne Anforderung liefert die Karte ihren Standard und der ist nach jeder
frischen USB-Anmeldung **640×480** — dort kommt ein praktisch schwarzes Bild:

| | Auflösung | mittlere Helligkeit |
|---|---|---|
| ohne Anforderung | 640×480 | **4** von 255 |
| 1920×1080 angefordert | 1920×1080 | sauberes Bild |

Deshalb steht `capture_size: [1920, 1080]` in `config.py`, und
`_LiveReader._open()` setzt es bei jedem Öffnen — auch beim Reconnect nach
einem USB-Reset.

Das einmal gesetzte Format bleibt am Gerät stehen, bis es neu angemeldet wird.
Genau daher kam das Muster *„nach dem Stromzyklus geht das Live-Bild nicht"*.

---

## Drucker

| | |
|---|---|
| Modell | **Canon SELPHY CP1500** |
| USB-ID | `04a9:3302`, Treiber `usblp` |
| CUPS-Name | `Canon_SELPHY_CP1500` — Zustand `idle`, `enabled` |
| In der Config | `printer_name: "Canon_SELPHY_CP1500"` |
| Druckbereit | ja (`printing.available()` = True) |

CUPS kennt **keinen Standarddrucker** (`lpstat -d` meldet
*no system default destination*). Das ist unkritisch, weil `printer_name`
explizit gesetzt ist — ein leerer Wert würde hier aber ins Leere laufen.

Daneben existiert `CUPS-BRF-Printer`, ein virtueller Braille-Drucker aus der
Debian-Grundinstallation. `printing.list_printers()` markiert ihn korrekt als
`virtual: True`.

---

## Taster (GPIO)

| Funktion | Pin | Status |
|---|---|---|
| Auslösen | **GPIO 27** | verbaut |
| Rechts / Collage / Drucken | **GPIO 22** | verbaut |
| Links / Zurück | GPIO 17 | **nicht verbaut** |

```
hardware: Taster: trigger=GPIO27  right=GPIO22
hardware: Nicht verbaut: left — die UI blendet die zugehoerigen Aktionen aus
```

Ohne den linken Taster weckt **trigger + rechts gleichzeitig** die Kamera, und
„Zurück" auf dem Ergebnis-Schirm erledigt der 10-Sekunden-Timer.

Das README nennt weiterhin „3× Taster mit Pull-up" — das ist die Anforderung,
nicht der Ist-Zustand.

---

## Netzwerk

| Interface | Treiber | Zustand | Adresse |
|---|---|---|---|
| `eth0` | — | UP | `192.168.178.58` (Heim-LAN, hierüber läuft SSH) |
| `wlan0` | `brcmfmac` | UP | `192.168.4.1` — **trägt den Hotspot** (eingebauter Chip) |
| `wlan1` | `rtl8xxxu` | **DOWN** | keine Verbindung |

`wlan1` ist ein **TP-Link TL-WN823N** (`2357:0109`) am USB. Er ist
angeschlossen, aber ohne Funktion — der Hotspot `fotobox-hotspot` läuft auf
dem eingebauten WLAN des Pi.

Vermutlich steckt er für die geparkte Idee *„WLAN-Uplink über den USB-Stick"*
(`75dff77`). Solange die nicht umgesetzt ist, belegt er einen USB-Port ohne
Gegenwert.

MAC-Adressen: `ip -br link`.

---

## USB-Belegung

Alle Geräte hängen am fest verbauten USB-Hub des Pi 4 (`2109:3431`, VIA Labs
— **kein externer Hub**), und zwar durchgehend mit **480 Mbit**:

```
Bus 001 (USB 2.0, 480M)
  └─ VIA-Labs-Hub (4 Ports)
       ├─ Port 1: TP-Link TL-WN823N     ← ohne Funktion
       ├─ Port 2: Canon SELPHY CP1500
       ├─ Port 3: MacroSilicon Capture  ← USB-3.0-Gerät auf USB-2.0-Pfad
       └─ Port 4: Canon EOS 700D

Bus 002 (USB 3.0, 5000M)               ← LEER
```

Die Capture-Card ist ein USB-3.0-Gerät, läuft aber mit 480 Mbit. Sie steckt
also in einem schwarzen USB-2.0-Port. Säße sie in einem blauen, erschiene sie
auf **Bus 002 mit 5000 Mbit**.

### Ausfälle am 26.08.

Beide auf demselben Bus, innerhalb einer Stunde:

```
07:57  usb 1-1.3: device not accepting address 4, error -71
       usb 1-1-port3: unable to enumerate USB device      ← Capture-Card weg
08:32  usb 1-1.4: USB disconnect, device number 12        ← Kamera weg
       usb 1-1.4: new high-speed USB device number 13     ← nach 8 s zurück
```

Die Kamera kam von selbst zurück und die Box hat es abgefangen (Auto-Wecken,
Halte-Prozess neu, Watchdog). Die Capture-Card musste von Hand neu gesteckt
werden.

`error -71` ist ein Protokollfehler — Strom, Kabel oder Port. Ein
ursächlicher Zusammenhang mit der Bus-Auslastung ist **plausibel, aber nicht
bewiesen**: dafür müsste nach dem Umstecken über längere Zeit Ruhe sein.

---

## Offene Punkte

| Punkt | Schwere | Nachweis fehlt |
|---|---|---|
| Pi bei 79,8 °C, weiche Temperaturgrenze schon erreicht | hoch | Verhalten unter Event-Dauerlast |
| Monitor kann nur 1024×768, Box rendert 1920×1080 | hoch | ob QR-Codes bei ~67 px noch scannen |
| `xset` gegen Bildschirmschoner unter Wayland | hoch | ob der Monitor über Stunden anbleibt |
| Zwei USB-Ausfälle an einem Vormittag | mittel | ob Umstecken es behebt |
| WLAN-Stick belegt einen Port ohne Funktion | niedrig | — |

---

## Befehle zum Nachschauen

```bash
# Pi
tr -d '\0' < /proc/device-tree/model
vcgencmd measure_temp && vcgencmd get_throttled
free -h && df -h /

# USB
lsusb -t
sudo dmesg -T | grep -iE 'usb|uvc' | tail -20

# Bildschirm
cat /sys/class/drm/card1-HDMI-A-1/modes
grep -a 'Display:' ~/Fotobox/logs/fotobox.log | tail -4

# Kamera — Dienst vorher stoppen, sonst hält der Halte-Prozess das Gerät
sudo systemctl stop fotobox
gphoto2 --summary
gphoto2 --get-config output
sudo systemctl start fotobox

# Capture-Card
v4l2-ctl -d /dev/video0 --all | head -20

# Drucker
lpstat -p && lpstat -d
```
