from __future__ import annotations

import re
from typing import Any
from cwh_writing_rules import unsupported_padding_issues, writing_rules


ROLE_PATTERN = (
    r"(?:首席经济学家|首席专家|副主任|副主席|副会长|副院长|理事长|研究员|"
    r"秘书长|分析师|委员|教授|主任|主席|会长|院长|专家)"
)
# Only match an actual attribution verb. Bare ``分析``/``解读`` are often
# nouns or modifiers (for example ``宏观分析人士`` and ``政策解读文章``),
# so treating them as verbs can hide a later, genuinely short expert claim.
OPINION_PATTERN = r"(?:分析(?:认为|指出|称)|解读(?:认为|指出|称)|认为|指出|表示|建议|强调|称|提到)"
ANONYMOUS_EXPERT_PATTERN = re.compile(
    rf"(?:受访|有关|业内|行业|相关)?(?:专家|人士|从业者|学者|分析师)(?:观点)?{OPINION_PATTERN}"
)
TITLED_PERSON_PATTERN = re.compile(
    rf"(?:^|[。；])(?P<title>[\u4e00-\u9fff（）()、·]{{2,100}}?{ROLE_PATTERN})"
    rf"(?P<person>[\u4e00-\u9fff]{{2,4}})(?={OPINION_PATTERN}|从)"
)
BARE_PERSON_PATTERN = re.compile(
    rf"(?:^|[。；，、：\s])(?P<person>[\u4e00-\u9fff]{{2,4}})(?={OPINION_PATTERN})"
)
MIN_ATTRIBUTED_CLAIM_CJK = writing_rules()["viewpoint"]["minimum_claim_cjk"]
GENERIC_VOICES = {
    "媒体",
    "专家",
    "学者",
    "业内人士",
    "有关人士",
    "受访专家",
    "公开网络补证",
    "监测系统Excel",
}
PROHIBITED_VIEWPOINT_PROSE_PATTERNS = (
    (re.compile(r"样本来源[:：]"), "正文不得另列样本来源清单"),
    (re.compile(r"公开网络补证"), "正文不得暴露证据工程标签"),
    (re.compile(r"报道汇集.+(?:等|分别).+(?:分析|判断|观点)"), "不得用报道汇集句替代逐一主体归因"),
    (re.compile(r"(?:多家|多篇|相关)媒体(?:普遍)?(?:认为|指出|关注|分析)"), "不得用泛化媒体归因替代具体媒体或账号"),
)


def _topic_viewpoints(data: dict[str, Any]) -> list[dict[str, Any]]:
    return list((data.get("viewpoints") or {}).get("by_topic") or [])


def enrich_viewpoint_titles(data: dict[str, Any]) -> None:
    """Reuse a verified title for the same person within one subtopic."""

    for viewpoint in _topic_viewpoints(data):
        clusters = list(viewpoint.get("clusters") or [])
        title_by_person: dict[str, str] = {}

        for cluster in clusters:
            details = str(cluster.get("details") or cluster.get("analysis") or "")
            for match in TITLED_PERSON_PATTERN.finditer(details):
                title_by_person.setdefault(
                    match.group("person"),
                    f"{match.group('title')}{match.group('person')}",
                )
            for evidence in cluster.get("evidence") or []:
                if str(evidence.get("attribution_status") or "").lower() != "named_person":
                    continue
                attribution = str(evidence.get("attribution") or "").strip()
                match = re.search(
                    rf"{ROLE_PATTERN}(?P<person>[\u4e00-\u9fff]{{2,4}})$",
                    attribution,
                )
                if match:
                    title_by_person.setdefault(match.group("person"), attribution)

        if not title_by_person:
            continue
        for cluster in clusters:
            field = "details" if cluster.get("details") is not None else "analysis"
            details = str(cluster.get(field) or "")
            for person, titled_person in sorted(
                title_by_person.items(), key=lambda item: len(item[0]), reverse=True
            ):
                details = re.sub(
                    rf"(?<![\u4e00-\u9fff]){re.escape(person)}(?={OPINION_PATTERN})",
                    titled_person,
                    details,
                )
            cluster[field] = details


