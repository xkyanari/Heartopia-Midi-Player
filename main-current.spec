# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import re


project_dir = Path.cwd()
app_config_path = project_dir / "app_config.py"
app_config_text = app_config_path.read_text(encoding="utf-8")
version_match = re.search(r'^APP_VERSION = "v(\d+)\.(\d+)\.(\d+)"$', app_config_text, re.MULTILINE)
if not version_match:
        raise RuntimeError("APP_VERSION must use the vMAJOR.MINOR.PATCH format")

major, minor, patch = (int(value) for value in version_match.groups())
version = f"{major}.{minor}.{patch + 1}"
app_config_path.write_text(
        re.sub(
                r'^APP_VERSION = "v[^\"]+"$',
                f'APP_VERSION = "v{version}"',
                app_config_text,
                count=1,
                flags=re.MULTILINE,
        ),
        encoding="utf-8",
)

version_file = project_dir / "version_info.txt"
version_file.write_text(
        f'''# UTF-8
VSVersionInfo(
    ffi=FixedFileInfo(
        filevers=({major}, {minor}, {patch + 1}, 0),
        prodvers=({major}, {minor}, {patch + 1}, 0),
        mask=0x3f,
        flags=0x0,
        OS=0x40004,
        fileType=0x1,
        subtype=0x0,
        date=(0, 0)
    ),
    kids=[
        StringFileInfo([
            StringTable(
                '040904B0',
                [StringStruct('CompanyName', 'Heartopia MIDI Player'),
                 StringStruct('FileDescription', 'MIDI player for Heartopia'),
                 StringStruct('FileVersion', '{version}'),
                 StringStruct('InternalName', 'Heartopia-Midi-Player'),
                 StringStruct('OriginalFilename', 'main-{version}.exe'),
                 StringStruct('ProductName', 'Heartopia MIDI Player'),
                 StringStruct('ProductVersion', '{version}')]
            )
        ]),
        VarFileInfo([VarStruct('Translation', [1033, 1200])])
    ]
)
''',
        encoding="utf-8",
)

from app_config import APP_VERSION

exe_name = f"main-{APP_VERSION.removeprefix('v')}"

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name=exe_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    version=version_file,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
