# Fotobox — Roadmap bis zum Event (Mitte Oktober 2026)

**Ziel:** Die Fotobox ist Mitte Oktober 2026 einsatzbereit — Kaltstart ohne Tastatur,
Gäste erreichen die Galerie per QR-Code, Drucken funktioniert sichtbar, und ein
Absturz beendet nicht den Abend.

**Stand:** Letzter Commit 09.05.2026, danach 3,5 Monate Pause. Das Projekt endete
mitten im Refactoring `6bff061` (Owner-Defaults vs. Mieter-Felder) — dabei ist ein
Blocker entstanden, der die Galerie für Gäste unerreichbar macht (P0-1).

**Rahmen:** Nur eigene Events bis Oktober (keine Vermietung an Dritte) · Drucker
Canon Selphy, 10×15 · Hardware ab Ende August wieder verfügbar · harter Termin.

**Fortschritt:** 6 / 22 erledigt (P0: 4/4 ✅ · P1: 2/11 · P2: 0/7) — P3 zählt nicht mit.
Stand 22.08.2026: P0-Block komplett, dazu P1-13 und P1-14. P1-15 teilweise.

---

## Zeitplan

| Zeitraum | Fokus | Abschlusskriterium |
|---|---|---|
| ~~**22.–30. Aug**~~ ✅ | P0 komplett + P1-13, P1-14, P1-15 (alles ohne Hardware) | erledigt 22.08. — Blocker gefixt, `tsc -b` grün, Routen getestet |
| **31. Aug – 6. Sep** | Hardware-Smoke-Test des Ist-Zustands, **dann** P1-5, P1-6, P1-7 | Box startet nach Reboot allein und bleibt an |
| **7.–20. Sep** | Drucken (P1-9), Capture-Robustheit (P1-10), Rollover (P1-11) | 10 Drucke am Stück, Kamera-Fehler sichtbar |
| **21.–27. Sep** | Betriebs-Härtung: P1-8, P1-12 + P2-17, P2-18, P2-19 | Ein Abend Dauerlauf ohne Eingriff |
| **28. Sep – 4. Okt** | Rest P2, Doku, Tests ausbauen | README stimmt mit Code überein |
| **5.–11. Okt** | **Generalprobe** — voller Aufbau, mind. 2 h, echte Gäste-Handys | Abnahme-Checkliste unten vollständig |
| **12. Okt – Event** | **Feature-Freeze.** Nur noch Bugfixes aus der Generalprobe | Packliste abgehakt |

> Die Generalprobe liegt bewusst **eine volle Woche vor dem Event**, damit
> gefundene Probleme noch reparierbar sind. Danach kommt kein neues Feature mehr rein.

---

## P0 — Blocker

Ohne diese vier läuft das Event nicht. Alle hardware-unabhängig, also sofort machbar.

- [x] **1. Hotspot wieder aktivierbar machen** — `config.py:42`, `config.py:16-26`, `gallery_server.py:966,1001`
      `hotspot_enabled` steht hartkodiert auf `False` **und** fehlt in `_MIETER_FIELDS`
      — es lässt sich über keinen Weg mehr einschalten, auch nicht per `config.json`.
      Folge: Der Gallery-Server bindet auf `127.0.0.1`, kein Gast-Handy erreicht ihn,
      und der QR-Code auf dem Boxschirm (`ui.py:228`) zeigt ins Leere.
      *Fix:* Default auf `True`; Bind-Entscheidung aus dem tatsächlich gewünschten
      Hotspot-Zustand ableiten, damit `--no-hotspot` (`main.py:162`) und `dev_server.py`
      weiterhin auf `127.0.0.1` bleiben. Tote Keys (`hotspot_enabled`, `hotspot_ip`,
      `hotspot_interface`, `gallery_port`) aus `config.json.example` entfernen —
      Achtung: `install.sh:123` liest `hotspot_ip` noch von dort.

