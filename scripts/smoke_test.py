#!/usr/bin/env python3
"""Hardware-Gegenprüfung für die Fotobox — auf dem Pi ausführen.

    cd ~/Fotobox && venv/bin/python scripts/smoke_test.py

Prüft in einem Durchlauf genau das, was sich auf einer Entwicklungsmaschine
nicht feststellen lässt: Display-Stack, systemd-Verhalten, Bildschirmschoner,
Log-Rotation, Drucker, Hotspot, Kamera, Capture-Card, GPIO.

Bewusst nicht-invasiv: Kamera und Capture-Card werden nur angefasst, wenn der
Fotobox-Dienst gerade NICHT läuft — sonst würde die Prüfung dem laufenden
Betrieb das Gerät wegnehmen. Es wird nichts installiert und nichts geändert.

Exit-Code 0 = keine FEHLER (Warnungen sind erlaubt), 1 = mindestens ein Fehler.
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

GREEN, YELLOW, RED, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = YELLOW = RED = DIM = RESET = ""

_results = {"ok": 0, "warn": 0, "fail": 0, "skip": 0}


def _line(kind, label, detail=""):
    mark = {"ok": f"{GREEN}  OK  {RESET}", "warn": f"{YELLOW} WARN {RESET}",
            "fail": f"{RED} FEHL {RESET}", "skip": f"{DIM} über {RESET}"}[kind]
    _results[kind] += 1
    print(f"{mark} {label}")
    if not detail:
        return
    rows = [r for r in str(detail).strip().splitlines() if r.strip()]
    # Deckeln: ein Python-Traceback wuerde den Bericht sonst unlesbar machen.
    # Bei Ueberlaenge zaehlt das Ende — dort steht die eigentliche Meldung.
    if len(rows) > 9:
        rows = [f"… {len(rows) - 8} Zeilen ausgelassen"] + rows[-8:]
    for row in rows:
        print(f"        {DIM}{row[:150]}{RESET}")


def ok(label, detail=""):   _line("ok", label, detail)
def warn(label, detail=""): _line("warn", label, detail)
def fail(label, detail=""): _line("fail", label, detail)
def skip(label, detail=""): _line("skip", label, detail)


def head(title):
    print(f"\n{title}\n{'─' * len(title)}")


def run(args, timeout=10):
    """Kommando ausführen. Rückgabe: (rc, stdout+stderr). rc=None = nicht da."""
    env = dict(os.environ, PYGAME_HIDE_SUPPORT_PROMPT="1")
    try:
        p = subprocess.run(args, capture_output=True, text=True,
                           timeout=timeout, check=False, env=env)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except FileNotFoundError:
        return None, f"{args[0]} nicht installiert"
    except subprocess.TimeoutExpired:
        return None, f"{args[0]} nach {timeout}s abgebrochen"
    except OSError as exc:
        return None, str(exc)


def service_active(name="fotobox"):
    rc, _ = run(["systemctl", "is-active", "--quiet", name])
    return rc == 0


# ── 1. Display-Stack (P1-5) ────────────────────────────────────────────────────

def check_display():
    head("1. Display-Stack (P1-5)")
    try:
        import display_env
    except ImportError as exc:
        return fail("display_env nicht importierbar", exc)

    env = dict(os.environ)
    env.pop("SDL_VIDEODRIVER", None)          # echte Erkennung, nicht die Vorgabe
    result = display_env.detect(
        environ=env, uid=os.getuid(),
        exists=os.path.exists, listdir=os.listdir,
        platform=sys.platform)
    ok(f"Session erkannt als '{result['session']}'",
       f"Treiber-Reihenfolge: {', '.join(result['drivers'])}\n"
       f"Ergänzt: {result['env'] or 'nichts'}")

    if service_active():
        return skip("Display wirklich öffnen",
                    "fotobox.service läuft und hält den Bildschirm — "
                    "erst 'sudo systemctl stop fotobox', dann erneut prüfen")

    # Der eigentliche Test — bewusst ueber UI._open_display(), also exakt den
    # Weg, den die Box beim Start nimmt (inklusive Treiber-Reihenfolge und
    # SCALED-Entscheidung). Ein eigener set_mode-Aufruf hier wuerde etwas
    # anderes pruefen als das, was spaeter wirklich laeuft.
    code = (
        "import sys; sys.path.insert(0, %r)\n"
        "import pygame; pygame.init()\n"
        "from ui import UI, W, H\n"
        "try:\n"
        "    s = UI._open_display()\n"
        "    print('OK %%dx%%d driver=%%s' %% (s.get_size()[0], s.get_size()[1],\n"
        "                                     pygame.display.get_driver()))\n"
        "except Exception as e:\n"
        "    print('FAIL %%s: %%s' %% (type(e).__name__, e))\n"
    ) % BASE
    rc, out = run([sys.executable, "-c", code], timeout=40)
    out = out.strip()
    m = re.search(r"OK (\d+)x(\d+) driver=(\S+)", out)
    if m:
        w, h, drv = int(m.group(1)), int(m.group(2)), m.group(3)
        ok(f"Vollbild über '{drv}'", f"Zeichenfläche {w}x{h}")
        if (w, h) != (1920, 1080):
            fail(f"Zeichenfläche ist {w}x{h}, nicht 1920x1080",
                 "UI._scaling_flag() haette pygame.SCALED setzen muessen — "
                 "das Layout haengt an den Konstanten W/H und sitzt sonst daneben")
    else:
        fail("Kein SDL-Videotreiber bekommt ein Vollbild", out)


# ── 2. systemd (P0-4) ──────────────────────────────────────────────────────────

def check_systemd():
    head("2. systemd (P0-4)")
    unit = "/etc/systemd/system/fotobox.service"
    if not os.path.isfile(unit):
        return fail("Unit nicht installiert", f"{unit} fehlt — './install.sh' laufen lassen")

    text = open(unit, encoding="utf-8", errors="replace").read()
    for key, want in (("Restart", "on-failure"), ("RuntimeDirectory", "fotobox")):
        m = re.search(rf"^{key}=(.+)$", text, re.M)
        got = m.group(1).strip() if m else None
        if got == want:
            ok(f"{key}={want}")
        else:
            fail(f"{key} ist '{got}', erwartet '{want}'",
                 "Die installierte Unit ist älter als fotobox.service im Repo — "
                 "'./install.sh' erneut laufen lassen")

    rc, out = run(["systemd-analyze", "verify", unit])
    if rc == 0:
        ok("systemd-analyze verify ohne Beanstandung")
    elif rc is None:
        skip("systemd-analyze verify", out)
    else:
        warn("systemd-analyze meldet etwas", out)

    rc, out = run(["systemctl", "is-enabled", "fotobox"])
    (ok if out.strip() == "enabled" else fail)(
        f"Dienst ist '{out.strip() or 'unbekannt'}'",
        "" if out.strip() == "enabled" else "sudo systemctl enable fotobox")

    rc, out = run(["systemctl", "get-default"])
    target = out.strip()
    if target == "graphical.target":
        ok("Boot-Target ist graphical.target")
    else:
        fail(f"Boot-Target ist '{target}'",
             "Die UI braucht eine Desktop-Session:\n"
             "  sudo raspi-config nonint do_boot_behaviour B4\n"
             "  sudo systemctl set-default graphical.target")

    if os.path.isdir("/run/fotobox"):
        ok("/run/fotobox vorhanden", f"beschreibbar: {os.access('/run/fotobox', os.W_OK)}")
    else:
        warn("/run/fotobox fehlt",
             "Entsteht durch RuntimeDirectory beim Dienststart — "
             "harmlos solange der Dienst nicht lief")


# ── 3. Bildschirmschoner (P1-6) ────────────────────────────────────────────────

def check_blanking():
    head("3. Bildschirmschoner (P1-6)")
    autostart = os.path.expanduser("~/.config/autostart/fotobox-no-blank.desktop")
    (ok if os.path.isfile(autostart) else fail)(
        "Autostart-Eintrag", autostart if os.path.isfile(autostart)
        else f"{autostart} fehlt — './install.sh' laufen lassen")

    rc, out = run(["xset", "q"])
    if rc == 0:
        blank = re.search(r"timeout:\s*(\d+)", out)
        dpms = "DPMS is Enabled" in out
        if blank and blank.group(1) == "0" and not dpms:
            ok("xset: Blanking und DPMS aus")
        else:
            warn(f"xset: timeout={blank.group(1) if blank else '?'}, DPMS aktiv={dpms}",
                 "Der Monitor kann mitten im Event schwarz werden. Sofort abstellen:\n"
                 "  xset s off; xset -dpms; xset s noblank")
    else:
        skip("xset nicht verfügbar",
             "Unter Wayland gibt es kein xset — Blanking dort über den "
             "Compositor prüfen (labwc/wayfire) oder im Dauerlauf beobachten")

    cmdline = "/boot/firmware/cmdline.txt"
    if os.path.isfile(cmdline):
        txt = open(cmdline, encoding="utf-8", errors="replace").read()
        (ok if "consoleblank=0" in txt else warn)(
            "consoleblank=0 in cmdline.txt",
            "" if "consoleblank=0" in txt
            else "Konsolen-Blanking bleibt aktiv (nur relevant ohne Desktop-Session)")


# ── 4. Log-Rotation (P1-8) ─────────────────────────────────────────────────────

def check_logrotate():
    head("4. Log-Rotation (P1-8)")
    conf = "/etc/logrotate.d/fotobox"
    if not os.path.isfile(conf):
        return fail("logrotate-Konfiguration fehlt", f"{conf} — './install.sh' laufen lassen")
    ok("Konfiguration installiert", conf)

    rc, out = run(["logrotate", "--debug", conf], timeout=20)
    if rc == 0:
        ok("logrotate --debug ohne Fehler")
    elif rc is None:
        skip("logrotate nicht installiert", out)
    else:
        fail("logrotate lehnt die Konfiguration ab", out)

    for name in ("fotobox.log", "gallery.log"):
        path = os.path.join(BASE, "logs", name)
        if os.path.isfile(path):
            mb = os.path.getsize(path) / 1024 / 1024
            (warn if mb > 50 else ok)(f"{name}: {mb:.1f} MB",
                                      "ungewöhnlich gross" if mb > 50 else "")


# ── 5. Drucker (P1-9) ──────────────────────────────────────────────────────────

def check_printer():
    head("5. Drucker (P1-9)")
    try:
        import config
        import printing
    except ImportError as exc:
        return fail("printing nicht importierbar", exc)

    printers = printing.list_printers()
    if not printers:
        return fail("CUPS kennt keinen Drucker",
                    "install.sh richtet bewusst keinen ein. Anleitung im README "
                    "unter 'Drucker einrichten (Canon Selphy)'.")
    ok(f"{len(printers)} Drucker gefunden",
       "\n".join(f"{p['name']}  [{p['state']}]" for p in printers))

    st = printing.refresh_status(config.cfg)
    (ok if st["available"] else fail)(
        f"Zielgerät: {st['printer'] or '—'}", st["message"])

    rc, out = run(["lpstat", "-o"])
    if rc == 0:
        jobs = [l for l in out.splitlines() if l.strip()]
        (warn if jobs else ok)(
            f"Warteschlange: {len(jobs)} Aufträge",
            "\n".join(jobs[:5]) + ("\n  'cancel -a' leert sie" if jobs else ""))

    if st["available"]:
        print(f"        {DIM}Testdruck: venv/bin/python -c \"import config,printing;"
              f"print(printing.print_photo('<foto.jpg>', config.cfg))\"{RESET}")


# ── 6. Hotspot und Galerie (P0-1, P1-12) ───────────────────────────────────────

def check_network():
    head("6. Hotspot und Galerie (P0-1, P1-12)")
    try:
        import config
    except ImportError as exc:
        return fail("config nicht importierbar", exc)

    (ok if config.cfg.get("hotspot_enabled") else fail)(
        f"hotspot_enabled = {config.cfg.get('hotspot_enabled')}",
        "" if config.cfg.get("hotspot_enabled") else "Ohne Hotspot erreicht kein Gast die Galerie")

    rc, out = run(["nmcli", "-t", "-f", "NAME,DEVICE,STATE", "connection", "show", "--active"])
    if rc is None:
        warn("nmcli nicht verfügbar", out)
    elif "fotobox-hotspot" in out:
        ok("Hotspot-Verbindung aktiv",
           "\n".join(l for l in out.splitlines() if "fotobox" in l))
    else:
        warn("fotobox-hotspot ist nicht aktiv",
             "Normal, solange die Box nicht läuft. Sonst: journalctl -u fotobox | grep -i hotspot")

    ifname = config.cfg.get("hotspot_interface", "wlan0")
    rc, out = run(["ip", "-4", "addr", "show", ifname])
    if rc == 0:
        m = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
        want = config.cfg.get("hotspot_ip", "192.168.4.1")
        if m and m.group(1) == want:
            ok(f"{ifname} hat {want}")
        elif m:
            warn(f"{ifname} hat {m.group(1)}, erwartet {want}",
                 "gallery_url und der Captive-Portal-Redirect zeigen auf die "
                 "erwartete IP — unter der anderen erreicht der Gast nichts")
        else:
            warn(f"{ifname} hat keine IPv4-Adresse")

    # Was der Code in der Sidebar traegt: den Galerie-Link. Er ist der Weg
    # zurueck, nachdem der Gast das Anmeldefenster geschlossen hat.
    link = config.cfg.get("gallery_url", "")
    (ok if link else warn)(
        "QR-Code am Boxschirm trägt den Galerie-Link",
        link or "gallery_url ist leer — dann zeichnet die Sidebar keinen Code")

    captive = "/etc/NetworkManager/dnsmasq-shared.d/captive.conf"
    try:
        with open(captive, encoding="utf-8") as fh:
            conf = fh.read()
    except OSError:
        conf = ""
    if not conf:
        warn("Captive-Portal-DNS", f"{captive} fehlt oder ist leer")
    else:
        ok("Captive-Portal-DNS", captive)
        # Zweiter Weg ins Anmeldefenster: ohne Option 114 haengt alles an
        # den Verbindungstests der Handys — und die schickt ein Geraet
        # nicht mehr, das das Netz schon kennt.
        (ok if "dhcp-option=114" in conf else warn)(
            "Portal-Ansage per DHCP-Option 114 (RFC 8910)",
            next((l for l in conf.splitlines() if "114" in l),
                 "fehlt — Dienst neu starten, hotspot.py schreibt sie beim Start"))

    # Port 80 ohne root: setcap auf der venv-Python
    py = os.path.join(BASE, "venv", "bin", "python")
    real = os.path.realpath(py) if os.path.exists(py) else sys.executable
    rc, out = run(["getcap", real])
    if rc == 0 and "cap_net_bind_service" in out:
        ok("venv-Python darf Port 80 binden", out.strip())
    elif rc is None:
        skip("getcap nicht verfügbar", out)
    else:
        warn("setcap fehlt auf der venv-Python",
             f"{real}\nGalerie fällt auf Port 5000 zurück, das Captive-Portal "
             "funktioniert dann NICHT. './install.sh' erneut laufen lassen.")

    if service_active():
        # Bewusst ueber die IP und nicht ueber gallery_url: mit gesetztem
        # gallery_hostname traegt die einen Namen, und den loest allein der
        # dnsmasq des Hotspots auf. Der Resolver der Box selbst haengt am
        # Uplink und kennt ihn nicht — der Test wuerde fehlschlagen, obwohl
        # fuer die Gaeste alles stimmt.
        url = config.build_gallery_url(
            config.cfg.get("hotspot_ip", "192.168.4.1"),
            config.cfg.get("gallery_port", 80))
        rc, out = run(["curl", "-fsS", "-o", "/dev/null", "-w", "%{http_code}",
                       "--max-time", "5", url])
        (ok if rc == 0 else fail)(f"Galerie antwortet unter {url}", out.strip())
        name = config.cfg.get("gallery_url", "")
        if name and name != url:
            ok(f"Für Gäste zusätzlich unter {name}",
               "Loest nur im Fotobox-WLAN auf (Captive-DNS) — von der Box "
               "aus deshalb nicht pruefbar")


# ── 7. Kamera, Capture-Card, GPIO ──────────────────────────────────────────────

def check_hardware():
    head("7. Kamera, Capture-Card, GPIO")
    busy = service_active()

    rc, out = run(["gphoto2", "--auto-detect"], timeout=20)
    if rc is None:
        fail("gphoto2 nicht installiert", out)
    elif busy:
        skip("Kamera-Erkennung",
             "fotobox.service läuft und hält den USB-Zugriff — "
             "'sudo systemctl stop fotobox' und erneut prüfen")
    else:
        models = [l for l in out.splitlines()[2:] if l.strip()]
        (ok if models else fail)(
            f"gphoto2 erkennt {len(models)} Kamera(s)",
            "\n".join(models) if models else
            "Kamera an? USB-Kabel? Im Menü auf PC-Verbindung gestellt?")

    try:
        import config
        dev = config.cfg.get("capture_device", 0)
    except ImportError:
        dev = 0
    if busy:
        skip("Capture-Card", "Dienst läuft und hält /dev/video*")
    else:
        code = (f"import cv2,sys;c=cv2.VideoCapture({dev});"
                "r,f=c.read();c.release();"
                "print('OK %dx%d'%(f.shape[1],f.shape[0]) if r and f is not None else 'KEIN BILD')")
        rc, out = run([sys.executable, "-c", code], timeout=25)
        (ok if "OK" in out else fail)(
            f"Capture-Card (Index {dev})", out.strip() or "kein Signal")

    if busy:
        skip("GPIO", "Dienst läuft und belegt die Pins")
    else:
        # Warnungen ausblenden: gpiozero meldet auf Nicht-Pi-Systemen vier
        # PinFactory-Fallbacks, bevor es scheitert — das ist kein Befund.
        code = ("import warnings; warnings.filterwarnings('ignore')\n"
                "try:\n"
                "    from gpiozero import Button\n"
                "    b=[Button(p,pull_up=True) for p in (17,27,22)]\n"
                "    print('OK Pins ' + ', '.join(str(x.pin) for x in b))\n"
                "except Exception as e:\n"
                "    print('%s: %s' % (type(e).__name__, e))\n")
        rc, out = run([sys.executable, "-c", code], timeout=15)
        line = out.strip().splitlines()[-1] if out.strip() else "keine Ausgabe"
        (ok if line.startswith("OK") else warn)(
            "GPIO-Buttons", line if not line.startswith("OK") else line[3:])


# ── 8. Konfiguration und Speicher ──────────────────────────────────────────────

def check_config():
    head("8. Konfiguration und Speicher")
    try:
        import config
        import disk_monitor
    except ImportError as exc:
        return fail("Module nicht importierbar", exc)

    # Werte aus config._DEFAULTS statt einer zweiten Kopie — sonst prueft der
    # Smoke-Test nach einer Default-Aenderung gegen Werte, die es nicht gibt.
    shipped = {k: config.default_value(k)
               for k in ("admin_pin", "host_pin", "wifi_password")}
    still = [k for k, v in shipped.items() if config.cfg.get(k) == v]
    (warn if still else ok)(
        "Auslieferungs-PINs", ", ".join(still) + " noch auf Standard — im "
        "Admin-Panel ändern" if still else "alle geändert")

    pw = config.cfg.get("wifi_password", "")
    (ok if 8 <= len(pw) <= 63 else fail)(
        f"WLAN-Passwort ({len(pw)} Zeichen)",
        "" if 8 <= len(pw) <= 63 else "WPA2 verlangt 8–63 — der Hotspot startet sonst nicht")

    free = disk_monitor.get_free_mb(BASE)
    block = config.cfg.get("disk_block_mb", 150)
    warn_mb = config.cfg.get("disk_warn_mb", 500)
    if free < 0:
        fail("Freier Speicher nicht ermittelbar")
    elif free < block:
        fail(f"Nur {free} MB frei", f"unter disk_block_mb ({block}) — Aufnahme ist gesperrt")
    elif free < warn_mb:
        warn(f"{free} MB frei", f"unter disk_warn_mb ({warn_mb})")
    else:
        ok(f"{free / 1024:.1f} GB frei")

    if shutil.which("git"):
        rc, out = run(["git", "-C", BASE, "status", "--porcelain"])
        if rc == 0:
            dirty = [l for l in out.splitlines() if l.strip()]
            (warn if dirty else ok)(
                "Arbeitsbaum", f"{len(dirty)} geänderte Dateien" if dirty else "sauber")


# ── 9. Abhängigkeiten (P1-15) ──────────────────────────────────────────────────

def check_deps():
    head("9. Abhängigkeiten (P1-15)")
    lock = os.path.join(BASE, "requirements.pi.txt")
    if os.path.isfile(lock):
        ok("requirements.pi.txt vorhanden", lock)
    else:
        warn("Kein Lockfile für den Pi",
             "Einmalig erzeugen und committen, dann ist der Event-Tag reproduzierbar:\n"
             "  venv/bin/pip freeze > requirements.pi.txt")

    rc, out = run([os.path.join(BASE, "venv", "bin", "pip"), "list", "--format=freeze"])
    if rc == 0:
        want = ("flask", "pygame", "opencv-python", "pillow", "waitress", "qrcode", "gpiozero")
        found = {l.split("==")[0].lower(): l.strip() for l in out.splitlines() if "==" in l}
        missing = [p for p in want if p not in found]
        (fail if missing else ok)(
            "Python-Pakete",
            f"fehlen: {', '.join(missing)}" if missing else
            "\n".join(found[p] for p in want if p in found))


def main():
    print(f"Fotobox — Hardware-Gegenprüfung\n{DIM}{BASE}{RESET}")
    if service_active():
        print(f"{YELLOW}Hinweis: fotobox.service läuft. Prüfungen, die Kamera, "
              f"Capture-Card, GPIO oder Bildschirm exklusiv brauchen, werden "
              f"übersprungen.\nFür den vollen Durchlauf: sudo systemctl stop fotobox"
              f"{RESET}")

    for check in (check_display, check_systemd, check_blanking, check_logrotate,
                  check_printer, check_network, check_hardware, check_config,
                  check_deps):
        try:
            check()
        except Exception as exc:                      # noqa: BLE001
            fail(f"{check.__name__} abgebrochen", f"{type(exc).__name__}: {exc}")

    r = _results
    print(f"\n{'═' * 52}")
    print(f"  {GREEN}{r['ok']} ok{RESET} · {YELLOW}{r['warn']} Warnungen{RESET} · "
          f"{RED}{r['fail']} Fehler{RESET} · {DIM}{r['skip']} übersprungen{RESET}")
    if r["fail"]:
        print(f"\n{RED}Nicht einsatzbereit — die Fehler oben abarbeiten.{RESET}")
    elif r["warn"]:
        print(f"\n{YELLOW}Einsatzbereit, aber die Warnungen vor dem Event ansehen.{RESET}")
    else:
        print(f"\n{GREEN}Alles grün.{RESET}")
    return 1 if r["fail"] else 0


if __name__ == "__main__":
    sys.exit(main())
