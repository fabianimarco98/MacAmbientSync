#!/usr/bin/env python3
"""
Mac Screen Ambient Sync -> Home Assistant
Captures the Mac screen in real-time, calculates the dominant/average color
of the scene (with cinematic saturation and black bar/letterbox removal)
and synchronizes the RGB lamp in Home Assistant.
"""

import colorsys
import json
import logging
import os
import shutil
import signal
import ssl
import sys
import time
from pathlib import Path
import urllib.request
import urllib.error

try:
    import mss
    from PIL import Image
except ImportError:
    print("[ERROR] Missing dependencies. Install with: pip install mss pillow pyyaml PyQt6")
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

# Default Configuration
DEFAULT_CONFIG = {
    "home_assistant": {
        "url": "http://192.168.1.100:8123",
        "token": "INSERISCI_IL_TUO_LONG_LIVED_ACCESS_TOKEN",
        "entity_id": "light.your_rgb_lamp",
        "timeout": 2.0
    },
    "capture": {
        "monitor_index": -1,       # -1 = Automatic (follow mouse/active screen), 1 = Primary, 2 = Secondary, 0 = All
        "fps": 4,                  # 3-5 Hz is ideal for Wi-Fi / Zigbee lamps
        "sample_width": 64,        # Fast downscale for near-zero CPU load
        "sample_height": 36,
        "ignore_black_bars": True, # Removes movie black bars (letterbox)
        "black_threshold": 18      # Minimum brightness to consider a pixel non-black
    },
    "color_processing": {
        "saturation_boost": 1.35,  # Boosts colors for a vivid cinematic effect
        "brightness_boost": 1.10,  # Brightness scaling
        "min_brightness": 25,      # Minimum brightness so lamp stays visible in dark scenes
        "max_brightness": 255,     # Maximum brightness
        "smoothing_factor": 0.35,  # 0.1 = ultra smooth, 0.9 = reactive/instant
        "change_threshold": 8,     # Minimum RGB difference before sending HA request
        "transition_time": 0.3     # Native Home Assistant transition time (seconds)
    }
}


def has_screen_capture_permission() -> bool:
    """Checks if macOS Screen Recording permission is granted."""
    try:
        import ctypes
        import ctypes.util
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        preflight = getattr(cg, "CGPreflightScreenCaptureAccess", None)
        if preflight:
            preflight.restype = ctypes.c_bool
            return bool(preflight())
    except Exception as e:
        logger.debug(f"Permission check error: {e}")
    return True


def request_screen_capture_permission() -> bool:
    """Explicitly requests Screen Recording permission from macOS."""
    try:
        import ctypes
        import ctypes.util
        cg = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreGraphics"))
        request_access = getattr(cg, "CGRequestScreenCaptureAccess", None)
        if request_access:
            request_access.restype = ctypes.c_bool
            return bool(request_access())
    except Exception as e:
        logger.debug(f"Permission request error: {e}")
    return False


def get_config_path() -> Path:
    """Returns the path to the configuration file in Application Support."""
    app_support_dir = Path.home() / "Library" / "Application Support" / "MacAmbientSync"
    app_support_dir.mkdir(parents=True, exist_ok=True)
    return app_support_dir / "config.yaml"


def load_config() -> dict:
    """Loads configuration from YAML file or falls back to defaults."""
    config_path = get_config_path()
    
    # If config does not exist, copy from example if available
    if not config_path.exists():
        example_path = Path(__file__).parent / "config.example.yaml"
        if getattr(sys, 'frozen', False):
            # Py2app / PyInstaller bundle environment
            res_path = Path(sys.executable).parent.parent / "Resources" / "config.example.yaml"
            if res_path.exists():
                example_path = res_path
                
        if example_path.exists():
            try:
                shutil.copy(example_path, config_path)
            except Exception as e:
                logger.warning(f"Could not copy config.example.yaml: {e}")
    
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # Deep copy default
    
    if config_path.exists() and yaml is not None:
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f)
                if user_cfg and isinstance(user_cfg, dict):
                    for section, values in user_cfg.items():
                        if isinstance(values, dict) and section in cfg:
                            cfg[section].update(values)
                        else:
                            cfg[section] = values
        except Exception as e:
            logger.error(f"Error loading config.yaml: {e}")
            
    return cfg


