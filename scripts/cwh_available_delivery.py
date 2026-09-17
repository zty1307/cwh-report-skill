"""Deliver available evidence without inventing missing voices or certification."""
from __future__ import annotations
import copy
import re


DELIVERY_POLICY = "deliver_available_with_gaps"
GAP_NOTICE = "本轮在监测期内未取得可引用的独立解读，保留该议题的传播数据；这不代表没有相关讨论。"


def available_delivery(data: dict) -> bool:
    return (data.get("metadata") or {}).get("delivery_policy") == DELIVERY_POLICY


def valid_gap(topic: dict) -> bool:
    gap = topic.get("evidence_gap") or {}
    return not topic.get("clusters") and gap.get("status") == "no_usable_interpretation_in_reviewed_material" and all(
        isinstance(gap.get(key), str) and gap[key].strip()
        for key in ("notice", "search_evidence", "recorded_by")
    )


def prepare_available_delivery(data: dict) -> dict:
    """Counts/search logs explain density; they never certify a semantic claim.

    Only empty clusters are removed. A zero-voice topic remains an explicit gap,
    and selected/unmapped candidates are still rejected by existing validators.
    """
    result = copy.deepcopy(data)
    result.setdefault("metadata", {})["delivery_policy"] = DELIVERY_POLICY
    research = (result.get("research_audit") or {}).get("domestic_media_research") or {}
    pools = {p["topic"]: p for p in research.get("candidate_pool_by_topic") or []}
    reviews = {p["topic"]: p for p in (research.get("public_article_corpus_review") or {}).get("topic_reviews") or []}
    from cwh_search_budget import query_budget_evidence
    budget_notices = list(result['metadata'].get('upstream_review_gaps') or [])
    for topic, review in reviews.items():
        completed = len(set(review.get('reviewed_record_ids') or []))
        deferred = len(set(review.get('deferred_record_ids') or []))
        if deferred and completed < min(12, completed + deferred):
            notice = f'{topic}本轮仅完成{completed}篇原文审核，另有{deferred}篇待审；未达到阅读目标，仅交付已核验内容。'
            review['reading_shortfall_notice'] = notice
            budget_notices.append(notice)
    for pool in pools.values():
        delayed = (pool.get('reading_scope') or {}).get('semantic_reading_deferred_item_ids') or []
        if delayed:
            budget_notices.append(f"{pool['topic']}有{len(delayed)}篇已取得原文但模型阅读未完成的材料暂未审完；现稿不包含其未获核验的观点，不代表相关解读不存在。")
        saturation = pool.get('saturation') or {}
        rounds = saturation.get('rounds') or []
        if rounds and int(rounds[-1].get('new_independent_viewpoints') or 0) > 0:
            proof = query_budget_evidence(saturation, research.get('execution_profile'))
            if proof:
                saturation['completed'] = False
                saturation['budget_stop'] = proof
                budget_notices.append(f"{pool['topic']}已达到本轮{proof['configured_max_queries']}次查询上限，但最后一轮仍有新增观点；检索未证明饱和，保留现有证据交付。")
    if budget_notices:
        result['metadata']['research_budget_gaps'] = budget_notices
    synthesis_gaps = [t['topic'] + '：分组未完成，已提取观点暂按来源顺序排列，待独立核验。'
        for t in (result.get('viewpoints') or {}).get('by_topic') or []
        if any(c.get('cluster_key') == 'source_order' for c in t.get('clusters') or [])]
    if synthesis_gaps:
        result['metadata']['research_budget_gaps'] = list(dict.fromkeys(
            result['metadata'].get('research_budget_gaps', []) + synthesis_gaps))
    review_gaps = [row['notice'] for row in result['metadata'].get('independent_review_gaps', [])]
    if review_gaps:
        result['metadata']['research_budget_gaps'] = list(dict.fromkeys(
            result['metadata'].get('research_budget_gaps', []) + review_gaps))
    for topic in (result.get("viewpoints") or {}).get("by_topic") or []:
        pool = pools.get(topic["topic"], {})
        executions = [q for r in (pool.get("saturation") or {}).get("rounds") or [] for q in r.get("executions") or []]
        audit = "; ".join(f"{q.get('query_id')}: {q.get('status')} ({q.get('result_count', 0)} URLs)" for q in executions)
        if not audit:
            # Missing research cannot be disguised as a legitimate zero result.
            continue
        original = topic.get("clusters") or []
        empty = [c.get("cluster_key") or c.get("summary") for c in original if not c.get("evidence")]
        topic["clusters"] = [c for c in original if c.get("evidence")]
        if empty:
            topic.setdefault("delivery_adjustments", {})["removed_empty_clusters"] = empty
        clusters = topic["clusters"]
        voices = {re.sub(r"\s+", "", str(e.get("speaker_name") or e.get("attribution") or e.get("source") or "")).casefold()
                  for c in clusters for e in c.get("evidence") or []} - {""}
        review = reviews.get(topic["topic"], {})
        count_note = (f"本轮已审核原始记录{len(set(review.get('reviewed_record_ids') or []))}篇，"
                      f"另有{len(set(review.get('deferred_record_ids') or []))}篇未审；"
                      f"当前选入{len(voices)}个独立主体、{len(clusters)}个非空观点簇。"
                      "按现有证据交付，不补造主体、不以未审材料证明不存在解读。")
        def exception(reason):
            return {"reason": reason, "search_evidence": audit, "reviewed_by": "controller_count_audit_not_semantic_certification"}
        if len(voices) < 4:
            topic.setdefault("evidence_shortfall", exception(count_note))
        if len(clusters) == 1:
            topic.setdefault("single_cluster_exception", exception(count_note))
        for cluster in clusters:
            cluster.setdefault("thin_cluster_exception", exception(count_note))
        if not clusters and not any(c.get("decision") == "eligible" for c in pool.get("candidates") or []):
            topic["heading"] = topic["topic"]
            topic["evidence_gap"] = {"status": "no_usable_interpretation_in_reviewed_material",
                                     "notice": GAP_NOTICE, "search_evidence": audit,
                                     "recorded_by": "controller", "scope": count_note}
    return result
