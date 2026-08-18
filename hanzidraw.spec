# hanzidraw.spec
# Build a Windows executable:  pyinstaller hanzidraw.spec
# The character database is NOT bundled; the app builds it on first run.
block_cipher = None

a = Analysis(
    ["src/hanzidraw/__main__.py"],
    pathex=["src"],
    hiddenimports=["PySide6.QtSvg"],
    datas=[("NOTICE", ".")],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name="hanzidraw",
    console=False,
    upx=False,
)
