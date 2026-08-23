import os
import sys
import threading
import time
import rumps
import mss
from PIL import Image
from screen_sync import ColorProcessor, HomeAssistantClient, load_config, DEFAULT_CONFIG
import logging
import urllib.request
import urllib.error

logger = logging.getLogger("AmbientSync")

class AmbientSyncApp(rumps.App):
    def __init__(self):
        super(AmbientSyncApp, self).__init__("🎨")
        self.config = load_config()
        self.ha_client = HomeAssistantClient(self.config["home_assistant"])
        self.processor = ColorProcessor(self.config)
        self.running = False
        self.thread = None
        
        # Menu items
        self.start_stop_btn = rumps.MenuItem("Start Sync", callback=self.toggle_sync)
        self.menu = [
            self.start_stop_btn,
            "Edit Config...",
            rumps.separator,
            "Quit"
        ]

    @rumps.clicked("Edit Config...")
    def edit_config(self, _):
        config_path = os.path.expanduser("~/Library/Application Support/MacAmbientSync/config.yaml")
        os.system(f'open "{config_path}"')

    def toggle_sync(self, sender):
        if not self.running:
            self.start_sync()
        else:
            self.stop_sync()

    def start_sync(self):
        self.config = load_config() # Reload config on start
        ha_cfg = self.config["home_assistant"]
        if ha_cfg["token"] == "INSERT_YOUR_LONG_LIVED_TOKEN_HERE":
            rumps.alert("Configuration Error", "Please edit config.yaml and insert your Home Assistant token and URL.")
            self.edit_config(None)
            return

        self.ha_client = HomeAssistantClient(ha_cfg)
        self.processor = ColorProcessor(self.config)
        
        self.running = True
        self.start_stop_btn.title = "Stop Sync"
        self.title = "🔴"
        
        self.thread = threading.Thread(target=self.sync_loop)
        self.thread.daemon = True
        self.thread.start()

    def stop_sync(self):
        self.running = False
        self.start_stop_btn.title = "Start Sync"
        self.title = "🎨"

    def sync_loop(self):
        fps = max(1, self.config["capture"]["fps"])
        sleep_interval = 1.0 / fps
        sw = self.config["capture"]["sample_width"]
        sh = self.config["capture"]["sample_height"]
        monitor_idx = self.config["capture"]["monitor_index"]
        transition = self.config["color_processing"]["transition_time"]

        with mss.mss() as sct:
            if monitor_idx >= len(sct.monitors):
                mon = sct.monitors[0]
            else:
                mon = sct.monitors[monitor_idx]

            while self.running:
                start_time = time.time()
                try:
                    sct_img = sct.grab(mon)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                    img_small = img.resize((sw, sh), Image.Resampling.BILINEAR)
                    rgb, brightness = self.processor.calculate_dominant_color(img_small)

                    if self.processor.should_update(rgb, brightness):
                        self.ha_client.update_light(rgb, brightness, transition)
                except Exception as e:
                    logger.error(f"Sync loop error: {e}")

                elapsed = time.time() - start_time
                to_sleep = max(0.01, sleep_interval - elapsed)
                time.sleep(to_sleep)

    @rumps.clicked("Quit")
    def quit_app(self, _):
        self.running = False
        rumps.quit_application()

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    app = AmbientSyncApp()
    app.run()
