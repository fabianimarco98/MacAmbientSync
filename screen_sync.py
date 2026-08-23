#!/usr/bin/env python3
"""
Mac Screen Ambient Sync -> Home Assistant
Cattura lo schermo del Mac in tempo reale, calcola il colore dominante/medio
della scena (con saturazione cinematografica e rimozione bande nere/letterbox)
e sincronizza la lampada RGB su Home Assistant.
"""

import colorsys
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

try:
    import mss
    from PIL import Image
except ImportError:
    print("[ERROR] Dipendenze mancanti. Installa con: pip install mss pillow pyyaml")
    sys.exit(1)

try:
    import yaml
except ImportError:
    yaml = None

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("AmbientSync")

# Default Config
DEFAULT_CONFIG = {
    "home_assistant": {
        "url": "http://192.168.X.X:8123",
        "token": "INSERISCI_QUI_IL_TUO_LONG_LIVED_TOKEN",
        "entity_id": "light.tua_lampada_rgb",
        "timeout": 1.0
    },
    "capture": {
        "monitor_index": 1,        # 1 = Monitor Principale
        "fps": 5,                  # 3-5 Hz è ideale per lampade Wi-Fi/Zigbee senza sovraccarico
        "sample_width": 64,        # Downscale rapido per CPU-load quasi a zero
        "sample_height": 36,
        "ignore_black_bars": True, # Rimuove bande nere film (letterbox)
        "black_threshold": 20      # Luminosità minima per considerare un pixel non-nero
    },
    "color_processing": {
        "saturation_boost": 1.35,  # Esalta i colori per un effetto cinema vivido
        "brightness_boost": 1.1,
        "min_brightness": 30,      # Minimo per non spegnere la lampada nelle scene scure
        "max_brightness": 255,
        "smoothing_factor": 0.4,   # 0.1 = ultra morbido, 0.9 = reattivo/istantaneo
        "change_threshold": 12,    # Differenza minima RGB prima di inviare chiamata ad HA
        "transition_time": 0.3     # Tempo di transizione nativo di Home Assistant (secondi)
    }
}

class ColorProcessor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.prev_rgb = (0, 0, 0)
        self.prev_brightness = 0
        self.smoothed_rgb = [0.0, 0.0, 0.0]
        self.smoothed_brightness = 0.0
        self.first_run = True

    def calculate_dominant_color(self, pil_image):
        """Estrae il colore dominante medio, filtrando bande nere e aumentando la saturazione."""
        img = pil_image.convert("RGB")
        pixels = list(img.getdata())
        
        r_total, g_total, b_total = 0, 0, 0
        valid_pixels = 0
        black_thresh = self.cfg["capture"]["black_threshold"]
        ignore_black = self.cfg["capture"]["ignore_black_bars"]

        for r, g, b in pixels:
            # Calcolo luminosità apparente
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if ignore_black and luminance < black_thresh:
                continue
            r_total += r
            g_total += g
            b_total += b
            valid_pixels += 1

        # Se lo schermo è quasi tutto nero (o titoli di coda)
        if valid_pixels == 0:
            avg_r, avg_g, avg_b = 10, 10, 15
            brightness = self.cfg["color_processing"]["min_brightness"]
        else:
            avg_r = r_total / valid_pixels
            avg_g = g_total / valid_pixels
            avg_b = b_total / valid_pixels
            
            # Boost saturazione colore (RGB -> HSV -> Boost S -> RGB)
            h, s, v = colorsys.rgb_to_hsv(avg_r / 255.0, avg_g / 255.0, avg_b / 255.0)
            s = min(1.0, s * self.cfg["color_processing"]["saturation_boost"])
            v = min(1.0, v * self.cfg["color_processing"]["brightness_boost"])
            r_boost, g_boost, b_boost = colorsys.hsv_to_rgb(h, s, v)
            
            avg_r, avg_g, avg_b = r_boost * 255.0, g_boost * 255.0, b_boost * 255.0
            
            # Luminosità dinamica scalata sui limiti
            raw_brightness = int(v * 255)
            min_b = self.cfg["color_processing"]["min_brightness"]
            max_b = self.cfg["color_processing"]["max_brightness"]
            brightness = max(min_b, min(max_b, raw_brightness))

        # Smoothing Esponenziale (EMA) per evitare cambi bruschi e scatti
        alpha = self.cfg["color_processing"]["smoothing_factor"]
        if self.first_run:
            self.smoothed_rgb = [avg_r, avg_g, avg_b]
            self.smoothed_brightness = brightness
            self.first_run = False
        else:
            for i in range(3):
                target = [avg_r, avg_g, avg_b][i]
                self.smoothed_rgb[i] = alpha * target + (1 - alpha) * self.smoothed_rgb[i]
            self.smoothed_brightness = alpha * brightness + (1 - alpha) * self.smoothed_brightness

        final_r = int(self.smoothed_rgb[0])
        final_g = int(self.smoothed_rgb[1])
        final_b = int(self.smoothed_rgb[2])
        final_brightness = int(self.smoothed_brightness)

        return (final_r, final_g, final_b), final_brightness

    def should_update(self, new_rgb, new_brightness):
        """Controlla se la variazione rispetto all'ultimo invio supera la soglia di sensibilità."""
        thresh = self.cfg["color_processing"]["change_threshold"]
        diff_r = abs(new_rgb[0] - self.prev_rgb[0])
        diff_g = abs(new_rgb[1] - self.prev_rgb[1])
        diff_b = abs(new_rgb[2] - self.prev_rgb[2])
        diff_bright = abs(new_brightness - self.prev_brightness)

        if diff_r > thresh or diff_g > thresh or diff_b > thresh or diff_bright > (thresh * 1.5):
            self.prev_rgb = new_rgb
            self.prev_brightness = new_brightness
            return True
        return False


