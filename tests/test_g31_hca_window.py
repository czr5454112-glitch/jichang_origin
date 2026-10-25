import pytest
from scripts.experiments.g31_no_wait import hca


def test_legacy_window_remains_exact():
    assert hca.observation_window({})==(8260,98259,90000)


def test_extended_window_inclusive_end_is_explicit():
    assert hca.observation_window({'observation_window':{'start_epoch':8260,'end_epoch':200000}})==(8260,200000,191741)


@pytest.mark.parametrize('window',[{'start_epoch':20,'end_epoch':19},{'start_epoch':False,'end_epoch':30},
                                 {'start_epoch':0,'end_epoch':30.5},{'start_epoch':-1,'end_epoch':30}])
def test_invalid_window_rejected(window):
    with pytest.raises(ValueError):hca.observation_window({'observation_window':window})


def test_run_passes_explicit_window_without_touching_canonical(monkeypatch,tmp_path):
    canonical=tmp_path/'canonical.jsonl';canonical.write_text('original identity',encoding='utf-8')
    manifest={'classes':str(tmp_path/'classes'),'observation_window':{'start_epoch':8260,'end_epoch':200000},
              'cells':{'map2_2x':{'canonical':str(canonical),'raw':'raw.txt','map':{'draft_raw':'map.txt'},'storage_in_goal':47,'storage_out_start':52}}}
    captured=[]
    monkeypatch.setattr(hca,'verify',lambda out:None)
    monkeypatch.setattr(hca,'read',lambda path:manifest)
    monkeypatch.setattr(hca.legacy,'run_campaign',lambda args:captured.append(args) or 0)
    monkeypatch.setattr(hca,'analyze',lambda out,label:None)
    hca.run(tmp_path,'map2_2x')
    assert captured[0].start_epoch==8260
    assert captured[0].max_epochs==191741
    assert captured[0].canonical_input==canonical
    assert canonical.read_text(encoding='utf-8')=='original identity'
