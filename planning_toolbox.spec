# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/planning_toolbox/gui/__init__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/planning_toolbox/config/*.yaml', 'planning_toolbox/config'),
        ('config/*.yaml', 'config'),
    ],
    hiddenimports=[
        'planning_toolbox',
        'planning_toolbox.gui',
        'planning_toolbox.cad',
        'planning_toolbox.gis',
        'planning_toolbox.indicators',
        'planning_toolbox.validators',
        'planning_toolbox.utils',
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PlanningToolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
