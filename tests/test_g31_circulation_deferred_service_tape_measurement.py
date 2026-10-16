import gzip
import json
import pytest
from scripts.experiments.g31_ics_circulation import measure_deferred_service_tape as m


@pytest.mark.parametrize('mode',('immediate','ram','spool'))
def test_real_writer_roundtrip_all_rows_and_order(tmp_path,mode):
    source=tmp_path/'source.gz'
    with gzip.open(source,'wt',encoding='utf8',compresslevel=1) as f:
        for i in range(5):f.write(json.dumps({'ordinal':i,'中文':'😀','value':{'b':i,'a':-0.}},ensure_ascii=False,allow_nan=False)+'\n');f.flush()
    result=m.measure(source,tmp_path/'output.gz',mode,5)
    assert result['rows']==5 and result['all_values_and_row_order_exact']
    assert result['full_replay_ns']>=result['hot_json_write_flush_ns']+result['deferred_close_ns']
    assert gzip.decompress(source.read_bytes())==gzip.decompress((tmp_path/'output.gz').read_bytes())


@pytest.mark.parametrize('defect',('missing','order','changed_encoding','truncated'))
def test_bad_tape_cannot_gain_success(tmp_path,defect):
    source=tmp_path/'source.gz';rows=[{'ordinal':0},{'ordinal':1}]
    if defect=='order':rows.reverse()
    if defect=='missing':rows.pop()
    with gzip.open(source,'wt',encoding='utf8') as f:
        for row in rows:f.write(json.dumps(row,separators=(',',':') if defect=='changed_encoding' else None)+'\n')
    if defect=='truncated':source.write_bytes(source.read_bytes()[:-6])
    with pytest.raises((ValueError,EOFError)):m.measure(source,tmp_path/'output.gz','spool',2)


def test_fixed_denominators_and_limits():
    assert m.CASES==('baseline','drop_first_ack','ack_withheld_in_window')
    assert len(m.ORDERS)==3 and all(set(x)=={'immediate','ram','spool'} and len(x)==3 for x in m.ORDERS)
    assert m.LIMIT==120 and m.candidate.MAX_BYTES==256*1024*1024 and m.candidate.MAX_ROWS==160000
