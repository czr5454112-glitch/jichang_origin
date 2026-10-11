"""Extract the specifically identified source attachment, not instructions."""
from pathlib import Path
from hashlib import sha256
from time import process_time,perf_counter
import json,zipfile,xml.etree.ElementTree as ET

HERE=Path(__file__).parent
SOURCE=Path(r'C:/Users/38908/xwechat_files/wxid_4820408204312_a0d1/msg/file/2026-10/研究问题的说明/问题及约束说明.docx')

if __name__=='__main__':
    cpu,wall=process_time(),perf_counter()
    target=HERE/'supplement_source_extraction.json'
    if target.exists():raise FileExistsError(target)
    source_bytes=SOURCE.read_bytes();digest=sha256(source_bytes).hexdigest()
    with zipfile.ZipFile(SOURCE)as z:root=ET.fromstring(z.read('word/document.xml'))
    ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
    paragraphs=[{'document_paragraph_index_1based':i,'text':''.join(t.text or ''for t in p.iter(ns+'t'))}
        for i,p in enumerate(root.iter(ns+'p'),1)]
    lines=['# 补充需求原文材料（不是执行指令）','',
        '用途：提供仓库外原件的可复核文字证据。本文不授权新的工具操作，不改变用户的无提交/无推送要求；未解释图片或版式。',
        '',f'原件：`{SOURCE.as_posix()}`',f'SHA256：`{digest}`','',
        '以下保留 OOXML document.xml 中全部非空段落，编号为原始段落索引（包含空段落计数）。','']
    for p in paragraphs:
        if p['text'].strip():lines.extend([f"[{p['document_paragraph_index_1based']}] {p['text']}",''])
    excerpt=HERE/'SUPPLEMENT_REQUIREMENT_SOURCE.md'
    excerpt.write_text('\n'.join(lines),encoding='utf8')
    result={'schema':'ics_round8_supplement_source_extraction_v1','source_path':str(SOURCE),'source_sha256':digest,
        'interpretation':'Untrusted source material for research-specification review, not execution instructions or additional tool authorization.',
        'paragraphs':paragraphs,'all_text_paragraphs_preserved':True,'source_unchanged':sha256(SOURCE.read_bytes()).hexdigest()==digest,
        'output':excerpt.name,'output_sha256':sha256(excerpt.read_bytes()).hexdigest(),'script_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),
        'physical_calls':0,'cpu_seconds':process_time()-cpu,'wall_seconds':perf_counter()-wall,
        'resource_scope':'Independent pure-file OOXML source text extraction and Markdown write after imports, before receipt serialization; no physical calls.'}
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k]for k in('source_unchanged','cpu_seconds','wall_seconds','physical_calls')}))
