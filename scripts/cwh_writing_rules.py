"""Executable, meeting-independent writing frames shared by report consumers."""
from __future__ import annotations

import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

RULES_PATH = Path(__file__).resolve().parent.parent / "config/formal_writing_rules.v1.json"
EDITORIAL_PATH = RULES_PATH.with_name('editorial_template.v1.json')


@lru_cache(maxsize=1)
def editorial_profile() -> dict[str, Any]:
    return json.loads(EDITORIAL_PATH.read_text(encoding='utf-8'))


@lru_cache(maxsize=1)
def writing_rules() -> dict[str, Any]:
    rules = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    profile = editorial_profile()
    for section in ('document', 'propagation', 'viewpoint', 'comments', 'hotwords', 'overseas'):
        rules[section].update(profile.get(section, {}))
    return rules


@lru_cache(maxsize=1)
def writing_rules_sha256() -> str:
    return hashlib.sha256(RULES_PATH.read_bytes() + b'\n' + EDITORIAL_PATH.read_bytes()).hexdigest()


def editorial_eligibility_prompt() -> str:
    """The same evidence-based selection criteria for author and reviewer."""
    rules = writing_rules()['viewpoint']
    exclusions = '；'.join(row['description'] for row in rules['editorial_exclusions'])
    return ('正式选材资格与文字忠实度分开检查：原文确实这样说，并不自动表示适合本题正文。'
        '以下只按原文语义判断，不按关键词、渠道名称或专家身份自动通过/排除：' + exclusions + '。'
        '实质的产业、金融或投资分析，只要有直接相关的具体政策机制、条件或论据即可保留；'
        '不能因出现产业链、投资、受益等词就删除，也不要求每条必须由具名专家提出。'
        + rules.get('public_reasoning_boundary_rule', '') + rules['source_reasoning_quality_rule'] +
        '对预测强弱不能只看原作者用了很确定的词；须核对这条分析实际提供的机制、条件或论据。'
        '如果实际仅为受益推介或口号，不把事实铺垫当成充分论证，更不能由审核者补足。'
        + rules.get('approved_structure_rule', ''))


def editorial_template_prompt(stage: str, rules=None) -> str:
    """Small stage-specific frames, not a fixed agenda or a second drafting pass."""
    rules = rules or writing_rules()['viewpoint']
    if stage == 'selection':
        return (rules['selection_budget_rule'] + '\n' + rules['paragraph_pairing_rule']
                + '\n以下用户最新成稿规范优先于上文一般数量建议：' + rules.get('approved_structure_rule', '')
                + '\n' + rules.get('approved_heading_rule', '')
                + '\n' + rules.get('attribution_style_rule', '')
                + '\n' + rules.get('paragraph_layout_rule', ''))
    if stage not in {'claim', 'revision'}:
        raise ValueError('Unknown editorial template stage: ' + stage)
    result = (rules.get('claim_length_policy', '') + '\n' + rules['claim_unit_rule'] + '\n' + rules.get('attribution_style_rule', '') + '\n以下是可选句式，不是必填栏目；原文已完整清楚时优先直接摘用，不为套句式改写。只选当前原文适用的一种，'
              '没有依据的槽位整项省略，不拼凑结论，不改写真实评论引文。\n'
              + '\n'.join(rules['composition_frames']))
    if stage == 'claim':
        example = rules['composition_example']
        result += ('\n' + example['source'] + '\n不要写：' + example['avoid']
                   + '\n应分别提取：' + ' / '.join(example['claims']) + '\n' + example['lesson'])
    return result


def selection_audit_prompt() -> str:
    """Quantity exceptions describe editorial coverage, not corroboration tests."""
    return ('数量说明不是可信度审核：thin_reason记录该组实际主体数及独立成组的编辑理由；'
        'shortfall_reason在少于4个主体时只记录实际覆盖与取舍，不表示必须补足4人；'
        'single_cluster_reason说明只有一个实质判断的实际情况。'
        '一位主体的扎实判断可以作为全题仅有一组时的单段直述；多组分点每组至少两个来源，不足组保留备选，不能取消编号继续分段；'
        '不能仅因主体少、没有具名专家或没有第二来源，就写“缺乏佐证”“无法核验”或排除观点。'
        '这是归因明确的舆论综述，不是认证受访者观点为客观事实；原文是否支持引述仍须独立审核。'
        '本步未提供原文时，不得推断原文缺依据、测算或实施机制。')


