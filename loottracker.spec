# PyInstaller spec – builds a single Nihor2-Loottracker.exe
# Build:  pip install pyinstaller  &&  pyinstaller loottracker.spec
block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[],
    datas=[("loottracker/web", "loottracker/web")],
    hiddenimports=["tkinter", "tkinter.filedialog"],
    excludes=["unittest", "pydoc", "test"],
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
    name="Nihor2-Loottracker",
    debug=False,
    strip=False,
    upx=False,
    console=True,   # the console window shows the URL; closing it ends the tool
    icon=None,
)
