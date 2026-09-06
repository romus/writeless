import subprocess
import sys

sys.setrecursionlimit(5000)

# macOS Sequoia+ tags copied files with com.apple.provenance, which blocks
# codesign from touching them, and py2app's real file copies never go
# through shutil.copy2 — so strip xattrs/signatures right where py2app
# actually signs (codesign_adhoc) instead of trying to catch every copy.
import py2app.util

_orig_codesign_adhoc = py2app.util.codesign_adhoc

def _codesign_adhoc_strip_provenance(bundle):
    for file in py2app.util._macho_find(bundle):
        subprocess.run(['xattr', '-c', file], capture_output=True)
        subprocess.run(['codesign', '--remove-signature', file], capture_output=True)
    _orig_codesign_adhoc(bundle)

py2app.util.codesign_adhoc = _codesign_adhoc_strip_provenance

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
