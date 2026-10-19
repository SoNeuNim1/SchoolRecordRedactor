"""SchoolRecordRedactor v4.0 - local-only format-aware PDF redaction.

Copyright (C) 2026 소느님. SPDX-License-Identifier: AGPL-3.0-only.

Local-only, format-aware actual PDF redaction for Korean school records.

No OCR: refuse scan-only / unsupported layout rather than silently claiming success.
All supplied PDFs remain unchanged. Graphic lines are NEVER erased by text redaction.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict
import os
import re
import uuid
import fitz

APP_VERSION = '4.0'
SUFFIX = "(모의면접용)"
FOOTER_FIELDS = (('keep_class','반'),('keep_number','번호'),('keep_name','성명'))
SAFE_PERSON_LABELS = {'성명','성별','주민등록번호','주민번호','주소','생년월일','학생정보','학적사항',':','：','사진','연락처', '전화번호', '국적'}
RRN_RE = re.compile(r'(?<!\d)\d{6}\s*[-‐–]?\s*\d{7}(?!\d)')
DATE_FOOTER_RE = re.compile(r"(?:19|20)\d{2}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일|(?:19|20)\d{2}[./-]\d{1,2}[./-]\d{1,2}\.?")
PRINT_KEYWORDS = ('출력일시','출력일자','출력자','출력교사','출력한','출력일','인쇄일','발급일시','인쇄자','담당교사')
TITLE_KEYWORDS = ('학교생활세부사항기록부','학교생활기록부')

@dataclass(frozen=True)
class Options:
    # The student's class and seat number are one "학번 유지" option.
    keep_student_id: bool = True
    keep_name: bool = True


@dataclass
class Result:
    pages: int
    removed_areas: int
    school_name: str
    notes: list[str]


class UnsupportedLayout(ValueError):
    pass


def is_generated_name(name: str) -> bool:
    return SUFFIX in Path(name).stem


def destination_for(source: Path, output_dir: Path) -> Path:
    return output_dir / (source.stem + SUFFIX + '.pdf')


def _words(page: fitz.Page):
    return list(page.get_text('words', sort=True))


def _tight_rect(w, *, left=0.45, right=0.45, up=0.45, down=0.45):
    return fitz.Rect(w[0]-left, w[1]-up, w[2]+right, w[3]+down)


def _find_school(doc: fitz.Document) -> str:
    page = doc[0]
    candidates = [w for w in _words(page)
                  if w[1] > page.rect.height*.88 and w[0] < page.rect.width*.42
                  and any(s in w[4] for s in ('고등학교','중학교','초등학교'))]
    return str(sorted(candidates, key=lambda w: w[1])[-1][4]) if candidates else ''


def _check_document(doc: fitz.Document):
    if len(doc) == 0:
        raise UnsupportedLayout('페이지가 없는 PDF입니다.')
    if doc.needs_pass:
        raise UnsupportedLayout('암호로 보호된 PDF는 지원하지 않습니다.')
    first = doc[0].get_text()
    if not any(t in first for t in TITLE_KEYWORDS):
        raise UnsupportedLayout('지원하는 학교생활기록부 양식이 아닙니다. 자동 삭제를 중단했습니다.')
    if not (('학생정보' in first or '인적' in first) and '성명' in first):
        raise UnsupportedLayout('첫 페이지 인적사항을 찾을 수 없습니다. 자동 삭제를 중단했습니다.')
    if any(page.rotation != 0 for page in doc):
        raise UnsupportedLayout('회전된 페이지가 있는 PDF는 자동 삭제를 지원하지 않습니다.')
    if len(_words(doc[0])) < 15:
        raise UnsupportedLayout('스캔 이미지이거나 텍스트가 없는 PDF입니다. 자동 삭제를 지원하지 않습니다.')


def _footer_labels(page: fitz.Page) -> dict[str, tuple]:
    words = _words(page)
    labels = {}
    for key, literal in FOOTER_FIELDS:
        matches = [w for w in words if str(w[4]).strip() == literal
                   and w[1] > page.rect.height*.87]
        if not matches:
            raise UnsupportedLayout(f'{page.number+1}쪽 하단의 {literal} 필드를 찾지 못했습니다. 파일을 건너뜁니다.')
        labels[key] = sorted(matches, key=lambda w: w[1])[-1]
    if not(labels['keep_class'][0] < labels['keep_number'][0] < labels['keep_name'][0]):
        raise UnsupportedLayout(f'{page.number+1}쪽 하단 식별정보 순서가 예상과 다릅니다.')
    baseline = [labels[k][1] for k, _ in FOOTER_FIELDS]
    if max(baseline)-min(baseline)>9:
        raise UnsupportedLayout(f'{page.number+1}쪽 하단 식별정보가 동일한 줄에 있지 않습니다.')
    return labels


def _footer_private_words(page: fitz.Page, labels: dict, options: Options):
    words = _words(page)
    fields = list(FOOTER_FIELDS)
    rects = []
    for idx, (key, name) in enumerate(fields):
        keep = options.keep_name if key == 'keep_name' else options.keep_student_id
        if keep:
            continue
        start = labels[key][0] - .5
        stop = (labels[fields[idx+1][0]][0] - .5 if idx < len(fields)-1
                else page.rect.width - 20)
        y = labels[key][1]
        for w in words:
            if start <= (w[0]+w[2])/2 < stop and abs(w[1]-y)<6:
                rects.append(_tight_rect(w))
    return rects


def _personal_words(page: fitz.Page):
    """Erase VALUES inside first-page personal-data row; preserve printed labels and grid."""
    words = _words(page)
    student_header = next((w for w in words if w[4]=='학생정보'), None)
    academic_header = next((w for w in words if w[4]=='학적사항'), None)
    if student_header is None or academic_header is None:
        raise UnsupportedLayout('첫 페이지 학생정보/학적사항 표를 인식하지 못했습니다.')
    if not student_header[1] < academic_header[1]:
        raise UnsupportedLayout('인적사항 위치가 예상과 다릅니다.')
    # Student-info rectangle: sensitive values often share a line with labels,
    # possibly multiple lines. Exclude outer row borders and static labels.
    y0 = student_header[1]-19
    y1 = academic_header[1]-7
    if y1-y0 < 20 or y1-y0 > page.rect.height*.22:
        raise UnsupportedLayout('학생정보 영역 크기가 예상 범위를 벗어납니다.')
    rects=[]
    for w in words:
        text = str(w[4]).strip()
        if w[0] >= student_header[2] + 4 and y0 <= (w[1]+w[3])/2 <= y1:
            if text.rstrip(':：') not in SAFE_PERSON_LABELS:
                rects.append(_tight_rect(w))
    # Extra printed values above '1. 인적·학적사항', e.g. class identity, department
    # and personal student numbers; do not delete first column's printed year numbers.
    section = next((w for w in words if '인적·학적사항' in w[4]), None)
    if section:
        start = page.rect.height*.14
        finish = section[1]-8
        for w in words:
            if w[0] >= page.rect.width*.19 and start < w[1] < finish:
                if w[4] not in {'학과','구분','학년'}:
                    rects.append(_tight_rect(w))
    # Some layouts place the RRN and address in additional rows inside the
    # student-data box. Redact their values (not grid) anywhere before academic row.
    for w in words:
        if w[0] > page.rect.width*.15 and w[1] > student_header[1]-25 and w[3] < academic_header[1]-4:
            if str(w[4]).rstrip(':：') not in SAFE_PERSON_LABELS:
                rects.append(_tight_rect(w))
    return rects


def _photo_rect(page: fitz.Page) -> fitz.Rect:
    # Printed NEIS school-record photo area in example layout; clipping applies
    # to image pixels only, not vector grid lines (graphics=0).
    r=page.rect
    return fitz.Rect(r.width*.765,r.height*.143,r.width*.956,r.height*.305)


def _date_teacher_words(page: fitz.Page, labels: dict):
    """Delete print-date and print-user text without touching page numbers or
    optional class/number/name identity boxes at the bottom of each page.

    A print date is not always in the lowest 5% of the page. Detect its
    literal date structure on the footer line, independent of page count.
    """
    words = _words(page)
    left_identity = labels['keep_class'][0]
    min_y = page.rect.height * .875
    lines = defaultdict(list)
    for w in words:
        cx = (w[0] + w[2]) / 2
        if w[1] >= min_y and cx < left_identity - 3:
            lines[(w[5], w[6])].append(w)
    rects = []
    for line in lines.values():
        line.sort(key=lambda w: w[0])
        text = ' '.join(str(w[4]) for w in line)
        parts = []
        offset = 0
        for w in line:
            start = offset
            offset += len(str(w[4]))
            parts.append((start, offset, w))
            offset += 1
        spans = [m.span() for m in DATE_FOOTER_RE.finditer(text)]
        for start, end in spans:
            for w_start, w_end, w in parts:
                if w_start < end and w_end > start:
                    rects.append(_tight_rect(w, left=.15, right=.15, up=.15, down=.15))
        # Print operator / issue-by line. Only trim text on the left of the
        # identity fields so the student identification toggle is respected.
        if any(k in text.replace(' ', '') for k in PRINT_KEYWORDS):
            rects.extend(_tight_rect(w, left=.15, right=.15, up=.15, down=.15) for w in line)
    return rects


def _bottom_print_strip(page: fitz.Page, labels: dict) -> fitz.Rect:
    """Erase the separate tiny print trail BELOW the page-number / identity row.

    NEIS printouts can put "2026.10.19 11:01 / network address / operator"
    into their own bottom-most line. It may be fragmented, tiny, rasterized, or
    stored as vector drawings. A narrow bottom margin cut, starting *after*
    the identity cells, is more reliable than text regex and does not touch the
    page number, student's class, number, name, or the table's border.
    """
    # Printed footer field characters end just above the bottom table border.
    # Leave 3pt under the text so the existing cell border stays untouched.
    y = max(w[3] for w in labels.values()) + max(3.,page.rect.height*.004)
    # Fail closed for page templates where the footer has moved too far up:
    # such a large strip might otherwise eat school-record contents.
    if not page.rect.height*.92 <= y <= page.rect.height*.975:
        raise UnsupportedLayout(
            f'{page.number+1}쪽의 하단 위치가 예상과 달라 출력정보를 안전하게 지울 수 없습니다.')
    return fitz.Rect(0, y, page.rect.width, page.rect.height)


def _middle_school_words(page: fitz.Page):
    """Redact the student's prior middle-school name in first-page 학적사항.

    Do not erase the graduation date, grade or graduation wording. Works with
    school name either joined (OO중학교) or split (OO 중학교).
    """
    words = _words(page)
    header = next((w for w in words if str(w[4]).strip() == '학적사항'), None)
    if not header:
        raise UnsupportedLayout('첫 페이지 학적사항을 인식하지 못했습니다.')
    next_section = next((w for w in words if w[1] > header[1]+16 and
                         (str(w[4]).startswith('출결상황') or str(w[4]) == '2.')), None)
    end_y = next_section[1] if next_section else header[1] + 82
    start_y = header[1] - 18
    academic = [w for w in words if start_y < (w[1]+w[3])/2 < end_y-7
                and w[0] >= header[2]+3]
    rects = []
    for w in academic:
        val = str(w[4]).strip()
        if '중학교' not in val:
            continue
        # Do not hide ordinary labels (e.g., '출신 중학교' in the template).
        if val in ('중학교', '출신중학교'):
            preceding = [p for p in academic if p[5:7] == w[5:7] and p[2] <= w[0]
                         and w[0] - p[2] < 16]
            preceding.sort(key=lambda p:p[0], reverse=True)
            matching=[]
            for p in preceding:
                token = str(p[4]).strip()
                if (not re.fullmatch(r'[가-힣·ㆍA-Za-z()]{2,24}', token)
                    or token in {'출신', '학교', '학적', '졸업', '입학', '전입', '전출'}):
                    break
                matching.append(p)
                if len(matching) == 2:
                    break
            if matching:
                rects.extend(_tight_rect(p, left=.18, right=.18, up=.12, down=.12)
                             for p in [w]+matching)
        else:
            rects.append(_tight_rect(w, left=.18, right=.18, up=.12, down=.12))
    return rects


def _rrn_words(page: fitz.Page):
    words = _words(page)
    lines = defaultdict(list)
    for w in words:
        lines[(w[5],w[6])].append(w)
    rects=[]
    for line in lines.values():
        line.sort(key=lambda w:w[0])
        joined=' '.join(str(w[4]) for w in line)
        if RRN_RE.search(joined):
            for w in line:
                if re.search(r'\d{6}|\d{7}',str(w[4])) or re.fullmatch(r'[-‐–]',str(w[4])):
                    rects.append(_tight_rect(w))
    return rects


def _make_plans(doc: fitz.Document, options: Options):
    _check_document(doc)
    school=_find_school(doc)
    if not school:
        raise UnsupportedLayout('하단 학교명을 인식하지 못했습니다. 안전을 위해 자동 처리를 중단했습니다.')
    plans=[]
    for index, page in enumerate(doc):
        if len(_words(page))<7:
            raise UnsupportedLayout(f'{index+1}쪽이 스캔 이미지이거나 읽을 수 없습니다.')
        labels=_footer_labels(page)
        rects=_footer_private_words(page, labels, options)
        rects += _date_teacher_words(page, labels)
        rects += _rrn_words(page)
        # No switch: automatically delete the issuing school's name wherever
        # it occurs, not only on the footer. The previous middle school is
        # additionally redacted from the first-page academic record.
        rects.extend(page.search_for(school))
        photo = None
        if index==0:
            rects += _personal_words(page)
            rects += _middle_school_words(page)
            photo = _photo_rect(page)
            # Some first-page fields include teacher's name adjacent to label.
            words=_words(page)
            for i,w in enumerate(words):
                if w[1] < page.rect.height*.5 and str(w[4]).strip() in {'담임교사','담당교사','출력교사'}:
                    same_line=[other for other in words if w[2]<other[0]<w[2]+130 and abs(other[1]-w[1])<5]
                    rects.extend(_tight_rect(other) for other in same_line)
        # Trim and de-duplicate: too-large blanket redactions are not allowed.
        dedup={}
        for r in rects:
            r=(fitz.Rect(r)&page.rect)
            if r.width>.5 and r.height>.5:
                dedup[tuple(round(v,2) for v in r)] = r
        bottom_strip = _bottom_print_strip(page, labels)
        plans.append((list(dedup.values()), photo, bottom_strip))
    return school,plans


def _redact_in_memory(doc:fitz.Document,plans):
    count=0
    for page,(rects,photo,bottom_strip) in zip(doc,plans):
        # Image-only removal in the fixed photo box should not erase graphics.
        if photo is not None:
            page.add_redact_annot(photo, fill=(1,1,1),cross_out=False)
            count+=1
        for rect in rects:
            page.add_redact_annot(rect,fill=(1,1,1),cross_out=False)
            count+=1
        if rects or photo is not None:
            page.apply_redactions(images=2, graphics=0, text=0)
        # A *separate pass* protects all main table lines while removing even
        # bottom-margin print trails implemented as vector drawing, text, or
        # image pixels. Graphics are removed only if fully covered by strip.
        page.add_redact_annot(bottom_strip,fill=(1,1,1),cross_out=False)
        page.apply_redactions(images=2, graphics=1, text=0)
        count += 1
    return count


def preview_page(source: str |Path,page_index:int,options: Options,scale: float=1.3)->bytes:
    with fitz.open(str(source)) as doc:
        _,plans=_make_plans(doc,options)
        if not 0<=page_index<len(doc):
            raise IndexError('미리보기 페이지가 올바르지 않습니다.')
        page=doc[page_index]
        rects,photo,bottom_strip=plans[page_index]
        for r in rects:
            page.add_redact_annot(r,fill=(1,1,1),cross_out=False)
        if photo is not None:
            page.add_redact_annot(photo,fill=(1,1,1),cross_out=False)
        if rects or photo is not None:
            page.apply_redactions(images=2, graphics=0,text=0)
        page.add_redact_annot(bottom_strip,fill=(1,1,1),cross_out=False)
        page.apply_redactions(images=2, graphics=1, text=0)
        return page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False).tobytes('png')


def inspect_file(source:str|Path,options:Options)->dict:
    with fitz.open(str(source)) as doc:
        school,plans=_make_plans(doc,options)
        return {'pages':len(doc),'school':school,'areas':sum(len(r)+(p is not None)+1 for r,p,_ in plans)}


def anonymize_pdf(source: str|Path,destination:str|Path,options:Options=Options())->Result:
    src=Path(source)
    dest=Path(destination)
    if not src.is_file():
        raise FileNotFoundError(f'원본 파일이 없습니다: {src}')
    if src.resolve()==dest.resolve():
        raise ValueError('원본 PDF는 덮어쓸 수 없습니다.')
    if dest.exists():
        raise FileExistsError('같은 이름의 결과 파일이 이미 있습니다. 기존 파일은 덮어쓰지 않습니다.')
    if is_generated_name(src.name):
        raise ValueError('이미 모의면접용으로 처리된 PDF는 다시 처리하지 않습니다.')
    dest.parent.mkdir(parents=True,exist_ok=True)
    with fitz.open(str(src)) as doc:
        school,plans=_make_plans(doc,options)
        identity_left_edges = [_footer_labels(page)['keep_class'][0] for page in doc]
        pages=len(doc)
        count=_redact_in_memory(doc,plans)
        if doc.get_toc(): doc.set_toc([])
        if doc.get_page_labels(): doc.set_page_labels([])
        doc.scrub(metadata=True,xml_metadata=True,attached_files=True,embedded_files=True,
                  hidden_text=True,javascript=True,remove_links=True,redactions=False)
        # Retain the licensing-relevant producer attribution while clearing the
        # original PDF's identifying author, creator, timestamps and title.
        # Never copy creator metadata from the school document into the output.
        doc.set_metadata({
            'title': '', 'author': '', 'subject': '', 'keywords': '',
            'creator': '', 'creationDate': '', 'modDate': '',
            'producer': 'PyMuPDF / MuPDF - Artifex Software, Inc.'
        })
        tmp=dest.with_name('.tmp_redact_'+uuid.uuid4().hex+'.pdf')
        try:
            doc.save(str(tmp),garbage=4,deflate=True,clean=True,encryption=fitz.PDF_ENCRYPT_NONE)
            with fitz.open(str(tmp)) as check:
                if len(check)!=pages:
                    raise RuntimeError('저장 후 페이지 수가 달라졌습니다.')
                for idx,page in enumerate(check):
                    text=page.get_text()
                    if school in text:
                        raise RuntimeError(f'{idx+1}쪽에 학교명이 남아 있습니다. 결과를 저장하지 않았습니다.')
                    footer_words = _words(page)
                    identity_x = identity_left_edges[idx]
                    footer_text = ' '.join(w[4] for w in footer_words
                        if w[1] > page.rect.height*.875 and (w[0]+w[2])/2 < identity_x-3)
                    if DATE_FOOTER_RE.search(footer_text):
                        raise RuntimeError(f'{idx+1}쪽 하단 출력 날짜가 남아 있습니다. 결과를 저장하지 않았습니다.')
                    # Bottom print metadata is often a fine-print line UNDER
                    # the footer, not part of it. Check *all* extracted words
                    # there, without trying to guess variable personal names.
                    after_footer = plans[idx][2]
                    if any(fitz.Rect(w[:4]).intersects(after_footer) for w in footer_words):
                        raise RuntimeError(f'{idx+1}쪽 최하단에 출력자/시간 정보가 남아 있습니다. 결과를 저장하지 않았습니다.')
                    if idx == 0:
                        # Check remaining named middle schools in the academic zone.
                        remaining = _middle_school_words(page)
                        if remaining:
                            raise RuntimeError('첫 페이지 출신 중학교명이 남아 있습니다. 결과를 저장하지 않았습니다.')
                    if RRN_RE.search(text):
                        raise RuntimeError(f'{idx+1}쪽에 주민등록번호 패턴이 남아 있습니다. 결과를 저장하지 않았습니다.')
                    # The profile row must not retain name/sex values.
                    if idx==0:
                        if _personal_words(page):
                            raise RuntimeError('첫 페이지 인적사항의 개인정보가 남아 있습니다. 결과를 저장하지 않았습니다.')
                if any(check.metadata.get(k) for k in
                       ('author', 'title', 'creator', 'creationDate', 'modDate')):
                    raise RuntimeError('PDF 속성의 일부 개인정보를 제거하지 못했습니다.')
                if 'Artifex' not in check.metadata.get('producer',''):
                    raise RuntimeError('PDF 제작자 표시가 누락되었습니다.')
            # Atomic no-overwrite publish; another task creating a same-named
            # file meanwhile must never be overwritten (unlike os.replace()).
            os.link(tmp, dest)
        finally:
            tmp.unlink(missing_ok=True)
    return Result(pages,count,school,[])
