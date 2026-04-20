import logging
import signal
import sys
import threading
from enum import Enum, auto

import pygame

import config
from camera import Camera
from hardware import PhotoButton
from ui import UI, MODES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


class State(Enum):
    IDLE        = auto()
    MODE_SELECT = auto()
    SHOOTING    = auto()
    REVIEW      = auto()


# Modus-Konfiguration: (frames, photo_size, anzahl_fotos)
def _mode_config(mode: str):
    if mode == "Fotostreifen":
        return config.STRIP_FRAMES, config.STRIP_PHOTO_SIZE, 4
    if mode == "Collage":
        return config.COLLAGE_FRAMES, config.COLLAGE_PHOTO_SIZE, 4
    return config.POLAROID_FRAMES, config.POLAROID_PHOTO_SIZE, 3


def _shoot_sequence(ui: UI, camera, mode: str):
    frames, photo_size, num_photos = _mode_config(mode)
    ui.set_layout(frames, photo_size)

    for shot in range(num_photos):
        if shot > 0:
            # Kurze Pause zwischen Aufnahmen, Gallery bereits aktualisiert zeigen
            deadline = pygame.time.get_ticks() + 1800
            while pygame.time.get_ticks() < deadline:
                ui.render()
                pygame.event.pump()
                pygame.time.wait(30)

        capture_result: dict = {"path": None}
        done = threading.Event()

        def _capture(res=capture_result, ev=done):
            try:
                res["path"] = camera.capture(config.PICTURE_PATH)
            except Exception as exc:
                logger.error("Aufnahme fehlgeschlagen: %s", exc)
            finally:
                ev.set()

        ui.show_countdown(
            config.COUNTDOWN_SECONDS,
            on_trigger=_capture if camera else None,
        )
        ui.show_flash()
        ui.play_shutter()

        if camera:
            # UI weiter rendern während Kamera fertig wird
            while not done.wait(timeout=0.033):
                ui.render()
                pygame.event.pump()
            if capture_result["path"]:
                ui.add_photo(capture_result["path"])
        else:
            logger.info("Kein Foto — Kamera nicht verbunden")


def main():
    running = True

    def shutdown(signum=None, frame=None):
        nonlocal running
        logger.info("Shutdown-Signal empfangen — beende Fotobox")
        running = False

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    # Buttons (None wenn GPIO nicht verfügbar)
    btn_up = btn_down = btn_ok = None
    try:
        btn_up   = PhotoButton(config.BUTTON_UP)
        btn_down = PhotoButton(config.BUTTON_DOWN)
        btn_ok   = PhotoButton(config.BUTTON_OK)
        logger.info("Alle 3 Buttons initialisiert")
    except Exception as exc:
        logger.warning("GPIO-Buttons nicht verfügbar (%s) — nur Tastatur", exc)

    camera = None
    try:
        camera = Camera()
    except Exception as exc:
        logger.warning("Kamera nicht verfügbar (%s) — Foto-Aufnahme deaktiviert", exc)

    ui = None
    try:
        ui = UI(
            config.CAPTURE_DEVICE,
            config.POLAROID_FRAMES,
            config.LIVE_VIEW_RECT,
            config.OVERLAY_PATH,
            config.POLAROID_PHOTO_SIZE,
        )
    except Exception as exc:
        logger.error("UI konnte nicht gestartet werden: %s", exc)
        sys.exit(1)

    ui.reload_idle_photos()
    logger.info("Fotobox bereit")

    state        = State.IDLE
    selected_mode = 0
    review_until  = 0

    # Entprellungs-Helfer: merkt, ob ein Knopf gerade gehalten wurde
    _last_up = _last_down = _last_ok = False

    def pressed_up() -> bool:
        hw = btn_up.is_pressed() if btn_up else False
        return hw or ui.key_up_pressed()

    def pressed_down() -> bool:
        hw = btn_down.is_pressed() if btn_down else False
        return hw or ui.key_down_pressed()

    def pressed_ok() -> bool:
        hw = btn_ok.is_pressed() if btn_ok else False
        return hw or ui.key_ok_pressed()

    try:
        while running:
            if ui.check_quit_events():
                break

            # Flanken-Erkennung (rising edge) für alle drei Knöpfe
            cur_up   = pressed_up()
            cur_down = pressed_down()
            cur_ok   = pressed_ok()
            edge_up   = cur_up   and not _last_up
            edge_down = cur_down and not _last_down
            edge_ok   = cur_ok   and not _last_ok
            _last_up, _last_down, _last_ok = cur_up, cur_down, cur_ok

            # ── IDLE ──────────────────────────────────────────────────────────
            if state == State.IDLE:
                ui.draw_idle()
                if edge_ok:
                    logger.info("→ MODE_SELECT")
                    state = State.MODE_SELECT
                    ui.wait_for_all_release()

            # ── MODE_SELECT ───────────────────────────────────────────────────
            elif state == State.MODE_SELECT:
                ui.draw_mode_select(selected_mode)
                if edge_up:
                    selected_mode = (selected_mode - 1) % len(MODES)
                elif edge_down:
                    selected_mode = (selected_mode + 1) % len(MODES)
                elif edge_ok:
                    mode = MODES[selected_mode]
                    logger.info("Modus gewählt: %s → SHOOTING", mode)
                    state = State.SHOOTING
                    ui.wait_for_all_release()
                    _shoot_sequence(ui, camera, mode)
                    review_until = pygame.time.get_ticks() + int(config.REVIEW_DURATION * 1000)
                    ui.reload_idle_photos()
                    state = State.REVIEW

            # ── REVIEW ────────────────────────────────────────────────────────
            elif state == State.REVIEW:
                ui.render(show_live=False)
                if pygame.time.get_ticks() >= review_until or edge_ok:
                    logger.info("→ IDLE")
                    state = State.IDLE
                    ui.wait_for_all_release()

            pygame.time.wait(16)

    except Exception as exc:
        logger.error("Unerwarteter Fehler: %s", exc, exc_info=True)
    finally:
        for btn in (btn_up, btn_down, btn_ok):
            if btn:
                btn.close()
        if camera:
            camera.close()
        if ui:
            ui.close()
        logger.info("Fotobox beendet")


if __name__ == "__main__":
    main()
