"""WLAN-Hotspot über NetworkManager.

Wir konfigurieren die Connection explizit (band=bg, channel=6,
ipv4.method=shared mit fester IP) statt 'nmcli device wifi hotspot'
zu nutzen — dadurch ist DHCP, IP-Range und Frequenz vorhersagbar.
"""
import logging
import subprocess
import sys
from typing import Optional

import config

logger = logging.getLogger(__name__)

CONN_NAME = "fotobox-hotspot"
CAPTIVE_CONF_PATH = "/etc/NetworkManager/dnsmasq-shared.d/captive.conf"


def _write_captive_conf(ip: str) -> str:
    """Schreibt captive.conf so dass dnsmasq alle DNS-Anfragen auf die
    übergebene IP umleitet (Captive-Portal-DNS-Hijack).

    Bevorzugt direktes Schreiben (install.sh chownt die Datei dem
    Service-User). Fällt das wegen fehlender Rechte fehl, wird via
    'sudo -n tee' nachversucht (NOPASSWD-Regel aus install.sh).

    Rückgabe:
      "changed"   — Datei neu geschrieben, dnsmasq muss neu gestartet werden
      "unchanged" — Datei hatte bereits den gewünschten Inhalt
      "failed"    — Write fehlgeschlagen (kein Schreibrecht trotz Fallback)
    """
    content = (
        "# Fotobox Captive-Portal: alle DNS-Anfragen auf Hotspot-IP umleiten\n"
        "# Wird zur Laufzeit von hotspot.py geschrieben.\n"
        f"address=/#/{ip}\n"
    )
    try:
        with open(CAPTIVE_CONF_PATH, "r", encoding="utf-8") as f:
            if f.read() == content:
                return "unchanged"
    except OSError:
        pass  # existiert nicht / nicht lesbar → einfach schreiben

    # Direktschreiben (chown-Variante)
    try:
        with open(CAPTIVE_CONF_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        logger.info("Captive-DNS auf %s gesetzt", ip)
        return "changed"
    except PermissionError:
        pass  # → sudo-Fallback
    except OSError as exc:
        logger.warning("Captive-DNS-Config (%s) Schreibfehler: %s",
                       CAPTIVE_CONF_PATH, exc)
        return "failed"

    # sudo-Fallback (NOPASSWD-tee aus install.sh)
    try:
        proc = subprocess.run(
            ["sudo", "-n", "tee", CAPTIVE_CONF_PATH],
            input=content, text=True, capture_output=True, timeout=5,
        )
        if proc.returncode == 0:
            logger.info("Captive-DNS auf %s gesetzt (via sudo-Fallback)", ip)
            return "changed"
        logger.warning(
            "Captive-DNS sudo-tee fehlgeschlagen (rc=%d): %s "
            "— install.sh ggf. neu laufen lassen",
            proc.returncode, proc.stderr.strip()[:200])
        return "failed"
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.SubprocessError) as exc:
        logger.warning("Captive-DNS sudo-Fallback nicht verfügbar: %s", exc)
        return "failed"


def _nmcli(args: list, timeout: int = 10, check: bool = False):
    """nmcli mit Timeout, gibt CompletedProcess zurück oder None bei Fehler."""
    try:
        return subprocess.run(
            ["nmcli"] + args,
            capture_output=True, text=True, timeout=timeout, check=check,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired,
            subprocess.CalledProcessError) as exc:
        logger.warning("nmcli %s fehlgeschlagen: %s", args[0] if args else "?", exc)
        return None


def _interface_exists(ifname: str) -> bool:
    r = _nmcli(["-t", "-f", "DEVICE,TYPE", "device"], timeout=5)
    if r is None or r.returncode != 0:
        return False
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[0] == ifname and parts[1] == "wifi":
            return True
    return False


