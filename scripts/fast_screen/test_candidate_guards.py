import copy,unittest
from candidate_guards import reason,date_context_flags

class CandidateGuardContracts(unittest.TestCase):
    def test_old_date_context_is_flagged_without_excluding_or_inventing_statement_date(self):
        v={'kind':'person','name':'甲','excerpt':'据某报2026年3月12日报道，甲指出应完善托育服务。','role_excerpt':''}
        before=copy.deepcopy(v);flags=date_context_flags(v,'2026-05-15 19:00:00')
        self.assertEqual('2026-03-12',flags[0]['context_date']);self.assertFalse(flags[0]['automatic_exclusion']);self.assertEqual(before,v)
        self.assertFalse(date_context_flags({**v,'kind':'account'},'2026-05-15'))
        self.assertFalse(date_context_flags(v,'2026-03-01'))
    def test_meeting_itself_is_not_external_opinion(self):
        v={'kind':'institution','name':'7月31日国务院常务会议','claim':'原有观点不改变。'};before=copy.deepcopy(v)
        self.assertEqual('meeting_statement_is_not_external_opinion',reason(v));self.assertEqual(before,v)
        self.assertFalse(reason({'kind':'institution','name':'中国人民大学课题组'}))
        self.assertFalse(reason({'kind':'account','name':'会议观察'}))
    def test_generic_speaker_needs_identity_but_full_group_is_preserved(self):
        self.assertEqual('current_speaker_label_is_not_identifiable',reason({'kind':'institution','name':'受访专家'}))
        self.assertFalse(reason({'kind':'institution','name':'交通运输部规划研究院城市交通与现代物流研究所课题组'}))
        self.assertFalse(reason({'kind':'institution','name':'住房和城乡建设部'}))

if __name__=='__main__':unittest.main()
