"""WLAN-Hotspot über NetworkManager.

Wir konfigurieren die Connection explizit (band=bg, channel=6,
ipv4.method=shared mit fester IP) statt 'nmcli device wifi hotspot'
zu nutzen — dadurch ist DHCP, IP-Range und Frequenz vorhersagbar.
"""
import logging
import subprocess
import sys
import time
from typing import Optional

import config

logger = logging.getLogger(__name__)

CONN_NAME = "fotobox-hotspot"
CAPTIVE_CONF_PATH = "/etc/NetworkManager/dnsmasq-shared.d/captive.conf"


def captive_conf_content(ip: str) -> str:
    """Inhalt der captive.conf fuer diese Hotspot-IP.

    Eigene Funktion, weil install.sh die Datei beim ersten Boot schreibt
    und hotspot.py bei jedem Start. Liefen die beiden auseinander, faende
    _write_captive_conf jedes Mal einen abweichenden Inhalt, schriebe neu
    und startete den Hotspot einmal zusaetzlich durch.
    """
    # Die Option traegt bewusst die IP und nicht den Hostnamen: dieser
    # Aufruf ist der erste, den das Handy nach dem Beitritt macht, und er
    # darf nicht davon abhaengen, dass DNS schon funktioniert. Den schoenen
    # Namen liefert erst die Antwort (gallery_server.api_captive_portal).
    api = config.build_gallery_url(
        ip, config.cfg.get("gallery_port", 80)).rstrip("/") + "/api/captive/portal"
    return (
        "# Fotobox Captive-Portal: alle DNS-Anfragen auf Hotspot-IP umleiten\n"
        "# Wird zur Laufzeit von hotspot.py geschrieben.\n"
        f"address=/#/{ip}\n"
        "# RFC 8910: Adresse der Captive-Portal-API. Handys ab iOS 14 /\n"
        "# Android 11 lesen sie und zeigen den Anmelden-Banner, ohne auf\n"
        "# ihre eigenen Verbindungstests angewiesen zu sein.\n"
        f'dhcp-option=114,"{api}"\n'
    )


def _write_captive_conf(ip: str) -> str:
    """Schreibt captive.conf: DNS-Hijack auf die übergebene IP plus die
    Portal-Adresse als DHCP-Option 114.

    Zwei Wege zum selben Ziel, weil der erste allein nicht verlässlich ist.
    Der DNS-Hijack fängt die Verbindungstests der Handys ab — aber nur,
    wenn das Handy überhaupt welche schickt. Wer das Anmeldefenster einmal
    weggetippt hat oder das Netz schon kennt, schickt keine mehr und steht
    dann "verbunden, aber sonst passiert nichts" da. Option 114 (RFC 8910)
    sagt es stattdessen ausdrücklich beim DHCP-Handshake, bei jedem
    Beitritt aufs Neue.

    Bevorzugt direktes Schreiben (install.sh chownt die Datei dem
    Service-User). Fällt das wegen fehlender Rechte fehl, wird via
    'sudo -n tee' nachversucht (NOPASSWD-Regel aus install.sh).

    Rückgabe:
      "changed"   — Datei neu geschrieben, dnsmasq muss neu gestartet werden
      "unchanged" — Datei hatte bereits den gewünschten Inhalt
      "failed"    — Write fehlgeschlagen (kein Schreibrecht trotz Fallback)
    """
    content = captive_conf_content(ip)

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


def _connection_uuids(ctype: str = "802-11-wireless") -> list:
    """UUIDs aller gespeicherten Connections vom gewuenschten Typ."""
    r = _nmcli(["-t", "-f", "UUID,TYPE", "connection", "show"], timeout=5)
    if r is None or r.returncode != 0:
        return []
    uuids = []
    for line in r.stdout.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == ctype:
            uuids.append(parts[0])
    return uuids


def _connection_field(uuid: str, fields: list) -> dict:
    """Liest einzelne Settings einer Connection als dict (leer bei Fehler)."""
    r = _nmcli(["-t", "-f", ",".join(fields), "connection", "show", "uuid", uuid],
               timeout=5)
    if r is None or r.returncode != 0:
        return {}
    out = {}
    for line in r.stdout.splitlines():
        key, sep, value = line.partition(":")
        if sep:
            out[key] = value
    return out


