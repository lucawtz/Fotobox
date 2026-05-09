#!/usr/bin/env python3
"""Kamera-Diagnose: zeigt was gphoto2 mit der Kamera kann.

Auf dem Pi ausführen:
    cd ~/Fotobox
    python3 diagnose_camera.py

Während des Tests die Kamera beobachten und notieren ob:
  - das Display angeht
  - der Spiegel klappert (klick) — normal beim Live-View-Start
  - der Auslöser auslöst (lauter Klick + neues Foto im Speicher) — schlecht!
  - sich gar nichts tut
"""
import subprocess
import time


def run(cmd, label=None):
    if label:
        print(f"\n=== {label} ===")
    print(f">>> {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        print(f"  returncode: {r.returncode}")
        if r.stdout.strip():
            for line in r.stdout.strip().split("\n")[:20]:
                print(f"  out| {line}")
        if r.stderr.strip():
            for line in r.stderr.strip().split("\n")[:20]:
                print(f"  err| {line}")
        return r
    except subprocess.TimeoutExpired:
        print("  TIMEOUT")
        return None
    except FileNotFoundError:
        print("  FEHLT: gphoto2 nicht installiert")
        return None


def wait(s, msg):
    print(f"\n... warte {s}s — {msg}")
    time.sleep(s)


print("=" * 70)
print("FOTOBOX KAMERA-DIAGNOSE")
print("=" * 70)

# 1. Auto-detect
run(["gphoto2", "--auto-detect"], "1. Kamera erkannt?")

# 2. Suche relevante Config-Optionen
print("\n=== 2. Live-View Config-Optionen ===")
r = subprocess.run(["gphoto2", "--list-config"],
                   capture_output=True, text=True, timeout=15)
relevant = [l for l in r.stdout.split("\n")
            if any(kw in l.lower() for kw in
                   ["view", "live", "preview", "mirror", "output", "capture"])]
for line in relevant:
    print(f"  {line}")

# 3. Aktueller viewfinder-Wert
run(["gphoto2", "--get-config", "viewfinder"], "3. viewfinder-Status")

# 4. viewfinder=1 testen
run(["gphoto2", "--set-config", "viewfinder=1"], "4. viewfinder=1 setzen")
wait(3, "Kamera beobachten — Display an? Spiegel hochgeklappt?")

# 5. eosviewfinder=1 testen (alternativer Config-Name)
run(["gphoto2", "--set-config", "eosviewfinder=1"], "5. eosviewfinder=1 setzen")
wait(3, "Kamera beobachten")

# 6. Output-Konfiguration (HDMI-Zielsteuerung)
run(["gphoto2", "--get-config", "output"], "6. output-Status")

# 7. Optional: capture-preview (auf Wunsch)
print("\n" + "=" * 70)
print("OPTIONALER TEST 'capture-preview':")
print("Bei deiner früheren Beobachtung war die Vermutung dass dieser Befehl")
print("den Auslöser triggert. Lass uns das definitiv klären.")
print("Bitte JETZT die Kamera beobachten beim nächsten Aufruf:")
ans = input("\n[Enter] um den Test zu starten, [s] um zu überspringen: ")
if ans.strip().lower() != "s":
    run(["gphoto2", "--capture-preview", "--filename=/tmp/_diag_preview.jpg",
         "--force-overwrite"], "7. capture-preview")
    print("\nWas ist passiert?")
    print("  a) Display ging an, Spiegel klappert (1 Klick) → das ist NORMAL")
    print("  b) Lautes 'Klack-Klack' wie beim Auslösen + Foto auf SD-Karte")
    print("     → das wäre der Bug, dann lassen wir den Befehl weg")

print("\n" + "=" * 70)
print("Diagnose fertig — bitte die komplette Ausgabe zeigen!")
