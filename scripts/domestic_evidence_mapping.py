"""Validate domestic viewpoint claims against immutable source-text snapshots.

The validator deliberately separates deterministic provenance checks from the
semantic judgment made by an approved model or human reviewer.  A semantic
review is accepted only after every proposition points to a continuous span in
the stored source snapshot; the deterministic gate then verifies hashes,
offsets, speaker identity, article metadata, and final-report propagation.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Any, Iterable


MAPPING_VERSION = "1.0"
VALID_FIDELITY = {"verbatim", "lightly_trimmed", "faithful_paraphrase"}
VALID_ATTRIBUTION_STATUS = {"named_person", "media_voice", "self_media"}
VALID_REVIEW_VERDICTS = {"fully_supported"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def has_ambiguous_meeting_reference(value: Any) -> bool:
    text = re.sub(r'\s+', '', str(value or ''))
    return bool(re.search(r'(?:本次|这次|此次|该|(?:\d{4}年)?[0-9一二三四五六七八九十]{1,2}月(?:[0-9一二三四五六七八九十]{1,2}日)?)会议', text)
                or re.search(r'(?:按照|根据|落实)会议部署|(?:^|[，；。：:])会议(?:既)?(?:部署|提出|要求|指出|强调|决定)', text))


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _numbers(value: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", value)
    arabic = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?%?(?![\w.])", normalized))
    chinese = set(
        re.findall(
            r"[零〇一二两三四五六七八九十百千万亿]+(?:年|月|日|个|项|条|家|人|倍|亿元|万元|公里|种|类|轮|方面|%|％)",
            normalized,
        )
    )
    return arabic | chinese


def _quoted_terms(value: str) -> set[str]:
    return {
        _normalized(term)
        for term in re.findall(r"[“\"]([^”\"]{2,40})[”\"]", value)
        if _normalized(term)
    }


def _semantic_key(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", unicodedata.normalize("NFKC", str(value or ""))).lower()


def _topic_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    viewpoints = data.get("viewpoints") or {}
    return [row for row in viewpoints.get("by_topic") or [] if isinstance(row, dict)]


def _candidate_rows(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    research = ((data.get("research_audit") or {}).get("domestic_media_research") or {})
    rows: list[tuple[str, dict[str, Any]]] = []
    for pool in research.get("candidate_pool_by_topic") or []:
        if not isinstance(pool, dict):
            continue
        topic = _text(pool.get("topic"))
        for candidate in pool.get("candidates") or []:
            if isinstance(candidate, dict):
                rows.append((topic, candidate))
    return rows


def _issue(code: str, message: str, **context: Any) -> dict[str, Any]:
    return {"code": code, "severity": "error", "message": message, **context}


def _validate_span(
    source_text: str,
    expected_text: str,
    start: Any,
    end: Any,
    *,
    label: str,
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
        return [_issue("span_offsets_missing", f"{label}缺少整数起止位置，无法回到原文。", **context)]
    if start < 0 or end <= start or end > len(source_text):
        return [_issue("span_offsets_invalid", f"{label}的原文位置越界。", **context)]
    if source_text[start:end] != expected_text:
        issues.append(_issue("span_text_mismatch", f"{label}与保存快照中对应位置的连续原文不一致。", **context))
    return issues


def validate_analysis_mapping(data: dict[str, Any], *, require_semantic_review: bool = True) -> dict[str, Any]:
    """Return a deterministic audit for an analysis_bundle/report_data payload."""

    issues: list[dict[str, Any]] = []
    metadata = data.get("metadata") or {}
    if _text(metadata.get("evidence_mapping_version")) != MAPPING_VERSION:
        issues.append(
            _issue(
                "mapping_version_missing",
                f"境内证据映射版本必须为{MAPPING_VERSION}，旧版或未映射证据不能进入正式报告。",
            )
        )
    if not _text(metadata.get("authoring_run_id")):
        issues.append(_issue("authoring_run_id_missing", "境内观点包缺少authoring_run_id，无法证明语义复核来自独立第二遍运行。"))

    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    snapshots: dict[str, tuple[str, str, str]] = {}
    eligible_count = 0
    snapshot_count = 0
    for topic, candidate in _candidate_rows(data):
        candidate_id = _text(candidate.get("candidate_id"))
        if candidate_id:
            candidates[(topic, candidate_id)] = candidate
        if _text(candidate.get("decision")) != "eligible":
            continue
        eligible_count += 1
        context = {"topic": topic, "candidate_id": candidate_id}
        snapshot = candidate.get("source_snapshot")
        if not isinstance(snapshot, dict):
            issues.append(_issue("source_snapshot_missing", "合格候选缺少原始页面文本快照。", **context))
            continue
        snapshot_count += 1
        required = ("snapshot_id", "url", "title", "captured_at", "capture_method", "source_text", "source_text_sha256")
        missing = [field for field in required if not _text(snapshot.get(field))]
        if missing:
            issues.append(_issue("source_snapshot_fields_missing", "原始页面快照缺少字段：" + "、".join(missing), **context))
            continue
        snapshot_id = _text(snapshot.get("snapshot_id"))
        source_text = str(snapshot.get("source_text") or "")
        digest = _sha256_text(source_text)
        if digest != _text(snapshot.get("source_text_sha256")).lower():
            issues.append(_issue("source_snapshot_hash_mismatch", "原始页面快照文本哈希不一致，内容可能被修改。", **context))
        if _normalized(snapshot.get("url")) != _normalized(candidate.get("url")):
            issues.append(_issue("source_snapshot_url_mismatch", "原始页面快照链接与候选链接不一致。", **context))
        if _normalized(snapshot.get("title")) != _normalized(candidate.get("title")):
            issues.append(_issue("source_snapshot_title_mismatch", "原始页面快照标题与候选文章标题不一致。", **context))
        signature = (_text(snapshot.get("url")), _text(snapshot.get("title")), digest)
        if snapshot_id in snapshots and snapshots[snapshot_id] != signature:
            issues.append(_issue("source_snapshot_id_collision", "同一snapshot_id对应了不同页面或文本。", **context))
        snapshots[snapshot_id] = signature

    evidence_ids: set[str] = set()
    evidence_count = 0
    mapped_count = 0
    for viewpoint in _topic_rows(data):
        topic = _text(viewpoint.get("topic"))
        for cluster_index, cluster in enumerate(viewpoint.get("clusters") or [], 1):
            if not isinstance(cluster, dict):
                continue
            details = _text(cluster.get("details") or cluster.get("analysis"))
            for evidence_index, evidence in enumerate(cluster.get("evidence") or [], 1):
                if not isinstance(evidence, dict):
                    continue
                evidence_count += 1
                candidate_id = _text(evidence.get("candidate_id"))
                evidence_id = _text(evidence.get("evidence_id"))
                context = {
                    "topic": topic,
                    "cluster_index": cluster_index,
                    "evidence_index": evidence_index,
                    "candidate_id": candidate_id,
                    "evidence_id": evidence_id,
                }
                if not evidence_id:
                    issues.append(_issue("evidence_id_missing", "成文观点缺少唯一evidence_id。", **context))
                elif evidence_id in evidence_ids:
                    issues.append(_issue("evidence_id_duplicate", "evidence_id重复，无法一对一反查。", **context))
                else:
                    evidence_ids.add(evidence_id)
                candidate = candidates.get((topic, candidate_id))
                if not candidate or _text(candidate.get("decision")) != "eligible":
                    issues.append(_issue("eligible_candidate_missing", "成文观点没有映射到本议题的合格候选。", **context))
                    continue
                snapshot = candidate.get("source_snapshot") or {}
                source_text = str(snapshot.get("source_text") or "")
                snapshot_id = _text(snapshot.get("snapshot_id"))
                if _text(evidence.get("source_snapshot_id")) != snapshot_id:
                    issues.append(_issue("evidence_snapshot_mismatch", "成文观点引用的source_snapshot_id与候选快照不一致。", **context))
                if _normalized(evidence.get("url")) != _normalized(candidate.get("url")):
                    issues.append(_issue("evidence_url_mismatch", "成文观点链接与候选原始链接不一致。", **context))
                if _normalized(evidence.get("article_title")) != _normalized(candidate.get("title")):
                    issues.append(_issue("evidence_article_title_mismatch", "成文观点的文章标题与候选原始标题不一致。", **context))

                attribution_status = _text(evidence.get("attribution_status"))
                speaker_name = _text(evidence.get("speaker_name"))
                speaker_role = _text(evidence.get("speaker_role"))
                attribution = _text(evidence.get("attribution"))
                if attribution_status not in VALID_ATTRIBUTION_STATUS:
                    issues.append(_issue("attribution_status_invalid", "成文观点缺少有效的发言主体类型。", **context))
                if not speaker_name:
                    issues.append(_issue("speaker_name_missing", "成文观点缺少可单独核验的发言人、媒体或账号名称。", **context))
                elif speaker_name not in attribution:
                    issues.append(_issue("speaker_attribution_mismatch", "speaker_name未包含在正式归因中。", **context))
                if attribution_status == "named_person":
                    if re.search(r"[、,，]|(?:和|及)", speaker_name):
                        issues.append(_issue("multiple_speakers_in_evidence", "一条成文证据合并了多个发言人，必须逐人拆分。", **context))
                    if not speaker_role:
                        issues.append(_issue("speaker_role_missing", "具名专家缺少原文提供的机构或职务。", **context))

                excerpt = str(evidence.get("source_excerpt") or "")
                if not excerpt.strip():
                    issues.append(_issue("source_excerpt_missing", "成文观点缺少连续原文片段。", **context))
                else:
                    issues.extend(
                        _validate_span(
                            source_text,
                            excerpt,
                            evidence.get("source_excerpt_start"),
                            evidence.get("source_excerpt_end"),
                            label="source_excerpt",
                            context=context,
                        )
                    )
                    publisher_attribution = attribution_status in {"media_voice", "self_media"} and speaker_name in {
                        _text(candidate.get("source")), _text(candidate.get("account"))
                    }
                    if speaker_name and speaker_name not in excerpt and not publisher_attribution:
                        issues.append(_issue("speaker_not_in_excerpt", "发言主体未出现在该观点对应的连续原文片段中。", **context))
                    if attribution_status == "named_person" and speaker_role and _semantic_key(speaker_role) not in _semantic_key(excerpt):
                        issues.append(_issue("speaker_role_not_in_excerpt", "具名专家的机构或职务未出现在对应原文片段中。", **context))

                formal_claim = _text(evidence.get("formal_claim"))
                if require_semantic_review and has_ambiguous_meeting_reference(formal_claim):
                    issues.append(_issue("ambiguous_meeting_reference", "正式观点含未展开的会议指称；须依据原文明确实际会议名称，不能由宿主猜测替换。", **context))
                if not formal_claim:
                    issues.append(_issue("formal_claim_missing", "成文观点缺少正式报告表述。", **context))
                elif _normalized(formal_claim) not in _normalized(details):
                    issues.append(_issue("formal_claim_not_in_cluster", "正式观点没有逐字进入所属观点簇正文。", **context))
                if _text(evidence.get("wording_fidelity")) not in VALID_FIDELITY:
                    issues.append(_issue("wording_fidelity_invalid", "wording_fidelity缺失或取值无效。", **context))
                unsupported_numbers = sorted(_numbers(formal_claim) - _numbers(excerpt))
                if unsupported_numbers:
                    issues.append(_issue("claim_adds_numbers", "正式观点新增了原文片段中没有的数字：" + "、".join(unsupported_numbers), **context))
                unsupported_terms = sorted(_quoted_terms(formal_claim) - _quoted_terms(excerpt))
                if unsupported_terms:
                    issues.append(_issue("claim_adds_quoted_terms", "正式观点新增了原文片段中没有的专名或引号表述：" + "、".join(unsupported_terms), **context))

                if not require_semantic_review:
                    if not any(issue.get("evidence_id") == evidence_id for issue in issues):
                        mapped_count += 1
                    continue
                review = evidence.get("semantic_review")
                if not isinstance(review, dict):
                    issues.append(_issue("semantic_review_missing", "成文观点缺少逐命题语义核验。", **context))
                    continue
                if _text(review.get("verdict")) not in VALID_REVIEW_VERDICTS:
                    issues.append(_issue("semantic_review_not_supported", "语义核验未明确判定为fully_supported。", **context))
                missing_review = [field for field in ("reviewed_by", "reviewed_at", "rationale") if not _text(review.get(field))]
                if missing_review:
                    issues.append(_issue("semantic_review_fields_missing", "语义核验缺少字段：" + "、".join(missing_review), **context))
                propositions = [row for row in review.get("propositions") or [] if isinstance(row, dict)]
                if not propositions:
                    issues.append(_issue("semantic_propositions_missing", "语义核验没有把观点拆成可核验命题。", **context))
                    continue
                proposition_text = "".join(_text(row.get("text")) for row in propositions)
                if not proposition_text:
                    issues.append(_issue("semantic_proposition_text_missing", "语义核验命题缺少文本。", **context))
                elif _semantic_key(proposition_text) != _semantic_key(formal_claim):
                    issues.append(_issue("semantic_propositions_incomplete", "逐命题核验没有完整覆盖formal_claim，可能遗漏了未经核验的结论。", **context))
                excerpt_start = evidence.get("source_excerpt_start")
                excerpt_end = evidence.get("source_excerpt_end")
                for proposition_index, proposition in enumerate(propositions, 1):
                    prop_context = {**context, "proposition_index": proposition_index}
                    if _text(proposition.get("verdict")) not in VALID_REVIEW_VERDICTS:
                        issues.append(_issue("semantic_proposition_not_supported", "存在未被原文完全支持的子命题。", **prop_context))
                    quote = str(proposition.get("source_quote") or "")
                    if not _text(proposition.get("text")) or not quote.strip() or not _text(proposition.get("rationale")):
                        issues.append(_issue("semantic_proposition_fields_missing", "子命题缺少命题文本、原文依据或核验理由。", **prop_context))
                        continue
                    issues.extend(
                        _validate_span(
                            source_text,
                            quote,
                            proposition.get("source_quote_start"),
                            proposition.get("source_quote_end"),
                            label=f"第{proposition_index}个子命题原文依据",
                            context=prop_context,
                        )
                    )
                    quote_start = proposition.get("source_quote_start")
                    quote_end = proposition.get("source_quote_end")
                    if (
                        isinstance(excerpt_start, int)
                        and not isinstance(excerpt_start, bool)
                        and isinstance(excerpt_end, int)
                        and not isinstance(excerpt_end, bool)
                        and isinstance(quote_start, int)
                        and not isinstance(quote_start, bool)
                        and isinstance(quote_end, int)
                        and not isinstance(quote_end, bool)
                        and not (excerpt_start <= quote_start < quote_end <= excerpt_end)
                    ):
                        issues.append(_issue("semantic_quote_outside_excerpt", "子命题引用位置不在该观点的连续原文片段内。", **prop_context))
                if not any(issue.get("evidence_id") == evidence_id for issue in issues):
                    mapped_count += 1

    return {
        "schema_version": MAPPING_VERSION,
        "status": "passed" if not issues else "blocked",
        "eligible_candidate_count": eligible_count,
        "snapshot_count": snapshot_count,
        "evidence_count": evidence_count,
        "mapped_evidence_count": mapped_count,
        "issues": issues,
    }


def analysis_bundle_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for viewpoint in _topic_rows(data):
        for cluster in viewpoint.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            for evidence in cluster.get("evidence") or []:
                if isinstance(evidence, dict) and _text(evidence.get("evidence_id")):
                    rows[_text(evidence.get("evidence_id"))] = evidence
    return rows


def validate_semantic_review_packet(
    analysis: dict[str, Any],
    packet: dict[str, Any],
    *,
    source_bundle_sha256: str,
) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    if _text(packet.get("review_version")) != MAPPING_VERSION:
        issues.append(_issue("review_version_invalid", f"独立语义复核版本必须为{MAPPING_VERSION}。"))
    if _text(packet.get("review_pass")) != "independent_second_pass":
        issues.append(_issue("review_pass_not_independent", "语义复核必须标记为independent_second_pass。"))
    authoring_run_id = _text((analysis.get("metadata") or {}).get("authoring_run_id"))
    reviewer_run_id = _text(packet.get("reviewer_run_id"))
    if not reviewer_run_id:
        issues.append(_issue("reviewer_run_id_missing", "独立语义复核缺少reviewer_run_id。"))
    elif reviewer_run_id == authoring_run_id:
        issues.append(_issue("reviewer_not_independent", "语义复核与观点撰写使用了同一run_id，不能视为独立第二遍核验。"))
    if _text(packet.get("source_bundle_sha256")).lower() != source_bundle_sha256.lower():
        issues.append(_issue("review_source_hash_mismatch", "独立语义复核对应的analysis_bundle哈希不一致。"))
    expected = _evidence_by_id(analysis)
    reviews = [row for row in packet.get("reviews") or [] if isinstance(row, dict)]
    actual: dict[str, dict[str, Any]] = {}
    for index, review in enumerate(reviews, 1):
        evidence_id = _text(review.get("evidence_id"))
        if not evidence_id:
            issues.append(_issue("review_evidence_id_missing", f"第{index}条独立语义复核缺少evidence_id。"))
        elif evidence_id in actual:
            issues.append(_issue("review_evidence_id_duplicate", f"独立语义复核重复审核evidence_id：{evidence_id}。"))
        else:
            actual[evidence_id] = review
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    if missing:
        issues.append(_issue("review_evidence_missing", "独立语义复核漏审：" + "、".join(missing[:12])))
    if extra:
        issues.append(_issue("review_evidence_extra", "独立语义复核引用了不存在的evidence_id：" + "、".join(extra[:12])))
    for evidence_id, review in actual.items():
        if evidence_id not in expected:
            continue
        actual_reviewer = _text(review.get('reviewer_run_id')) or reviewer_run_id
        forbidden = {authoring_run_id, _text((packet.get('repair_provenance') or {}).get('author_repair_run_id'))} - {''}
        if actual_reviewer in forbidden:
            issues.append(_issue('reviewer_not_independent', '局部修复的作者不能审核自己的观点。', evidence_id=evidence_id))
        if review.get('reviewer_run_id') and actual_reviewer not in (packet.get('reviewer_run_ids') or [reviewer_run_id]):
            issues.append(_issue('reviewer_run_id_unlisted', '逐条复核run_id未在独立运行清单中留痕。', evidence_id=evidence_id))
        if _text(review.get("verdict")) not in VALID_REVIEW_VERDICTS:
            issues.append(_issue("review_not_fully_supported", "独立复核未判定该观点为fully_supported。", evidence_id=evidence_id))
        for field in ("reviewed_by", "reviewed_at", "rationale", "propositions"):
            if not review.get(field):
                issues.append(_issue("review_fields_missing", "独立语义复核缺少字段：" + field, evidence_id=evidence_id))
    return issues


def apply_semantic_review_packet(
    analysis: dict[str, Any],
    packet: dict[str, Any],
    *,
    source_bundle_sha256: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    issues = validate_semantic_review_packet(analysis, packet, source_bundle_sha256=source_bundle_sha256)
    if issues:
        return copy.deepcopy(analysis), issues
    verified = copy.deepcopy(analysis)
    reviews = {_text(row.get("evidence_id")): row for row in packet.get("reviews") or [] if isinstance(row, dict)}
    for evidence_id, evidence in _evidence_by_id(verified).items():
        review = dict(reviews[evidence_id])
        review.pop("evidence_id", None)
        review["review_pass"] = "independent_second_pass"
        review["reviewer_run_id"] = _text(review.get('reviewer_run_id')) or _text(packet.get("reviewer_run_id"))
        evidence["semantic_review"] = review
    (verified.setdefault("metadata", {}))["semantic_review_packet_sha256"] = hashlib.sha256(
        json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return verified, []


def mapping_problem_messages(audit: dict[str, Any]) -> list[str]:
    messages = []
    for row in audit.get("issues") or []:
        context = []
        if _text(row.get("topic")):
            context.append("议题=" + _text(row.get("topic")))
        if _text(row.get("candidate_id")):
            context.append("候选=" + _text(row.get("candidate_id")))
        if _text(row.get("evidence_id")):
            context.append("证据=" + _text(row.get("evidence_id")))
        prefix = "[" + "；".join(context) + "] " if context else ""
        messages.append(prefix + _text(row.get("message") or row.get("code")))
    return messages


def _dashboard_data(path: Path) -> dict[str, Any]:
    html = path.read_text(encoding="utf-8")
    match = re.search(r'<script[^>]+id="dashboard-data"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise ValueError("Dashboard structured data is missing")
    payload = json.loads(match.group(1))
    return payload if isinstance(payload, dict) else {}


def _docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    return "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", xml, re.S))


def _mapping_rows(data: dict[str, Any]) -> Iterable[tuple[str, str]]:
    for viewpoint in _topic_rows(data):
        for cluster in viewpoint.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            details = _text(cluster.get("details") or cluster.get("analysis"))
            for evidence in cluster.get("evidence") or []:
                if isinstance(evidence, dict):
                    yield _text(evidence.get("evidence_id")), details


def validate_release_mapping(report_dir: Path, *, upstream_analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    report_data = json.loads((report_dir / "report_data.json").read_text(encoding="utf-8-sig"))
    analysis = report_data.get("analysis_bundle") or {}
    audit = validate_analysis_mapping(analysis)
    issues = list(audit.get("issues") or [])
    upstream_rows = dict(_mapping_rows(upstream_analysis or analysis))
    report_rows = dict(_mapping_rows(analysis))
    if upstream_analysis is not None and upstream_rows != report_rows:
        issues.append(_issue("report_mapping_changed", "渲染后的report_data与上游证据映射不一致。"))
    dashboard = _dashboard_data(report_dir / "cwh_dashboard.html")
    dashboard_analysis = dashboard.get("analysis_bundle") or {}
    if dict(_mapping_rows(dashboard_analysis)) != report_rows:
        issues.append(_issue("dashboard_mapping_missing", "工作台未完整保留上游evidence_id与观点映射。"))
    docx_text = _normalized(_docx_text(report_dir / "cwh_formal_report.docx"))
    for evidence_id, details in report_rows.items():
        if evidence_id and _normalized(details) not in docx_text:
            issues.append(_issue("word_claim_missing", "Word正文未保留该证据对应的完整观点簇正文。", evidence_id=evidence_id))
    audit.update({
        "status": "passed" if not issues else "blocked",
        "issues": issues,
        "report_mapping_count": len(report_rows),
        "dashboard_mapping_count": len(dict(_mapping_rows(dashboard_analysis))),
        "word_backcheck_count": sum(1 for _, details in report_rows.items() if _normalized(details) in docx_text),
    })
    return audit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_bundle", type=Path, nargs="?")
    parser.add_argument("--report-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.report_dir:
        audit = validate_release_mapping(args.report_dir)
    elif args.analysis_bundle:
        audit = validate_analysis_mapping(json.loads(args.analysis_bundle.read_text(encoding="utf-8-sig")))
    else:
        parser.error("provide analysis_bundle or --report-dir")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if audit.get("status") == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