def _purge_self_ssid_clients(ssid: str) -> None:
    """Loescht Client-Profile, die auf unsere eigene Hotspot-SSID zeigen.

    Klickt jemand am Pi-Desktop im WLAN-Menue auf die eigene Fotobox-SSID,
    legt NetworkManager (bzw. netplan) ein infrastructure-Profil mit
    autoconnect=yes an. Das Profil ist an kein Interface gebunden, NM
    probiert es also auf jedem freien WLAN-Adapter (z.B. dem USB-Stick
    wlan1) und versucht, sich mit dem eigenen Hotspot zu verbinden. Der
    Handshake scheitert zwangslaeufig, NM fragt nach einem neuen Key —
    und der Passwort-Dialog ploppt mitten im Event alle paar Minuten auf.
    Solche Profile sind nie sinnvoll, also raus damit.
    """
    for uuid in _connection_uuids():
        info = _connection_field(uuid, [
            "connection.id", "802-11-wireless.mode", "802-11-wireless.ssid"])
        if not info:
            continue
        name = info.get("connection.id", uuid)
        if name == CONN_NAME:
            continue
        if info.get("802-11-wireless.ssid") != ssid:
            continue
        # Leeres Feld / "--" bedeutet bei NM den Default: infrastructure
        if info.get("802-11-wireless.mode") == "ap":
            continue
        logger.info(
            "Hotspot: loesche Client-Profil '%s' auf eigener SSID '%s' "
            "(sonst fragt NetworkManager staendig nach dem WLAN-Passwort)",
            name, ssid)
        _nmcli(["connection", "down", "uuid", uuid], timeout=10)
        r = _nmcli(["connection", "delete", "uuid", uuid], timeout=10)
        if r is None or r.returncode != 0:
            logger.warning(
                "Hotspot: Client-Profil '%s' konnte nicht geloescht werden: %s",
                name, (r.stderr if r else "no result").strip()[:200])


def _delete_existing() -> None:
    """Alte fotobox-hotspot-Connection entfernen damit ein frischer Build
    nicht von kaputten Altsettings gestört wird."""
    _nmcli(["connection", "delete", CONN_NAME], timeout=10)


