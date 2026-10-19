# -*- mode: python ; coding: utf-8 -*-
# Portable one-file build reference (no absolute user-home paths).
# The authoritative release build is build_exe.py, which generates its own .spec.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all
ROOT = Path(SPECPATH)
all_datas = [(str(ROOT / 'LICENSE'), '.'),
             (str(ROOT / '_release_licenses'), 'LICENSES')]
all_binaries = []
all_hidden = []
for module_name in ('pymupdf','fitz'):
    data_files, binary_files, hidden = collect_all(module_name)
    all_datas.extend(data_files)
    all_binaries.extend(binary_files)
    all_hidden.extend(hidden)
a = Analysis([str(ROOT/'src'/'boot.py')],
    pathex=[str(ROOT/'src')], binaries=all_binaries, datas=all_datas,
    hiddenimports=all_hidden, hookspath=[], hooksconfig={},
    runtime_hooks=[], excludes=[], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
    name='SchoolRecordRedactor', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True,
    console=False)
