# MacAmbientSync

MacAmbientSync is a modern, lightweight macOS desktop application that captures your screen colors in real time and synchronizes them with **Home Assistant** RGB lights (lamps, LED strips, lightbars). Engineered with an ultra-efficient capture pipeline for near-zero CPU usage (<1%) and cinematic, vivid color reproduction.

---

## ✨ Features

* 🖥️ **Modern Native macOS GUI**: Full desktop interface built with PyQt6 featuring a sleek dark theme, real-time controls, instant parameter tuning, and live status badges without needing to manually edit configuration files.
* 🚀 **Automatic Synchronization on Launch**: Automatically detects existing Home Assistant credentials and starts ambient syncing as soon as the app is opened.
* 🛑 **Clean & Instant Shutdown**: Closing the window or pressing `Cmd+Q` / `Cmd+W` immediately terminates capture threads and network loops with zero orphan background processes.
* 🎨 **Cinematic Ambilight Color Algorithm**:
  * HSV saturation boost to prevent dull or washed-out lighting.
  * Weighted luminance filtering that eliminates false tints on dark or gray scenes.
  * Exponential Moving Average (EMA) smoothing for fluid, stutter-free transitions.
  * Dynamic brightness scaling with configurable minimum and maximum thresholds.
* 📺 **Intelligent Letterbox Detection**: Automatically detects and ignores horizontal movie black bars (e.g. 21:9 aspect ratios) so only active video content is analyzed.
* ⚡ **Ultra-Low CPU (<1%) & Network Throttle**: High-speed memory-based downsampling with `mss` and sensitivity thresholding to protect your local network and Home Assistant from request flooding.
* 🖥️ **Multi-Monitor Support**: Choose between your built-in Mac display, external monitors, or an all-monitors combined mode with dynamic real-time switching.
* 🔍 **Live Video & Color Preview**: Live thumbnail showing the downscaled screen capture alongside dominant RGB, HEX values, and brightness percentages.
* ⚡ **Built-In Connection & Hardware Testing**: Integrated "Test Connection" button for API verification and a "Test Light" button to pulse an orange color to your lamp.
* 🔓 **macOS Permission Diagnostics**: Built-in status check and direct shortcut to macOS *System Settings → Privacy & Security → Screen Recording*.

---

## 📋 Requirements

* macOS 12 Monterey, macOS 13 Ventura, macOS 14 Sonoma, or macOS 15 Sequoia
* Python 3.9 or newer
* A working **Home Assistant** instance on your local network
* An RGB, RGBW, or RGBWW light entity configured in Home Assistant

---

## 🚀 Quick Start

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/fabianimarco98/MacAmbientSync.git
cd MacAmbientSync

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Launch the Desktop Application

```bash
source venv/bin/activate
python3 app.py
```

*(Optional)* If you prefer running without a GUI in headless / CLI mode:
```bash
python3 screen_sync.py
```

---

## ⚙️ Configuration Guide

Within the application interface:

### 🏠 Home Assistant Tab
* **Server URL**: The local IP address and port of your Home Assistant server (e.g., `http://192.168.1.100:8123`).
* **Access Token**: A **Long-Lived Access Token** generated from your Home Assistant profile (*Profile → Security → Long-Lived Access Tokens*).
* **Light Entity ID**: The target light entity name (e.g., `light.living_room_lamp` or `light.desk_strip`).
* **Request Timeout**: Network timeout in seconds (default: `2.0s`).
* **Test Connection**: Validates token and entity reachability.
* **Test Light**: Sends an immediate orange test pulse to verify physical lamp control.

### 🖥️ Screen Tab
* **Target Display**: Select which screen to capture (Built-in Display, External Monitor, or All Combined).
* **Sampling Frequency (FPS)**: Capture rate (default: `4 Hz`). 3–5 Hz is recommended for Zigbee, Z-Wave, and Wi-Fi lamps.
* **Sample Dimensions**: Downscaled resolution (default: `64x36`) for near-zero CPU usage.
* **Black Bar Detection**: Filters out top/bottom black borders during 21:9 widescreen movies.

### 🎨 Color & Effects Tab
* **Saturation Boost**: Multiplier to enhance vividness (default: `1.35x`).
* **Brightness Boost**: Multiplier for scene brightness (default: `1.10x`).
* **Minimum / Maximum Brightness**: Keeps the lamp dimly lit during pitch-black movie scenes without completely switching off.
* **Transition Smoothing (EMA)**: Exponential smoothing factor (`0.10` = ultra-smooth, `0.90` = immediate response).
* **Change Threshold**: Sensitivity threshold to suppress redundant Home Assistant state updates.
* **Home Assistant Transition Time**: Native fade transition duration reported to Home Assistant in seconds.

Click **💾 Save Configuration** to persist your settings to disk (`~/Library/Application Support/MacAmbientSync/config.yaml`).

---

## 🔒 macOS Permissions

macOS requires explicit permission for apps to capture screen contents:

1. When first running the app, macOS will prompt for **Screen Recording** permissions.
2. If the app displays only your wallpaper or dark purple/gray tones, navigate to:
   **System Settings → Privacy & Security → Screen Recording**
3. Ensure your terminal (Terminal, iTerm2, VS Code, etc.) or **MacAmbientSync** is toggled **ON**.
4. The app interface also includes a direct **"Open macOS Privacy & Security Settings"** shortcut button.

> [!NOTE]
> If you are using a VPN (e.g., Cisco AnyConnect) that blocks local LAN access, enable *Allow Local LAN Access* in your VPN client or disconnect to reach Home Assistant.

---

## 📦 Building Standalone macOS App (.app)

### Option A: Using py2app

```bash
source venv/bin/activate
pip install py2app
python setup.py py2app
```

The compiled application bundle will be created at `dist/MacAmbientSync.app`.

### Option B: Using PyInstaller

```bash
source venv/bin/activate
pip install pyinstaller
pyinstaller MacAmbientSync.spec
```

The generated application bundle will be located at `dist/MacAmbientSync.app`.

---

## 📂 Project Structure

```text
MacAmbientSync/
├── app.py                  # PyQt6 Desktop GUI application
├── screen_sync.py          # Screen capture engine & Home Assistant client
├── config.example.yaml     # Example configuration file
├── setup.py                # py2app packaging script
├── MacAmbientSync.spec     # PyInstaller bundle specification
├── requirements.txt        # Python package dependencies
└── README.md               # Documentation
```

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.