def _build_connection(ifname: str, ssid: str, password: str,
                      hotspot_ip: str) -> bool:
    """Erstellt die fotobox-hotspot-Connection mit expliziten Settings.

    WICHTIG: alle Settings in einem einzigen 'connection add' setzen, nicht
    add+modify aufteilen. NetworkManager (zumindest <=1.42 auf Bookworm)
    legt bei 'ipv4.method=shared' das Subnetz beim ersten Aktivieren fest
    — kommt 'ipv4.addresses' erst per späterem modify, ignoriert NM den
    Wert und nutzt 10.42.0.1/24 (interner Default). Phone landet dann im
    10.42-Subnet und kann den im QR-Code geworfenen 192.168.4.1 nie
    erreichen.
    """
    # Aus 192.168.4.1 wird 192.168.4.1/24 für den ipv4.addresses-Wert
    ipv4_addr = f"{hotspot_ip}/24"

    # Ohne Passwort wird der AP offen aufgespannt: die wifi-sec-Settings
    # entfallen dann komplett. Sie mit leerem PSK zu setzen geht nicht —
    # NetworkManager lehnt 'wpa-psk' ohne Schluessel ab, und die
    # Connection kaeme gar nicht erst zustande.
    #
    # Offen ist eine bewusste Wahl des Betreibers, keine Panne: am
    # Eventabend ist das Abtippen des Passworts die Huerde, an der Gaeste
    # haengenbleiben. Wer im Funkbereich steht, kommt dann allerdings
    # ohne Weiteres ins Netz und damit in die Galerie.
    security = [] if not password else [
        "wifi-sec.key-mgmt", "wpa-psk",
        "wifi-sec.proto", "rsn",
        "wifi-sec.pairwise", "ccmp",
        "wifi-sec.group", "ccmp",
        "wifi-sec.psk", password,
    ]

    r = _nmcli([
        "connection", "add",
        "type", "wifi",
        "ifname", ifname,
        "con-name", CONN_NAME,
        "autoconnect", "no",
        "ssid", ssid,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless.channel", "6",
        "ipv4.method", "shared",
        "ipv4.addresses", ipv4_addr,
        "ipv6.method", "ignore",
    ] + security, timeout=15)
    if r is None or r.returncode != 0:
        logger.warning("Hotspot-Add fehlgeschlagen: %s",
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
    last_stdout = ""
    for _ in range(max(1, retries)):
        try:
            result = subprocess.run(
                ["ip", "-4", "-o", "addr", "show", "dev", ifname],
                capture_output=True, text=True, timeout=5,
            )
        except Exception as exc:
            logger.debug("ip-addr-Read auf %s fehlgeschlagen: %s", ifname, exc)
            time.sleep(delay_s)
            continue
        if result.returncode == 0:
            last_stdout = result.stdout
            # Output: "4: wlan1    inet 10.42.0.1/24 brd 10.42.0.255 ..."
            for token in result.stdout.split():
                if "/" in token and token.startswith(("10.", "192.168.", "172.")):
                    return token.split("/")[0]
        time.sleep(delay_s)
    logger.warning(
        "Hotspot: Interface %s hat nach %.1fs keine IPv4 — letzte 'ip addr' "
        "Ausgabe: %r", ifname, retries * delay_s, last_stdout.strip()[:200])
    return None


# Wie lange start() beim Kaltstart darauf wartet, dass NetworkManager das
# WLAN-Interface kennt.
#
# fotobox.service startet mit graphical.target. network.target sagt nur, dass
# die Netzwerk-Einrichtung *begonnen* hat — ob NetworkManager wlan0 schon
# registriert hat (Treiber geladen, rfkill frei), ist damit nicht gesagt.
# Vorher hiess "nmcli device kennt wlan0 nicht" sofort: Hotspot faellt aus,
# eine Warnzeile im Log, und niemand merkt es, bis der erste Gast den QR-Code
# scannt. Wiederholt wird nichts — die Box laeuft dann den ganzen Abend ohne
# WLAN, bis jemand den Service neu startet.
INTERFACE_WAIT_S = 30.0
INTERFACE_RETRY_S = 2.0


def _connection_up(label: str, attempts: int = 3, delay_s: float = 1.0) -> bool:
    """'nmcli connection up' auf die Hotspot-Connection, mit Wiederholung.

    Zwei Faelle brauchen denselben Retry: nach einem schnellen down/up ist
    NetworkManager kurz busy und lehnt den ersten Versuch ab, und beim
    Kaltstart ist das WLAN-Geraet zwar registriert, aber noch nicht nutzbar
    (Firmware laedt, rfkill). Beides ist nach ein, zwei Sekunden vorbei —
    ohne Wiederholung bliebe der AP bis zum naechsten Service-Neustart aus.
    """
    for attempt in range(1, attempts + 1):
        r = _nmcli(["connection", "up", CONN_NAME], timeout=20)
        if r is not None and r.returncode == 0:
            return True
        logger.warning("%s Versuch %d/%d fehlgeschlagen: %s", label, attempt,
                       attempts, (r.stderr if r else "no result").strip()[:200])
        if attempt < attempts:
            time.sleep(delay_s)
    return False


def _wait_for_interface(ifname: str, timeout_s: float = INTERFACE_WAIT_S,
                        delay_s: float = INTERFACE_RETRY_S) -> bool:
    """Wartet bis NetworkManager `ifname` als WLAN-Geraet fuehrt.

    Der Normalfall kostet nichts: ist das Interface da, kehrt die Funktion
    beim ersten Blick zurueck. Gewartet wird nur im Rennen gegen den Boot.
    """
    if _interface_exists(ifname):
        return True
    logger.info("Hotspot: NetworkManager kennt '%s' noch nicht — bis zu "
                "%.0f s warten (Kaltstart)", ifname, timeout_s)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(delay_s)
        if _interface_exists(ifname):
            logger.info("Hotspot: '%s' ist da, Hotspot wird aufgebaut", ifname)
            return True
    return False


def start() -> bool:
    if sys.platform != "linux":
        logger.warning("Hotspot: nur auf Linux verfügbar (Plattform: %s)", sys.platform)
        return False

    cfg = config.cfg
    ssid = cfg["wifi_ssid"]
    password = cfg["wifi_password"]
    ifname = cfg.get("hotspot_interface", "wlan0")
    hotspot_ip = cfg.get("hotspot_ip", "192.168.4.1")

    # Leer heisst "offen und so gewollt". Zwischen 1 und 7 Zeichen ist
    # dagegen immer ein Versehen: WPA2 verlangt mindestens 8, der AP kaeme
    # gar nicht hoch, und ein stillschweigend offenes Netz waere die
    # schlechteste aller Antworten darauf.
    if 0 < len(password) < 8:
        logger.warning("Hotspot: WPA2 verlangt min. 8 Zeichen Passwort — "
                       "abgebrochen (leer lassen fuer ein offenes Netz)")
        return False
    if not password:
        logger.warning("Hotspot '%s' wird OHNE Passwort aufgespannt — jeder "
                       "in Funkreichweite kommt in die Galerie", ssid)

    if not _wait_for_interface(ifname):
        logger.error(
            "Hotspot-Interface '%s' auch nach %.0f s nicht gefunden — Hotspot "
            "wird nicht gestartet. Verfuegbare Interfaces zeigt 'nmcli device'.",
            ifname, INTERFACE_WAIT_S)
        return False

    _purge_self_ssid_clients(ssid)
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
    if not _connection_up("Hotspot-Up"):
        logger.error("Hotspot-Up auf %s endgueltig fehlgeschlagen — es gibt "
                     "kein Gaeste-WLAN", ifname)
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
            if not _connection_up("Hotspot-Reload"):
                logger.error(
                    "Hotspot konnte nach Captive-DNS-Update NICHT neu "
                    "gestartet werden — manueller Eingriff: "
                    "'sudo nmcli connection up %s'", CONN_NAME)
        config.cfg["hotspot_ip"] = actual_ip
        # Ueber gallery_host, nicht ueber actual_ip: mit gesetztem
        # gallery_hostname traegt die URL den Namen, und der Captive-
        # Redirect schickt die Gaeste dann dorthin statt auf die IP.
        config.cfg["gallery_url"] = config.build_gallery_url(
            config.gallery_host(config.cfg),
            config.cfg.get("gallery_port", 80))
    else:
        logger.warning(
            "Hotspot: Interface-IP konnte nach Start nicht ausgelesen werden "
            "— QR-Code zeigt evtl. falsche IP (%s aus config)", hotspot_ip)

    logger.info("Hotspot '%s' gestartet auf %s — IP: %s, Channel 6 (2.4 GHz)",
                ssid, ifname, actual_ip or hotspot_ip)
    return True