- [x] **2. SPA-Fallback für `/event/<folder>`** — `gallery_server.py`
      Der React-Router kennt die Route (`frontend/src/App.tsx:22`), Flask nicht:
      es gibt nur `/`, `/photo/...`, `/admin/...` und keinen 404-Catch-all.
      Reload oder geteilter Link → nacktes Flask-404.
      *Fix:* Eigene Route oder `@app.errorhandler(404)`, der `index.html` ausliefert.
      Betrifft auch `PhotoView.tsx:70`, das nach dem Löschen des letzten Fotos
      genau dorthin navigiert.

- [x] **3. Lightbox löscht das falsche Foto** — `frontend/src/pages/PhotoView.tsx:44-65`
      `current` hängt an `startIndex` → `useParams().filename`, aber `onSlideChange`
      macht nur `window.history.replaceState`, was react-router nie beobachtet.
      Der Gast wischt zu Foto 7, tippt „Löschen" — weg ist Foto 1. Gleiches gilt
      für „Speichern" und den Zähler „1 / N" im Header.
      *Fix:* `current` an einen `activeIndex`-State hängen statt an den URL-Parameter.

- [x] **4. systemd härten** — `fotobox.service:8`
      `Restart=no` — jeder unbehandelte Crash, jeder OOM-Kill lässt die Box für den
      Rest des Abends tot liegen und verlangt SSH.
      *Fix:* `Restart=on-failure` + `RestartSec`, dazu `RuntimeDirectory=fotobox`,
      damit `/run/fotobox` den Reboot übersteht statt nur zufällig von
      `scripts/usb_export.py` als root neu angelegt zu werden.

---

## P1 — Muss vor dem Event

- [ ] **5. Display-Stack klären: X11 oder Wayland** — `fotobox.service:11`, `install.sh`
      Die Unit setzt `DISPLAY=:0`. Bookworm startet auf Pi 4/5 je nach Version einen
      Wayland-Compositor — dann findet SDL kein X11 und die Box bleibt schwarz.
      **Muss auf der echten Hardware verifiziert werden**, ggf. `SDL_VIDEODRIVER`
      setzen oder X11 erzwingen.
      *Höchstes Risiko im Plan* — wird erst beim ersten Hardware-Test sichtbar,
      deshalb steht der Smoke-Test bewusst gleich am Anfang der Hardware-Phase.

- [ ] **6. Bildschirmschoner / DPMS deaktivieren** — `install.sh`
      Nichts im Repo verhindert, dass der Monitor nach ~10 Minuten mitten im Event
      schwarz wird.

- [ ] **7. Autologin / Boot-Target sicherstellen** — `install.sh`
      Die Unit hängt an `graphical.target`, aber der Installer prüft nirgends, ob
      der Pi überhaupt grafisch bootet. Bootet er in die CLI, ist der Service
      aktiviert, die X-Session die er braucht existiert aber nie.

- [ ] **8. Log-Rotation** — `fotobox.service:14-15`, `gallery_server.py:1006`
      Beide Logs wachsen unbegrenzt (`StandardOutput=append:` bzw. ein
      `FileHandler` auf `logs/gallery.log`). logrotate-Config oder Rotation im Code.

- [ ] **9. Drucken fertigbauen (Canon Selphy, 10×15)** — `main.py:70-77`, `ui.py:830`, `config.py`, Admin-UI
      Aktuell ein nacktes `subprocess.Popen(["lp", path])`: kein Zielgerät, kein
      Papierformat, kein Layout, **kein sichtbares Feedback**. Der Gast drückt E,
      nichts passiert, die einzige Spur ist eine Zeile im Log. `install.sh` installiert
      CUPS und setzt `lpadmin`, richtet aber **nie einen Drucker ein** — ab Werk
      scheitert `lp` mit „no default destination".
      *Umfang:* Drucker + Papierformat + Kopien in `_DEFAULTS` und Admin-Panel ·
      10×15 randlos via Gutenprint · „Druckt…"/Fehler-Overlay auf dem Boxschirm ·
      Button ausblenden wenn CUPS kein Ziel kennt · `Popen` einsammeln (aktuell
      ein Zombie-Prozess pro Druck) · Selphy-Einrichtung im README dokumentieren.

