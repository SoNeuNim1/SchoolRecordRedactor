"""Generate fully fictitious NEIS-like PDF fixtures, never real student data.
SPDX-License-Identifier: AGPL-3.0-only
"""
from pathlib import Path
from io import BytesIO
from PIL import Image,ImageDraw
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4

FONT=Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf')

def make_pdf(path: Path, pages: int, *, include_school=True):
    if not FONT.exists():
        raise RuntimeError('Fixture generation requires a Korean TTF font available in the test environment.')
    pdfmetrics.registerFont(TTFont('FictitiousKorean', str(FONT)))
    W,H=A4
    path.parent.mkdir(parents=True, exist_ok=True)
    cv=canvas.Canvas(str(path),pagesize=A4,pageCompression=1)
    cv.setTitle('FAKE DEMO - SCHOOL RECORD');cv.setAuthor('FAKE TEST OPERATOR')
    def text(x,top,value,sz=9):
        cv.setFont('FictitiousKorean',sz)
        cv.drawString(x,H-top-sz,value)
    def line(y,x0=32,x1=565):cv.line(x0,H-y,x1,H-y)
    for i in range(pages):
        cv.setStrokeColorRGB(.35,.38,.42)
        text(105,78,'학교생활세부사항기록부(학교생활기록부II)',16)
        if i==0:
            text(40,125,'졸업 대장 번호')
            text(120,126,'001')
            text(40,154,'구분')
            text(190,154,'학과')
            text(40,210,'학년')
            text(185,215,'제1학년')
            text(41,299,'1. 인적·학적사항',11)
            line(321);line(365);line(413)
            text(38,337,'학생정보')
            text(88,324,'성명')
            text(111,324,':')
            text(133,324,'가상학생')
            text(225,324,'성별')
            text(250,324,':')
            text(264,324,'남')
            text(90,347,'주민등록번호')
            text(185,347,'000000-0000000')
            text(355,347,'주소')
            text(399,347,'가상도 가상시 가상동')
            text(38,383,'학적사항')
            text(90,382,'2024년 01월 05일')
            text(280,382,'가상중학교')
            text(360,382,'졸업')
            text(90,399,'2024년 03월 01일')
            text(280,399,'제1학년 입학')
            text(40,433,'2. 출결상황',11)
            text(45,467,'학년')
            text(140,467,'수업일수')
            text(280,467,'특기사항')
            text(44,490,'1')
            text(130,490,'191')
            text(280,490,'가상 자료 - 실제 학생과 무관')
            # Pixel image, not a real person's photo.
            im=Image.new('RGB',(240,280),(224,236,245));d=ImageDraw.Draw(im)
            d.ellipse((85,50,155,120),fill=(110,125,148))
            d.rounded_rectangle((46,127,194,260),radius=40,fill=(110,125,148))
            cv.drawImage(ImageReader(im),W*.774,H-H*.295,width=W*.17,height=H*.14)
        else:
            text(40,125,'6. 창의적 체험활동상황 / 7. 교과학습발달상황',10)
            text(60,190,'가상 학생의 활동 기록 (실제 학생 정보가 아닙니다).')
            text(60,215,'지속적인 탐구와 협력을 통해 문제를 해결함.')
            if include_school:
                text(60,245,'가상고등학교에서 개최한 행사에 적극 참여함.')
        line(767);line(802)
        text(35,784,'가상고등학교' if include_school else '모의학교')
        text(250,784,f'{i+1} / {pages}')
        text(338,784,'반')
        text(367,784,'4')
        text(427,784,'번호')
        text(452,784,'21')
        text(480,784,'성명')
        text(512,784,'가상학생')
        text(60,819,'2026.10.19 13:40 / 출력자: 가상교사 / 192.0.2.1',8)
        cv.showPage()
    cv.save()

if __name__=='__main__':
    here=Path(__file__).resolve().parent.parent/'samples'
    make_pdf(here/'가상_생활기록부_4쪽.pdf',4)
    make_pdf(here/'가상_생활기록부_12쪽.pdf',12)
    print('Created only fictitious samples.')
