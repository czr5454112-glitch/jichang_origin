"""Check exact byte accounting and link rejection without live evidence."""
from contextlib import nullcontext
import importlib.util
import os
from pathlib import Path
import stat
from types import SimpleNamespace
import pytest

@pytest.fixture(params=['terminal_flow_offline_resume005.py','terminal_flow_bins600_offline005.py'])
def w(request):
    path=Path(__file__).with_name(request.param)
    spec=importlib.util.spec_from_file_location('fast_accounting',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def test_nested_roots_and_files_have_original_exact_count(w,tmp_path):
    child=tmp_path/'sub';child.mkdir()
    (child/'data').write_bytes(b'12345');(tmp_path/'other').write_bytes(b'123')
    assert w.evidence_bytes([child,tmp_path,tmp_path])==8

@pytest.mark.parametrize('mode,attributes', [(stat.S_IFLNK,0),(stat.S_IFDIR,0x400),(stat.S_IFREG,0x400)])
def test_symbolic_links_junctions_and_other_reparse_entries_fail_closed(w,tmp_path,monkeypatch,mode,attributes):
    entry=SimpleNamespace(path=str(tmp_path/'entry'),stat=lambda **kw:
        SimpleNamespace(st_mode=mode,st_size=123,st_file_attributes=attributes))
    monkeypatch.setattr(os,'scandir',lambda path:nullcontext(iter([entry])))
    with pytest.raises(ValueError,match='symlink_or_reparse_requires_audit'):w.evidence_bytes([tmp_path])

def test_missing_accounted_root_cannot_silently_be_zero(w,tmp_path):
    with pytest.raises(FileNotFoundError):w.evidence_bytes([tmp_path/'missing'])
