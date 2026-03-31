import os
import shutil
import subprocess
import sys

sys.setrecursionlimit(5000)

# macOS Sequoia+ adds com.apple.provenance to copied files, which prevents
# py2app/macholib from modifying Mach-O headers. Strip xattrs and ad-hoc
# signatures after each copy so the build can proceed.
_orig_copy2 = shutil.copy2

def _copy2_strip_provenance(src, dst, **kwargs):
    result = _orig_copy2(src, dst, **kwargs)
    dest = dst if not os.path.isdir(dst) else os.path.join(dst, os.path.basename(src))
    dest_str = os.fsdecode(dest)
    if dest_str.endswith(('.so', '.dylib')):
        subprocess.run(['xattr', '-c', dest], capture_output=True)
        subprocess.run(['codesign', '--remove-signature', dest], capture_output=True)
    return result

shutil.copy2 = _copy2_strip_provenance

from setuptools import setup
from writeless.constants import APP_VERSION

APP = ['app.py']
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'packages': ['writeless', 'rumps', 'sounddevice', '_sounddevice_data',
                 'faster_whisper', 'ctranslate2', 'numpy', 'pynput', 'certifi'],
    'excludes': ['torch', 'torchgen', 'scipy', 'sympy', 'numba',
                 'onnxruntime', 'torchaudio', 'torchvision'],
    'plist': {
        'CFBundleName': 'Write Less',
        'CFBundleDisplayName': 'Write Less',
        'CFBundleIdentifier': 'dev.romus.app.writeless',
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_VERSION,
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
