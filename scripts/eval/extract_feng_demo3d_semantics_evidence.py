#!/usr/bin/env python3
"""Read a supplied Demo3D ZIP/XML and preserve relevant source, without executing it."""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import zipfile


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path(
        'C:/STUDY/民航二所项目相关/冯汝琛相关材料/冯汝琛相关材料'))
    parser.add_argument('--output', type=Path, default=Path(
        'outputs/runtime/feng_dh_semantics_reaudit_20260905/primary_model_evidence'))
    args = parser.parse_args()
    model = args.source_root / 'ICS项目/地图模型/ICS_algorithm-2.demo3d'
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(model) as z:
        members = [{'name': i.filename, 'bytes': i.file_size} for i in z.infolist()]
        raw = z.read('ICS_algorithm.demo3d')
    root = ET.fromstring(raw)
    selected_native = {
        'SensorScript.1': {'NativeSource': [(54, 59)]},
        'SensorScript.2': {'NativeSource': [(48, 69), (152, 164)]},
        'IntersectionController': {'NativeSource': [(169, 178), (893, 915), (928, 938),
            (962, 981), (1004, 1019), (1062, 1069), (1085, 1104), (1293, 1300)]},
        'BaggageHandling.3': {
            'ToteSystems/IntersectionControllerCS.cs': [(103, 110), (159, 169), (980, 1006), (1164, 1172)],
            'ToteSystems/FlowControlCS.cs': [(437, 466), (501, 519)],
            'Utils.cs': [(34, 56)]},
    }
    selected_source = {'FlowControlComponent': [(5, 17)]}
    scripts = []
    files = []
    source_excerpts = []
    for c in root.findall('./ScriptLibrary/Scripts/C/E/V'):
        name = c.findtext('Name') or ''
        sid = c.findtext('Id')
        text = c.findtext('Source') or ''
        native = c.findtext('NativeSource') or ''
        entries = []
        if native.lstrip().startswith('<Project>'):
            for f in ET.fromstring(native).findall('File'):
                member = f.get('Path', '').replace('\\', '/')
                data = base64.b64decode(f.text or '', validate=True)
                entries.append((member, data))
        elif native:
            entries.append(('NativeSource', native.encode('utf-8')))
        manifest = {
            'id': sid, 'name': name, 'modified_by': c.findtext('MDBY'),
            'modified_time': c.findtext('MDTM'), 'source_characters': len(text),
            'source_utf8_sha256': sha(text.encode('utf-8')),
            'native_characters': len(native),
            'native_files': [{'member': p, 'bytes': len(d), 'sha256': sha(d)} for p, d in entries],
        }
        scripts.append(manifest)
        wanted = [(p, d, selected_native[name][p]) for p, d in entries if p in selected_native.get(name, {})]
        if name in selected_source:
            wanted.append(('Source', text.encode('utf-8'), selected_source[name]))
        for member, data, spans in wanted:
            files.append({'script_id': sid,
                          'script_name': name, 'embedded_member': member,
                          'bytes': len(data), 'sha256': sha(data)})
            lines = data.decode('utf-8-sig').splitlines()
            source_excerpts.append(dict(files[-1], excerpts=[
                {'start_line': lo, 'end_line': min(hi, len(lines)),
                 'text': '\n'.join(lines[lo - 1:hi])} for lo, hi in spans]))

    names = {s['id']: s['name'] for s in scripts}
    scene = next(e for e in root if e.tag.endswith('Scene'))
    bindings = []
    timing = []
    procedures = []

    def scalar(value: ET.Element | None) -> object:
        if value is None:
            return None
        if len(value) == 0:
            return value.text or ''
        if value.find('V') is not None:
            return value.findtext('V')
        return ET.tostring(value, encoding='unicode')

    def walk(e: ET.Element, parent: str = '') -> None:
        path = parent + '/' + (e.findtext('N') or '')
        p = e.find('P')
        if p is not None:
            sid = p.findtext('./ScriptKey/Id')
            props = {x.findtext('Name'): scalar(x.find('Value'))
                     for x in p.findall('./CustomProperties/CP/e')}
            record = {'path': path, 'visual_id': e.findtext('Id'),
                      'visual_type': next(iter(e.attrib.values()), ''),
                      'script_id': sid, 'script_name': names.get(sid),
                      'native_type_name': p.findtext('NativeTypeName')}
            if sid in names:
                bindings.append(record)
            if 'TransferTime' in props or 'TransferDuration' in props or names.get(sid, '').startswith('SensorScript'):
                allowed = ['TransferTime', 'TransferDuration', 'TransferDelay',
                           'InductionMode', 'TargetBlockedMode', 'DisableForLinPhys', 'Enabled']
                record = dict(record, configured_properties={k: props[k] for k in allowed if k in props},
                              native_transfer_duration=p.findtext('TransferDuration'),
                              body_type=p.findtext('BodyType'))
                timing.append(record)
            if path == '/SceneVisual/FlowControl1':
                main = next(x for x in p.findall('./CustomProperties/CP/e')
                            if x.findtext('Name') == 'MainProcedure')
                xtype = '{http://www.w3.org/2001/XMLSchema-instance}type'
                for proc in main.iter():
                    if proc.attrib.get(xtype) not in ['e3d:ProcedureControl', 'e3d:QLPControl']:
                        continue
                    proc_name = ('MainProcedure' if proc.attrib.get(xtype) == 'e3d:QLPControl' else
                        next((x.findtext('T') for x in proc.findall('./CH/E') if x.findtext('NM') == 'format'), None))
                    procedures.append({'procedure': proc_name, 'visual_id': record['visual_id'],
                        'locator': 'Scene/FlowControl1/P/CustomProperties/CP/e[Name=MainProcedure]',
                        'ast_sha256': sha(ET.tostring(proc, encoding='utf-8')),
                        'visible_tokens_in_xml_order': [x.text for x in proc.iter('T') if x.text],
                        'call_names': [x.findtext('./CH/E/T') for x in proc.iter()
                                       if x.attrib.get(xtype) == 'e3d:ProcCallControl']})
                procedures.append({'scene_object': path, 'MainProcedureEnabled': props.get('MainProcedureEnabled'),
                    'PLC_visual_id': next(x for x in p.findall('./CustomProperties/CP/e')
                                           if x.findtext('Name') == 'PLC').findtext('./Value/Visual'),
                    'OnInitialize': p.findtext('./OnInitialize/Name'),
                    'script_id': sid, 'script_name': names.get(sid)})
        for child in e.findall('./C/e'):
            walk(child, path)

    walk(scene)
    dump(out / 'model_manifest.json', {
        'source_relative_path': 'ICS项目/地图模型/ICS_algorithm-2.demo3d',
        'source_bytes': model.stat().st_size, 'source_sha256': sha(model.read_bytes()),
        'archive_members': members, 'xml_member': 'ICS_algorithm.demo3d',
        'xml_bytes': len(raw), 'xml_sha256': sha(raw),
        'scene': {k: scene.findtext('P/' + k) for k in
                  ['PhysicsEnabled', 'SimulationLinearPhysics', 'PhysicsEngineType']},
        'script_containers': scripts,
        'direct_scene_script_binding_counts': dict(sorted(Counter(x['script_name'] for x in bindings).items())),
        'excerpted_source_files': files,
        'scope': 'Static extraction only; no model, script, assembly, project or network endpoint executed.'})
    grouped = Counter((x['script_name'], x['native_type_name']) for x in bindings)
    dump(out / 'scene_script_bindings.json', {
        'total_direct_bindings': len(bindings),
        'counts_by_script_and_native_class': [{'script_name': k[0], 'native_type_name': k[1], 'count': n}
            for k, n in sorted(grouped.items(), key=lambda pair: (pair[0][0] or '', pair[0][1] or ''))],
        'relevant_instances': [x for x in bindings if x['script_name'] in
            ['SensorScript.1', 'SensorScript.2', 'FlowControlComponent', 'IntersectionController']]})
    dump(out / 'transfer_and_sensor_instances.json', timing)
    dump(out / 'source_excerpts.json', source_excerpts)
    dump(out / 'flowcontrol_visual_procedures.json', procedures)
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    docs = []
    for name, spans in {
        '系统设计说明书.docx': [(49, 60), (65, 84), (104, 117), (127, 127)],
        '仿真报告.docx': [(45, 48), (80, 86), (104, 126), (158, 176)],
        '用户使用手册.docx': [(37, 37), (46, 46)],
        '系统安装手册.docx': [(58, 69)],
    }.items():
        path = args.source_root / 'ICS项目/ICS相关文档' / name
        with zipfile.ZipFile(path) as z:
            doc = ET.fromstring(z.read('word/document.xml'))
        paragraphs = [''.join(t.text or '' for t in e.findall('.//w:t', ns))
                      for e in doc.findall('.//w:body//w:p', ns)]
        docs.append({'source_relative_path': 'ICS项目/ICS相关文档/' + name,
                     'sha256': sha(path.read_bytes()),
                     'locator': '1-based body descendant w:p, including empty and table paragraphs',
                     'paragraphs': [{'p': i + 1, 'text': t} for i, t in enumerate(paragraphs)
                                    if any(lo <= i + 1 <= hi for lo, hi in spans)]})
    dump(out / 'engineering_document_excerpts.json', docs)
    print(json.dumps({'output': str(out), 'source_files': len(files),
                      'bindings': len(bindings), 'transfer_and_sensor_instances': len(timing)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
