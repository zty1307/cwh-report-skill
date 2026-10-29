import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cwh_screen_bridge import materialize_screen


def test_one_invalid_native_identity_range_does_not_discard_completed_article_or_valid_claim(tmp_path):
    def save(name,value):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    content='研究员张三表示，需要完善跨部门配套规则。'
    save('model/sources.json',[{'id':'r2','content':content}])
    save('model/article_decisions.json',[{'id':'r2','code':'has_view','views':[]}])
    candidate={'id':'r2','topic':'本期议题','errors':[],'kind':'person','name':'张三','role':'研究员',
               'excerpt_start':0,'excerpt_end':len(content),'claim':'需要完善跨部门配套规则。','candidate_id':'good'}
    save('results_guarded/candidates_pending_independent_review.json',[
        {**candidate,'candidate_id':'bad','identity':['unknown/1','unknown/2']},candidate])
    (tmp_path/'host_audit').mkdir()
    topics,quarantine,runs=materialize_screen(tmp_path,{'r2':{'content':content,'record_id':'source2','topic_hits':[1]}},['本期议题'])
    assert len(topics['本期议题'])==1
    decision=topics['本期议题'][0]['decision']
    assert decision['decision']=='eligible' and len(decision['claims'])==1
    assert decision['claims'][0]['screen_candidate_id']=='good'
    assert quarantine[0]['candidate']['candidate_id']=='bad'
    assert quarantine[0]['reason']=='invalid_identity_paragraph_range'