def _free_interface(ifname: str) -> None:
    """Trennt aktive WLAN-Client-Verbindungen auf ifname, damit der Hotspot
    nicht von einem auto-reconnectenden Heim-WLAN verdrängt wird."""
    r = _nmcli(["-t", "-f", "NAME,DEVICE,TYPE", "connection", "show", "--active"],
               timeout=5)
    if r is None or r.returncode != 0:
        return
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) < 3:
            continue
        name, device, ctype = parts[0], parts[1], parts[2]
        if device != ifname or ctype != "802-11-wireless" or name == CONN_NAME:
            continue
        logger.info("Hotspot: trenne konkurrierende Verbindung '%s' auf %s",
                    name, ifname)
        _nmcli(["connection", "down", name], timeout=10)


def _delete_existing() -> None:
    """Alte fotobox-hotspot-Connection entfernen damit ein frischer Build
    nicht von kaputten Altsettings gestört wird."""
    _nmcli(["connection", "delete", CONN_NAME], timeout=10)


def _build_connection(ifname: str, ssid: str, password: str,
                      hotspot_ip: str) -> bool:
    """Erstellt die fotobox-hotspot-Connection mit expliziten Settings."""
    # Aus 192.168.4.1 wird 192.168.4.1/24 für den ipv4.addresses-Wert
    ipv4_addr = f"{hotspot_ip}/24"

    # Schritt 1: Connection anlegen
    r = _nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", ifname,
        "con-name", CONN_NAME,
        "autoconnect", "no",
        "ssid", ssid,
    ], timeout=10)
    if r is None or r.returncode != 0:
        logger.warning("Hotspot-Add fehlgeschlagen: %s",
                       (r.stderr if r else "no result").strip()[:200])
        return False

    # Schritt 2: AP-Mode + 2.4 GHz + Channel 6 + WPA2 + DHCP-Share
    r = _nmcli([
        "connection", "modify", CONN_NAME,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless.channel", "6",
        "ipv4.method", "shared",
        "ipv4.addresses", ipv4_addr,
        "ipv6.method", "ignore",
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.proto", "rsn",
        "wifi-sec.pairwise", "ccmp",
        "wifi-sec.group", "ccmp",
        "wifi-sec.psk", password,
    ], timeout=10)
    if r is None or r.returncode != 0:
        logger.warning("Hotspot-Modify fehlgeschlagen: %s",
                       (r.stderr if r else "no result").strip()[:200])
        return False

    return True


def stop() -> None:
    """Beendet den Hotspot."""
    _nmcli(["connection", "down", CONN_NAME], timeout=10)
    logger.info("Hotspot beendet")


def _read_interface_ip(ifname: str, retries: int = 20,
                       delay_s: float = 0.5) -> Optional[str]:
    """Liest die tatsächlich zugewiesene IPv4-Adresse aus dem Interface.

    NetworkManager weist die IP nach 'connection up' asynchron zu — ggf.
    erst 1-2 Sekunden später, auf langsamen Pis bis ~10 s. Wir retryen
    deshalb großzügig (Default: bis zu 10 Sekunden warten) bevor wir
    aufgeben.
    """
    import time
    for _ in range(max(1, retries)):
        try:
            result = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", "dev", ifname],
                capture_output=True, text=True, timeout=5,
            )
        except Exception:
            time.sleep(delay_s)
            continue
        if result.returncode == 0:
            # Output: "4: wlan1    inet 10.42.0.1/24 brd 10.42.0.255 ..."
            for token in result.stdout.split():
                if "/" in token and token.startswith(("10.", "192.168.", "172.")):
                    return token.split("/")[0]
        time.sleep(delay_s)
    return None