class HomeAssistantClient:
    def __init__(self, ha_cfg):
        self.url = ha_cfg["url"].rstrip("/")
        self.token = ha_cfg["token"]
        self.entity_id = ha_cfg["entity_id"]
        self.timeout = ha_cfg.get("timeout", 1.0)
        self.service_url = f"{self.url}/api/services/light/turn_on"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def update_light(self, rgb_color, brightness, transition):
        payload = {
            "entity_id": self.entity_id,
            "rgb_color": [rgb_color[0], rgb_color[1], rgb_color[2]],
            "brightness": brightness,
            "transition": transition
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(self.service_url, data=data, headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status == 200
        except urllib.error.HTTPError as e:
            logger.error(f"Errore HTTP da Home Assistant: {e.code} - {e.reason}")
            return False
        except Exception as e:
            logger.debug(f"Errore di rete temporaneo verso HA: {e}")
            return False


def load_config():
    app_support_dir = Path.home() / "Library" / "Application Support" / "MacAmbientSync"
    app_support_dir.mkdir(parents=True, exist_ok=True)
    config_path = app_support_dir / "config.yaml"
    
    # If the user hasn't created a config yet, create a default one from example if it exists
    if not config_path.exists():
        example_path = Path(__file__).parent / "config.example.yaml"
        if example_path.exists():
            import shutil
            shutil.copy(example_path, config_path)
            
    if config_path.exists() and yaml:
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f)
            # Merge
            cfg = DEFAULT_CONFIG.copy()
            if user_cfg:
                for k, v in user_cfg.items():
                    if isinstance(v, dict) and k in cfg:
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
            return cfg
    return DEFAULT_CONFIG


def main():
    config = load_config()
    ha_cfg = config["home_assistant"]
    
    if ha_cfg["token"] == "INSERISCI_QUI_IL_TUO_LONG_LIVED_TOKEN":
        logger.error("Token di Home Assistant non configurato!")
        logger.info("Modifica 'config.yaml' inserendo il tuo Long-Lived Access Token e l'entity_id della lampada.")
        sys.exit(1)

    logger.info("=====================================================")
    logger.info("  Mac Ambient Screen Sync -> Home Assistant avviato  ")
    logger.info(f"  Target: {ha_cfg['entity_id']} @ {ha_cfg['url']}")
    logger.info(f"  FPS di campionamento: {config['capture']['fps']} Hz")
    logger.info("  Premi CTRL+C per arrestare la sincronizzazione.")
    logger.info("=====================================================")

    ha_client = HomeAssistantClient(ha_cfg)
    processor = ColorProcessor(config)
    
    fps = max(1, config["capture"]["fps"])
    sleep_interval = 1.0 / fps
    sw = config["capture"]["sample_width"]
    sh = config["capture"]["sample_height"]
    monitor_idx = config["capture"]["monitor_index"]
    transition = config["color_processing"]["transition_time"]

    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        logger.info("\nArresto in corso...")
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    with mss.mss() as sct:
        # Seleziona monitor
        if monitor_idx >= len(sct.monitors):
            mon = sct.monitors[0]  # Tutto lo schermo virtuale
        else:
            mon = sct.monitors[monitor_idx]

        while running:
            start_time = time.time()
            try:
                # 1. Screenshot super veloce
                sct_img = sct.grab(mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # 2. Downsampling estremo (riduce CPU a < 1%)
                img_small = img.resize((sw, sh), Image.Resampling.BILINEAR)

                # 3. Calcolo colore e luminosità
                rgb, brightness = processor.calculate_dominant_color(img_small)

                # 4. Invia solo se c'è variazione significativa
                if processor.should_update(rgb, brightness):
                    ha_client.update_light(rgb, brightness, transition)
                    logger.info(f"🎨 RGB: {rgb} | Luminosità: {brightness}/255")

            except Exception as e:
                logger.error(f"Errore ciclo di cattura: {e}")

            # Calcolo sleep dinamico per mantenere il framerate preciso
            elapsed = time.time() - start_time
            to_sleep = max(0.01, sleep_interval - elapsed)
            time.sleep(to_sleep)

    logger.info("Sync terminato.")

if __name__ == "__main__":
    main()
