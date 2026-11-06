from pathlib import Path
from tempfile import TemporaryDirectory
import cairo,subprocess
from pdf_tools import process
import gi
gi.require_version('Poppler','0.18')
from gi.repository import Poppler
with TemporaryDirectory() as td:
    root=Path(td);source=root/'test.pdf';surface=cairo.PDFSurface(str(source),400,500);ctx=cairo.Context(surface)
    for page in range(3):
        ctx.set_font_size(24);ctx.move_to(30,60);ctx.show_text('Document page '+str(page+1));ctx.show_page()
    surface.finish();original=source.read_bytes()
    out=process('text',source,root/'text.txt');assert 'Document page 3' in out.read_text()
    out=process('split',source,root/'pages.pdf','1,3');assert Poppler.Document.new_from_file(out.as_uri(),None).get_n_pages()==2
    out=process('compress',source,root/'compressed.pdf');assert Poppler.Document.new_from_file(out.as_uri(),None).get_n_pages()==3
    for output in (source,root/'pages.pdf'):
        before=output.read_bytes()
        try:process('split',source,output,'1');raise AssertionError('Overwrite allowed')
        except ValueError:pass
        assert output.read_bytes()==before
    try:process('split',source,root/'bad.pdf','1;echo bad');raise AssertionError('Invalid range allowed')
    except ValueError:pass
    out=process('ocr',source,root/'ocr.pdf');assert Poppler.Document.new_from_file(out.as_uri(),None).get_n_pages()==3
    assert source.read_bytes()==original
print('PASS: real text extraction, page ranges, compression, OCR, input validation, originals and existing outputs preserved')
