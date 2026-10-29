import copy
import pytest
from cwh_routed_comment_contract import conflict_repair_packet,merge_conflict_repair
from cwh_comment_semantics import COMPACT_CODES

def test_only_conflict_receives_intact_original_context():
    packet={'topics':{'1':'政策'},'posts':[{'id':'p1','text':'原帖完整末尾。'},{'id':'p2','text':'其他原帖。'}],
        'rows':[{'id':1,'post_id':'p1','text':'负面评论完整原话。'},{'id':2,'post_id':'p2','text':'已完成的原话。'}]}
    original={'labels':[[1,0,'oppose'],[2,1,'support']],'selected':[[2,'支持具体政策']]}
    before=copy.deepcopy((packet,original))
    repair=conflict_repair_packet(packet,original,COMPACT_CODES)
    assert repair['rows']==packet['rows'][:1] and repair['posts']==packet['posts'][:1]
    got=merge_conflict_repair(packet,original,repair,{'labels':[[1,0,'context_missing']],'selected':[]},COMPACT_CODES,repair_run_id='actual-repair')
    assert (packet,original)==before
    assert got['rows'][0]['label']=='exclude'
    assert got['rows'][0]['reviewer_run_id']=='actual-repair'
    assert 'reviewer_run_id' not in got['rows'][1]
    assert got['rows'][1]['label']=='positive' and got['rows'][1]['formal']
    assert got['rows'][1]['heading']=='支持具体政策'

def test_repair_cannot_certify_unresolved_topic_or_add_quote():
    packet={'topics':{'1':'政策'},'posts':[{'id':'p','text':'完整原文'}],
        'rows':[{'id':1,'post_id':'p','text':'完整评论'}]}
    original={'labels':[[1,0,'oppose']],'selected':[]}
    repair=conflict_repair_packet(packet,original,COMPACT_CODES)
    for response in [{'labels':[[1,0,'oppose']],'selected':[]},
                     {'labels':[[1,1,'oppose']],'selected':[[1,'擅自新选']]},
                     {'labels':[],'selected':[]}]:
        with pytest.raises(ValueError):merge_conflict_repair(packet,original,repair,response,COMPACT_CODES,repair_run_id='actual-repair')