def save_config(cfg: dict) -> bool:
    """Saves the configuration dictionary to the YAML file."""
    config_path = get_config_path()
    try:
        if yaml is not None:
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        else:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        return False


def get_available_monitors() -> list:
    """Discovers all connected monitors with friendly names and resolutions."""
    monitors_list = []
    
    # Add Automatic option first
    monitors_list.append({
        "index": -1,
        "name": "🎯 Automatico (Segue lo schermo del mouse / video attivo)",
        "width": 0,
        "height": 0,
        "left": 0,
        "top": 0
    })

    try:
        from PyQt6.QtGui import QGuiApplication
        qt_screens = QGuiApplication.screens()
        qt_names = [s.name() for s in qt_screens]
    except Exception:
        qt_names = []

    try:
        with mss.mss() as sct:
            for idx, mon in enumerate(sct.monitors):
                if idx == 0:
                    name = f"🖥️ Tutti i Monitor Uniti ({mon['width']}x{mon['height']})"
                else:
                    screen_name = qt_names[idx - 1] if idx - 1 < len(qt_names) else ""
                    if "Built-in" in screen_name or idx == 1:
                        disp_desc = f"Schermo Mac Integrato ({screen_name})" if screen_name else "Schermo Mac Integrato"
                    else:
                        disp_desc = f"Display Esterno ({screen_name})" if screen_name else f"Display Esterno {idx}"
                    name = f"🖥️ Monitor {idx}: {disp_desc} ({mon['width']}x{mon['height']})"

                monitors_list.append({
                    "index": idx,
                    "name": name,
                    "width": mon["width"],
                    "height": mon["height"],
                    "left": mon["left"],
                    "top": mon["top"]
                })
    except Exception as e:
        logger.error(f"Error enumerating monitors: {e}")
        monitors_list.append({"index": 1, "name": "Monitor 1: Schermo Mac (1920x1080)", "width": 1920, "height": 1080})

    return monitors_list


