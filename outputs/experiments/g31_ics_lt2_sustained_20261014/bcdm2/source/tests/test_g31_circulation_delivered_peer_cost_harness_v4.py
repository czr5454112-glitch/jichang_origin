from test_g31_circulation_delivered_peer_cost_harness_v2 import *
from types import SimpleNamespace
from scripts.experiments.g31_ics_circulation import measure_delivered_peer_cost_v4 as v4


@pytest.mark.parametrize('flag,label',[('--prepare-worker','prepare'),('--pure-worker','pure'),('--worker','execute')])
def test_stage_logs_are_exclusive_and_never_overwritten(tmp_path,flag,label):
    seen=[]
    def run(command,**kwargs):
        seen.append(command);kwargs['stdout'].write(b'prefix');return {'status':'exited','exitcode':0}
    function=v4.private(v4.run_child,{'bounded_windows_job':SimpleNamespace(run=run)})
    assert function(tmp_path,[flag],'token')['exitcode']==0
    assert (tmp_path/(label+'_stdout.log')).read_bytes()==b'prefix'
    with pytest.raises(FileExistsError):function(tmp_path,[flag],'token')
    assert len(seen)==1


def test_prepare_then_execute_same_directory_preserves_both_stages(tmp_path):
    calls=[]
    def run(command,**kwargs):
        calls.append(command);kwargs['stdout'].write(command[0].encode());return {'status':'exited','exitcode':0}
    function=v4.private(v4.run_child,{'bounded_windows_job':SimpleNamespace(run=run)})
    function(tmp_path,['--prepare-worker'],'prepare');function(tmp_path,['--worker'],'execute')
    assert len(calls)==2
    assert (tmp_path/'prepare_stdout.log').read_bytes()==b'--prepare-worker'
    assert (tmp_path/'execute_stdout.log').read_bytes()==b'--worker'


def test_unknown_child_stage_cannot_launch(tmp_path):
    with pytest.raises(ValueError,match='one_child_stage'):v4.run_child(tmp_path,['--other'],'token')
