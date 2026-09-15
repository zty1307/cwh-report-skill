"""Build clearly labelled review files without changing formal pipeline gates.

Only registered, hash-matching workbook facts and independently verified
viewpoints enter readable prose. Unaccepted drafts stay in source artifacts.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import shutil
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.oxml.ns import qn
from cwh_pipeline_runtime import atomic_write_json, sha256_file, utc_now
from ingest_monitoring_workbook import ingest_workbook
from generate_dashboard import generate_dashboard


def accepted_path(job: Path, state: dict, stage: str, artifact: str) -> Path | None:
    row = next((x for x in state.get("stages", []) if x.get("stage_id") == stage), {})
    raw = (row.get("artifacts") or {}).get(artifact)
    digest = (row.get("artifact_hashes") or {}).get(artifact)
    if row.get("status") != "succeeded" or not raw or not digest:
        return None
    path = Path(raw)
    path = path if path.is_absolute() else job / path
    return path if path.is_file() and sha256_file(path) == digest else None


def build_review_delivery(job: Path) -> dict:
    job = job.resolve()
    state = json.loads((job / "pipeline_state.json").read_text(encoding="utf-8"))
    out = job / "review_delivery"
    out.mkdir(exist_ok=True)
    blocked = [f"{row.get('label') or row['stage_id']}：{row.get('message') or row.get('status')}"
               for row in state.get("stages", []) if row.get("status") != "succeeded"]
    workbook = accepted_path(job, state, "workbook", "workbook")
    system = ingest_workbook(workbook) if workbook else {}
    verified = accepted_path(job, state, "domestic_evidence_verification", "analysis_bundle_verified")
    bundle = json.loads(verified.read_text(encoding="utf-8")) if verified else {}
    # Deliver source artifacts too, but never silently promote them to prose.
    registered = {str(path.resolve()): row.get('stage_id')
                  for row in state.get('stages', [])
                  for key in (row.get('artifacts') or {})
                  if (path := accepted_path(job, state, row['stage_id'], key))}
    source_paths = list((job / 'artifacts').glob('*'))
    source_paths += list((job / 'worker/domestic_viewpoints').glob('author-topic-*.cache.json'))
    source_artifacts = [{"path": str(path.resolve()), "name": path.name,
                         "sha256": sha256_file(path),
                         "accepted_stage": registered.get(str(path.resolve())),
                         "status": "stage_hash_verified" if str(path.resolve()) in registered else "unaccepted_source_not_report_conclusion"}
                        for path in sorted(set(source_paths)) if path.is_file()
                        and path.suffix.lower() in {'.json', '.md', '.png', '.xlsx', '.docx'}]
    topic_rows = []
    for row in system.get("subevents", []):
        totals = row.get("totals") or {}
        topic_rows.append({"topic": row["title"], "display": row["title"],
                           "spread_count": row.get("total_spread", totals.get("total_spread")),
                           "domestic_media": totals.get("domestic_mainstream"),
                           "overseas_media": totals.get("overseas_media"),
                           "self_media": sum(totals.get(key) or 0 for key in ("wechat_public", "weibo", "video_account", "new_media")),
                           "sentiment_sample_status": "pending", "sentiment_denominator": 0})
    title = f"{state.get('input_contract', {}).get('agenda') or '国务院常务会'}舆情情况 待审核稿"
    notice = "待审核稿，未通过正式交付门禁。仅展示已登记且校验一致的数据和已独立复核的观点；缺失章节不代表没有相关舆情。"
    paragraphs = [("Title", title), ("Normal", notice), ("Heading 1", "一、传播概况")]
    totals = system.get("overall", {}).get("totals", {})
    period = system.get("monitoring_period", {})
    if "total_spread" in totals:
        paragraphs.append(("Normal", f"监测时间为{period.get('start', '未注明')}至{period.get('end', '未注明')}，系统记录相关信息{totals['total_spread']}条。各子议题允许重复命中，不相加作为总事件传播量。"))
        for row in topic_rows:
            paragraphs.append(("Normal", f"{row['topic']}：系统记录{row['spread_count']}条。"))
    else:
        paragraphs.append(("Normal", "标准总表尚未通过校验，暂不展示传播量。"))
    paragraphs.append(("Heading 1", "二、境内观点"))
    for topic in (bundle.get("viewpoints") or {}).get("by_topic", []):
        paragraphs.append(("Heading 2", topic["topic"]))
        for cluster in topic.get("clusters", []):
            paragraphs.append(("Normal", str(cluster.get("details") or "")))
            for evidence in cluster.get("evidence", []):
                paragraphs.append(("Normal", f"来源：{evidence.get('speaker_name') or evidence.get('source', '')} {evidence.get('url', '')}"))
    if not bundle:
        paragraphs.append(("Normal", "境内观点尚未完成独立原文复核，不将未经确认的模型草稿作为报告结论。"))
    paragraphs.extend([("Heading 1", "三、评论与境外舆情"),
                       ("Normal", "当前为未完成交付，评论情感和境外解读尚未纳入本待审核稿。已采集原始材料保留在任务目录，不能把缺失视为零结果。"),
                       ("Heading 1", "四、待完成事项")])
    paragraphs.extend(("Normal", item) for item in blocked)
    if source_artifacts:
        paragraphs.append(("Heading 1", "附：现有过程产物"))
        paragraphs.append(("Normal", "以下文件一并保留。阶段校验一致不等于全部内容复核通过；未验收模型草稿仅供查看，不能作为报告结论。"))
        paragraphs.extend(("Normal", f"{item['name']}（{'阶段文件校验一致' if item['accepted_stage'] else '未验收过程材料'}）：{item['path']}")
                          for item in source_artifacts)
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(2.3)
    for name in ("Normal", "Title", "Heading 1", "Heading 2"):
        style = doc.styles[name]
        style.font.name = "宋体"
        style.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), "宋体")
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.size = Pt(12 if name == "Normal" else 16 if name == "Title" else 14)
    for style, value in paragraphs:
        doc.add_paragraph(value, style)
    word = out / "cwh_review_draft.docx"
    doc.save(word)
    markdown = out / "cwh_review_draft.md"
    markdown.write_text("\n\n".join(("# " if style == "Title" else "## " if style.startswith("Heading") else "") + text for style, text in paragraphs), encoding="utf-8")
    data = {"delivery_class": "review_draft", "generated_at": utc_now(),
            "meeting": {"agenda": title, "topics": [x["topic"] for x in topic_rows]},
            "system_data": system, "topic_stats": topic_rows,
            "analysis_bundle": copy.deepcopy(bundle), "viewpoints": copy.deepcopy(bundle.get("viewpoints") or {}),
            "audit": {"acceptance": {"ready_for_formal_delivery": False, "blockers": blocked or [notice]}},
            "artifacts": {"formal_docx": str(word), "formal_report": str(markdown),
                          "report_data": str(out / "report_data.json"), "audit": str(out / "cwh_audit.json")}}
    if workbook:
        copied = out / "cwh_monitoring_workbook.xlsx"
        shutil.copy2(workbook, copied)
        data["artifacts"]["data_workbook"] = str(copied)
    dashboard = generate_dashboard(data, out / "cwh_review_dashboard.html")
    data["artifacts"]["dashboard"] = str(dashboard)
    atomic_write_json(out / "report_data.json", data)
    atomic_write_json(out / "cwh_audit.json", data["audit"])
    manifest = {"delivery_class": "review_draft", "ready_for_formal_delivery": False,
                "pipeline_status": state.get("status"), "pending": blocked,
                "available_source_artifacts": source_artifacts,
                "artifacts": {Path(value).name: sha256_file(Path(value)) for value in data["artifacts"].values() if Path(value).is_file()}}
    atomic_write_json(out / "manifest.json", manifest)
    return {"status": "review_draft", "manifest": str(out / "manifest.json"), "word": str(word), "dashboard": str(dashboard)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(build_review_delivery(Path(args.job_dir)), ensure_ascii=False))
