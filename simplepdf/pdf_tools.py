"""PDF exports: publish new files atomically, preserving originals."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

def process(action, source, output, pages='1', language='eng', gui=False):
    source, output = Path(source).resolve(), Path(output).absolute()
    if not source.is_file() or source.suffix.lower() != '.pdf':
        raise ValueError('Choose a PDF document.')
    if output.exists() or source == output:
        raise ValueError('Choose a new output filename. Existing files are preserved.')
    if action == 'split' and not re.fullmatch(r'[1-9][0-9]*(?:-[1-9][0-9]*)?(?:,[1-9][0-9]*(?:-[1-9][0-9]*)?)*', pages):
        raise ValueError('Use page numbers such as 1, 2-5, or 1,3-5.')
    if action == 'ocr' and not re.fullmatch(r'[a-zA-Z0-9_]+(?:\+[a-zA-Z0-9_]+)*', language):
        raise ValueError('Use an installed OCR language such as eng, deu, or eng+deu.')
    with tempfile.TemporaryDirectory(prefix='.simplepdf-', dir=output.parent) as work:
        temporary = Path(work)/('result.txt' if action == 'text' else 'result.pdf')
        if action == 'text':
            command = ['pdftotext', '-layout', str(source), str(temporary)]
        elif action == 'split':
            command = ['qpdf', str(source), '--pages', '.', pages, '--', str(temporary)]
        elif action == 'compress':
            command = ['qpdf', '--object-streams=generate', '--stream-data=compress', '--recompress-flate', '--compression-level=9', str(source), str(temporary)]
        elif action == 'ocr':
            command = ['ocrmypdf', '--skip-text', '--output-type', 'pdf', '--optimize', '0', '--jobs', '2', '-l', language, str(source), str(temporary)]
        else:
            raise ValueError('Unknown PDF action.')
        progress = None
        if gui:
            progress = subprocess.Popen(['zenity', '--progress', '--pulsate', '--no-cancel', '--auto-close', '--title=PDF tools', '--text=Processing document…'], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        finally:
            if progress:
                progress.stdin.close()
                progress.wait()
        # qpdf uses exit 3 for warnings with a successfully written document.
        allowed = (0, 3) if action in ('split', 'compress') else (0,)
        if result.returncode not in allowed or not temporary.is_file():
            raise RuntimeError(result.stdout[-4000:] or 'PDF processing failed.')
        os.link(temporary, output)  # Create atomically; never overwrite an existing file.
    return output