- [ ] **10. Capture-Fehler sichtbar machen** — `main.py:52-58`, `main.py:288`
      Countdown läuft, Blitz feuert, gphoto2 scheitert — der Gast sieht **nichts**.
      Das Fehlerbanner (`ui.py:706`) erscheint nur wenn `camera.available` false ist.
      Zusätzlich: `main.py:59` wartet bis zu 35 s, während die Render-Schleife steht →
      eingefrorener „Lächeln!"-Frame ohne jede Rückmeldung.

- [ ] **11. Event-Ordner-Rollover um Mitternacht** — `events.py:28-31`
      `current_event_folder` leitet den Ordner aus `datetime.now()` ab. Ein Event
      von 20:00 bis 02:00 wird um 00:00 still auf zwei Ordner aufgeteilt: zwei
      Einträge in der Galerie, der ZIP-Download zieht nur eine Hälfte, `max_photos`
      gilt doppelt. Dasselbe passiert beim Ändern von `event_name` mitten im Event.
      *Fix:* Ordner beim Start einfrieren oder explizite Admin-Aktion „Neues Event starten".

- [ ] **12. WLAN-Änderung im Admin greift nicht** — `frontend/src/pages/admin/AdminWifi.tsx:40`, `gallery_server.py:753-757`
      Das Speichern schreibt SSID/Passwort in die Config, startet den Hotspot aber
      nie neu. Der Boxschirm zeigt binnen einer Sekunde die neue SSID (`ui.py`
      lädt die Config laufend nach), der AP sendet weiter die alte — die angezeigten
      Zugangsdaten sind schlicht falsch und niemand kommt rein.
      *Nebenbei:* Der Server nimmt jedes Passwort an, auch dreistellige; die
      Client-Prüfung (`AdminWifi.tsx:98`) lässt sich per direktem POST umgehen und
      `hotspot.py:220` verweigert dann beim nächsten Boot den Start.

- [x] **13. Google Fonts selbst hosten** — `frontend/index.html:19-24`
      Der Hotspot hat kein Internet, und dnsmasq leitet `fonts.googleapis.com` auf
      den Pi um — das „Stylesheet" ist in Wahrheit ein 302 auf die Galerie. Die
      Schrift fällt auf jedem Gast-Handy auf `system-ui` zurück.

- [x] **14. Preview beim Löschen mitentfernen** — `gallery_server.py:544-550`
      Foto und Thumbnail werden gelöscht, die 1280px-Preview nicht. `/preview/...`
      liefert das „gelöschte" Foto unbegrenzt weiter aus — und genau diese URL
      rendert `PhotoView.tsx:229`.

- [ ] **15. `requirements.txt` pinnen** — *teilweise erledigt (22.08.)*
      ~~Sieben Pakete, null Versionen.~~ Alle sieben sind jetzt per `~=` auf die
      Minor-Version gepinnt, ein `install.sh` zieht also keinen neuen Major/Minor
      mehr. **Offen:** exakte Pins gibt es bewusst noch nicht, weil die
      Dev-Maschine (macOS/x86, py3.9) und das Pi (Linux/ARM, py3.11+)
      unterschiedliche Wheels brauchen. In der Hardware-Phase auf dem Pi einmal
      `venv/bin/pip freeze > requirements.pi.txt` laufen lassen und committen —
      erst dann ist der Event-Tag wirklich reproduzierbar.

---

## P2 — Sollte

- [ ] **16. Minimal-Testsuite (pytest)**
      Es gibt aktuell **keinen einzigen Test** und keine CI. Zuerst die Funktionen,
      die still Daten zerstören oder Sicherheitsgrenzen ziehen:
      `events.is_safe_event` und `gallery_server._safe_filename/_safe_path`
      (Path-Traversal-Guards) · `config.load_config`/`save_config`-Roundtrip
      (genau dort sitzt P0-1) · `disk_monitor.enforce_photo_max_age` und
      `enforce_max_photos` (löschen Nutzerdaten) · `collage.make_collage`.

