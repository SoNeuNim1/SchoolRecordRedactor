"""Collect redistributable third-party license notices from the actual Windows build.
Copyright (C) 2026 소느님. SPDX-License-Identifier: AGPL-3.0-only.
"""
from __future__ import annotations
import importlib.metadata as metadata
import json
import shutil
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '_release_licenses'


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={'User-Agent': 'SchoolRecordRedactor-license-builder/4.0.1'})
    with urllib.request.urlopen(request, timeout=40) as res:
        content = res.read(300_000)
    if not content or len(content) > 290_000:
        raise RuntimeError('라이선스 파일 다운로드 크기 확인 실패: ' + url)
    return content


def _select_or_download(candidates, url, required, name):
    for candidate in candidates:
        if candidate is not None:
            p = Path(candidate)
            if p.is_file():
                data = p.read_bytes()
                if required.lower().encode("utf-8") in data.lower():
                    print('License from installed files:', name, p)
                    return data, str(p)
    data = _download(url)
    if required.lower().encode('utf-8') not in data.lower():
        raise RuntimeError(name + ' 공식 라이선스 검증 실패')
    print('License from upstream URL:', name, url)
    return data, url


def collect():
    """Gather applicable texts; fail build if license texts cannot be collected."""
    if sys.platform != 'win32':
        raise RuntimeError('실제 Windows 빌드 환경에서만 라이선스를 수집합니다.')
    import tkinter
    import PyInstaller
    import fitz
    if fitz.VersionBind != '1.26.7':
        raise RuntimeError('의도한 PyMuPDF 버전과 빌드 버전이 일치하지 않습니다.')
    OUT.mkdir(exist_ok=True)
    base = Path(sys.base_prefix)
    pyver = f'v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'
    python_data,py_source = _select_or_download(
        [base/'LICENSE.txt', base/'LICENSE',base/'Doc'/'license.rst'],
        f'https://raw.githubusercontent.com/python/cpython/{pyver}/LICENSE',
        'PYTHON SOFTWARE FOUNDATION LICENSE', 'Python')
    root_tcl = base/'tcl'
    tcl_ver = str(tkinter.Tcl().eval('info patchlevel'))
    root_dir = root_tcl / f'tcl{tcl_ver[:3]}'
    tk_dir = root_tcl / f'tk{tcl_ver[:3]}'
    tcl_data,tcl_source = _select_or_download(
        [root_dir/'license.terms', root_tcl/'tcl8.6'/'license.terms', root_tcl/'tcl8.7'/'license.terms'],
        'https://raw.githubusercontent.com/tcltk/tcl/core-8-6-branch/license.terms',
        'copyrighted by the Regents', 'Tcl')
    tk_data,tk_source = _select_or_download(
        [tk_dir/'license.terms', root_tcl/'tk8.6'/'license.terms',root_tcl/'tk8.7'/'license.terms'],
        'https://raw.githubusercontent.com/tcltk/tk/core-8-6-branch/license.terms',
        'copyrighted by the Regents', 'Tk')
    version=PyInstaller.__version__
    dist=metadata.distribution('pyinstaller')
    distbase=Path(dist.locate_file(''))
    installer_candidates=[]
    for fn in ('COPYING.txt','LICENSE.txt','COPYING','LICENSE'):
        installer_candidates.append(distbase/fn)
        installer_candidates.append(distbase/'PyInstaller'/fn)
        for item in list(dist.files or []):
            if item.name.casefold() == fn.casefold():
                installer_candidates.append(Path(dist.locate_file(item)))
    pi_data,pi_source = _select_or_download(
        installer_candidates,
        f'https://raw.githubusercontent.com/pyinstaller/pyinstaller/v{version}/COPYING.txt',
        'Bootloader Exception', 'PyInstaller')
    checks=[('Python-PSF-LICENSE.txt',python_data),('Tcl-license.terms',tcl_data),
            ('Tk-license.terms',tk_data),('PyInstaller-COPYING.txt',pi_data)]
    for name,data in checks:
        (OUT/name).write_bytes(data)
    shutil.copyfile(ROOT/'LICENSE',OUT/'SchoolRecordRedactor-AGPL-3.0.txt')
    shutil.copyfile(ROOT/'LICENSES'/'PyMuPDF-COPYING.txt',OUT/'PyMuPDF-COPYING.txt')
    notices = f'''SchoolRecordRedactor 4.0.1 - THIRD PARTY NOTICES

Copyright (C) 2026 소느님. The application source is AGPL-3.0-only.
The software is provided WITHOUT ANY WARRANTY; see the AGPL license.
You may redistribute and modify it under the terms of AGPL-3.0-only.

Third-party components in the executable:
- PyMuPDF 1.26.7 / MuPDF: Artifex Software, Inc. AGPL v3 or commercial license.
  Source: https://pypi.org/project/PyMuPDF/1.26.7/
- Python {sys.version.split()[0]}: Python Software Foundation License.
  License from: {py_source}
- Tcl/Tk {tcl_ver}: Tcl/Tk license terms.
  Tcl license from: {tcl_source}
  Tk license from: {tk_source}
- PyInstaller {version} and bundled bootloader: GPL-2.0-or-later with bootloader exception.
  Some runtime hooks have Apache-2.0 terms; see bundled PyInstaller COPYING.
  License from: {pi_source}

Full license texts appear in LICENSES/ alongside the executable.
Application corresponding source, build scripts and dependency versions:
  Download the matching SOURCE.zip beside the Windows binary on the
  publisher's download page. The publisher must supply a working link.

Official project: This software is NOT an official product of the Ministry of
Education, any education office, or NEIS.
PDF anonymization is NOT guaranteed. Review each output PDF before sharing.
'''
    (OUT/'THIRD_PARTY_NOTICES.txt').write_text(notices,encoding='utf-8')
    report={'app_version':'4.0.1','python':sys.version.split()[0],
            'tcl':tcl_ver,'pyinstaller':version,'pymupdf':fitz.VersionBind,
            'copyright':'Copyright (C) 2026 소느님',
            'licenses':[x for x,_ in checks]}
    (OUT/'LICENSES_MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return OUT


if __name__=='__main__':
    try:print('LICENSE COLLECTION:', collect())
    except Exception as e:
        print('LICENSE COLLECTION FAILED:',e)
        raise SystemExit(1)
