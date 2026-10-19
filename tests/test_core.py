"""Actual content deletion, batch safety, page count, privacy, and metadata.
Tests exclusively generate *fictitious* PDFs. SPDX-License-Identifier: AGPL-3.0-only.
"""
import sys,unittest,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from redactor_core import Options,anonymize_pdf, UnsupportedLayout, destination_for, preview_page
from create_synthetic import make_pdf
import fitz

class PublicReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def test_all_options_and_mixed_lengths(self):
        for pages in (4,12):
            src=self.root/f'{pages}쪽_가상.pdf';make_pdf(src,pages)
            source_bytes=src.read_bytes()
            for keep_id,keep_name in ((True,True),(True,False),(False,True),(False,False)):
                out=self.root/f'{pages}_{int(keep_id)}{int(keep_name)}.pdf'
                result=anonymize_pdf(src,out,Options(keep_id,keep_name))
                self.assertEqual(result.pages,pages)
                self.assertEqual(src.read_bytes(),source_bytes)
                with fitz.open(out) as pdf:
                    self.assertEqual(len(pdf),pages)
                    self.assertIn('Artifex',pdf.metadata['producer'])
                    for k in ('author','title','creator','creationDate','modDate'):
                        self.assertFalse(pdf.metadata.get(k))
                    for i,p in enumerate(pdf):
                        t=p.get_text()
                        self.assertNotIn('가상고등학교',t)
                        self.assertNotIn('000000-0000000',t)
                        self.assertNotIn('가상교사',t)
                        self.assertNotIn('192.0.2.1',t)
                        self.assertNotIn('2026.10.19',t)
                        self.assertIn(f'{i+1} / {pages}',t)
                        if i==0:
                            self.assertNotIn('가상중학교',t)
                            self.assertNotIn('주민등록번호 000000',t)
                            self.assertIn('성명:',t)
                            self.assertNotIn('001',t)
                        foot=' '.join(w[4] for w in p.get_text('words') if w[1]>770 and w[0]>=330)
                        self.assertEqual('4' in foot,keep_id)
                        self.assertEqual('21' in foot,keep_id)
                        self.assertEqual('가상학생' in foot,keep_name)

    def test_never_overwrite_and_no_reprocessing(self):
        source=self.root/'기록.pdf';make_pdf(source,4)
        out=destination_for(source,self.root)
        anonymize_pdf(source,out)
        result=out.read_bytes()
        with self.assertRaises(FileExistsError):anonymize_pdf(source,out)
        self.assertEqual(result,out.read_bytes())
        with self.assertRaises(ValueError):
            anonymize_pdf(out,self.root/'재처리.pdf')

    def test_unsupported_layout_fails_closed(self):
        source=self.root/'다른양식.pdf'
        with fitz.open() as pdf:
            pg=pdf.new_page();pg.insert_text((30,70),'UNSUPPORTED DOCUMENT')
            pdf.save(source)
        out=self.root/'결과.pdf'
        with self.assertRaises(UnsupportedLayout):anonymize_pdf(source,out)
        self.assertFalse(out.exists())

    def test_preview_and_extracted_artifacts(self):
        src=self.root/'가상_미리보기.pdf';make_pdf(src,4)
        self.assertGreater(len(preview_page(src,0,Options(),1.0)),5000)

if __name__=='__main__':unittest.main()
