from setuptools import setup

APP = ['app.py']
DATA_FILES = ['config.example.yaml']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': '', # You can add an icon.icns here
    'plist': {
        'LSUIElement': True, # Runs as a menubar-only app (no dock icon)
        'CFBundleName': 'MacAmbientSync',
        'CFBundleDisplayName': 'MacAmbientSync',
        'CFBundleIdentifier': 'com.marcofabiani.macambientsync',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        # To avoid problems with screen recording permissions:
        'NSCameraUsageDescription': 'This app needs screen recording permissions to capture screen colors.',
    },
    'packages': ['rumps', 'mss', 'PIL', 'yaml']
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
