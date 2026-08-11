# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['src/planning_toolbox/gui/__init__.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/planning_toolbox/config/*.yaml', 'planning_toolbox/config'),
        ('src/planning_toolbox/knowledge/*.json', 'planning_toolbox/knowledge'),
        ('src/planning_toolbox/gis/arcpy_worker.py', 'planning_toolbox/gis'),
        ('src/planning_toolbox/sketchup/plugin', 'planning_toolbox/sketchup/plugin'),
        ('config/*.yaml', 'config'),
        ('assets/planning_toolbox.ico', 'assets'),
    ],
    hiddenimports=[
        'planning_toolbox',
        'planning_toolbox.gui',
        'planning_toolbox.cad',
        'planning_toolbox.gis',
        'planning_toolbox.indicators',
        'planning_toolbox.validators',
        'planning_toolbox.utils',
        # Imported lazily by the GUI worker; keep these explicit so the
        # packaged black/white centreline conversion works reliably.
        'planning_toolbox.cad.planning.image_to_dxf',
        'planning_toolbox.knowledge.image_cards',
        'planning_toolbox.knowledge.sketchup_components',
        'planning_toolbox.knowledge.sketchup_modeling',
        'planning_toolbox.mcp_server',
        'skimage.measure',
        'skimage.morphology',
        'PySide6.QtCore',
        'PySide6.QtWidgets',
        'PySide6.QtGui',
        'openpyxl',
        'reportlab.pdfbase.cidfonts',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The application uses PySide6 exclusively.  Some scientific Python
    # environments also install PyQt5, which PyInstaller cannot freeze
    # alongside PySide6 in the same executable.
    # Keep the desktop distribution focused on runtime dependencies.  These
    # packages are optional development/notebook integrations pulled in by
    # scientific-library introspection and are not used by Planning Toolbox.
    excludes=[
        'PyQt5',
        'PyQt6',
        'pytest',
        '_pytest',
        'IPython',
        'jedi',
        'parso',
        'docutils',
        'sphinx',
        'astroid',
        'black',
        'yapf',
        'nbformat',
        'notebook',
        'jupyter',
        'dask',
        'distributed',
        'numba',
        'llvmlite',
        'tkinter',
        '_tkinter',
        'astropy',
        'astropy_iers_data',
        'zmq',
        'cloudpickle',
        'pandas',
        # Optional GIS adapters remain external so the base desktop package
        # stays small. QGIS/GDAL is detected and called through ogr2ogr.
        'pyproj',
        'pyogrio',
        'geopandas',
        'osgeo',
        'arcpy',
        'pyarrow',
        'pytz',
        'fsspec',
        'boto3',
        'botocore',
        'tables',
        'sqlalchemy',
        'cryptography',
        'bcrypt',
        'qtpy',
        'sklearn',
        'torch',
        'cupy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
    icon='assets/planning_toolbox.ico',
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='PlanningToolbox',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
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
    upx=False,
    upx_exclude=[],
    name='PlanningToolbox',
)
