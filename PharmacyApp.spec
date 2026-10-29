# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for Pharmacy Management System desktop application.
Configured for PyInstaller 6.x on Windows (Python 3.13 64-bit).
Conservative build: onedir mode, UPX disabled, assets explicitly collected.
"""
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

# Collect CustomTkinter themes (green.json), fonts, icons, and Matplotlib mpl-data
datas = []
datas += collect_data_files('customtkinter')
datas += collect_data_files('matplotlib')

# Targeted hidden imports for dynamically loaded backends
hiddenimports = [
    'matplotlib.backends.backend_tkagg',
    'PIL._tkinter_finder',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'IPython', 'jupyter', 'notebook', 'scipy', 'sklearn',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PharmacyApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX explicitly disabled
    console=False,  # Windowed GUI application
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # UPX explicitly disabled
    upx_exclude=[],
    name='PharmacyApp',
)
