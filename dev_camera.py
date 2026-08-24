"""Webcam-Ersatz fuer die gphoto2-Kamera — ausschliesslich fuer Dev-Betrieb.

Auf der Entwicklungsmaschine (macOS/Windows) gibt es weder gphoto2 noch eine
angeschlossene DSLR, dadurch bleibt `Camera.available` False und der Ausloeser
wird in main.py stumm ignoriert. Der Live-View funktioniert dort trotzdem, weil
er ueber cv2 von der eingebauten Webcam kommt — nur eben ein anderer Codepfad.

DevCamera schliesst genau diese Luecke: sie speichert den letzten Live-Frame als
JPEG und erfuellt damit dieselbe Schnittstelle wie Camera (available,
error_message, capture, wake_liveview, close).

Bewusst NUR per `--dev-camera` aktivierbar und nicht als automatischer Fallback:
sonst wuerde eine am Eventtag abgezogene DSLR unbemerkt Webcam-Bilder liefern,
statt den Fehler ehrlich auf dem Homescreen anzuzeigen.
"""
import logging
import os
import time

import cv2

import camera as _camera_mod

logger = logging.getLogger(__name__)


class DevCamera:
    """Nimmt Fotos aus dem laufenden Live-View statt per gphoto2.

    Oeffnet bewusst KEIN eigenes cv2.VideoCapture: die UI haelt das
    Capture-Device bereits offen, und macOS gibt dieselbe Kamera kein zweites
    Mal heraus. Stattdessen liefert `frame_provider` den letzten BGR-Frame —
    in main.py wird dafuer `ui.latest_live_frame` eingehaengt.
    """

    # Der LiveReader-Thread braucht nach dem Start ein paar Frames Vorlauf,
    # bevor latest() etwas anderes als None liefert.
    _FRAME_WAIT_S = 2.0

    def __init__(self, frame_provider=None):
        self._frame_provider = frame_provider
        self.available = True
        self.error_message = ""
        # Damit Admin-Panel/Galerie denselben Status sehen wie bei echter Kamera.
        _camera_mod._set_status(True, "")
        logger.warning("DEV-KAMERA aktiv — Fotos kommen aus dem Live-View, "
                       "nicht aus einer DSLR. Nicht fuer den Echtbetrieb!")

    def set_frame_provider(self, provider):
        """Wird in main.py nachtraeglich gesetzt, weil die UI (und damit der
        LiveReader) erst nach der Kamera konstruiert wird."""
        self._frame_provider = provider

    def capture(self, directory: str, on_shutter=None) -> str:
        if self._frame_provider is None:
            raise RuntimeError("Dev-Kamera: kein Live-View verbunden")

        frame = None
        deadline = time.monotonic() + self._FRAME_WAIT_S
        while time.monotonic() < deadline:
            frame = self._frame_provider()
            if frame is not None:
                break
            time.sleep(0.05)
        if frame is None:
            raise RuntimeError("Dev-Kamera: kein Bild vom Live-View erhalten")

        os.makedirs(directory, exist_ok=True)
        # Millisekunden im Namen — identisch zu Camera.capture, damit zwei
        # Collage-Shots in derselben Sekunde sich nicht ueberschreiben.
        filename = f"foto_{int(time.time() * 1000)}.jpg"
        path = os.path.join(directory, filename)
        # Der Ausloesemoment der Webcam ist der gegriffene Frame — hier ist er
        # schon vorbei, also sofort melden. Die UI beendet daraufhin ihr
        # "Lächeln!", genau wie an der echten Kamera.
        if on_shutter is not None:
            on_shutter()
        if not cv2.imwrite(path, frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92]):
            raise RuntimeError(f"Dev-Kamera: konnte {path} nicht schreiben")

        logger.info("Foto gespeichert (Dev-Kamera): %s", path)
        return path

    # Die Webcam braucht weder Spiegel noch USB-Session — capture() ist nach
    # spaetestens _FRAME_WAIT_S durch. main.py leitet daraus seinen UI-Timeout
    # ab, deshalb muss der Wert auch hier existieren.
    capture_budget_s = 5.0

    def wake_liveview(self, with_preview: bool = None,
                      reset_output: bool = False):
        """No-op — der LiveReader laeuft ohnehin durchgehend."""

    def request_liveview(self):
        """No-op — siehe wake_liveview."""

    def close(self):
        """No-op — das Capture-Device gehoert der UI, die schliesst es selbst."""
