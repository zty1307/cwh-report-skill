"""Registered review contracts; explicit clarifications, no arbitrary policy edits."""
from recover_more_views import POLICY as BASE
from portable_screen import digest

CLARIFICATIONS='''
执行口径澄清：
1. 审查对象是candidate.name/kind指认的真正发言人，不是默认审查发表账号。具名专家接受采访或被媒体转载，其观点仍可成为待溯源候选；不能仅因“非本号原创、记者转述、转引专家”而剔除。仍须核实原文确把完整判断归给这个人，不能把记者背景说明或别人的话混入。
2. 原发时间与发言人绑定。当前账号新发文章，不会让其中旧专家引语自动变成本期观点。原文明示早于agenda.window_start的报道日期、发言日期或可确定的旧发言语境时，应排除该条作为本期发言；当前作者基于旧数据独立作出的新分析另论。参考文献、数据截止日不是发言日期。日期不明但身份和原文支持明确时可retain留待核日期，不要仅因没有精确原发日就称身份不明。不得凭记忆补造具体日期。
3. claim只是不含归属前缀的观点字段。交付时脚本会拼成“完整机构职务+姓名认为，claim”或“微信公众号‘全名’认为，claim”；应结合name、kind、role整体审查。作者原文明确作出的未来判断可作为其判断保留，不要求与会议部署逐字一致，也不要求原作者没说“预计”时强行加上它。原文确有“预计、可能、如果”等条件则必须保留，不能用“认为”掩盖条件被删。
4. 依据仅为提供的原文及议题资料。不能用未提供的所谓通稿原文、证书、数据库身份或模型记忆作为否决证据。身份差异须指出候选与原文哪项实际不同；原文明示相同机构职务姓名时，不要凭想象制造差异。原文确实缺完整身份则needs_source_identity，不能凭知识补齐。
5. 账号自己署名的编辑部或研究组可归完整账号，不强制每位作者实名；外引匿名受访专家、论坛嘉宾不能包装成账号或论坛机构自己的观点。本次会议自身部署仍不是外部舆论分析，具体行业、个人经营或投资判断也仍须符合本期公共议题范围。
6. 不改写claim，不补姓名职务，不重组采访归属。需要改观点归属、漏条件、混说话人的用needs_rewrite；姓名职务尚不能确认用needs_source_identity；单纯报道、部署复述、常识、股票买卖或明确期外旧发言为exclude。每个拒绝理由必须由提供的原文支持，不能为严格而添加原文没有的门槛。
'''
VERSIONS={'base':BASE,'clarified':BASE+CLARIFICATIONS}
BY_HASH={digest(v):v for v in VERSIONS.values()}
