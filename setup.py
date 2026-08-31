from setuptools import setup

APP = ['app.py']
DATA_FILES = ['config.example.yaml']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': '', # You can add an icon.icns here
    'plist': {
        'CFBundleName': 'MacAmbientSync',
        'CFBundleDisplayName': 'MacAmbientSync',
        'CFBundleIdentifier': 'com.marcofabiani.macambientsync',
        'CFBundleVersion': '1.1.0',
        'CFBundleShortVersionString': '1.1.0',
        'NSRequiresAquaSystemAppearance': False,
        'NSScreenCaptureUsageDescription': 'MacAmbientSync needs screen recording permissions to capture screen colors in real-time.',
        'NSCameraUsageDescription': 'MacAmbientSync needs screen capture permissions to analyze screen colors.',
    },
    'packages': ['PyQt6', 'mss', 'PIL', 'yaml']
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
