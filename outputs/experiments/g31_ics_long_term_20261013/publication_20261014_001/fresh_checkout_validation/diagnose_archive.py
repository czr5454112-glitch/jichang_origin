from pathlib import Path
import json
import tarfile
import traceback

out=Path(__file__).resolve().parent
root=out.parent/'clean_checkout_001'
result={'operation':'safe extraction diagnosis of already-owned partial fresh archive','source':'source_commit_A.tar'}
try:
    with tarfile.open(out/'source_commit_A.tar') as tar:
        members=tar.getmembers()
        for index,member in enumerate(members):
            target=(root/member.name).resolve()
            if not target.is_relative_to(root.resolve()) or not(member.isdir() or member.isfile()):
                raise ValueError('unsafe archive member')
            try:
                if not target.exists():
                    tar.extract(member,root)
            except Exception as exc:
                result.update(failed_member=member.name,absolute_path=str(target),path_length=len(str(target)),member_index=index,error=str(exc),traceback=traceback.format_exc())
                raise
    result['status']='extracted'
except Exception:
    result['status']='failed'
(out/'extraction_diagnosis.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