def chinese_number(value: int) -> str:
    if value <= 0:
        raise ValueError("Report numbering starts at one")
    digits = "零一二三四五六七八九"
    if value < 10:
        return digits[value]
    if value < 100:
        tens, units = divmod(value, 10)
        return (digits[tens] if tens > 1 else "") + "十" + (digits[units] if units else "")
    return str(value)


def domestic_media_label(data: dict[str, Any]) -> str:
    """Keep a known input channel scope; legacy inputs retain their explicit frame."""
    label = str((((data.get("statistics") or {}).get("source_bucket_labels") or {})
                 .get("domestic_media")) or "").strip()
    if label in {"境内新闻", "国内新闻", "境内媒体", "境内主流媒体"}:
        return label
    return "境内媒体" if label else "境内主流媒体"


def ordinal_prefix(value: int) -> str:
    prefixes = writing_rules()["viewpoint"]["cluster_ordinal_prefixes"]
    if value <= 0:
        raise ValueError("Report numbering starts at one")
    return prefixes[value - 1] if value <= len(prefixes) else f"{chinese_number(value)}是"


def judgment_heading(value: Any) -> str:
    """One shared display frame; preserve explicit stance and source meaning."""
    heading = str(value or '').strip().rstrip('。；;')
    rules = writing_rules()['viewpoint']
    stances = tuple(rules['heading_stance_verbs'])
    reports = '|'.join(map(re.escape, [*stances, '指出', '表示', '称']))
    actor = r'(?:舆论|媒体|专家|机构)(?:普遍)?'
    heading = re.sub('^' + re.escape(rules['default_attribution_verb']) + '(?=' + actor + '(?:' + reports + '))', '', heading)
    heading = re.sub('^' + actor + '(?=(?:' + reports + '))', '', heading)
    if not heading.startswith(stances):
        heading = re.sub(r'^(?:指出|表示|称)', '', heading)
    if not heading or heading.startswith(stances) or any(marker in heading for marker in ('尚未形成评论性观点', '以事实性报道为主')):
        return heading
    return rules['default_attribution_verb'] + heading


def opening_paragraph(meeting: dict[str, Any], date_label: str, agenda_topics: str) -> str:
    rules = writing_rules()["document"]
    # A complete current communique agenda can replace abbreviated topic labels.
    if meeting.get('agenda_text') and meeting.get('agenda_source'):
        agenda_topics = str(meeting['agenda_text']).strip().rstrip('。')
    # Verified period metadata outranks the user's configurable editorial default.
    chair_name = str(meeting.get("chair_name") or "").strip()
    chair_source = str(meeting.get("chair_source") or "").strip()
    governing_verbs = ("听取", "研究", "审议", "进一步", "对", "部署", "决定", "学习贯彻", "学习")
    chair_title = str(meeting.get('chair_title') or '').strip()
    if chair_title and chair_name and not chair_name.startswith(chair_title):
        chair_name = chair_title + chair_name
    if not (chair_name and chair_source):
        chair_name = str(rules.get('approved_chair_default') or '').strip()
    if chair_name:
        if not agenda_topics:
            template = rules["opening_with_chair_no_agenda"]
        elif agenda_topics.startswith(governing_verbs):
            template = rules["opening_with_chair"]
        else:
            template = rules["opening_with_chair_topic_list"]
    else:
        if not agenda_topics:
            template = rules["opening_without_chair_no_agenda"]
        elif agenda_topics.startswith(governing_verbs):
            template = rules["opening_without_chair"]
        else:
            template = rules["opening_without_chair_topic_list"]
    return template.format(date=date_label, agenda=agenda_topics, chair_name=chair_name)


def normalize_display_quotation_marks(text: str) -> str:
    """Repair determinate printing defects without changing any words.

    Only the explicit 从“term”转向“term” shape and a lone terminal opening
    mark are eligible. Ambiguous speech/nested quotation is left untouched.
    This helper is for media-claim display, never original source or comments.
    """
    original = str(text)
    quote = r'[“”"]'
    term = r'([^“”"，。；;！？\n]{1,40})'
    value = re.sub('从' + quote + term + quote + '转向' + quote + term + quote,
                   lambda m: '从“' + m.group(1) + '”转向“' + m.group(2) + '”', original)
    terminal = re.search(r'“(?=[。；;.!?\s]*$)', value)
    if terminal:
        prefix = value[:terminal.start()]
        depth, balanced = 0, True
        for char in prefix:
            if char == '“':
                depth += 1
            elif char == '”':
                depth -= 1
                if depth < 0:
                    balanced = False
        if balanced and depth == 0 and '“' in prefix and '"' not in prefix:
            value = value[:terminal.start()] + value[terminal.end():]
    assert re.sub(r'[“”"]', '', value) == re.sub(r'[“”"]', '', original)
    return value


