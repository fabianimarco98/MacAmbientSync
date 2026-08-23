# MacAmbientSync

MacAmbientSync is a lightweight macOS App (with a Menu Bar icon) that captures your Mac screen in real-time, calculates the dominant or average color of the scene, and synchronizes an RGB lamp or LED strip connected to Home Assistant. Optimized to have near-zero impact on your CPU.

## Features

*   **Native Menu Bar App**: A status bar icon in the top right to easily start/stop the sync or edit settings.
*   **Extremely low CPU impact**: Uses extreme downscaling before color calculation to ensure CPU usage stays under 1%.
*   **Vivid colors**: Applies a saturation and brightness boost (configurable) to avoid dull or gray lighting effects.
*   **Black bar removal**: Automatically detects and ignores the "letterbox" format (e.g., 21:9 movies).
*   **Smoothing and efficiency**: Uses exponential moving average for smooth color transitions and avoids useless network calls to Home Assistant if the color variation is minimal.

## Installation for End Users

1. Download and unzip `MacAmbientSync.app` from the latest release.
2. Move the App to your **Applications** folder.
3. Click the palette icon 🎨 in your menu bar.
4. Click on **Edit Config...** to configure:
   * `url`: your Home Assistant address (e.g., `http://192.168.1.100:8123`)
   * `token`: your Home Assistant Long-Lived Access Token
   * `entity_id`: the entity ID of your lamp (e.g., `light.living_room_lamp`)
5. Click on **Start Sync**! The icon will turn 🔴 to indicate that screen capture is active.

## Building from Source (For Developers)

If you want to compile the app yourself from source:

1.  Clone this repository.
2.  Create a Python virtual environment and install dependencies:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    pip install py2app
    ```
3.  Run the build command:
    ```bash
    python setup.py py2app
    ```
4.  You will find the ready-to-use application in the `dist/MacAmbientSync.app` folder.

## Advanced Configuration

In the `config.yaml` file (accessible via the `Edit Config...` menu) you can adjust several parameters:

*   `fps`: Sampling frequency. 3-5 Hz is often optimal.
*   `monitor_index`: Which monitor to capture (useful if you use external displays).
*   `saturation_boost`: Value > 1 to enhance colors.
*   `smoothing_factor`: Lower value (e.g., 0.2) for smooth transitions, higher value (e.g., 0.8) for fast changes.
