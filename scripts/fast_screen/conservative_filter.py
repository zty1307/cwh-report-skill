"""High-recall deterministic article exclusion, without a top-N cutoff.

Historical model labels are read only by evaluate(), never by the filter.
All nonexcluded articles go to full-text AI review exactly once.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from functools import lru_cache


POLICY_VERSION = "conservative-7"
SPLIT = re.compile(r"[。！？!?；;\n]+")
ROLE = re.compile(r"教授|研究员|经济学家|学者|分析师|专家|智库|课题组|研究组|评论员|律师|作者|署名|撰文|社论|锐评|社评|网评|评论称|分析称|受访|对.{0,16}记者.{0,8}(?:表示|指出|认为)")
ANALYSIS = re.compile(r"认为|建议|意味着|关键|根源|难点|瓶颈|短板|制约|风险|问题|原因|由于|因此|背后|逻辑|矛盾|不足|不够|有助于|取决于|并非|而是|不能|不应|才能|必须|需要|应当|亟须|值得|解读|点评|观察|反思|挑战|机遇|痛点|堵点|协同|可持续|低水平|重复建设|过度|闲置|避免|为何|为什么")
STRONG_ANALYSIS = re.compile(r"认为|建议|意味着|关键在于|根源|难点|瓶颈|短板|制约|风险在于|问题在于|原因在于|背后|逻辑|矛盾|不足|不够|有助于|取决于|并非|而是|不能|不应|才能|亟须|解读|点评|反思|挑战|痛点|堵点|低水平|重复建设|过度|闲置|为何|为什么|正是因为|不仅.{0,30}更|不只是|决定了|误导|可靠性|干扰")
CAUSAL_ANALYSIS = re.compile(r"反向拉动|双向协同|形成联动|相互依赖|供需错配|降低.{0,18}成本|提升.{0,18}效率|由于.{0,35}(?:因此|导致)|使得|从而|有利于|将为.{0,30}提供|关键在|本质是|改变.{0,18}格局|不再.{0,25}而")
OFFICIAL_SENTENCE = re.compile(r"会议(?:指出|强调|要求|听取|审议|研究)|国常会(?:指出|强调|要求|提出|部署)|会商(?:指出|强调|要求)|他强调")
INDEPENDENT_EXTENSION = re.compile(r"意味着|表明|反映出|背后|我们认为|笔者|作者|我认为|解读|点评|不难看出|可见|这说明|值得注意")
DEPLOYMENT = re.compile(r"^(?:会议(?:指出|强调|要求|认为|听取|审议|研究)|要|进一步提高|国务院总理|中共中央|习近平|李强|张国清|新华社.{0,18}电)")
TRADE = re.compile(r"涨停|买入|卖出|仓位|短线|低吸|打板|止盈|止损|追涨|抄底|减仓|加仓|荐股|个股|大盘|主力资金|板块轮动")
TRADE_TITLE = re.compile(r"股市|A股|复盘|早盘|午评|收评|晚评|龙虎榜|行情|投资策略|后市|涨停|爆雷")
ATTRIBUTED_ANALYSIS = re.compile(r"(?:报告|研究|机构|证券|分析|评论|经济学家|学者|教授|研究员|律师).{0,25}(?:认为|指出|显示|建议|发现|预测|表示)|(?:认为|分析认为|点评|解读)[：:]")
POLICY_DIAGNOSIS = re.compile(r"供需|供给|需求|失衡|门槛|跨区域|跨地区|自主可控|协同调度|技术外流|安全审查|数据归属|控制权|合规|监管|标准|制度|机制|运力|发射成本")
FOOTER = re.compile(r"来源|编辑|责编|审核|校对|监制|记者|通讯员|摄影|供稿|出品|公众号|微信号|关注|转发|阅读原文|点击|点赞|在看|分享|订阅|版权|转载|侵权|免责声明|投稿|往期|相关阅读|推荐阅读|热点推荐|广告|扫码|二维码|长按|视频|图片|图源|图片来源|附件|联系电话|网址|邮箱|制作|运营|本文|发布|播报|新闻|客户端|人民网|新华网|新华社|央视|总台|融媒体|电视台|人民日报|日报|晚报|周报")


class _AlnumLowerTranslation(dict):
    def __missing__(self, codepoint):
        char = chr(codepoint)
        value = char.lower() if char.isalnum() else None
        self[codepoint] = value
        return value

_ALNUM_LOWER = _AlnumLowerTranslation()

@lru_cache(maxsize=8192)
def compact(value: str) -> str:
    # Per-character lowercase semantics, including Greek sigma and U+0130.
    # Whole-string lower() would not be equivalent for every Unicode input.
    return value.translate(_ALNUM_LOWER)


def csv_write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        if rows:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)


def sentence_records(content: str) -> list[tuple[str, str]]:
    rows = []
    for part in SPLIT.split(content):
        normalized = compact(part)
        if normalized:
            rows.append((part.strip(), normalized))
    return rows


def containment_deduplicate(rows: list[dict]) -> tuple[list[dict], dict[str, str]]:
    """Merge only when every substantive sentence occurs in a longer article.

    Titles or a similarity score alone never establish duplication. Short
    speaker/analysis sentences are also protected; only obvious short footer
    lines can differ. Original records remain in the raw corpus and audit.
    """
    kept, duplicates, anchor_index, bodies = [], {}, {}, {}
    for row in sorted(rows, key=lambda r: (-len(r["content"]), r["id"])):
        parts = sentence_records(row["content"])
        fragments = [normalized for raw, normalized in parts
                     if (len(normalized) >= 18 or ROLE.search(raw) or STRONG_ANALYSIS.search(raw))
                     and not (len(normalized) < 55 and FOOTER.search(raw)
                              and not ROLE.search(raw) and not STRONG_ANALYSIS.search(raw))]
        anchors = [fragment[:24] for fragment in fragments if len(fragment) >= 24]
        choices = min((anchor_index.get(anchor, set()) for anchor in anchors), key=len, default=set())
        representative = next((candidate for candidate in sorted(choices)
                               if fragments and all(fragment in bodies[candidate] for fragment in fragments)), None)
        if representative:
            duplicates[row["id"]] = representative
            continue
        kept.append(row)
        body = compact(row["content"])
        bodies[row["id"]] = body
        # Index all sentence prefixes, including those that would count only
        # as footer in the shorter article, for an exact containment search.
        for _, normalized in parts:
            if len(normalized) >= 24:
                anchor_index.setdefault(normalized[:24], set()).add(row["id"])
    kept.sort(key=lambda r: int(r.get("excel_row", 0)))
    return kept, duplicates


def filter_records(records: list[dict], agenda: dict, deployment_pattern=None) -> tuple[list[dict], list[dict], dict]:
    started = time.perf_counter()
    parsed = {row["id"]: sentence_records(row["content"]) for row in records}
    df = Counter()
    for parts in parsed.values():
        df.update({normalized for _, normalized in parts if len(normalized) >= 18})
    # Repeated statements are removed ONLY when their wording identifies an
    # official deployment. Repeated expert or account analysis is preserved.
    deployment_pattern = deployment_pattern or DEPLOYMENT
    official_templates = sorted({normalized for parts in parsed.values() for raw, normalized in parts
                          if len(normalized) >= 18 and df[normalized] >= 8 and deployment_pattern.search(raw)},
                          key=lambda value: (-len(value), value))
    aliases = [list(dict.fromkeys([topic, re.sub(r"（.*?）", "", topic), *extra]))
               for topic, extra in zip(agenda["topics"], agenda["topic_aliases"])]
    audits, remaining = [], []
    representatives = {}
    for row in records:
        text = row["content"]
        all_text = row["title"] + "\n" + text
        topics = [topic for topic, words in zip(agenda["topics"], aliases) if any(w in all_text for w in words)]
        parts = parsed[row["id"]]
        residual = [(raw, normalized) for raw, normalized in parts if normalized not in official_templates]
        body_residual = [(raw, normalized) for raw, normalized in residual
                         if len(normalized) >= 18 and not (len(normalized) < 55 and FOOTER.search(raw))]
        normalized_text = compact(text)
        # Replace only repetitive official sentences. Preserve positions, and
        # scan the entire body for ALL agenda contexts (never just a lead).
        masked = normalized_text
        for template in official_templates:
            if template in masked:
                masked = masked.replace(template, " " * len(template))
        for sentence in re.split(r"[。！？!?；;]+", text):
            normalized = compact(sentence)
            if normalized and OFFICIAL_SENTENCE.search(sentence) and not ROLE.search(sentence) and not INDEPENDENT_EXTENSION.search(sentence):
                masked = masked.replace(normalized, " " * len(normalized))
        contexts = []
        for words in aliases:
            for word in words:
                term = compact(word)
                start = 0
                while term and (at := normalized_text.find(term, start)) >= 0:
                    contexts.append(masked[max(0, at - 150):at + len(term) + 280])
                    start = at + len(term)
        residual_text = "\n".join(contexts)
        role_hits = ROLE.findall(residual_text)
        view_hits = ANALYSIS.findall(residual_text)
        strong_hits = STRONG_ANALYSIS.findall(residual_text) + CAUSAL_ANALYSIS.findall(residual_text)
        global_role_protection = bool(ROLE.search(masked) or ATTRIBUTED_ANALYSIS.search(masked))
        commentary_protection = bool(re.search(r"点评[：:]|解读[：:]", text) and POLICY_DIAGNOSIS.search(residual_text))
        template_chars = sum(len(normalized) for _, normalized in parts if normalized in official_templates)
        body_chars = sum(len(normalized) for _, normalized in parts)
        text_key = hashlib.sha256(compact(text).encode()).hexdigest()
        reason, duplicate_of = "", ""
        if not text.strip():
            reason = "empty_body"
        elif row.get("published_at") and not (agenda["window_start"] <= row["published_at"] <= agenda["window_end"]):
            reason = "monitored_time_outside_window"
        elif text_key in representatives:
            reason, duplicate_of = "duplicate_normalized_full_text", representatives[text_key]
        elif not topics and not (global_role_protection and STRONG_ANALYSIS.search(masked)):
            reason = "no_agenda_term"
        elif template_chars >= 100 and not role_hits and not view_hits and not global_role_protection:
            reason = "official_copy_without_analysis_signal"
        elif not role_hits and not view_hits and not global_role_protection:
            reason = "agenda_context_without_analysis_signal"
        elif not role_hits and not strong_hits and not global_role_protection:
            reason = "agenda_context_only_generic_policy_words"
        elif (TRADE_TITLE.search(row["title"]) or len(set(TRADE.findall(text))) >= 3) and len(TRADE.findall(text)) >= 5 and not role_hits and not global_role_protection and not commentary_protection:
            reason = "trading_article_without_attributed_topic_analysis"
        elif body_chars < 100 and not role_hits and not view_hits:
            reason = "very_short_without_analysis_signal"
        if not reason:
            representatives[text_key] = row["id"]
            remaining.append(row)
        audits.append({"id": row["id"], "title": row["title"], "account": row.get("account", ""),
                       "decision": "exclude" if reason else "full_text_ai_review",
                       "reason": reason, "duplicate_of": duplicate_of,
                       "topics": "|".join(topics), "body_chars": body_chars,
                       "official_template_chars": template_chars,
                       "residual_chars": sum(len(n) for _, n in body_residual),
                       "role_signal_count": len(role_hits), "analysis_signal_count": len(view_hits),
                       "strong_analysis_count": len(strong_hits),
                       "global_attribution_protection": global_role_protection,
                       "commentary_protection": commentary_protection,
                       "strong_signal_evidence": " | ".join(dict.fromkeys(residual_text[max(0,m.start()-45):m.end()+65].strip()
                                                                         for m in STRONG_ANALYSIS.finditer(residual_text)))[:650],
                       "residual_preview": residual_text[:320], "url": row.get("url", "")})
    remaining, contained = containment_deduplicate(remaining)
    for audit in audits:
        if audit["id"] in contained:
            audit.update(decision="exclude", reason="substantive_sentences_contained_in_representative",
                         duplicate_of=contained[audit["id"]])
        elif audit["duplicate_of"] in contained:
            audit["duplicate_of"] = contained[audit["duplicate_of"]]
    summary = {"policy": POLICY_VERSION, "input_rows": len(records), "remaining_articles": len(remaining),
               "excluded_by_reason": dict(Counter(row["reason"] for row in audits if row["reason"])),
               "remaining_full_text_characters": sum(len(row["content"]) for row in remaining),
               "script_seconds": round(time.perf_counter()-started, 3)}
    return remaining, audits, summary


def evaluate(audits: list[dict], remaining: list[dict], labels_path: Path) -> dict:
    with labels_path.open(encoding="utf-8-sig", newline="") as stream:
        labels = list(csv.DictReader(stream))
    if labels and "review_decision" in labels[0]:
        labels = [row for row in labels if row["review_decision"] == "passed"]
    kept = {row["id"] for row in remaining}
    decisions = {row["id"]: row for row in audits}
    represented = []
    for label in labels:
        excerpt = re.sub(r"\s+", "", label["excerpt"])
        found = next((row["id"] for row in remaining if excerpt and excerpt in re.sub(r"\s+", "", row["content"])), None)
        represented.append((label, found))
    return {"historical_label_count": len(labels), "same_record_retained": sum(row["id"] in kept for row in labels),
            "excerpt_represented": sum(bool(found) for _, found in represented),
            "missing": [{"id": row["id"], "topic": row["topic"], "reason": decisions[row["id"]]["reason"]}
                        for row, found in represented if not found],
            "note": "Historical model nominations are diagnostics, not verified ground truth."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--agenda", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--labels", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    records = json.loads(args.records.read_text(encoding="utf-8"))
    agenda = json.loads(args.agenda.read_text(encoding="utf-8"))
    remaining, audits, summary = filter_records(records, agenda)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "remaining_records.json").write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
    csv_write(args.out / "filter_audit.csv", audits)
    summary["historical_diagnostics"] = {str(path): evaluate(audits, remaining, path) for path in args.labels}
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