def start() -> bool:
    if sys.platform != "linux":
        logger.warning("Hotspot: nur auf Linux verfügbar (Plattform: %s)", sys.platform)
        return False

    cfg = config.cfg
    ssid = cfg["wifi_ssid"]
    password = cfg["wifi_password"]
    ifname = cfg.get("hotspot_interface", "wlan0")
    hotspot_ip = cfg.get("hotspot_ip", "192.168.4.1")

    if len(password) < 8:
        logger.warning("Hotspot: WPA2 verlangt min. 8 Zeichen Passwort — abgebrochen")
        return False

    if not _interface_exists(ifname):
        logger.warning(
            "Hotspot-Interface '%s' nicht gefunden — Hotspot wird nicht gestartet",
            ifname)
        return False

    _free_interface(ifname)
    _delete_existing()

    if not _build_connection(ifname, ssid, password, hotspot_ip):
        _delete_existing()
        return False

    # Schritt 3: Connection starten
    # captive.conf NICHT vor dem Up neu schreiben — sonst kollidiert das
    # mit dem Post-Up-Write (siehe unten) und jeder Service-Restart
    # triggert einen down/up-Cycle. dnsmasq nutzt für diese Up-Phase die
    # captive.conf aus dem letzten Lauf (oder install.sh beim 1. Boot),
    # was praktisch immer schon die richtige IP enthält.
    r = _nmcli(["connection", "up", CONN_NAME], timeout=20)
    if r is None or r.returncode != 0:
        err = (r.stderr if r else "no result").strip()[:200]
        logger.warning("Hotspot-Up fehlgeschlagen (%s): %s", ifname, err)
        return False

    # Echte IP aus dem Interface auslesen — kann sich von hotspot_ip
    # unterscheiden weil NetworkManager im 'shared mode' standardmäßig
    # 10.42.0.1/24 zuweist und unser ipv4.addresses ignoriert.
    actual_ip = _read_interface_ip(ifname)
    if actual_ip:
        if actual_ip != hotspot_ip:
            logger.info(
                "Hotspot: NetworkManager nutzt %s (config wollte %s)",
                actual_ip, hotspot_ip)
        # captive.conf nur dann (re)schreiben + neustarten, wenn der
        # Inhalt tatsächlich abweicht — das passiert i.d.R. nur beim
        # 1. Boot nach Install oder bei IP-Wechsel. Subsequent Service-
        # Restarts treffen "unchanged" und triggern keinen Reload.
        write_state = _write_captive_conf(actual_ip)
        if write_state == "changed":
            logger.info("Captive-DNS angepasst — Hotspot wird kurz neu "
                        "gestartet damit dnsmasq die neue IP einliest")
            _nmcli(["connection", "down", CONN_NAME], timeout=10)
            # Up-Retry: NetworkManager kann nach einem schnellen down/up
            # kurz busy sein und den ersten Versuch ablehnen. Wir geben
            # bis zu 3 Versuche, sonst bleibt der Hotspot tot.
            up_ok = False
            import time
            for attempt in range(3):
                r = _nmcli(["connection", "up", CONN_NAME], timeout=20)
                if r is not None and r.returncode == 0:
                    up_ok = True
                    break
                logger.warning(
                    "Hotspot-Reload Versuch %d/3 fehlgeschlagen: %s",
                    attempt + 1, (r.stderr if r else "no result").strip()[:200])
                if attempt < 2:
                    time.sleep(1)
            if not up_ok:
                logger.error(
                    "Hotspot konnte nach Captive-DNS-Update NICHT neu "
                    "gestartet werden — manueller Eingriff: "
                    "'sudo nmcli connection up %s'", CONN_NAME)
        config.cfg["hotspot_ip"] = actual_ip
        config.cfg["gallery_url"] = config.build_gallery_url(
            actual_ip, config.cfg.get("gallery_port", 80))
    else:
        logger.warning(
            "Hotspot: Interface-IP konnte nach Start nicht ausgelesen werden "
            "— QR-Code zeigt evtl. falsche IP (%s aus config)", hotspot_ip)

    logger.info("Hotspot '%s' gestartet auf %s — IP: %s, Channel 6 (2.4 GHz)",
                ssid, ifname, actual_ip or hotspot_ip)
    return True