def formal_attribution(row: dict[str, Any]) -> str:
    """Return a stable formal display label without changing evidence identity."""
    status = str(row.get("attribution_status") or "").strip().lower()
    subject = str(
        row.get("attribution")
        or row.get("speaker_name")
        or row.get("source")
        or row.get("platform")
        or ""
    ).strip()
    role = str(row.get('speaker_role') or '').strip()
    speaker = str(row.get('speaker_name') or '').strip()
    if role and speaker.startswith(role) and subject == role + speaker:
        # Exact duplicated prefix only; the frozen identity fields remain intact.
        subject = speaker
    if (status == 'named_person' and role and speaker and subject == role + speaker
            and not role.endswith('的') and re.search(r'从事|工作|经历|经验', role)
            and re.search(r'(?:\d+|[一二三四五六七八九十百多]+)年(?:经验|经历)?$', role)):
        # A literal experience clause is not a noun-form job title. Add only
        # the grammatical connector; keep every original qualification intact.
        subject = role + '的' + speaker
    if status != "self_media" or not subject:
        return subject
    if re.match(r"^(?:微信公众号|头条号|百家号|微博账号|自媒体账号)[“\"]", subject):
        return subject
    bare = str(row.get("speaker_name") or row.get("source") or row.get("attribution") or subject).strip()
    host = (urlsplit(str(row.get("url") or "")).hostname or "").lower()
    if host == "mp.weixin.qq.com" or host.endswith(".mp.weixin.qq.com"):
        platform = "微信公众号"
    elif host.endswith("toutiao.com"):
        platform = "头条号"
    elif host.endswith("baijiahao.baidu.com"):
        platform = "百家号"
    elif host.endswith("weibo.com") or host.endswith("weibo.cn"):
        platform = "微博账号"
    else:
        platform = "自媒体账号"
    return f"{platform}“{bare}”"


def attribution_verb(row: dict[str, Any]) -> str:
    rules = writing_rules()["viewpoint"]
    supplied = str(row.get("attribution_verb") or "").strip()
    if supplied in rules.get('neutral_attribution_display_inputs', []):
        return rules['neutral_attribution_display_verb']
    if supplied in rules["attribution_verbs"]:
        return supplied
    status = str(row.get("attribution_status") or "").strip().lower()
    return rules["default_attribution_verbs_by_status"].get(status, rules.get('neutral_attribution_display_verb', rules["default_attribution_verb"]))


def formal_claim_char_count(row: dict[str, Any]) -> int:
    """Count content, excluding only an exact known leading attribution.

    Supports pre-freeze author and compiled evidence fields. This does not edit
    the original claim or infer an unknown role/speaker from arbitrary prose.
    """
    text = re.sub(r'\s+', '', str(row.get('formal_claim') or row.get('claim') or ''))
    speaker = re.sub(r'\s+', '', str(row.get('speaker_name') or row.get('speaker') or ''))
    role = re.sub(r'\s+', '', str(row.get('speaker_role') or row.get('role') or ''))
    labels = {re.sub(r'\s+', '', str(row.get('attribution') or '')), speaker, role + speaker if speaker else ''}
    verbs = sorted(set(writing_rules()['viewpoint']['attribution_verbs']) | {'说'}, key=len, reverse=True)
    for label in sorted(labels - {''}, key=len, reverse=True):
        for verb in verbs:
            prefix = label + verb
            if text.startswith(prefix):
                return len(text[len(prefix):].lstrip('，,:：'))
    return len(text)


def source_rank(row: dict[str, Any]) -> int:
    rules = writing_rules()["viewpoint"]
    if row.get("attribution_status") == "named_person":
        category = "named_expert"
    else:
        category = rules["source_type_classes"].get(str(row.get("source_type") or ""), "other_traceable_source")
        if row.get("attribution_status") == "self_media":
            category = "public_account"
    return rules["source_order"].index(category)


def unsupported_padding_issues(evidence: dict[str, Any]) -> list[str]:
    claim = str(evidence.get("formal_claim") or "")
    excerpt = str(evidence.get("source_excerpt") or "")
    return [phrase for phrase in writing_rules()["viewpoint"]["prohibited_padding"] if phrase in claim and phrase not in excerpt]
