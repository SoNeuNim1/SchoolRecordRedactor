"""Reproducible-ish Windows EXE release builder for SchoolRecordRedactor v4.0.1.
Copyright (C) 2026 소느님. SPDX-License-Identifier: AGPL-3.0-only.

Run on 64-bit Windows with Python 3.10+. The OTHER PCs need no Python.
The build computer downloads dependencies; no student PDF is transmitted.
"""
from __future__ import annotations
import argparse, hashlib, json, platform, shutil, subprocess, sys, urllib.request, zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
NAME='SchoolRecordRedactor'
VERSION='4.0.1'
DIST=ROOT/'EXE_배포본'
PYMUPDF_SDIST_SHA256='71add8bdc8eb1aaa207c69a13400693f06ad9b927bea976f5d5ab9df0bb489c3'


def run(cmd, *, dry_run=False):
    print('>',subprocess.list2cmdline([str(x) for x in cmd]),flush=True)
    if not dry_run:
        subprocess.run([str(x) for x in cmd],check=True,cwd=ROOT)


def archive(zip_path,items):
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=8) as z:
        for src,dest in items:
            src=Path(src)
            if src.is_dir():
                for p in sorted(src.rglob('*')):
                    if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts:
                        z.write(p,Path(dest)/p.relative_to(src))
            elif src.is_file():
                z.write(src,dest)


def source_zip():
    result=DIST/f'{NAME}_v{VERSION}_SOURCE.zip'
    files=[]
    for file in (DIST/'BUILD_REQUIREMENTS_FROZEN.txt',):
        if file.exists():files.append((file,file.name))
    for directory in ('src','tests','samples','docs','LICENSES','.github','_release_licenses'):
        files.append((ROOT/directory,directory))
    for filename in ('LICENSE','README.md','CHANGELOG.md','build_exe.py',
                     'requirements-build.txt','requirements-runtime.txt',
                     '01_build_onefile.bat','02_build_folder.bat','license_assets.py','.gitignore',
                     '03_run_source.bat','PUBLIC_RELEASE_CHECKLIST.md','SchoolRecordRedactor.spec'):
        files.append((ROOT/filename,filename))
    archive(result,files)
    return result



def fetch_third_party_sources():
    """Download pinned upstream source tarball with published integrity hash.

    This provides the upstream source distribution alongside our own source;
    maintainers must still check complete corresponding-source obligations.
    """
    dst=DIST/'pymupdf-1.26.7.tar.gz'
    if dst.exists():
        with dst.open('rb') as f:
            checksum=hashlib.file_digest(f,'sha256').hexdigest()
        if checksum==PYMUPDF_SDIST_SHA256:
            print('Third-party source already verified:',dst)
            return dst
        dst.unlink()
    api='https://pypi.org/pypi/pymupdf/1.26.7/json'
    with urllib.request.urlopen(api,timeout=60) as f:
        release=json.load(f)
    choices=[x for x in release.get('urls',[]) if x.get('filename')=='pymupdf-1.26.7.tar.gz'
             and x.get('packagetype')=='sdist']
    if len(choices)!=1 or choices[0]['digests']['sha256']!=PYMUPDF_SDIST_SHA256:
        raise RuntimeError('공식 제3자 소스의 버전/해시 확인 실패')
    print('Downloading licensed upstream source (~84MB):',choices[0]['url'])
    temp=dst.with_suffix('.download')
    try:
        h=hashlib.sha256()
        with urllib.request.urlopen(choices[0]['url'],timeout=90) as r, temp.open('wb') as w:
            while True:
                block=r.read(1024*1024)
                if not block:break
                h.update(block);w.write(block)
        if h.hexdigest()!=PYMUPDF_SDIST_SHA256:
            raise RuntimeError('제3자 소스 SHA-256 불일치: 공개 금지')
        temp.rename(dst)
    finally:
        temp.unlink(missing_ok=True)
    print('Verified source SHA256',h.hexdigest())
    return dst

