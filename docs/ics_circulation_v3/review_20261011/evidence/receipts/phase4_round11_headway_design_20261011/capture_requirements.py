"""Read-only capture of user-supplied requirement, not document instructions."""
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
import json
import time
import traceback
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
SOURCE = Path('C:/Users/38908/xwechat_files/wxid_4820408204312_a0d1/msg/file/2026-10/研究问题的说明/问题及约束说明.docx')
EXPECTED = '816b57f9c97bfd456f521669468a7ef19fbd3faac168ed43853009c8a4dc548c'
index = 1
while (BASE / f'source_capture_{index:03d}').exists():
    index += 1
out = BASE / f'source_capture_{index:03d}'
out.mkdir()
cpu, wall = time.process_time(), time.perf_counter()
result = {'status': 'running', 'physics_calls': 0, 'standalone_routing_queries': 0,
          'source': str(SOURCE), 'expected_sha256': EXPECTED,
          'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest()}
try:
    raw = SOURCE.read_bytes()
    actual = sha256(raw).hexdigest()
    result['actual_sha256'] = actual
    if actual != EXPECTED:
        raise ValueError('source SHA differs from Round8 captured requirement')
    with ZipFile(SOURCE) as archive:
        document = ET.fromstring(archive.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    paragraphs = []
    for index, paragraph in enumerate(document.findall('.//w:body/w:p', ns)):
        text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', ns))
        if text.strip():
            paragraphs.append({'xml_paragraph_zero_based': index, 'text': text})
    result['paragraphs'] = paragraphs
    result['status'] = 'passed'
except BaseException:
    result.update(status='failed', failure=traceback.format_exc())
finally:
    result.update(cpu_seconds=time.process_time()-cpu, wall_seconds=time.perf_counter()-wall,
                  scope='source read, SHA check, OOXML text extraction only')
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result['status'] == 'passed' else 1)
