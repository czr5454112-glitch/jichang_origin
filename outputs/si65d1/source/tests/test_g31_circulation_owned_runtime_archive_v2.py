"""Synthetic filesystem preparation safety; no native/model/actual raw decode."""
import copy
import hashlib
from pathlib import Path
import pytest
from scripts.experiments.g31_ics_circulation import prepare_live_owned_initial_runtime_v2 as p


def source(tmp_path):
    root=tmp_path/'workspace';file=root/'scripts'/'a.py';file.parent.mkdir(parents=True);file.write_bytes(b'x=1\r\n')
    return root,file


def test_absolute_legacy_read_merges_to_one_canonical_key(tmp_path):
    root,file=source(tmp_path);data=file.read_bytes();before=file.stat().st_mtime_ns
    result=p.merge_sources(root,[(str(file),data),('scripts/a.py',data),('scripts\\a.py',data)])
    assert result=={'scripts/a.py':data} and file.stat().st_mtime_ns==before


def test_duplicate_path_different_content_rejected(tmp_path):
    root,file=source(tmp_path)
    with pytest.raises(ValueError,match='conflict'):p.merge_sources(root,[(str(file),b'a'),('scripts/a.py',b'b')])


@pytest.mark.parametrize('kind',['outside','drive_relative','parent','nul','type'])
def test_read_identity_cannot_escape_or_use_drive_relative(tmp_path,kind):
    root,file=source(tmp_path)
    name={'outside':str(tmp_path/'outside.py'),'drive_relative':'C:relative.py','parent':'scripts/../a.py','nul':'a\x00.py','type':True}[kind]
    with pytest.raises(ValueError):p.canonical_source(root,name)


@pytest.mark.parametrize('name',['C:/outside.py','scripts\\a.py','../a.py','C:relative.py','scripts/./a.py','/a.py'])
def test_archive_keys_must_already_be_relative_posix(tmp_path,name):
    with pytest.raises(ValueError):p.canonical_archive_target(tmp_path/'out',name)


def test_all_targets_validated_before_first_write(tmp_path):
    root,file=source(tmp_path);output=tmp_path/'out';before=file.read_bytes()
    with pytest.raises(ValueError):p.archive_sources(root,output,{'scripts/a.py':before,str(file):b'evil'})
    assert not output.exists() and file.read_bytes()==before


def test_existing_archive_never_overwritten(tmp_path):
    root,file=source(tmp_path);output=tmp_path/'out';files={'scripts/a.py':file.read_bytes()}
    mapping=p.archive_sources(root,output,files);target=output/mapping['scripts/a.py'];before=target.read_bytes()
    with pytest.raises(FileExistsError):p.archive_sources(root,output,{'scripts/a.py':b'evil'})
    assert target.read_bytes()==before and file.read_bytes()==before


def test_archive_equal_to_current_source_is_rejected(tmp_path):
    output=tmp_path/'out';root=output/'source';file=root/'scripts'/'a.py';file.parent.mkdir(parents=True);file.write_bytes(b'x')
    with pytest.raises(ValueError,match='must_not_be_current'):p.archive_sources(root,output,{'scripts/a.py':b'evil'})
    assert file.read_bytes()==b'x'


@pytest.mark.parametrize('kind',['absolute','escape','missing'])
def test_archive_verifier_rejects_bad_mapping(tmp_path,kind):
    root,file=source(tmp_path);output=tmp_path/'out';mapping=p.archive_sources(root,output,{'scripts/a.py':file.read_bytes()})
    plan={'source_sha256':{'scripts/a.py':p.sha(file)},'source_archive':copy.deepcopy(mapping)}
    if kind=='absolute':plan['source_archive']['scripts/a.py']=str(file)
    elif kind=='escape':plan['source_archive']['scripts/a.py']='../workspace/scripts/a.py'
    else:plan['source_archive'].clear()
    with pytest.raises(ValueError):p.verify_archive(root,output,plan)


def test_source_files_normalizes_absolute_predecessor_before_merge(tmp_path,monkeypatch):
    root,file=source(tmp_path);data=file.read_bytes()
    monkeypatch.setattr(p,'ROOT',root)
    monkeypatch.setattr(p,'read',lambda path:{'source_sha256':{str(file):hashlib.sha256(data).hexdigest()}})
    monkeypatch.setattr(p.image,'source_closure',lambda root,entries:{'scripts/a.py':data})
    assert p.source_files()=={'scripts/a.py':data}


def setup_prepare(root,file,output,monkeypatch):
    from scripts.experiments.g31_ics_circulation import live_obligation_owned_same_information_search as search
    monkeypatch.setattr(p,'ROOT',root);monkeypatch.setattr(p,'OUT',output.parent)
    monkeypatch.setattr(p,'source_gate',lambda:{'test':'read_only'})
    monkeypatch.setattr(p,'pure_gate',lambda:{'test':'synthetic_not_acceptance'})
    monkeypatch.setattr(p,'source_files',lambda:{'scripts/a.py':file.read_bytes()})
    monkeypatch.setattr(search,'source_proof',lambda:{'synthetic_only':True})
    for folder,name in [('live_owned_initial_runtime_source_prepare_001','plan.json'),('live_owned_initial_runtime_pure_001','receipt.json')]:
        path=output.parent/folder/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('{}')


def test_full_prepare_archives_once_verifies_before_ready_never_writes_current(tmp_path,monkeypatch):
    root,file=source(tmp_path);output=tmp_path/'results'/'prepare002';setup_prepare(root,file,output,monkeypatch)
    before=file.read_bytes();stamp=file.stat().st_mtime_ns;events=[];real_open=Path.open;real_verify=p.verify_archive;real_write=p.write
    def opened(path,mode='r',*args,**kwargs):
        if any(flag in mode for flag in ('w','x','a','+')):assert path.resolve()!=file.resolve()
        return real_open(path,mode,*args,**kwargs)
    def checked(*args):events.append('verify');return real_verify(*args)
    def written(path,value):events.append(Path(path).name);return real_write(path,value)
    monkeypatch.setattr(Path,'open',opened);monkeypatch.setattr(p,'verify_archive',checked);monkeypatch.setattr(p,'write',written)
    p.prepare(output)
    plan=p.read(output/'plan.json');ready=p.read(output/'ready.json')
    assert events==['verify','plan.json','verify','ready.json']
    assert plan['source_archive']=={'scripts/a.py':'source/scripts/a.py'}
    assert ready['plan']['sha256']==p.sha(output/'plan.json') and ready['source_count']==1
    assert file.read_bytes()==before and file.stat().st_mtime_ns==stamp


def test_prepare_failure_cannot_write_ready(tmp_path,monkeypatch):
    root,file=source(tmp_path);output=tmp_path/'results'/'failed';setup_prepare(root,file,output,monkeypatch)
    def failed(*args):raise ValueError('deliberate_archive_mismatch')
    monkeypatch.setattr(p,'verify_archive',failed)
    with pytest.raises(ValueError,match='mismatch'):p.prepare(output)
    assert not (output/'plan.json').exists() and not (output/'ready.json').exists()


@pytest.mark.parametrize('data',['text',bytearray(b'x')])
def test_nonimmutable_source_bytes_rejected(tmp_path,data):
    root,_=source(tmp_path)
    with pytest.raises(ValueError,match='source_bytes'):p.merge_sources(root,[('scripts/a.py',data)])
