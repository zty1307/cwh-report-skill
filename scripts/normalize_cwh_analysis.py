#!/usr/bin/env python3
"""Mechanically assemble formal viewpoint prose from reviewed atomic evidence.

The model is responsible for evidence selection and faithful ``formal_claim``
values.  This module owns the repetitive report wording so different model
families cannot silently change attribution style, ordering, or punctuation.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from cwh_pipeline_runtime import atomic_write_json
from cwh_available_delivery import available_delivery, valid_gap
from cwh_writing_rules import judgment_heading as canonical_judgment_heading
from cwh_writing_rules import attribution_verb, formal_attribution, source_rank, writing_rules, writing_rules_sha256
from cwh_writing_rules import normalize_display_quotation_marks


STANCE_RE = re.compile("^(?:" + "|".join(re.escape(value) for value in writing_rules()["viewpoint"]["attribution_verbs"]) + ")")


def clean_sentence(value: Any) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    return text.rstrip("。；;，,")


def terminated_sentence(value: str) -> str:
    """Add display punctuation only; never append another stop after a full quote."""
    text = str(value or '').strip()
    if not text:
        return ''
    if re.search(r'[。！？!?][”’"\u300d\u300f]*$', text):
        return text
    return text + '。'


def judgment_heading(value: Any) -> str:
    """Use a neutral reported-judgment frame, never invent approval or criticism."""
    return canonical_judgment_heading(value)


def evidence_sentence(row: dict[str, Any]) -> str:
    claim = normalize_display_quotation_marks(clean_sentence(row.get("formal_claim")))
    if not claim:
        return ""
    subject = clean_sentence(formal_attribution(row))
    if not subject or claim.startswith(subject):
        return claim
    # Preserve a literal source sentence whose explicit attribution follows
    # the ordinary reporting connector. Do not prepend that same name again.
    connected = re.sub(r'^对此[，,]', '', claim, count=1)
    if connected != claim and connected.startswith(subject) and STANCE_RE.match(connected[len(subject):]):
        return claim
    # A literal quotation may already close with its exact declared speaker.
    # Keep that postposed attribution verbatim; do not prepend the same name
    # a second time or strip any frozen claim/source text.
    tail = re.search(r'[”’"」』]' + re.escape(subject) + r'(?:' +
                     '|'.join(re.escape(v) for v in writing_rules()['viewpoint']['attribution_verbs']) + r')(?=$|[，,。；;：:])', claim)
    if tail:
        return claim
    name = clean_sentence(row.get("speaker_name"))
    # Expand an existing exact name-only attribution; preserve the atomic claim
    # and its attribution verb, rather than introducing a second attribution.
    if name and subject.endswith(name) and claim.startswith(name) and STANCE_RE.match(claim[len(name):]):
        return subject + claim[len(name):]
    # A reviewed claim can already introduce the same speaker using one of
    # their explicitly supplied roles. Keep that literal claim: expanding it
    # to another role spelling would break the frozen claim-to-prose mapping.
    # Do not infer a role from arbitrary prose or suppress another speaker.
    if row.get("attribution_status") == "named_person" and name and subject.endswith(name):
        role = clean_sentence(row.get("speaker_role"))
        roles = [role, *re.split(r"[、，,；;]", role)] if role else []
        for supplied_role in roles:
            prefix = supplied_role + name
            if supplied_role and claim.startswith(prefix) and STANCE_RE.match(claim[len(prefix):]):
                return claim
    if STANCE_RE.match(claim):
        return f"{subject}{claim}"
    verb = attribution_verb(row)
    return f"{subject}{verb}，{claim}"


def assemble_cluster_details(cluster: dict[str, Any]) -> str:
    parts: list[str] = []
    seen: set[str] = set()
    for row in cluster.get("evidence") or []:
        if not isinstance(row, dict):
            continue
        sentence = evidence_sentence(row)
        signature = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", sentence).lower()
        if not sentence or not signature or signature in seen:
            continue
        seen.add(signature)
        parts.append(terminated_sentence(sentence))
    return "".join(parts)


def normalize_analysis(data: dict[str, Any]) -> dict[str, Any]:
    for topic in ((data.get("viewpoints") or {}).get("by_topic") or []):
        if not isinstance(topic, dict):
            continue
        if available_delivery(data) and valid_gap(topic):
            topic['heading'] = topic['topic']
            continue
        topic["heading"] = judgment_heading(topic.get("heading"))
        for cluster in topic.get("clusters") or []:
            if not isinstance(cluster, dict):
                continue
            cluster["summary"] = judgment_heading(cluster.get("summary"))
            for row in cluster.get('evidence') or []:
                if row.get('attribution_status') != 'self_media' or 'author_formal_claim' in row:
                    continue
                name = clean_sentence(row.get('speaker_name'))
                original = str(row.get('formal_claim') or '')
                verbs = ['解读称', *writing_rules()['viewpoint']['attribution_verbs']]
                labels = sorted({name, formal_attribution(row)}, key=len, reverse=True)
                prefix = '|'.join(re.escape(label) for label in labels if label)
                match = re.match('(?:' + prefix + ')(?:(' + '|'.join(map(re.escape, verbs)) + r')[，,:：\s]*|[：:]\s*)', original) if prefix else None
                if match and original[match.end():].strip():
                    # Strip only an exact redundant account attribution before
                    # freezing/review; original text and author wording remain.
                    row['author_formal_claim'] = original
                    row['formal_claim'] = original[match.end():].strip()
                    row['attribution_verb'] = '称' if match[1] in (None, '解读称') else match[1]
            # Python's stable sort preserves source order within the same
            # priority class. Only explicit source metadata changes priority.
            cluster["evidence"] = sorted(cluster.get("evidence") or [], key=lambda row: source_rank(row) if isinstance(row, dict) else 999)
            details = assemble_cluster_details(cluster)
            cluster["details"] = details
            cluster.pop("analysis", None)
    metadata = data.setdefault("metadata", {})
    metadata["writing_contract_version"] = "formal-writing-rules.v1"
    metadata["writing_assembly"] = "deterministic_from_atomic_claims"
    metadata["writing_rules_sha256"] = writing_rules_sha256()
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize CWH analysis prose deterministically.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="", help="Defaults to in-place update of --input.")
    args = parser.parse_args()
    source = Path(args.input).resolve()
    target = Path(args.output).resolve() if args.output else source
    data = json.loads(source.read_text(encoding="utf-8"))
    atomic_write_json(target, normalize_analysis(data))
    print(json.dumps({"status": "ok", "output": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
