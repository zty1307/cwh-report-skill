import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import cwh_remaining_research as remaining


def test_completed_native_selection_including_local_repairs_is_not_repeated(tmp_path,monkeypatch):
    log=tmp_path/'native.jsonl';log.write_text('actual completed selection and repairs','utf-8')
    calls=[]
    def select(request,choices,command,workspace,timeout,model_call,**kwargs):
        calls.append(request)
        return {'items':choices,'heading':'已有判断','clusters':[]},{'session_id':'real-run','log':str(log),'seconds':2}
    monkeypatch.setattr(remaining,'native_topic_synthesis',select)
    args=({'eligible_items':[]},[],['glm'],tmp_path,90,None)
    first,_=remaining.completed_topic_selection(*args)
    second,run=remaining.completed_topic_selection(*args)
    assert first==second and len(calls)==1 and run['cache_reused'] and run['seconds']==0
    log.write_text('tampered','utf-8')
    with pytest.raises(ValueError):remaining.completed_topic_selection(*args)