- [ ] **17. Galerie auf aktives Event beschränken** — `gallery_server.py:474,485,440`
      `/api/events` und `/api/photos` liefern alles auf der Platte, und
      `/api/download-zip` zippt jedes fremde Event — die einzige Prüfung ist
      `is_safe_event` (Traversal), nicht Zugehörigkeit. Bei eigenen Events
      entschärft, aber Gäste sehen trotzdem die Fotos der letzten Feier.

- [ ] **18. Disk-Full-Handling** — `config.py:77`, `ui.py:695`
      `disk_warn_mb` färbt nur Text gelb. Keine Aufnahme-Verweigerung, kein Alarm.
      Bei voller Karte scheitert gphoto2 — still, siehe P1-10.

- [ ] **19. README + `config.json.example` synchronisieren** — nachgezählt, nicht geschätzt
      Die Config-Tabelle im README dokumentiert **15 von 30** Keys aus `_DEFAULTS`;
      es fehlen u.a. `theme`, `actions`, `gpio_pins`, `host_pin`, `subtitle`,
      `photo_max_age_days`, `live_view_rect`. Dazu steht `idle_timeout` mit `60`
      drin (`README.md:65`), tatsächlich ist der Default `0` (`config.py:39`,
      Slideshow aus), und `README.md:121` empfiehlt `hotspot_enabled: true` in der
      `config.json` — genau der Weg, den P0-1 unmöglich gemacht hat.
      `config.json.example` ist schlimmer: **18 von 26** Keys werden von
      `save_config` beim ersten Admin-Speichern kommentarlos verworfen, weil sie
      nicht in `_MIETER_FIELDS` stehen. Einziges echtes Mieter-Feld, das im
      Beispiel fehlt: `host_pin`.

- [ ] **20. Fetch-Timeouts im Frontend** — `frontend/src/api.ts`
      Kein einziger Timeout. Auf einem ausgelasteten 2,4-GHz-AP (`hotspot.py:150`
      pinnt Band bg / Kanal 6) hängt der Spinner endlos. Dazu: 8-Sekunden-Polling
      pro Handy, jeder Request ein voller `os.listdir` + `getmtime`.

- [ ] **21. Default-PINs sichtbar machen** — `config.py:37-38`, `config.py:30`
      `admin_pin: 1234`, `host_pin: 0000`, `wifi_password: fotobox123`. Bei eigenen
      Events kein Drama, aber ein Warnbanner im Admin-Panel solange die Defaults
      aktiv sind kostet fast nichts. Der Admin-PIN gibt „alle Fotos löschen" frei.

- [ ] **22. Toter Code raus**
      `gallery_server.py:214` `_PORTAL_PATHS` (definiert, nie referenziert) ·
      `usb_status.py:26` `is_active` (nie aufgerufen) · getracktes
      `__pycache__/fotobox.cpython-313.pyc` aus einem Modul, das es nicht mehr gibt.

---

## P3 — Bewusst nach Oktober geparkt

Nicht vergessen, nur nicht jetzt. Keiner dieser Punkte gefährdet das Event.

- [ ] **Box-UI als App bauen — pygame durch eine Web-Oberfläche ersetzen** —
      `ui.py` (1407 Zeilen), `main.py:222,383`, `camera.py`
      Das Projekt pflegt heute drei UI-Welten: pygame auf dem Boxschirm, React
      für die Galerie, React fürs Admin-Panel. Theme und Branding stehen
      deshalb doppelt — als Konstanten in `ui.py:16,33-40` und als MUI-Theme in
      `frontend/src/theme.ts`; jede Farbänderung will an zwei Stellen gepflegt
      werden. Eine React-Codebasis für alle drei Oberflächen führt das
      zusammen: Kiosk-Browser oder Tauri gegen den ohnehin laufenden
      Flask-Server. `main.py`, `camera.py` und `hardware.py` (gphoto2, GPIO)
      bleiben Python — es wechselt nur die Darstellungsschicht.
      *Offene Machbarkeitsfrage, vorab als Prototyp klären:* Der Live-View
      kommt als `cv2.VideoCapture`-Frame von der Capture-Card und wird direkt in
      die pygame-Surface geblittet (`ui.py:355-382`, laut Kommentar ~1 ms/Frame
      auf Pi 4B, Schleife mit 30 fps in `main.py:383`). Im Browser bräuchte es
      MJPEG oder WebRTC — mehr Latenz und mehr CPU auf demselben Pi, der
      nebenher gphoto2 und den Gallery-Server fährt. Schafft der Prototyp keine
      flüssige Vorschau, ist der Punkt erledigt und pygame bleibt.
      *Nicht vor dem Event:* `ui.py` ist der ausgereifteste Teil des Projekts,
      ein Rewrite hätte keine Generalprobe mehr.
      *Ersetzt den Punkt „Auflösungsunabhängiges pygame-Layout" weiter unten* —
      nicht in beides investieren.

