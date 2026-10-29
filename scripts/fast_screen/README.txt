国常会原始文章独立筛选工具：GLM优先适配实验版

输入与输出
用户只需给原始公众文章Excel和本期会议日期、议程。内部agenda.json由系统准备，不要求用户手写。
脚本扫描全部原始数据，排出最多50篇、合计不超过11万字符的完整导出正文，交给GLM提取观点，再生成分议题候选清单。
这是候选收集，不是可引用认证。重复转载、近义判断、待补职务或待核日期均须区分，不把提名数当独立声音数。
监测导出可能本身截断文章；完整导出正文不等于已取得原始网页全文。

启动
Python3.10+；读xlsx需openpyxl。
python native_screen_samples.py --workbook 原始文章.xlsx --agenda agenda.json --out 新目录 --run
默认目标为glm-5.3-ioa，沿用本机既有WorkBuddy身份验证，不读取或输出密钥。
只生成任务不调用模型：省略--run。已规范化数据可用--records records.json替代--workbook。
模型、分批及调用配置写在native_model_profiles.json，实验状态和真实覆盖须检查benchmark.json。
可显式选择已配置的--model glm-5.3-flash-ioa；其他模型保留为对照，不发生自动模型回退。
工具不依赖任何聊天记忆，不调用外部人际消息工具，不修改正式安装的常务会Skill或已有报告。

GLM适配的实际内容
GLM5.3以低强度思考运行；不能把关闭思考当作成功加速。请求带low不代表服务端效果已经得到证明。
使用此前整流程的有限语义审核系统指令，避免带入默认编程助手任务指令。
GLM使用姓名、职务、观点、证据段号等完整字段名，不要求翻译单字母缩写。
完整原文、原有提取规则及不同实质判断保留要求不变；不为加速硬截原文、限制每人观点条数或改成只读局部。
分批只是调用配置，某次小样本较快不能推断所有期次都更快。
GLM的排队更重视阅读成本、新主体、新论述线索与议题覆盖；并非把所有长文判成无用。与原99篇39万字队列不同，可能遗漏观点，需保留未读名单并单独检查取舍。50篇是本版明确的预算取舍，不是证明余下样本都用不了。
当前GLM每批最多12篇、文章载荷不超过60000字符。完整单篇过大时报错，不截断正文。
只读wire observer核对模型与推理参数的标量，不记录消息正文、请求地址、认证头或密钥，不改请求。

脚本与AI的分工
脚本处理Excel、排除审计、完整文章队列、相同原话调度关联、段号、ID、哈希、固定句式、字段校验、计时及失败保存。
相同专家原话不代表整篇文章相同。备用文章保留未读状态，不能记为已排除。
AI阅读全文，判断议题相关、独立分析、实际主体、完整机构职务、原话归属及预测条件。
不把股票买卖、会议部署、纯新闻、常识、匿名外引包装成可引用观点；不补造姓名职务、日期和观点。
无明确身份或日期的有价值线索保留待核。旧发言和当前作者基于旧数据作出的新分析须分开。

结果入口
results_guarded/分议题候选_脚本检查后_待复核.txt：按“完整机构职务+姓名认为”或“微信公众号全称认为”组织，附标题、监测时间、链接。
results_guarded/candidates_pending_independent_review.json：归属检查后全部候选，formal_ready=false。
results_guarded/returned_to_event_material_or_attribution_repair.json：会议自身部署、泛称主体归属退回待处理，保留原始记录，不排除整篇文章。
time_context_flags：观点或身份的原文范围含早于本期的完整日期时提示核实。它不是旧发言的自动结论，也不能认证无标记者发生在本期。
results/保留模型初始全部提名与字段问题；model/保留全文、原生响应、未读名单、调用及输入输出哈希。
review_queue/只准备独立审核任务，任务生成不代表已执行复核。
benchmark.json记录脚本与AI实际总时间、实际读完数量和提名，不把预算上限当成完成保证。

只复核拟采用的候选
先由报告编排选出candidate_id，再用新的独立上下文阅读全文复核；不把所有最终不会采用的提名重复审核。
python native_review_samples.py --job 初筛任务目录 --ids selected_ids.json --out 新复核目录
默认仍为GLM，自动使用新的独立上下文和完整原文，无需手写宿主JSON参数。更换模型可显式传--model。
selected_ids.json由系统编排生成，内容为candidate_id数组。审核宿主接收UTF-8 JSON，返回output_schema要求的JSON。
默认clarified规则明确具名专家转载可作线索、期外旧引语不可当本期新观点、账号原创分析不必强制每位编辑实名。
通过AI复核仍须核原始网页、原发时间、身份和正文适配。复核者也会漏判或给出矛盾理由，不得据retain自动进入正文。

时间与恢复
独立入口默认预算360秒、预留15秒记账；这不是整个报告40分钟的额外额度。整流程控制器须按共享剩余预算下调本步骤额度。
测试时间不含未执行的全网溯源、正文选用复核、分组写作与整份报告交付，不能声称整流程已40分钟完成。
超时或失败如实留为未读；不自动换模型，不重置原任务时钟，不覆盖旧目录。
根容器漏闭合仅允许机械补闭合符，不补字段或观点；单篇坏结构隔离为未读，后续只补读缺失的完整文章，并沿用原预算。
原发日已明确返回空字符串但漏了日期证据字段时，脚本可按未知空数组补齐并记录原因，不推断实际日期；有日期却缺证据或其他必需字段缺失仍保留待处理，不让整批导出崩溃。
断网暂停后的恢复用时与连续测速分开。复用旧结果须核验原文、规则、任务和响应哈希。

其他API宿主
业务任务使用普通JSON，包含完整材料、规则和输出结构。API宿主stdin读取任务，stdout返回一个JSON对象。
canonical_screen_transport.py为完整字段名接口，compact_screen_transport.py保留原压缩接口；完整原文不变。
宿主认证由部署环境管理，不将API密钥写入任务、配置包或提示词。不保证其他厂商支持相同推理参数，须按其官方文档适配。
GLM参数依据：https://docs.z.ai/guides/llm/glm-5.3

离线检查
python -m unittest test_portable_screen test_priority_screen test_recovery_contracts test_crossperiod_recall test_identity_whitespace_recovery test_opinion_gate_v8 test_optimized_host_contract test_compact_screen_transport test_collection_contracts test_native_screen_entry test_native_json_syntax test_localize_native_decode test_candidate_guards test_canonical_screen_transport test_glm_wire_observer test_native_review_entry test_collection_missing_fields -q
离线检查不调用真实模型，不代替真实覆盖和质量测试。工具包不含原始数据或认证信息。
