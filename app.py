#!/usr/bin/env python3
"""
MacAmbientSync - GUI Application
Modern macOS Desktop App to control screen ambient lighting sync with Home Assistant.
"""

import json
import os
import sys
import time
import threading
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QIcon, QKeySequence, QShortcut, QPalette
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QTabWidget, QLabel, QPushButton, QLineEdit,
    QSpinBox, QDoubleSpinBox, QSlider, QCheckBox, QComboBox,
    QTextEdit, QGroupBox, QFrame, QMessageBox, QStatusBar,
    QSizePolicy
)

import mss
from PIL import Image

from screen_sync import (
    ColorProcessor, HomeAssistantClient,
    load_config, save_config, get_available_monitors,
    DEFAULT_CONFIG, get_config_path, logger
)


class SyncWorker(QThread):
    """Background worker thread for capturing screen and sending colors to HA."""
    color_updated = pyqtSignal(tuple, int, bool, str)  # (rgb, brightness, sent_to_ha, status_msg)
    error_occurred = pyqtSignal(str)
    log_emitted = pyqtSignal(str, str)  # (level, message)

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        self.ha_client = HomeAssistantClient(self.config["home_assistant"])
        self.processor = ColorProcessor(self.config)

    def update_config(self, new_config):
        self.config = new_config
        self.ha_client = HomeAssistantClient(self.config["home_assistant"])
        self.processor.cfg = new_config
        self.processor.force_next_update = True

    def stop(self):
        self.running = False

    def run(self):
        self.running = True
        self.processor.reset()
        self.processor.force_next_update = True

        fps = max(1, self.config.get("capture", {}).get("fps", 5))
        sleep_interval = 1.0 / fps
        sw = self.config.get("capture", {}).get("sample_width", 64)
        sh = self.config.get("capture", {}).get("sample_height", 36)
        monitor_idx = self.config.get("capture", {}).get("monitor_index", 1)
        transition = self.config.get("color_processing", {}).get("transition_time", 0.0)

        self.log_emitted.emit("INFO", f"Avvio sincronizzazione schermo (Monitor: {monitor_idx}, FPS: {fps})")

        try:
            with mss.mss() as sct:
                if monitor_idx >= len(sct.monitors):
                    mon = sct.monitors[0]
                else:
                    mon = sct.monitors[monitor_idx]

                while self.running:
                    start_time = time.time()
                    try:
                        # Grab screenshot
                        sct_img = sct.grab(mon)
                        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                        img_small = img.resize((sw, sh), Image.Resampling.BILINEAR)

                        # Process colors
                        rgb, brightness = self.processor.calculate_dominant_color(img_small)

                        # Check if should update Home Assistant
                        sent = False
                        status_msg = ""
                        if self.processor.should_update(rgb, brightness):
                            success, msg = self.ha_client.update_light(rgb, brightness, transition)
                            sent = True
                            if success:
                                status_msg = "Inviato a Home Assistant"
                                self.log_emitted.emit("INFO", f"🎨 Colore inviato: RGB{rgb} - Lum: {brightness}/255")
                            else:
                                status_msg = f"Errore HA: {msg}"
                                self.log_emitted.emit("WARNING", f"Errore invio a Home Assistant: {msg}")

                        self.color_updated.emit(rgb, brightness, sent, status_msg)

                    except Exception as e:
                        err_str = f"Errore nel loop di cattura: {e}"
                        self.log_emitted.emit("ERROR", err_str)
                        self.error_occurred.emit(str(e))

                    elapsed = time.time() - start_time
                    to_sleep = max(0.01, sleep_interval - elapsed)
                    time.sleep(to_sleep)

        except Exception as e:
            self.log_emitted.emit("ERROR", f"Errore critico monitor/cattura: {e}")
            self.error_occurred.emit(str(e))
        finally:
            self.running = False
            self.log_emitted.emit("INFO", "Sincronizzazione schermo interrotta.")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mac Ambient Sync")
        self.resize(780, 700)
        self.setMinimumSize(680, 600)

        self.config = load_config()
        self.worker = None

        self.setup_ui()
        self.load_settings_to_ui()
        self.apply_theme()

        # Keyboard shortcuts
        QShortcut(QKeySequence("Ctrl+Q"), self, self.close)
        QShortcut(QKeySequence("Ctrl+W"), self, self.close)

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(18, 16, 18, 16)
        main_layout.setSpacing(14)

        # 1. TOP LIVE CONTROLS & STATUS CARD
        top_card = QFrame()
        top_card.setObjectName("TopCard")
        top_card_layout = QHBoxLayout(top_card)
        top_card_layout.setContentsMargins(16, 14, 16, 14)
        top_card_layout.setSpacing(20)

        # Left: Big Start/Stop Button & State
        btn_box = QVBoxLayout()
        self.btn_toggle_sync = QPushButton("▶  Avvia Sincronizzazione")
        self.btn_toggle_sync.setObjectName("BtnToggleSync")
        self.btn_toggle_sync.setMinimumHeight(48)
        self.btn_toggle_sync.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle_sync.clicked.connect(self.toggle_sync)
        btn_box.addWidget(self.btn_toggle_sync)

        self.lbl_status_badge = QLabel("⚪  Stato: Inattivo")
        self.lbl_status_badge.setObjectName("LblStatusBadge")
        btn_box.addWidget(self.lbl_status_badge)
        top_card_layout.addLayout(btn_box, 3)

        # Right: Live Dominant Color Preview Swatch & Details
        preview_box = QHBoxLayout()
        
        self.color_swatch = QFrame()
        self.color_swatch.setObjectName("ColorSwatch")
        self.color_swatch.setFixedSize(64, 64)
        self.color_swatch.setStyleSheet("background-color: #222226; border: 2px solid #444; border-radius: 12px;")
        preview_box.addWidget(self.color_swatch)

        color_info_box = QVBoxLayout()
        color_info_box.setSpacing(3)
        self.lbl_color_rgb = QLabel("RGB: ---, ---, ---")
        self.lbl_color_rgb.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.lbl_color_hex = QLabel("HEX: #------")
        self.lbl_color_hex.setStyleSheet("color: #888; font-size: 12px; font-family: monospace;")
        self.lbl_brightness_val = QLabel("Luminosità: --%")
        self.lbl_brightness_val.setStyleSheet("color: #aaa; font-size: 12px;")
        self.lbl_ha_status = QLabel("Nessun dato inviato")
        self.lbl_ha_status.setStyleSheet("color: #666; font-size: 11px;")

        color_info_box.addWidget(self.lbl_color_rgb)
        color_info_box.addWidget(self.lbl_color_hex)
        color_info_box.addWidget(self.lbl_brightness_val)
        color_info_box.addWidget(self.lbl_ha_status)
        preview_box.addLayout(color_info_box)

        top_card_layout.addLayout(preview_box, 4)
        main_layout.addWidget(top_card)

        # 2. TABBED CONFIGURATION
        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")

        self.tab_ha = QWidget()
        self.tab_capture = QWidget()
        self.tab_colors = QWidget()
        self.tab_logs = QWidget()

        self.setup_ha_tab()
        self.setup_capture_tab()
        self.setup_colors_tab()
        self.setup_logs_tab()

        self.tabs.addTab(self.tab_ha, "🏠 Home Assistant")
        self.tabs.addTab(self.tab_capture, "🖥️ Schermo")
        self.tabs.addTab(self.tab_colors, "🎨 Colore & Effetti")
        self.tabs.addTab(self.tab_logs, "📋 Log & Attività")

        main_layout.addWidget(self.tabs, 1)

        # 3. BOTTOM ACTIONS BAR
        bottom_bar = QHBoxLayout()
        bottom_bar.setContentsMargins(0, 0, 0, 0)

        self.btn_reset_defaults = QPushButton("↺  Ripristina Predefiniti")
        self.btn_reset_defaults.clicked.connect(self.reset_defaults)

        self.btn_save_config = QPushButton("💾  Salva Configurazione")
        self.btn_save_config.setObjectName("BtnSave")
        self.btn_save_config.clicked.connect(self.save_current_settings)

        self.btn_quit = QPushButton("✕  Chiudi ed Esci")
        self.btn_quit.setObjectName("BtnQuit")
        self.btn_quit.clicked.connect(self.close)

        bottom_bar.addWidget(self.btn_reset_defaults)
        bottom_bar.addStretch()
        bottom_bar.addWidget(self.btn_save_config)
        bottom_bar.addWidget(self.btn_quit)

        main_layout.addLayout(bottom_bar)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Pronto")

    def setup_ha_tab(self):
        layout = QVBoxLayout(self.tab_ha)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        form_group = QGroupBox("Parametri di Connessione Home Assistant")
        form_layout = QGridLayout(form_group)
        form_layout.setSpacing(12)

        # Server URL
        form_layout.addWidget(QLabel("URL Server:"), 0, 0)
        self.txt_ha_url = QLineEdit()
        self.txt_ha_url.setPlaceholderText("http://192.168.1.100:8123")
        form_layout.addWidget(self.txt_ha_url, 0, 1)

        # Token
        form_layout.addWidget(QLabel("Access Token:"), 1, 0)
        token_box = QHBoxLayout()
        self.txt_ha_token = QLineEdit()
        self.txt_ha_token.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_ha_token.setPlaceholderText("Long-Lived Access Token di Home Assistant")
        self.btn_toggle_token = QPushButton("👁️")
        self.btn_toggle_token.setFixedWidth(36)
        self.btn_toggle_token.setToolTip("Mostra / Nascondi Token")
        self.btn_toggle_token.clicked.connect(self.toggle_token_visibility)
        token_box.addWidget(self.txt_ha_token)
        token_box.addWidget(self.btn_toggle_token)
        form_layout.addLayout(token_box, 1, 1)

        # Entity ID
        form_layout.addWidget(QLabel("Entity ID Lampada:"), 2, 0)
        self.txt_ha_entity = QLineEdit()
        self.txt_ha_entity.setPlaceholderText("light.living_room_lamp")
        form_layout.addWidget(self.txt_ha_entity, 2, 1)

        # Timeout
        form_layout.addWidget(QLabel("Timeout Richieste (s):"), 3, 0)
        self.spin_ha_timeout = QDoubleSpinBox()
        self.spin_ha_timeout.setRange(0.2, 10.0)
        self.spin_ha_timeout.setSingleStep(0.1)
        self.spin_ha_timeout.setValue(2.0)
        form_layout.addWidget(self.spin_ha_timeout, 3, 1)

        layout.addWidget(form_group)

        # Buttons row for Testing Connection and Testing Lamp Color
        actions_row = QHBoxLayout()
        self.btn_test_conn = QPushButton("⚡  Verifica Connessione")
        self.btn_test_conn.setObjectName("BtnTestConn")
        self.btn_test_conn.setMinimumHeight(36)
        self.btn_test_conn.clicked.connect(self.test_ha_connection)

        self.btn_test_light = QPushButton("💡  Testa Luce (Invia Colore)")
        self.btn_test_light.setMinimumHeight(36)
        self.btn_test_light.setToolTip("Invia un colore di test arancione alla lampada per verificare la risposta fisica")
        self.btn_test_light.clicked.connect(self.send_test_color_to_lamp)

        actions_row.addWidget(self.btn_test_conn)
        actions_row.addWidget(self.btn_test_light)
        layout.addLayout(actions_row)

        # Test result banner
        self.lbl_test_result = QLabel("")
        self.lbl_test_result.setWordWrap(True)
        self.lbl_test_result.setStyleSheet("padding: 8px; border-radius: 6px;")
        self.lbl_test_result.hide()
        layout.addWidget(self.lbl_test_result)

        layout.addStretch()

    def setup_capture_tab(self):
        layout = QVBoxLayout(self.tab_capture)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Monitor selector
        mon_group = QGroupBox("Selezione Display e Prestazioni")
        mon_layout = QGridLayout(mon_group)
        mon_layout.setSpacing(12)

        mon_layout.addWidget(QLabel("Monitor da Catturare:"), 0, 0)
        mon_selector_box = QHBoxLayout()
        self.cmb_monitors = QComboBox()
        self.cmb_monitors.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.btn_refresh_monitors = QPushButton("🔄")
        self.btn_refresh_monitors.setFixedWidth(36)
        self.btn_refresh_monitors.setToolTip("Aggiorna elenco display")
        self.btn_refresh_monitors.clicked.connect(self.refresh_monitors)
        mon_selector_box.addWidget(self.cmb_monitors)
        mon_selector_box.addWidget(self.btn_refresh_monitors)
        mon_layout.addLayout(mon_selector_box, 0, 1)

        # FPS
        mon_layout.addWidget(QLabel("Frequenza Campionamento (FPS):"), 1, 0)
        fps_box = QHBoxLayout()
        self.slider_fps = QSlider(Qt.Orientation.Horizontal)
        self.slider_fps.setRange(1, 15)
        self.slider_fps.setValue(5)
        self.lbl_fps_val = QLabel("5 Hz")
        self.lbl_fps_val.setFixedWidth(45)
        self.slider_fps.valueChanged.connect(lambda v: self.lbl_fps_val.setText(f"{v} Hz"))
        fps_box.addWidget(self.slider_fps)
        fps_box.addWidget(self.lbl_fps_val)
        mon_layout.addLayout(fps_box, 1, 1)

        # Downsample dimensions
        mon_layout.addWidget(QLabel("Dimensioni Campione (WxH):"), 2, 0)
        dim_box = QHBoxLayout()
        self.spin_sample_w = QSpinBox()
        self.spin_sample_w.setRange(16, 320)
        self.spin_sample_w.setValue(64)
        self.spin_sample_h = QSpinBox()
        self.spin_sample_h.setRange(9, 180)
        self.spin_sample_h.setValue(36)
        dim_box.addWidget(QLabel("W:"))
        dim_box.addWidget(self.spin_sample_w)
        dim_box.addWidget(QLabel("H:"))
        dim_box.addWidget(self.spin_sample_h)
        dim_box.addStretch()
        mon_layout.addLayout(dim_box, 2, 1)

        layout.addWidget(mon_group)

        # Letterbox removal group
        lb_group = QGroupBox("Rilevamento Bande Nere (Film e Video)")
        lb_layout = QGridLayout(lb_group)
        lb_layout.setSpacing(12)

        self.chk_ignore_black = QCheckBox("Ignora bande nere superiori e inferiori (Letterbox 21:9)")
        lb_layout.addWidget(self.chk_ignore_black, 0, 0, 1, 2)

        lb_layout.addWidget(QLabel("Soglia Rilevamento Nero:"), 1, 0)
        thresh_box = QHBoxLayout()
        self.slider_black_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_black_thresh.setRange(0, 60)
        self.slider_black_thresh.setValue(18)
        self.lbl_black_thresh_val = QLabel("18")
        self.lbl_black_thresh_val.setFixedWidth(35)
        self.slider_black_thresh.valueChanged.connect(lambda v: self.lbl_black_thresh_val.setText(str(v)))
        thresh_box.addWidget(self.slider_black_thresh)
        thresh_box.addWidget(self.lbl_black_thresh_val)
        lb_layout.addLayout(thresh_box, 1, 1)

        layout.addWidget(lb_group)

        # Permissions helper
        perm_box = QHBoxLayout()
        btn_open_perms = QPushButton("⚙️  Apri Preferenze Privacy Schermo macOS")
        btn_open_perms.setToolTip("Consenti a MacAmbientSync l'accesso alla registrazione schermo se non cattura i colori delle finestre")
        btn_open_perms.clicked.connect(lambda: os.system('open "x-apple.systempreferences:com.apple.preference.security?Privacy_ScreenCapture"'))
        perm_box.addWidget(btn_open_perms)
        layout.addLayout(perm_box)

        layout.addStretch()

    def setup_colors_tab(self):
        layout = QVBoxLayout(self.tab_colors)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        color_group = QGroupBox("Miglioramento ed Elaborazione Colore")
        cg_layout = QGridLayout(color_group)
        cg_layout.setSpacing(12)

        # Saturation boost
        cg_layout.addWidget(QLabel("Boost Saturazione (Vivido):"), 0, 0)
        sat_box = QHBoxLayout()
        self.slider_sat = QSlider(Qt.Orientation.Horizontal)
        self.slider_sat.setRange(100, 250)
        self.slider_sat.setValue(135)
        self.lbl_sat_val = QLabel("1.35x")
        self.lbl_sat_val.setFixedWidth(45)
        self.slider_sat.valueChanged.connect(lambda v: self.lbl_sat_val.setText(f"{v/100:.2f}x"))
        sat_box.addWidget(self.slider_sat)
        sat_box.addWidget(self.lbl_sat_val)
        cg_layout.addLayout(sat_box, 0, 1)

        # Brightness boost
        cg_layout.addWidget(QLabel("Boost Luminosità:"), 1, 0)
        bright_box = QHBoxLayout()
        self.slider_bright_boost = QSlider(Qt.Orientation.Horizontal)
        self.slider_bright_boost.setRange(100, 200)
        self.slider_bright_boost.setValue(110)
        self.lbl_bright_boost_val = QLabel("1.10x")
        self.lbl_bright_boost_val.setFixedWidth(45)
        self.slider_bright_boost.valueChanged.connect(lambda v: self.lbl_bright_boost_val.setText(f"{v/100:.2f}x"))
        bright_box.addWidget(self.slider_bright_boost)
        bright_box.addWidget(self.lbl_bright_boost_val)
        cg_layout.addLayout(bright_box, 1, 1)

        # Min Brightness
        cg_layout.addWidget(QLabel("Luminosità Minima Lampada:"), 2, 0)
        min_b_box = QHBoxLayout()
        self.slider_min_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_min_bright.setRange(0, 100)
        self.slider_min_bright.setValue(25)
        self.lbl_min_bright_val = QLabel("25")
        self.lbl_min_bright_val.setFixedWidth(35)
        self.slider_min_bright.valueChanged.connect(lambda v: self.lbl_min_bright_val.setText(str(v)))
        min_b_box.addWidget(self.slider_min_bright)
        min_b_box.addWidget(self.lbl_min_bright_val)
        cg_layout.addLayout(min_b_box, 2, 1)

        # Max Brightness
        cg_layout.addWidget(QLabel("Luminosità Massima Lampada:"), 3, 0)
        max_b_box = QHBoxLayout()
        self.slider_max_bright = QSlider(Qt.Orientation.Horizontal)
        self.slider_max_bright.setRange(100, 255)
        self.slider_max_bright.setValue(255)
        self.lbl_max_bright_val = QLabel("255")
        self.lbl_max_bright_val.setFixedWidth(35)
        self.slider_max_bright.valueChanged.connect(lambda v: self.lbl_max_bright_val.setText(str(v)))
        max_b_box.addWidget(self.slider_max_bright)
        max_b_box.addWidget(self.lbl_max_bright_val)
        cg_layout.addLayout(max_b_box, 3, 1)

        # Smoothing factor
        cg_layout.addWidget(QLabel("Fluidità Transizioni (Smoothing):"), 4, 0)
        smooth_box = QHBoxLayout()
        self.slider_smoothing = QSlider(Qt.Orientation.Horizontal)
        self.slider_smoothing.setRange(5, 95)
        self.slider_smoothing.setValue(35)
        self.lbl_smoothing_val = QLabel("0.35")
        self.lbl_smoothing_val.setFixedWidth(40)
        self.slider_smoothing.valueChanged.connect(lambda v: self.lbl_smoothing_val.setText(f"{v/100:.2f}"))
        smooth_box.addWidget(self.slider_smoothing)
        smooth_box.addWidget(self.lbl_smoothing_val)
        cg_layout.addLayout(smooth_box, 4, 1)

        # Change threshold (sensitivity)
        cg_layout.addWidget(QLabel("Soglia di Variazione (Anti-spam HA):"), 5, 0)
        thresh_box = QHBoxLayout()
        self.slider_change_thresh = QSlider(Qt.Orientation.Horizontal)
        self.slider_change_thresh.setRange(1, 30)
        self.slider_change_thresh.setValue(8)
        self.lbl_change_thresh_val = QLabel("8")
        self.lbl_change_thresh_val.setFixedWidth(35)
        self.slider_change_thresh.valueChanged.connect(lambda v: self.lbl_change_thresh_val.setText(str(v)))
        thresh_box.addWidget(self.slider_change_thresh)
        thresh_box.addWidget(self.lbl_change_thresh_val)
        cg_layout.addLayout(thresh_box, 5, 1)

        # HA Transition time
        cg_layout.addWidget(QLabel("Tempo Transizione Home Assistant (s):"), 6, 0)
        trans_box = QHBoxLayout()
        self.spin_transition = QDoubleSpinBox()
        self.spin_transition.setRange(0.0, 3.0)
        self.spin_transition.setSingleStep(0.05)
        self.spin_transition.setValue(0.0)
        trans_box.addWidget(self.spin_transition)
        lbl_trans_hint = QLabel("(0.0 = istantaneo/senza ritardi)")
        lbl_trans_hint.setStyleSheet("color: #888; font-size: 11px;")
        trans_box.addWidget(lbl_trans_hint)
        trans_box.addStretch()
        cg_layout.addLayout(trans_box, 6, 1)

        layout.addWidget(color_group)
        layout.addStretch()

    def setup_logs_tab(self):
        layout = QVBoxLayout(self.tab_logs)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setObjectName("LogConsole")
        layout.addWidget(self.txt_logs, 1)

        log_actions = QHBoxLayout()
        self.chk_autoscroll = QCheckBox("Scorrimento automatico")
        self.chk_autoscroll.setChecked(True)
        
        self.btn_clear_logs = QPushButton("🗑️  Pulisci Log")
        self.btn_clear_logs.clicked.connect(self.txt_logs.clear)

        log_actions.addWidget(self.chk_autoscroll)
        log_actions.addStretch()
        log_actions.addWidget(self.btn_clear_logs)
        layout.addLayout(log_actions)

    def apply_theme(self):
        """Applies a clean, modern macOS dark theme stylesheet."""
        self.setStyleSheet("""
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
                font-size: 13px;
                color: #f0f0f2;
                background-color: #1a1a1e;
            }
            #TopCard {
                background-color: #24242b;
                border: 1px solid #363640;
                border-radius: 12px;
            }
            #BtnToggleSync {
                background-color: #28a745;
                color: white;
                font-weight: bold;
                font-size: 15px;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
            }
            #BtnToggleSync:hover {
                background-color: #2fb94d;
            }
            #BtnToggleSync.running {
                background-color: #e02424;
            }
            #BtnToggleSync.running:hover {
                background-color: #f03a3a;
            }
            #LblStatusBadge {
                font-weight: 500;
                color: #bbb;
                padding-left: 4px;
            }
            QTabWidget::pane {
                border: 1px solid #363640;
                border-radius: 8px;
                background-color: #222228;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1a1a1e;
                color: #8e8e99;
                padding: 8px 18px;
                margin-right: 4px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border: 1px solid transparent;
            }
            QTabBar::tab:selected {
                background-color: #222228;
                color: #ffffff;
                border: 1px solid #363640;
                border-bottom: 1px solid #222228;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background-color: #202026;
                color: #cccccc;
            }
            QGroupBox {
                border: 1px solid #363640;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 14px;
                font-weight: bold;
                color: #e0e0e0;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 5px;
            }
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
                background-color: #18181c;
                border: 1px solid #3c3c48;
                border-radius: 6px;
                padding: 6px 10px;
                color: #ffffff;
                selection-background-color: #007aff;
            }
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
                border: 1px solid #007aff;
            }
            QPushButton {
                background-color: #2d2d38;
                border: 1px solid #444455;
                border-radius: 6px;
                padding: 7px 14px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #383846;
                border-color: #55556a;
            }
            QPushButton:pressed {
                background-color: #1e1e24;
            }
            #BtnSave {
                background-color: #007aff;
                border-color: #0066cc;
                font-weight: bold;
            }
            #BtnSave:hover {
                background-color: #1a88ff;
            }
            #BtnQuit {
                background-color: #3a2222;
                border-color: #662222;
                color: #ff9999;
            }
            #BtnQuit:hover {
                background-color: #4a2828;
                border-color: #883333;
            }
            #BtnTestConn {
                background-color: #2c3e50;
                border-color: #34495e;
            }
            #BtnTestConn:hover {
                background-color: #34495e;
            }
            #LogConsole {
                background-color: #121214;
                border: 1px solid #363640;
                border-radius: 6px;
                font-family: Menlo, Monaco, "Courier New", monospace;
                font-size: 11px;
                color: #dcdcdc;
            }
            QSlider::groove:horizontal {
                border: none;
                height: 4px;
                background: #3c3c48;
                border-radius: 2px;
            }
            QSlider::sub-page:horizontal {
                background: #007aff;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #999;
                width: 14px;
                height: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QStatusBar {
                background-color: #161619;
                border-top: 1px solid #2a2a30;
                color: #888;
                font-size: 11px;
            }
        """)

    def refresh_monitors(self):
        """Populates the monitors dropdown."""
        curr_idx = self.cmb_monitors.currentData()
        self.cmb_monitors.clear()
        monitors = get_available_monitors()
        selected_found = False
        for mon in monitors:
            self.cmb_monitors.addItem(mon["name"], mon["index"])
            if mon["index"] == curr_idx:
                self.cmb_monitors.setCurrentIndex(self.cmb_monitors.count() - 1)
                selected_found = True

        if not selected_found and self.cmb_monitors.count() > 0:
            for i in range(self.cmb_monitors.count()):
                if self.cmb_monitors.itemData(i) == 1:
                    self.cmb_monitors.setCurrentIndex(i)
                    break

    def load_settings_to_ui(self):
        """Loads values from self.config into the input fields."""
        # Refresh monitors
        self.refresh_monitors()

        # HA Config
        ha_cfg = self.config.get("home_assistant", {})
        self.txt_ha_url.setText(ha_cfg.get("url", "http://192.168.1.100:8123"))
        self.txt_ha_token.setText(ha_cfg.get("token", ""))
        self.txt_ha_entity.setText(ha_cfg.get("entity_id", "light.your_rgb_lamp"))
        self.spin_ha_timeout.setValue(float(ha_cfg.get("timeout", 2.0)))

        # Capture Config
        cap_cfg = self.config.get("capture", {})
        target_mon = cap_cfg.get("monitor_index", 1)
        for i in range(self.cmb_monitors.count()):
            if self.cmb_monitors.itemData(i) == target_mon:
                self.cmb_monitors.setCurrentIndex(i)
                break

        fps = cap_cfg.get("fps", 5)
        self.slider_fps.setValue(fps)
        self.lbl_fps_val.setText(f"{fps} Hz")

        self.spin_sample_w.setValue(cap_cfg.get("sample_width", 64))
        self.spin_sample_h.setValue(cap_cfg.get("sample_height", 36))
        self.chk_ignore_black.setChecked(cap_cfg.get("ignore_black_bars", True))

        black_thresh = cap_cfg.get("black_threshold", 18)
        self.slider_black_thresh.setValue(black_thresh)
        self.lbl_black_thresh_val.setText(str(black_thresh))

        # Color Processing Config
        cp_cfg = self.config.get("color_processing", {})
        sat_boost = int(round(cp_cfg.get("saturation_boost", 1.35) * 100))
        self.slider_sat.setValue(sat_boost)
        self.lbl_sat_val.setText(f"{sat_boost/100:.2f}x")

        bright_boost = int(round(cp_cfg.get("brightness_boost", 1.10) * 100))
        self.slider_bright_boost.setValue(bright_boost)
        self.lbl_bright_boost_val.setText(f"{bright_boost/100:.2f}x")

        min_b = cp_cfg.get("min_brightness", 25)
        self.slider_min_bright.setValue(min_b)
        self.lbl_min_bright_val.setText(str(min_b))

        max_b = cp_cfg.get("max_brightness", 255)
        self.slider_max_bright.setValue(max_b)
        self.lbl_max_bright_val.setText(str(max_b))

        smooth = int(round(cp_cfg.get("smoothing_factor", 0.35) * 100))
        self.slider_smoothing.setValue(smooth)
        self.lbl_smoothing_val.setText(f"{smooth/100:.2f}")

        change_th = cp_cfg.get("change_threshold", 8)
        self.slider_change_thresh.setValue(change_th)
        self.lbl_change_thresh_val.setText(str(change_th))

        self.spin_transition.setValue(float(cp_cfg.get("transition_time", 0.0)))

    def get_settings_from_ui(self) -> dict:
        """Collects current UI values into a configuration dict."""
        mon_idx = self.cmb_monitors.currentData()
        if mon_idx is None:
            mon_idx = 1

        return {
            "home_assistant": {
                "url": self.txt_ha_url.text().strip(),
                "token": self.txt_ha_token.text().strip(),
                "entity_id": self.txt_ha_entity.text().strip(),
                "timeout": round(self.spin_ha_timeout.value(), 2)
            },
            "capture": {
                "monitor_index": mon_idx,
                "fps": self.slider_fps.value(),
                "sample_width": self.spin_sample_w.value(),
                "sample_height": self.spin_sample_h.value(),
                "ignore_black_bars": self.chk_ignore_black.isChecked(),
                "black_threshold": self.slider_black_thresh.value()
            },
            "color_processing": {
                "saturation_boost": round(self.slider_sat.value() / 100.0, 2),
                "brightness_boost": round(self.slider_bright_boost.value() / 100.0, 2),
                "min_brightness": self.slider_min_bright.value(),
                "max_brightness": self.slider_max_bright.value(),
                "smoothing_factor": round(self.slider_smoothing.value() / 100.0, 2),
                "change_threshold": self.slider_change_thresh.value(),
                "transition_time": round(self.spin_transition.value(), 2)
            }
        }

    def save_current_settings(self):
        """Saves current settings to disk and updates active worker."""
        self.config = self.get_settings_from_ui()
        if save_config(self.config):
            self.append_log("INFO", "Configurazione salvata con successo.")
            self.status_bar.showMessage("Configurazione salvata su disco", 3000)
            if self.worker and self.worker.isRunning():
                self.worker.update_config(self.config)
        else:
            self.append_log("ERROR", "Impossibile salvare la configurazione.")
            QMessageBox.critical(self, "Errore", "Impossibile salvare la configurazione.")

    def reset_defaults(self):
        """Resets all fields to default values."""
        reply = QMessageBox.question(
            self,
            "Ripristina Predefiniti",
            "Vuoi davvero ripristinare tutti i valori ai parametri predefiniti?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config = DEFAULT_CONFIG.copy()
            self.load_settings_to_ui()
            self.append_log("INFO", "Parametri reimpostati ai valori predefiniti.")

    def toggle_token_visibility(self):
        if self.txt_ha_token.echoMode() == QLineEdit.EchoMode.Password:
            self.txt_ha_token.setEchoMode(QLineEdit.EchoMode.Normal)
            self.btn_toggle_token.setText("🔒")
        else:
            self.txt_ha_token.setEchoMode(QLineEdit.EchoMode.Password)
            self.btn_toggle_token.setText("👁️")

    def test_ha_connection(self):
        """Tests Home Assistant API in a separate thread so UI does not freeze."""
        ha_cfg = {
            "url": self.txt_ha_url.text().strip(),
            "token": self.txt_ha_token.text().strip(),
            "entity_id": self.txt_ha_entity.text().strip(),
            "timeout": self.spin_ha_timeout.value()
        }

        self.btn_test_conn.setEnabled(False)
        self.btn_test_conn.setText("⏳ Verifica in corso...")
        self.lbl_test_result.hide()

        def run_test():
            client = HomeAssistantClient(ha_cfg)
            ok, msg = client.test_connection()
            return ok, msg

        def on_done(future_result):
            ok, msg = future_result
            self.btn_test_conn.setEnabled(True)
            self.btn_test_conn.setText("⚡  Verifica Connessione")
            self.lbl_test_result.show()
            if ok:
                self.lbl_test_result.setStyleSheet("background-color: #1e3d2f; color: #75f0a0; padding: 10px; border-radius: 6px; border: 1px solid #2e5d47;")
                self.lbl_test_result.setText(f"✓ {msg}")
                self.append_log("INFO", f"Test Connessione riuscito: {msg}")
            else:
                self.lbl_test_result.setStyleSheet("background-color: #3d1e1e; color: #f07575; padding: 10px; border-radius: 6px; border: 1px solid #5d2e2e;")
                self.lbl_test_result.setText(f"✗ {msg}")
                self.append_log("WARNING", f"Test Connessione fallito: {msg}")

        thread = threading.Thread(target=lambda: on_done(run_test()))
        thread.daemon = True
        thread.start()

    def send_test_color_to_lamp(self):
        """Sends a test color directly to Home Assistant light to verify hardware response."""
        ha_cfg = {
            "url": self.txt_ha_url.text().strip(),
            "token": self.txt_ha_token.text().strip(),
            "entity_id": self.txt_ha_entity.text().strip(),
            "timeout": self.spin_ha_timeout.value()
        }
        self.btn_test_light.setEnabled(False)
        self.btn_test_light.setText("⏳ Invio...")

        def run_test():
            client = HomeAssistantClient(ha_cfg)
            # Test color: Warm Orange
            ok, msg = client.update_light((255, 140, 30), 220, 0.0)
            return ok, msg

        def on_done(future_result):
            ok, msg = future_result
            self.btn_test_light.setEnabled(True)
            self.btn_test_light.setText("💡  Testa Luce (Invia Colore)")
            if ok:
                self.append_log("INFO", "💡 Colore di test arancione inviato con successo alla lampada!")
                self.status_bar.showMessage("Colore inviato alla lampada!", 4000)
            else:
                self.append_log("ERROR", f"Impossibile inviare colore alla lampada: {msg}")
                QMessageBox.warning(self, "Errore Test Luce", f"Impossibile inviare colore alla lampada: {msg}")

        thread = threading.Thread(target=lambda: on_done(run_test()))
        thread.daemon = True
        thread.start()

    def toggle_sync(self):
        """Starts or stops the screen sync worker."""
        if self.worker and self.worker.isRunning():
            self.stop_sync()
        else:
            self.start_sync()

    def start_sync(self):
        self.config = self.get_settings_from_ui()
        ha_cfg = self.config["home_assistant"]

        if not ha_cfg.get("token") or "INSERISCI" in ha_cfg.get("token") or "INSERT" in ha_cfg.get("token"):
            QMessageBox.warning(
                self,
                "Token Mancante",
                "Inserisci il tuo Long-Lived Access Token di Home Assistant nella scheda 'Home Assistant' prima di avviare la sincronizzazione."
            )
            self.tabs.setCurrentIndex(0)
            return

        # Start worker thread
        self.worker = SyncWorker(self.config)
        self.worker.color_updated.connect(self.on_color_updated)
        self.worker.log_emitted.connect(self.append_log)
        self.worker.error_occurred.connect(self.on_worker_error)
        self.worker.finished.connect(self.on_worker_stopped)
        self.worker.start()

        # Update UI state
        self.btn_toggle_sync.setText("⏹  Ferma Sincronizzazione")
        self.btn_toggle_sync.setStyleSheet("""
            background-color: #d32f2f;
            color: white;
            font-weight: bold;
            font-size: 15px;
            border: none;
            border-radius: 10px;
            padding: 10px 18px;
        """)
        mon_idx = self.config["capture"]["monitor_index"]
        self.lbl_status_badge.setText(f"🟢  In esecuzione (Monitor {mon_idx})")
        self.lbl_status_badge.setStyleSheet("color: #75f0a0; font-weight: bold;")
        self.status_bar.showMessage("Sincronizzazione schermo attiva")

    def stop_sync(self, wait=False):
        """Stops the worker thread cleanly."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            if wait:
                self.worker.wait(1500)
        self.on_worker_stopped()

    def on_worker_stopped(self):
        self.btn_toggle_sync.setText("▶  Avvia Sincronizzazione")
        self.btn_toggle_sync.setStyleSheet("""
            background-color: #28a745;
            color: white;
            font-weight: bold;
            font-size: 15px;
            border: none;
            border-radius: 10px;
            padding: 10px 18px;
        """)
        self.lbl_status_badge.setText("⚪  Stato: Inattivo")
        self.lbl_status_badge.setStyleSheet("color: #bbb; font-weight: normal;")
        self.lbl_ha_status.setText("Sincronizzazione fermata")
        self.status_bar.showMessage("Sincronizzazione fermata")

    def on_color_updated(self, rgb, brightness, sent, status_msg):
        """Updates color swatch and labels."""
        r, g, b = rgb
        hex_code = f"#{r:02X}{g:02X}{b:02X}"
        self.color_swatch.setStyleSheet(
            f"background-color: {hex_code}; border: 2px solid #555; border-radius: 12px;"
        )
        self.lbl_color_rgb.setText(f"RGB: {r}, {g}, {b}")
        self.lbl_color_hex.setText(f"HEX: {hex_code}")
        pct = int(round((brightness / 255.0) * 100))
        self.lbl_brightness_val.setText(f"Luminosità: {pct}% ({brightness}/255)")

        if sent:
            self.lbl_ha_status.setText("● Inviato a Home Assistant")
            self.lbl_ha_status.setStyleSheet("color: #75f0a0; font-size: 11px;")
        elif status_msg:
            self.lbl_ha_status.setText(status_msg)
            self.lbl_ha_status.setStyleSheet("color: #f0a075; font-size: 11px;")

    def on_worker_error(self, err_msg):
        self.lbl_status_badge.setText("🔴  Errore Sincronizzazione")
        self.lbl_status_badge.setStyleSheet("color: #f07575; font-weight: bold;")
        self.status_bar.showMessage(f"Errore: {err_msg}", 5000)

    def append_log(self, level, message):
        """Appends log entry to log tab."""
        t_str = time.strftime("%H:%M:%S")
        color = "#dcdcdc"
        if level == "ERROR":
            color = "#ff6b6b"
        elif level == "WARNING":
            color = "#feca57"
        elif level == "INFO":
            color = "#54a0ff"

        html = f"<span style='color:#777;'>[{t_str}]</span> <b style='color:{color};'>[{level}]</b> {message}"
        self.txt_logs.append(html)
        if self.chk_autoscroll.isChecked():
            self.txt_logs.moveCursor(self.txt_logs.textCursor().MoveOperation.End)

    def closeEvent(self, event):
        """Guarantees complete termination of the app when window is closed."""
        self.append_log("INFO", "Chiusura dell'applicazione richiesta...")
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(1000)
        
        # Save current window configuration
        save_config(self.get_settings_from_ui())

        event.accept()
        QApplication.instance().quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("MacAmbientSync")
    app.setOrganizationName("MarcoFabiani")
    app.setQuitOnLastWindowClosed(True)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