class ColorProcessor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.prev_rgb = (0, 0, 0)
        self.prev_brightness = 0
        self.smoothed_rgb = [0.0, 0.0, 0.0]
        self.smoothed_brightness = 0.0
        self.first_run = True
        self.force_next_update = True
        self.last_sent_time = 0

    def reset(self):
        """Resets smoothing state."""
        self.prev_rgb = (0, 0, 0)
        self.prev_brightness = 0
        self.smoothed_rgb = [0.0, 0.0, 0.0]
        self.smoothed_brightness = 0.0
        self.first_run = True
        self.force_next_update = True
        self.last_sent_time = 0

    def calculate_dominant_color(self, pil_image):
        """Extracts the average dominant color, filtering black bars and boosting saturation."""
        img = pil_image.convert("RGB")
        pixels = list(img.getdata())
        
        r_total, g_total, b_total = 0, 0, 0
        valid_pixels = 0
        black_thresh = self.cfg.get("capture", {}).get("black_threshold", 18)
        ignore_black = self.cfg.get("capture", {}).get("ignore_black_bars", True)

        for r, g, b in pixels:
            # Calculate apparent luminance
            luminance = 0.299 * r + 0.587 * g + 0.114 * b
            if ignore_black and luminance < black_thresh:
                continue
            r_total += r
            g_total += g
            b_total += b
            valid_pixels += 1

        # If the screen is almost entirely black (or credits)
        if valid_pixels == 0:
            avg_r, avg_g, avg_b = 10, 10, 15
            brightness = self.cfg.get("color_processing", {}).get("min_brightness", 25)
        else:
            avg_r = r_total / valid_pixels
            avg_g = g_total / valid_pixels
            avg_b = b_total / valid_pixels
            
            # Boost color saturation (RGB -> HSV -> Boost S -> RGB)
            sat_boost = self.cfg.get("color_processing", {}).get("saturation_boost", 1.35)
            bright_boost = self.cfg.get("color_processing", {}).get("brightness_boost", 1.10)
            
            h, s, v = colorsys.rgb_to_hsv(avg_r / 255.0, avg_g / 255.0, avg_b / 255.0)
            s = min(1.0, s * sat_boost)
            v = min(1.0, v * bright_boost)
            r_boost, g_boost, b_boost = colorsys.hsv_to_rgb(h, s, v)
            
            avg_r, avg_g, avg_b = r_boost * 255.0, g_boost * 255.0, b_boost * 255.0
            
            # Dynamic brightness scaled to limits
            raw_brightness = int(v * 255)
            min_b = self.cfg.get("color_processing", {}).get("min_brightness", 25)
            max_b = self.cfg.get("color_processing", {}).get("max_brightness", 255)
            brightness = max(min_b, min(max_b, raw_brightness))

        # Exponential Smoothing (EMA) to avoid sudden changes and stuttering
        alpha = self.cfg.get("color_processing", {}).get("smoothing_factor", 0.35)
        if self.first_run:
            self.smoothed_rgb = [avg_r, avg_g, avg_b]
            self.smoothed_brightness = float(brightness)
            self.first_run = False
        else:
            for i in range(3):
                target = [avg_r, avg_g, avg_b][i]
                self.smoothed_rgb[i] = alpha * target + (1 - alpha) * self.smoothed_rgb[i]
            self.smoothed_brightness = alpha * brightness + (1 - alpha) * self.smoothed_brightness

        final_r = max(0, min(255, int(round(self.smoothed_rgb[0]))))
        final_g = max(0, min(255, int(round(self.smoothed_rgb[1]))))
        final_b = max(0, min(255, int(round(self.smoothed_rgb[2]))))
        final_brightness = max(0, min(255, int(round(self.smoothed_brightness))))

        return (final_r, final_g, final_b), final_brightness

    def should_update(self, new_rgb, new_brightness):
        """Checks if the variation from the last send exceeds the sensitivity threshold, with initial force & heartbeat."""
        now = time.time()
        
        # Always send the initial frame immediately
        if self.force_next_update:
            self.force_next_update = False
            self.prev_rgb = new_rgb
            self.prev_brightness = new_brightness
            self.last_sent_time = now
            return True

        thresh = self.cfg.get("color_processing", {}).get("change_threshold", 8)
        diff_r = abs(new_rgb[0] - self.prev_rgb[0])
        diff_g = abs(new_rgb[1] - self.prev_rgb[1])
        diff_b = abs(new_rgb[2] - self.prev_rgb[2])
        diff_bright = abs(new_brightness - self.prev_brightness)

        # Heartbeat: re-send color every 4 seconds to maintain sync if light was altered
        if (now - self.last_sent_time) > 4.0:
            self.prev_rgb = new_rgb
            self.prev_brightness = new_brightness
            self.last_sent_time = now
            return True

        if diff_r >= thresh or diff_g >= thresh or diff_b >= thresh or diff_bright >= (thresh * 1.5):
            self.prev_rgb = new_rgb
            self.prev_brightness = new_brightness
            self.last_sent_time = now
            return True
        return False