- [ ] Service Worker / echtes PWA-Offline-Verhalten (Manifest existiert, SW nicht)
- [ ] Automatisches Backup (rsync/NAS) — aktuell nur der manuelle USB-Stick,
      kombiniert mit `photo_max_age_days: 7` Auto-Löschung
- [ ] Echte Mieter-Trennung + PIN-Zwangswechsel — erst relevant bei Vermietung
- [ ] Auflösungsunabhängiges pygame-Layout — 1920×1080 fest verdrahtet (`ui.py:16,33-40`);
      entfällt, falls die Web-Oberfläche oben kommt
- [ ] CSRF-Tokens auf den Admin-Endpunkten

---

## Generalprobe — Abnahme-Checkliste (5.–11. Okt)

Voller Aufbau wie am Event-Tag. Erst wenn hier alles hakt, gilt die Box als fertig.

- [ ] Kompletter Aufbau: Pi, Kamera, Capture-Card, Buttons, Monitor, Drucker
- [ ] Kaltstart — Box läuft ohne Tastatur und ohne SSH hoch
- [ ] 5+ Handys gleichzeitig im Hotspot
- [ ] QR-Code scannen → Galerie lädt, Schrift stimmt (Test für P1-13)
- [ ] Deep-Link auf ein Event teilen und neu laden (Test für P0-2)
- [ ] Einzelfoto und Collage auslösen
- [ ] 20 Drucke am Stück
- [ ] Foto in der Lightbox löschen — es verschwindet **das sichtbare** (Test für P0-3)
- [ ] Gelöschtes Foto ist auch über `/preview/...` weg (Test für P1-14)
- [ ] USB-Stick-Export inkl. Fortschritts-Overlay
- [ ] Stecker ziehen und wieder rein — Box kommt allein zurück (Test für P0-4)
- [ ] 2 h Dauerlauf **über Mitternacht hinweg** (Test für P1-11)
- [ ] Monitor bleibt an, kein Blanking (Test für P1-6)
- [ ] Speicher-Warnung provozieren
- [ ] Kamera im laufenden Betrieb ab- und wieder anstecken

---

## Packliste Event-Tag

- [ ] Pi + Netzteil (+ Ersatz-Netzteil)
- [ ] Kamera + geladener Akku + Ersatzakku + Netzteil/Dummy-Akku
- [ ] Capture-Card + HDMI-Kabel (+ Ersatz)
- [ ] Monitor + Netzteil
- [ ] Drucker + Papier/Farbband für mind. 2× erwartete Menge
- [ ] USB-Stick für den Export
- [ ] Tastatur (Notfall-Bedienung)
- [ ] Laptop mit SSH-Zugang + Zugangsdaten
- [ ] Mehrfachsteckdose + Verlängerung
- [ ] Kabelbinder / Gaffa

---

## Pflegehinweis

- Punkte werden **abgehakt, nicht gelöscht** — der Verlauf ist Teil des Dokuments.
- Neue Funde kommen mit derselben Struktur dazu: *was*, *wo* (Datei:Zeile), *warum*.
  Die „warum"-Zeile ist der eigentliche Wert — in vier Wochen weißt du sonst nicht mehr,
  worum es ging.
- Nummern bleiben stabil, damit Commit-Messages darauf verweisen können (`P1-9`).
- Den Fortschrittszähler oben beim Abhaken mitziehen.
- Ab dem 12. Oktober gilt Feature-Freeze: alles Neue wandert nach P3, egal wie klein.
