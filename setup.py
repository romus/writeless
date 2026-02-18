import sys
sys.setrecursionlimit(5000)

from setuptools import setup

APP = ['app.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'packages': ['writeless', 'rumps', 'sounddevice', '_sounddevice_data', 'whisper',
                 'torch', 'numpy', 'scipy', 'pynput', 'tiktoken', 'tqdm'],
    'plist': {
        'CFBundleName': 'Write Less',
        'CFBundleDisplayName': 'Write Less',
        'CFBundleIdentifier': 'dev.romus.app.writeless',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'LSUIElement': True,
        'NSMicrophoneUsageDescription':
            'Write Less needs microphone access to record and transcribe your speech.',
        'NSAccessibilityUsageDescription':
            'Write Less needs accessibility access for the global Cmd+Option+F8 hotkey.',
    },
}

setup(
    name='Write Less',
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