class HomeAssistantClient:
    def __init__(self, ha_cfg):
        self.url = ha_cfg.get("url", "").rstrip("/")
        self.token = ha_cfg.get("token", "")
        self.entity_id = ha_cfg.get("entity_id", "")
        self.timeout = float(ha_cfg.get("timeout", 2.0))
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.ssl_context = ssl._create_unverified_context()

    def test_connection(self) -> tuple[bool, str]:
        """Tests connection to Home Assistant API and verifies entity status."""
        if not self.url or "192.168.X.X" in self.url:
            return False, "URL di Home Assistant non configurato."
        if not self.token or "INSERISCI" in self.token or "INSERT" in self.token:
            return False, "Token di accesso non inserito."
        
        # 1. Check API root
        api_url = f"{self.url}/api/"
        req = urllib.request.Request(api_url, headers=self.headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as resp:
                if resp.status != 200:
                    return False, f"Risposta inattesa da Home Assistant: HTTP {resp.status}"
                data = json.loads(resp.read().decode("utf-8"))
                message = data.get("message", "API OK")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Errore 401: Token non valido o scaduto."
            return False, f"Errore HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            err_reason = str(e.reason)
            if "timed out" in err_reason.lower():
                return False, f"Timeout connessione verso {self.url}. Se usi una VPN (es. Cisco), disconnettila o consenti l'accesso alla rete locale."
            return False, f"Impossibile raggiungere Home Assistant ({err_reason})."
        except Exception as e:
            return False, f"Errore di connessione: {e}"

        # 2. Check Entity state
        if self.entity_id:
            entity_url = f"{self.url}/api/states/{self.entity_id}"
            req_ent = urllib.request.Request(entity_url, headers=self.headers, method="GET")
            try:
                with urllib.request.urlopen(req_ent, timeout=self.timeout, context=self.ssl_context) as resp:
                    if resp.status == 200:
                        ent_data = json.loads(resp.read().decode("utf-8"))
                        friendly_name = ent_data.get("attributes", {}).get("friendly_name", self.entity_id)
                        state = ent_data.get("state", "unknown")
                        return True, f"Connesso con successo! Entità '{friendly_name}' trovata (Stato: {state})."
                    else:
                        return False, f"Entità '{self.entity_id}' non trovata (HTTP {resp.status})."
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    return False, f"Entità '{self.entity_id}' non trovata su Home Assistant."
                return True, f"API Connessa ({message}), ma errore entità: {e.reason}"
            except Exception as e:
                return True, f"API Connessa, ma errore lettura stato entità: {e}"

        return True, f"Connessione a Home Assistant riuscita ({message})."

    def update_light(self, rgb_color, brightness, transition=0.3) -> tuple[bool, str]:
        """Sends light update to Home Assistant service."""
        service_url = f"{self.url}/api/services/light/turn_on"
        payload = {
            "entity_id": self.entity_id,
            "rgb_color": [int(rgb_color[0]), int(rgb_color[1]), int(rgb_color[2])],
            "brightness": int(brightness),
            "transition": float(transition)
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(service_url, data=data, headers=self.headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as resp:
                if resp.status == 200:
                    return True, "OK"
                return False, f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            err_msg = f"HTTP {e.code}: {e.reason}"
            logger.error(f"Home Assistant error: {err_msg}")
            return False, err_msg
        except Exception as e:
            logger.debug(f"Network error to HA: {e}")
            return False, str(e)


def main():
    config = load_config()
    ha_cfg = config["home_assistant"]
    
    if "INSERISCI" in ha_cfg.get("token", "") or "INSERT" in ha_cfg.get("token", ""):
        logger.error("Token Home Assistant non configurato!")
        logger.info(f"Modifica la configurazione in {get_config_path()}")
        sys.exit(1)

    logger.info("=====================================================")
    logger.info("  Mac Ambient Screen Sync -> Home Assistant CLI     ")
    logger.info(f"  Target: {ha_cfg['entity_id']} @ {ha_cfg['url']}")
    logger.info(f"  Sampling FPS: {config['capture']['fps']} Hz")
    logger.info("  Premi CTRL+C per terminare la sincronizzazione.   ")
    logger.info("=====================================================")

    ha_client = HomeAssistantClient(ha_cfg)
    processor = ColorProcessor(config)
    
    fps = max(1, config["capture"]["fps"])
    sleep_interval = 1.0 / fps
    sw = config["capture"]["sample_width"]
    sh = config["capture"]["sample_height"]
    monitor_idx = config["capture"]["monitor_index"]
    transition = config["color_processing"].get("transition_time", 0.3)

    running = True

    def handle_sigint(sig, frame):
        nonlocal running
        logger.info("\nInterruzione richiesta... Chiusura in corso.")
        running = False

    signal.signal(signal.SIGINT, handle_sigint)

    with mss.mss() as sct:
        if monitor_idx == -1:
            mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        elif monitor_idx >= len(sct.monitors):
            mon = sct.monitors[0]
        else:
            mon = sct.monitors[monitor_idx]

        while running:
            start_time = time.time()
            try:
                sct_img = sct.grab(mon)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                img_small = img.resize((sw, sh), Image.Resampling.BILINEAR)

                rgb, brightness = processor.calculate_dominant_color(img_small)

                if processor.should_update(rgb, brightness):
                    success, msg = ha_client.update_light(rgb, brightness, transition)
                    if success:
                        logger.info(f"🎨 RGB: {rgb} | Luminosità: {brightness}/255")
                    else:
                        logger.warning(f"Errore invio HA: {msg}")

            except Exception as e:
                logger.error(f"Errore ciclo di cattura: {e}")

            elapsed = time.time() - start_time
            to_sleep = max(0.01, sleep_interval - elapsed)
            time.sleep(to_sleep)

    logger.info("Sincronizzazione terminata.")


if __name__ == "__main__":
    main()