def cluster_has_named_person(cluster: dict[str, Any]) -> bool:
    text = " ".join(
        [str(cluster.get("details") or cluster.get("analysis") or "")]
        + [
            " ".join(
                str(evidence.get(key) or "")
                for key in ("attribution", "description", "content", "summary", "excerpt")
            )
            for evidence in cluster.get("evidence") or []
        ]
    )
    if TITLED_PERSON_PATTERN.search(text) or BARE_PERSON_PATTERN.search(text):
        return True
    return any(
        str(evidence.get("attribution_status") or "").lower() == "named_person"
        for evidence in cluster.get("evidence") or []
    )


def cluster_has_anonymous_expert_claim(cluster: dict[str, Any]) -> bool:
    text = str(cluster.get("details") or cluster.get("analysis") or "")
    return bool(ANONYMOUS_EXPERT_PATTERN.search(text))


def cluster_needs_attribution_review(cluster: dict[str, Any]) -> bool:
    # A named person elsewhere in the cluster cannot resolve a separate
    # anonymous-expert claim. Media and institutions may, however, be the
    # legitimate speaking subject and do not require an expert-name warning.
    if cluster_has_anonymous_expert_claim(cluster):
        return True
    if cluster.get("needs_attribution_review") is True:
        return True
    return False


def _cjk_length(value: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", value or ""))


def _attribution_voice_count(subject: str) -> int:
    value = str(subject or "").strip()
    titled_people = set(
        re.findall(rf"{ROLE_PATTERN}(?P<person>[\u4e00-\u9fff]{{2,4}})(?=$|[、，]|和|及)", value)
    )
    if titled_people:
        return len(titled_people)
    parts = [part.strip() for part in re.split(r"[、，]|(?:和|及)", value) if part.strip()]
    if len(parts) > 1 and all(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", part) for part in parts):
        return len(parts)
    return 1 if value else 0


def attributed_claims(text: str) -> list[dict[str, Any]]:
    """Extract attributed clauses for fidelity and density checks.

    This is deliberately a structural gate, not the semantic judge. The AI
    must still compare every formal claim with its source excerpt.
    """

    claims: list[dict[str, Any]] = []
    for clause in re.split(r"[。；\n]+", str(text or "")):
        clause = clause.strip(" ，；。")
        if not clause:
            continue
        matches = list(re.finditer(OPINION_PATTERN, clause))
        if not matches:
            continue
        subject_starts: list[int] = []
        for match in matches:
            delimiter = max(
                clause.rfind("，", 0, match.start()),
                clause.rfind(",", 0, match.start()),
                clause.rfind("：", 0, match.start()),
                clause.rfind(":", 0, match.start()),
            )
            subject_starts.append(delimiter + 1)
        for index, match in enumerate(matches):
            subject = clause[subject_starts[index] : match.start()].strip(" ，：")
            claim_end = subject_starts[index + 1] - 1 if index + 1 < len(matches) else len(clause)
            claim = clause[match.end() : claim_end].strip(" ，：, ")
            attributed_clause = clause[subject_starts[index] : claim_end].strip(" ，；。")
            claims.append(
                {
                    "clause": attributed_clause,
                    "subject": subject,
                    "claim": claim,
                    "claim_cjk_length": _cjk_length(claim),
                    "attribution_voice_count": _attribution_voice_count(subject),
                    "anonymous_expert": bool(ANONYMOUS_EXPERT_PATTERN.search(attributed_clause)),
                    "invented_interview_form": bool(re.search(r"受访(?:专家|学者|人士)", subject)),
                }
            )
    return claims


def _voice_key(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", str(value or "")).lower()


def _named_people(text: str) -> set[str]:
    people = {match.group("person") for match in TITLED_PERSON_PATTERN.finditer(text)}
    people.update(match.group("person") for match in BARE_PERSON_PATTERN.finditer(text))
    return {person for person in people if person not in GENERIC_VOICES}


def domestic_viewpoint_quality_issues(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return generic formal-writing issues for domestic viewpoint prose."""

    issues: list[dict[str, Any]] = []
    cross_topic_voices: dict[str, set[str]] = {}
    voice_labels: dict[str, str] = {}

    for viewpoint in _topic_viewpoints(data):
        topic = str(viewpoint.get("topic") or viewpoint.get("heading") or "未命名子议题")
        heading = str(viewpoint.get("heading") or "").strip().rstrip("。")
        reviewed_heading = re.sub(r"^(?:舆论|媒体|专家|机构)(?:普遍)?", "", heading).strip()
        stance_prefixes = tuple(writing_rules()["viewpoint"]["heading_stance_verbs"])
        if heading and not reviewed_heading.startswith(stance_prefixes) and "尚未形成评论性观点" not in heading:
            issues.append(
                {
                    "code": "viewpoint_heading_lacks_stance",
                    "severity": "error",
                    "topic": topic,
                    "message": (
                        f"{topic}的一级标题“{heading}”没有表达明确态度、判断或建议。"
                        "应改为以建议、认可、肯定、认为、期待、支持、质疑或担忧等证据支持的动词开头；"
                        "纯事实议题只能明确写监测期内尚未形成评论性观点。"
                    ),
                }
            )
        voice_clusters: dict[str, set[int]] = {}
        for cluster_index, cluster in enumerate(viewpoint.get("clusters") or [], 1):
            details = str(cluster.get("details") or cluster.get("analysis") or "").strip()
            cluster_name = str(cluster.get("summary") or f"分论点{cluster_index}")
            for phrase in writing_rules()["viewpoint"]["prohibited_phrases"]:
                if phrase in details or phrase in cluster_name or phrase in heading:
                    issues.append({
                        "code": "configured_prohibited_prose", "severity": "error", "topic": topic,
                        "cluster": cluster_name, "message": f"{topic}的成文包含禁用表述“{phrase}”；请使用具体主体与原文支持的判断。",
                    })
            for evidence in cluster.get("evidence") or []:
                for phrase in unsupported_padding_issues(evidence):
                    issues.append({
                        "code": "unsupported_rhetorical_padding", "severity": "error", "topic": topic,
                        "cluster": cluster_name, "evidence_id": evidence.get("evidence_id"),
                        "message": f"{topic}的观点新增了原文片段没有的套话“{phrase}”；请回到原文核对，不得填充字数。",
                    })
            for pattern, reason in PROHIBITED_VIEWPOINT_PROSE_PATTERNS:
                if pattern.search(details):
                    issues.append(
                        {
                            "code": "prohibited_viewpoint_prose",
                            "severity": "error",
                            "topic": topic,
                            "cluster": cluster_name,
                            "message": f"{topic}的“{cluster_name}”违反成文规则：{reason}。",
                        }
                    )
            reviewed_cluster_name = re.sub(
                r"^(?:舆论|媒体|专家|机构)(?:普遍)?",
                "",
                cluster_name,
            ).strip()
            if (
                cluster_name
                and not reviewed_cluster_name.startswith(stance_prefixes)
                and "尚未形成评论性观点" not in cluster_name
                and "以事实性报道为主" not in cluster_name
            ):
                issues.append(
                    {
                        "code": "viewpoint_cluster_heading_lacks_stance",
                        "severity": "error",
                        "topic": topic,
                        "cluster": cluster_name,
                        "message": (
                            f"{topic}的分论点“{cluster_name}”没有表达明确态度、判断或建议。"
                            "‘一是、二是’后的标题同样应以认为、建议、认可、肯定、期待、支持、质疑或担忧等动词开头；"
                            "纯事实分论点只能明确写尚未形成评论性观点或以事实性报道为主。"
                        ),
                    }
                )

            for person in _named_people(details):
                key = f"person:{_voice_key(person)}"
                voice_labels[key] = person
                voice_clusters.setdefault(key, set()).add(cluster_index)
                cross_topic_voices.setdefault(key, set()).add(topic)

            evidence_claim_signatures: set[str] = set()
            for evidence in cluster.get("evidence") or []:
                attribution = str(evidence.get("attribution") or "").strip()
                status = str(evidence.get("attribution_status") or "").lower()
                source = str(evidence.get("source") or "").strip()
                voice = attribution if status in {"named_person", "media_only", "media_voice"} else source
                if not voice or voice in GENERIC_VOICES:
                    continue
                key = f"evidence:{_voice_key(voice)}"
                voice_labels[key] = voice
                voice_clusters.setdefault(key, set()).add(cluster_index)
                formal_claim = str(evidence.get("formal_claim") or evidence.get("claim") or "").strip()
                claim_signature = _voice_key(formal_claim)
                if claim_signature:
                    if claim_signature in evidence_claim_signatures:
                        issues.append(
                            {
                                "code": "duplicate_independent_claim",
                                "severity": "error",
                                "topic": topic,
                                "cluster": cluster_name,
                                "message": (
                                    f"{topic}的“{cluster_name}”把完全相同的观点重复列为独立样本。"
                                    "同文转载或镜像页只能保留在审计数据中，正文和工作台只展示一次。"
                                ),
                            }
                        )
                    evidence_claim_signatures.add(claim_signature)

            for claim in attributed_claims(details):
                if claim["attribution_voice_count"] > 1:
                    issues.append(
                        {
                            "code": "multiple_voices_in_one_attribution",
                            "severity": "error",
                            "topic": topic,
                            "cluster": cluster_name,
                            "message": (
                                f"{topic}的“{cluster_name}”把多个发言主体合并为一条归因：{claim['clause']}。"
                                "应按专家、媒体或机构逐一拆分并分别检查原文忠实度和观点长度。"
                            ),
                        }
                    )
                if claim["claim_cjk_length"] < MIN_ATTRIBUTED_CLAIM_CJK:
                    issues.append(
                        {
                            "code": "attributed_claim_too_short",
                            "severity": "error",
                            "topic": topic,
                            "cluster": cluster_name,
                            "message": (
                                f"{topic}的“{cluster_name}”中存在过短归因：{claim['clause']}。"
                                "应回到原文补足论据、机制或限定，或与同一来源的相关表述合并。"
                            ),
                        }
                    )
                if claim["invented_interview_form"]:
                    issues.append(
                        {
                            "code": "media_attribution_needs_review",
                            "severity": "error",
                            "topic": topic,
                            "cluster": cluster_name,
                            "message": (
                                f"{topic}的“{cluster_name}”使用了“受访专家”但未给出姓名。"
                                "如原文是媒体判断，应改为媒体名认为/称/建议；如确为匿名来源，"
                                "应写媒体援引业内人士观点称并保留核验标记。"
                            ),
                        }
                    )

        for key, cluster_indexes in voice_clusters.items():
            if len(cluster_indexes) <= 1:
                continue
            label = voice_labels.get(key, key)
            issues.append(
                {
                    "code": "repeated_voice_within_topic",
                    "severity": "error",
                    "topic": topic,
                    "message": (
                        f"{topic}在{len(cluster_indexes)}个分论点中重复使用“{label}”。"
                        "应把该来源的相关观点合并为一次完整表述，并用其他独立来源支撑其余分论点。"
                    ),
                }
            )

    for key, topics in cross_topic_voices.items():
        if len(topics) <= 2:
            continue
        label = voice_labels.get(key, key)
        issues.append(
            {
                "code": "repeated_voice_across_topics",
                "severity": "warning",
                "message": (
                    f"“{label}”跨{len(topics)}个子议题重复出现。仅在观点确实独立且直接相关时保留，"
                    "否则优先增加来源多样性。"
                ),
            }
        )
    return issues


def formal_sentiment_row_ready(row: dict[str, Any]) -> bool:
    counts = row.get("sentiment") or {}
    total = sum(int(counts.get(label, 0) or 0) for label in ("positive", "neutral", "negative"))
    return bool(
        row.get("sentiment_formal_ready") is True
        and str(row.get("sentiment_sample_status") or "").lower() == "ready"
        and int(row.get("sentiment_denominator") or 0) > 0
        and row.get("sentiment_authority") == "large_scale_sentiment_analysis"
        and total > 0
    )


def formal_sentiment_available(data: dict[str, Any]) -> bool:
    rows = list(data.get("topic_stats") or [])
    return bool(rows) and all(formal_sentiment_row_ready(row) for row in rows)
