"""Dev-Entrypoint fuer den Galerie-Server.

Startet den Galerie-Server auf einem festen Dev-Port (5000), damit
`vite.config.ts` einen stabilen Proxy-Target hat. Auf dem Pi laeuft
weiterhin `gallery_server.py` direkt mit Port 80 aus config.json.
"""
import logging
import os

import config
import events
import gallery_server


DEV_PORT = 5000


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    os.makedirs(config.cfg["picture_dir"], exist_ok=True)
    events.migrate_flat_photos(config.cfg)
    config.cfg["gallery_port"] = DEV_PORT
    config.cfg["gallery_url"] = config.build_gallery_url(
        config.cfg.get("hotspot_ip", "127.0.0.1"), DEV_PORT)
    gallery_server.run(host="127.0.0.1", port=DEV_PORT)


if __name__ == "__main__":
    main()
