#!/usr/bin/env python3
"""USB-Auto-Export für die Fotobox.

Wird via udev-Regel beim Einstecken eines USB-Sticks getriggert.
Mountet den Stick, kopiert alle Fotos aus dem picture_dir rüber und
unmountet ihn wieder. Status wird nach /run/fotobox/usb_status.json
geschrieben — die UI zeigt darüber den Live-Fortschritt an.

Aufruf:  usb_export.py /dev/sda1
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Repo-Root erreichbar machen, damit `import config` funktioniert
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

import config  # noqa: E402

STATE_FILE  = Path("/run/fotobox/usb_status.json")
MOUNT_POINT = Path("/mnt/fotobox_usb")
EXTS = {".jpg", ".jpeg", ".png"}
LINGER_AFTER_DONE_S = 8


def write_state(state: str, current: int = 0, total: int = 0,
                message: str = "") -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps({
            "state":     state,        # mounting | copying | done | error
            "current":   current,
            "total":     total,
            "message":   message,
            "timestamp": time.time(),
        }))
    except OSError as exc:
        print(f"State-Schreiben: {exc}", file=sys.stderr)


def clear_state() -> None:
    try:
        STATE_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def unmount() -> None:
    subprocess.run(["umount", str(MOUNT_POINT)], check=False, timeout=15)
    try:
        MOUNT_POINT.rmdir()
    except OSError:
        pass


def mount(device: str) -> bool:
    MOUNT_POINT.mkdir(parents=True, exist_ok=True)
    # uid/gid mounten damit der pi-User schreiben kann; sync für sofortiges Flush
    cmd_options = [
        ["mount", "-o", "rw,sync,uid=1000,gid=1000", device, str(MOUNT_POINT)],
        ["mount", "-o", "rw,sync",                       device, str(MOUNT_POINT)],
        ["mount",                                        device, str(MOUNT_POINT)],
    ]
    for cmd in cmd_options:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        if r.returncode == 0:
            return True
    return False


def collect_photos(pic_dir: Path) -> list[tuple[Path, Path]]:
    """Liefert (absoluter Pfad, relativer Pfad ab pic_dir)."""
    out: list[tuple[Path, Path]] = []
    if not pic_dir.is_dir():
        return out
    for root, _dirs, files in os.walk(pic_dir):
        for f in files:
            if Path(f).suffix.lower() not in EXTS:
                continue
            full = Path(root) / f
            rel  = full.relative_to(pic_dir)
            out.append((full, rel))
    out.sort(key=lambda x: x[1])
    return out


def safe_label(name: str) -> str:
    keep = []
    for c in name:
        if c.isalnum() or c in "_-":
            keep.append(c)
        else:
            keep.append("_")
    return ("".join(keep).strip("_") or "Fotobox")[:40]


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: usb_export.py <device>", file=sys.stderr)
        return 2

    device = sys.argv[1]
    if not Path(device).exists():
        print(f"Device nicht gefunden: {device}", file=sys.stderr)
        return 1

    write_state("mounting", message="USB-Stick erkannt …")

    if not mount(device):
        write_state("error", message="Stick konnte nicht gelesen werden")
        time.sleep(LINGER_AFTER_DONE_S)
        clear_state()
        return 1

    try:
        pic_dir = Path(config.cfg["picture_dir"])
        photos = collect_photos(pic_dir)
        total = len(photos)

        if total == 0:
            write_state("done", 0, 0, "Keine Fotos vorhanden")
            time.sleep(LINGER_AFTER_DONE_S)
            return 0

        event_label = safe_label(config.cfg.get("event_name", "Fotobox"))
        date_str    = datetime.now().strftime("%Y-%m-%d")
        dest_root   = MOUNT_POINT / f"Fotobox_{event_label}_{date_str}"
        dest_root.mkdir(parents=True, exist_ok=True)

        write_state("copying", 0, total, "Kopiere …")

        copied = 0
        disk_full = False
        for src, rel in photos:
            dst = dest_root / rel
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                copied += 1
            except OSError as exc:
                # ENOSPC = Stick voll → Abbruch, weitere Versuche sind sinnlos
                # und produzieren nur halb-geschriebene Dateien.
                if getattr(exc, "errno", None) == 28:  # ENOSPC
                    disk_full = True
                    # Halb-geschriebene Datei wegwerfen
                    try:
                        if dst.exists():
                            dst.unlink()
                    except OSError:
                        pass
                    write_state("error", copied, total,
                                "USB-Stick voll – kopieren abgebrochen")
                    break
                write_state("copying", copied, total,
                            f"Übersprungen: {rel} ({exc})")
                continue
            except Exception as exc:
                write_state("copying", copied, total,
                            f"Übersprungen: {rel} ({exc})")
                continue
            write_state("copying", copied, total, str(rel))

        if disk_full:
            subprocess.run(["sync"], check=False, timeout=60)
            time.sleep(LINGER_AFTER_DONE_S)
            return 1

        # Buffer flush vor Unmount
        subprocess.run(["sync"], check=False, timeout=60)

        if copied == total:
            write_state("done", total, total, "Fertig — Stick entnehmen")
        else:
            write_state("done", copied, total,
                        f"{copied}/{total} kopiert — Stick entnehmen")

        time.sleep(LINGER_AFTER_DONE_S)
        return 0

    finally:
        unmount()
        # Status sofort entfernen damit das Overlay verschwindet
        clear_state()


if __name__ == "__main__":
    sys.exit(main())