def build(mode='onefile',dry_run=False,skip_install=False,skip_third_party_source=False):
    if not dry_run:
        if sys.platform!='win32' or platform.architecture()[0]!='64bit':
            raise RuntimeError('Windows 64-bit에서 빌드해야 합니다.')
        if sys.version_info < (3,10):
            raise RuntimeError('Python 3.10 이상이 필요합니다 (빌드 PC에서만).')
    if not (ROOT/'src'/'app.py').exists():
        raise FileNotFoundError('ZIP을 완전히 압축 해제한 뒤 실행하세요.')
    DIST.mkdir(exist_ok=True)
    if not skip_install:
        run([sys.executable,'-m','pip','install','--disable-pip-version-check',
             '-r',str(ROOT/'requirements-build.txt')],dry_run=dry_run)
    if not dry_run:
        import fitz, PyInstaller
        from license_assets import collect
        if fitz.VersionBind != '1.26.7':
            raise RuntimeError('PyMuPDF 1.26.7이 필요합니다. 현재: '+fitz.VersionBind)
        print('Python:',sys.version.split()[0], 'PyMuPDF:',fitz.VersionBind,
              'PyInstaller:',PyInstaller.__version__)
        # Public sources must contain their own license and fictitious samples only.
        if not (ROOT/'LICENSE').exists() or not (ROOT/'LICENSES'/'PyMuPDF-COPYING.txt').exists():
            raise RuntimeError('라이선스 고지 파일이 없어 배포를 중단했습니다.')
    if not dry_run:
        # Collect license texts from the *actual* Windows build runtime.
        # If collection fails, do not emit a public release ZIP.
        license_dir=collect()
    else:
        license_dir=ROOT/'_release_licenses'
    if not dry_run:
        if skip_third_party_source:
            raise RuntimeError('공개 배포 빌드에서는 제3자 소스 생략 옵션을 사용할 수 없습니다.')
        # Source must be downloaded and validated before any public archive is produced.
        fetch_third_party_sources()
    modes=('onefile','onedir') if mode=='both' else (mode,)
    for m in modes:
        location=DIST/('single' if m=='onefile' else 'folder')
        cmd=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--windowed',
             '--'+m,'--name',NAME,'--collect-all=pymupdf','--collect-all=fitz',
             '--paths',str(ROOT/'src'),'--distpath',str(location),
             '--workpath',str(ROOT/'_build_temp'/m),
             '--specpath',str(ROOT/'_build_spec'/m),
             '--add-data',str(ROOT/'LICENSE')+ ';.',
             '--add-data',str(license_dir)+ ';LICENSES',
             str(ROOT/'src'/'boot.py')]
        run(cmd,dry_run=dry_run)
        if dry_run:continue
        exe=(location/(NAME+'.exe') if m=='onefile'
             else location/NAME/(NAME+'.exe'))
        if not exe.is_file() or exe.stat().st_size < 100_000:
            raise RuntimeError('EXE 생성 실패: '+str(exe))
        print('OK',exe)
        package=[]
        if m=='onefile':
            package.append((exe,NAME+'.exe'))
        else:
            package.append((location/NAME,NAME))
        for x in ('LICENSE','README.md','PUBLIC_RELEASE_CHECKLIST.md'):
            package.append((ROOT/x,x))
        package.append((license_dir,'LICENSES'))
        package.append((ROOT/'docs','docs'))
        zname=DIST/f'{NAME}_v{VERSION}_Windows_{m}.zip'
        archive(zname,package)
        print('PUBLIC ZIP',zname)
        sha=hashlib.sha256(exe.read_bytes()).hexdigest()
        (DIST/f'{NAME}_v{VERSION}_{m}.sha256.txt').write_text(
            f'{sha}  {exe.name}\n',encoding='ascii')
        print('SHA256',sha)
    if not dry_run:
        # Preserve the exact environment versions alongside the source and generated .spec.
        try:
            full = subprocess.check_output([sys.executable,'-m','pip','freeze'],
                                           text=True,encoding='utf-8',errors='replace',cwd=ROOT)
            (DIST/'BUILD_REQUIREMENTS_FROZEN.txt').write_text(full,encoding='utf-8')
        except Exception as e:
            raise RuntimeError('빌드에 사용한 패키지 버전 기록 실패') from e
        # Rebuild source ZIP including generated spec and version snapshots.
        src=source_zip()
        print('SOURCE ZIP',src)
        print('IMPORTANT: Keep SOURCE ZIP available alongside the Windows ZIP.')
        print('IMPORTANT: Complete PUBLIC_RELEASE_CHECKLIST.md before blogging.')


def main():
    pa=argparse.ArgumentParser()
    pa.add_argument('--mode',choices=['onefile','onedir','both'],default='onefile')
    pa.add_argument('--dry-run',action='store_true')
    pa.add_argument('--skip-install',action='store_true')
    pa.add_argument('--skip-third-party-source',action='store_true')
    args=pa.parse_args()
    try:build(args.mode,args.dry_run,args.skip_install,args.skip_third_party_source)
    except Exception as e:
        print('BUILD FAILED:',e,flush=True)
        raise SystemExit(1)

if __name__=='__main__':main()
