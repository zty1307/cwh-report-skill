from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

from docx import Document
from docx.shared import Inches
from PIL import Image


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import formalize_cwh_report as FORMALIZE  # noqa: E402
import cwh_orchestrator as ORCHESTRATOR  # noqa: E402
import run_foreign_mediaspider as FOREIGN_RUNNER  # noqa: E402

import generate_dashboard as DASHBOARD  # noqa: E402


class CwhOverseasFormalizationTests(unittest.TestCase):
    def test_docx_chart_picture_has_meaningful_alt_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            image_path = Path(temp) / "chart.png"
            Image.new("RGB", (20, 20), "white").save(image_path)
            document = Document()
            shape = FORMALIZE.add_centered_picture(
                document,
                str(image_path),
                width=Inches(1),
                alt_text="各子议题信息传播总量对比图",
            )
            self.assertEqual("各子议题信息传播总量对比图", shape._inline.docPr.get("descr"))
            self.assertEqual("各子议题信息传播总量对比图", shape._inline.docPr.get("title"))

    def test_ai_reviewed_hotword_rows_are_not_an_image_authority_by_themselves(self) -> None:
        self.assertTrue(FORMALIZE.reviewed_hotword_pipeline_ready({
            "hotwords": [
                {
                    "word": "住房公积金",
                    "authority": "reviewed_wordcloud_audit",
                    "selection_method": "ai_semantic_review",
                }
            ]
        }))

    def test_reviewed_hotword_audit_supplies_the_exact_wordcloud_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / "reviewed_wordcloud.png"
            image.write_bytes(b"reviewed-wordcloud")
            audit = root / "hotword_audit.json"
            audit.write_text(json.dumps({
                "status": "ai_review_complete",
                "review_method": "ai_semantic_review",
                "second_pass_completed": True,
                "image_path": str(image),
            }), encoding="utf-8")
            resolved = FORMALIZE.reviewed_hotword_image_path({
                "artifacts": {"hotword_audit": str(audit)}
            })
        self.assertEqual(resolved, image)

    def test_reviewed_rows_without_audited_image_cannot_upgrade_fallback_chart(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chart_dir = root / "charts"
            chart_dir.mkdir()
            from PIL import Image
            Image.new('RGB', (20, 20), 'white').save(chart_dir / "trend_distribution_system.png")
            Image.new('RGB', (20, 20), 'navy').save(chart_dir / "topic_distribution_system.png")
            data = {
                "statistics": {"by_platform": {}, "by_date": {}},
                "topic_stats": [],
                "hotwords": [{
                    "word": "住房公积金",
                    "count": 10,
                    "authority": "reviewed_wordcloud_audit",
                    "selection_method": "ai_semantic_review",
                }],
            }
            FORMALIZE.ensure_docx_chart_images(data, root)
        self.assertEqual(data["artifacts"]["chart_authority"], "mixed_system_and_program_fallback")

    def test_stale_wordcloud_path_does_not_mask_copied_pipeline_image(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            chart_dir = root / "charts"
            chart_dir.mkdir()
            from PIL import Image
            Image.new('RGB', (20, 20), 'white').save(chart_dir / "trend_distribution_system.png")
            Image.new('RGB', (20, 20), 'navy').save(chart_dir / "topic_distribution_system.png")
            pipeline = chart_dir / "hotword_distribution_pipeline.png"
            pipeline.write_bytes(b"reviewed-pipeline-wordcloud")
            data = {
                "statistics": {"by_platform": {}, "by_date": {}},
                "topic_stats": [],
                "hotwords": [{"word": "数字中国", "count": 100}],
                "artifacts": {"wordcloud_image": str(root / "missing-wordcloud.png")},
            }
            charts = FORMALIZE.ensure_docx_chart_images(data, root)
        self.assertEqual(charts["hotword_distribution"], str(pipeline))
        self.assertEqual(data["artifacts"]["wordcloud_image"], str(pipeline))
        self.assertEqual(data["artifacts"]["chart_authority"], "monitoring_system_assets_plus_pipeline_wordcloud")

    def test_unreviewed_hotword_rows_do_not_authorize_pipeline_wordcloud(self) -> None:
        self.assertFalse(FORMALIZE.reviewed_hotword_pipeline_ready({
            "hotwords": [{"word": "项目", "authority": "raw_frequency"}]
        }))

    def test_completed_zero_row_collection_is_not_a_crawler_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "run.log").write_text(
                "finished_at=2026-08-05T15:46:51\nexit_code=0\n",
                encoding="utf-8",
            )
            result = FOREIGN_RUNNER.classify_collection_completion(
                executed=True,
                supervisor_exit_code=4,
                run_dir=run_dir,
                stdout="Status: foreign collection finished without data rows.",
            )
        self.assertTrue(result["collection_completed"])
        self.assertEqual(result["collection_status"], "completed_no_rows")
        self.assertTrue(result["zero_result"])
        self.assertEqual(result["collector_exit_code"], 0)

    def test_foreign_audit_accepts_verified_zero_rows_but_not_generic_exit_four(self) -> None:
        self.assertTrue(ORCHESTRATOR.foreign_collection_audit_succeeded({
            "dry_run": False,
            "command_exit_code": 4,
            "collection_completed": True,
            "collection_status": "completed_no_rows",
        }))
        self.assertFalse(ORCHESTRATOR.foreign_collection_audit_succeeded({
            "dry_run": False,
            "command_exit_code": 4,
        }))

    def test_missing_review_flags_are_rejected_by_default(self) -> None:
        row = {
            "source": "境外媒体",
            "title": "会议相关报道",
            "title_cn": "会议相关报道",
            "url": "https://example.test/unreviewed",
        }
        self.assertFalse(FORMALIZE.overseas_report_is_formal_eligible(row))

    def test_system_reviewed_allowlist_prevents_raw_excluded_row_reentry(self) -> None:
        system_data = {"overseas_reports": [{
            "source": "境外媒体甲",
            "title": "本次会议部署",
            "url": "https://example.test/included",
            "topic_hits": [1],
            "ai_report_category": "事实性报道",
        }]}
        samples = [
            {
                "source": "境外媒体甲",
                "title": "本次会议部署",
                "url": "https://example.test/included",
                "region": "overseas",
                "content": "报道本次会议部署。",
            },
            {
                "source": "境外媒体乙",
                "title": "Kimi K3技术细节公开",
                "url": "https://example.test/excluded",
                "region": "overseas",
                "content": "与会议无关，但含有威胁和争议等词。",
            },
        ]
        result = ORCHESTRATOR.build_system_reviewed_overseas(system_data, samples)
        titles = [row["title"] for rows in result["groups"].values() for row in rows]
        self.assertEqual(titles, ["本次会议部署"])
        self.assertTrue(result["groups"]["事实性报道"][0]["formal_include"])

    def test_formal_summary_never_falls_back_to_scraped_full_body(self) -> None:
        row = {"content": "整篇抓取正文。您查看的内容可能不完整。更多内容访问。"}
        self.assertEqual(FORMALIZE.formal_overseas_summary(row), "")

    def test_dashboard_uses_same_reviewed_overseas_universe_as_formal_report(self) -> None:
        data = {"appendices": {"overseas_reports": [
            {
                "source": "境外媒体甲",
                "title": "本次会议部署",
                "url": "https://example.test/included",
                "formal_include": True,
                "meeting_relevance": True,
                "overseas_category": "事实性报道",
            },
            {
                "source": "境外媒体乙",
                "title": "相关领域年度报告",
                "url": "https://example.test/excluded",
                "formal_include": False,
                "meeting_relevance": False,
                "overseas_category": "解读性报道",
            },
        ]}}

        rows = DASHBOARD.dashboard_overseas_rows(data)

        self.assertEqual([row["url"] for row in rows], ["https://example.test/included"])

    def test_ai_relevance_gate_excludes_topically_related_non_meeting_article(self) -> None:
        data = {
            "overseas": {
                "groups": {
                    "事实性报道": [{
                        "source": "境外媒体",
                        "title": "涉灾网络谣言案件",
                        "title_cn": "涉灾网络谣言案件",
                        "summary_cn": "转述涉灾案件",
                        "meeting_relevance": False,
                        "formal_include": False,
                        "url": "https://example.test/unrelated",
                    }]
                }
            }
        }
        self.assertEqual(FORMALIZE.appendix_overseas_rows(data), [])

    def test_reviewed_factual_label_is_not_overridden_by_risk_words(self) -> None:
        row = {
            "ai_report_category": "事实性报道",
            "summary_cn": "报道转述风险治理与争议处置情况。",
        }
        self.assertEqual(FORMALIZE.overseas_report_category(row), "事实性报道")

    def test_foreign_title_uses_reviewed_chinese_translation(self) -> None:
        row = {
            "title": "Chinese Premier Chairs State Council Executive Meeting",
            "title_cn": "李强主持召开国务院常务会议",
        }
        self.assertEqual(FORMALIZE.formal_overseas_title(row), "李强主持召开国务院常务会议")

    def test_formal_comment_paragraphs_hide_account_ids_and_use_chinese_quotes(self) -> None:
        data = {
            "overseas": {
                "public_comments": [{
                    "source": "@example_user",
                    "platform": "x",
                    "translation_cn": "为自然灾害做好准备，是拯救生命的关键基础。",
                    "url": "https://x.com/example_user/status/1",
                    "in_monitoring_window": False,
                    "ai_formal_include": True,
                    "ai_semantic_quality": "substantive",
                    "ai_formal_reason": "表达防灾准备与生命安全关切",
                }]
            }
        }
        paragraphs = FORMALIZE.overseas_comment_paragraphs(data)
        joined = "\n".join(paragraphs)
        self.assertIn("一是应急救灾与人员安全", joined)
        self.assertIn("X平台网友称", joined)
        self.assertIn("拯救生命", joined)
        self.assertNotIn("@example_user", joined)
        self.assertNotIn("监测期后", joined)

    def test_single_factual_category_has_no_lone_numbering(self) -> None:
        data = {"appendices": {"overseas_reports": [{
            "source": "联合早报",
            "title_cn": "国务院常务会议部署防汛救灾",
            "url": "https://example.test/factual",
            "overseas_category": "事实性报道",
            "formal_include": True,
            "meeting_relevance": True,
        }]}}
        text = "".join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertIn("境外媒体以事实性报道为主", text)
        self.assertIn("暂未发现可引用的评论性文章", text)
        self.assertIn("数据周期内", text)
        self.assertNotIn("一是", text)

    def test_interpretation_follows_factual_lead_without_category_numbering(self) -> None:
        data = {"appendices": {"overseas_reports": [
            {"source": "媒体甲", "title_cn": "会议部署", "url": "https://example.test/a", "overseas_category": "事实性报道", "formal_include": True, "meeting_relevance": True},
            {"source": "媒体乙", "title_cn": "政策解读", "summary_cn": "分析政策影响", "url": "https://example.test/b", "overseas_category": "解读性报道", "formal_include": True, "meeting_relevance": True},
        ]}}
        paragraphs = FORMALIZE.overseas_media_body_paragraphs(data)
        text = "".join(paragraphs)
        self.assertEqual(2, len(paragraphs))
        self.assertIn("相关解读如下", paragraphs[0])
        self.assertNotIn("以事实性报道为主", paragraphs[0])
        self.assertNotIn("围绕会议议题的政策影响展开解读", paragraphs[1])
        self.assertTrue(paragraphs[1].startswith('媒体乙文章《政策解读》称，'))
        self.assertNotIn("一是事实性报道", text)
        self.assertNotIn("二是解读性报道", text)

    def test_redundant_report_attribution_is_removed_but_real_source_chain_is_kept(self) -> None:
        import copy
        data = {'appendices': {'overseas_reports': [{
            'source': '媒体乙', 'title_cn': '政策解读', 'url': 'https://example.test/interpretive',
            'summary_cn': '报道认为，政策有望改善公共服务覆盖。',
            'overseas_category': '解读性报道', 'formal_include': True, 'meeting_relevance': True}]}}
        frozen = copy.deepcopy(data)
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertNotIn('称，报道认为', text)
        self.assertIn('称，政策有望改善公共服务覆盖', text)
        self.assertEqual(frozen, data)
        data['appendices']['overseas_reports'][0]['summary_cn'] = '报道引述研究机构认为，政策效果仍取决于资金安排。'
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertIn('引述研究机构认为', text)

    def test_generic_analysis_intro_is_removed_without_rewriting_frozen_summary(self) -> None:
        import copy
        data = {'appendices': {'overseas_reports': [{
            'source': '媒体乙', 'title_cn': '政策解读', 'url': 'https://example.test/interpretive',
            'summary_cn': '原分析认为，政策效果可能取决于资金安排。',
            'overseas_category': '解读性报道', 'formal_include': True, 'meeting_relevance': True}]}}
        frozen = copy.deepcopy(data)
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertIn('围绕会议议题的政策影响展开解读', text)
        self.assertIn('称，政策效果可能取决于资金安排', text)
        self.assertNotIn('原分析认为', text)
        self.assertEqual(frozen, data)
        data['appendices']['overseas_reports'][0]['summary_cn'] = '分析师认为，政策效果可能取决于资金安排。'
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertIn('称，分析师认为', text)

    def test_missing_workbook_category_never_silently_defaults_to_factual(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能静默默认为事实性报道"):
            ORCHESTRATOR.build_system_reviewed_overseas(
                {"overseas_reports": [{
                    "source": "境外媒体甲",
                    "title": "本次会议部署",
                    "url": "https://example.test/missing-category",
                    "topic_hits": [1],
                }]},
                [],
            )

    def test_foreign_source_adds_reviewed_chinese_name(self) -> None:
        self.assertEqual(
            FORMALIZE.formal_overseas_source({"source": "Wedoany English"}),
            "Wedoany英文网",
        )

    def test_region_only_source_is_marked_not_guessed_and_counts_are_unchanged(self) -> None:
        import copy
        self.assertEqual(FORMALIZE.formal_overseas_source({'source': '香港'}), '香港（媒体名称待核）')
        self.assertEqual(FORMALIZE.formal_overseas_source({'source': '香港商业电台'}), '香港商业电台')
        self.assertEqual(FORMALIZE.formal_overseas_source({'source': '香港', 'source_cn_simplified': '媒体甲'}), '媒体甲')
        rows = [{
            'source': source, 'title_cn': f'会议报道{source}', 'url': f'https://example.test/{i}',
            'overseas_category': '事实性报道', 'formal_include': True, 'meeting_relevance': True}
            for i, source in enumerate(['香港', '媒体甲', '媒体乙'])]
        data = {'appendices': {'overseas_reports': rows}}
        frozen = copy.deepcopy(data)
        selected = FORMALIZE.representative_overseas_rows(data)
        self.assertEqual(['媒体甲', '媒体乙'], [row['source'] for row in selected])
        self.assertEqual(3, len(FORMALIZE.appendix_overseas_rows(data)))
        self.assertEqual(frozen, data)
        data['appendices']['overseas_reports'] = [rows[0]]
        self.assertEqual(1, len(FORMALIZE.representative_overseas_rows(data)))
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs(data))
        self.assertIn('香港（媒体名称待核）文章', text)

    def test_existing_story_dedup_prefers_named_mirror_without_mutating_raw_rows(self) -> None:
        import copy
        rows = [{'source': source, 'title_cn': '同一会议的事实报道',
                 'url': f'https://example.test/{i}', 'overseas_category': '事实性报道',
                 'formal_include': True, 'meeting_relevance': True}
                for i, source in enumerate(['香港', '媒体甲'])]
        frozen = copy.deepcopy(rows)
        data = {'appendices': {'overseas_reports': rows}}
        selected = FORMALIZE.appendix_overseas_rows(data)
        self.assertEqual(['媒体甲'], [row['source'] for row in selected])
        self.assertEqual(frozen, rows)

    def test_traditional_title_requires_reviewed_simplified_field(self) -> None:
        self.assertEqual(
            FORMALIZE.formal_overseas_title({"title_cn": "國務院常務會議部署"}),
            "国务院常务会议部署",
        )
        self.assertEqual(
            FORMALIZE.formal_overseas_title({"title_cn": "國務院常務會議部署", "title_cn_simplified": "国务院常务会议部署"}),
            "国务院常务会议部署",
        )

    def test_complete_opencc_gate_catches_real_traditional_title(self) -> None:
        original = "陸新建核電增八機組 投資人民幣1700億"
        simplified = "陆新建核电增八机组 投资人民币1700亿"
        self.assertFalse(FORMALIZE.is_simplified_chinese_text(original))
        self.assertEqual(simplified, FORMALIZE.formal_overseas_title({"title_cn": original}))
        self.assertTrue(FORMALIZE.is_simplified_chinese_text(simplified))

    def test_formal_appendix_is_representative_top_ten_but_full_rows_remain(self) -> None:
        base = {"formal_include": True, "meeting_relevance": True, "overseas_category": "事实性报道"}
        data = {"appendices": {"overseas_reports": [
            {**base, "source": f"境外媒体{index}", "title_cn": f"国务院常务会议部署第{index}项工作", "url": f"https://example.test/story/{1000000 + index}", "confidence": index / 20}
            for index in range(15)
        ]}}
        self.assertEqual(15, len(FORMALIZE.appendix_overseas_rows(data)))
        self.assertEqual(10, len(FORMALIZE.formal_appendix_overseas_rows(data)))

    def test_twenty_six_reviewed_traditional_rows_still_yield_top_ten(self) -> None:
        base = {"formal_include": True, "meeting_relevance": True, "overseas_category": "事实性报道"}
        data = {"appendices": {"overseas_reports": [
            {
                **base,
                "source": f"境外媒體{index}",
                "title_cn": f"國務院常務會議核准第{index}個核電項目",
                "url": f"https://example.test/story/{2000000 + index}",
                "confidence": index / 30,
            }
            for index in range(26)
        ]}}
        rows = FORMALIZE.formal_appendix_overseas_rows(data)
        self.assertEqual(10, len(rows))
        self.assertTrue(all(FORMALIZE.is_simplified_chinese_text(row["_formal_title_cn"]) for row in rows))

    def test_isolated_replay_copies_nonzero_charts_without_touching_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / "source"
            out_dir = root / "replay"
            charts = source_dir / "charts"
            charts.mkdir(parents=True)
            source_chart = charts / "topic_distribution_system.png"
            source_chart.write_bytes(b"non-zero-system-chart")
            data_path = source_dir / "report_data.json"
            payload = {"artifacts": {"docx_charts": {"topic_distribution": str(source_chart)}}}
            data_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            before = hashlib.sha256(data_path.read_bytes()).hexdigest()

            FORMALIZE.prepare_isolated_replay_artifacts(payload, data_path, out_dir)

            copied = Path(payload["artifacts"]["docx_charts"]["topic_distribution"])
            self.assertTrue(copied.exists())
            self.assertGreater(copied.stat().st_size, 0)
            self.assertEqual(source_chart.read_bytes(), copied.read_bytes())
            self.assertEqual(before, hashlib.sha256(data_path.read_bytes()).hexdigest())
            self.assertEqual(
                out_dir / "report_data.json",
                FORMALIZE.report_data_output_path(data_path, out_dir, write_back=False),
            )
            self.assertEqual(
                data_path,
                FORMALIZE.report_data_output_path(data_path, out_dir, write_back=True),
            )

    def test_isolated_replay_recovers_wordcloud_from_local_pipeline_copy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source_dir = root / "source"
            charts = source_dir / "charts"
            charts.mkdir(parents=True)
            local_wordcloud = charts / "hotword_distribution_pipeline.png"
            local_wordcloud.write_bytes(b"reviewed-wordcloud")
            data_path = source_dir / "report_data.json"
            payload = {"artifacts": {"docx_charts": {
                "hotword_distribution": str(source_dir / "old-missing-wordcloud.png")
            }}}
            data_path.write_text(json.dumps(payload), encoding="utf-8")

            replay = root / "replay"
            FORMALIZE.prepare_isolated_replay_artifacts(payload, data_path, replay)

            copied = Path(payload["artifacts"]["docx_charts"]["hotword_distribution"])
            self.assertEqual(b"reviewed-wordcloud", copied.read_bytes())
            self.assertEqual(str(copied), payload["artifacts"]["wordcloud_image"])

    def test_formal_partial_appendix_keeps_one_representative_per_story(self) -> None:
        base = {"formal_include": True, "meeting_relevance": True, "overseas_category": "事实性报道"}
        data = {"appendices": {"overseas_reports": [
            {**base, "source": "联合新闻网", "title_cn": "陆砸8100亿冲核电拼经济", "url": "https://udn.com/news/story/7333/9663904"},
            {**base, "source": "经济日报", "title_cn": "陆砸8100亿冲核电拼经济 全力扩大非化石能源供给", "url": "https://money.udn.com/money/story/5603/9663904"},
            {**base, "source": "其他媒体", "title_cn": "国务院常务会议部署宏观政策", "url": "https://other.example/story/1234567"},
        ]}}
        rows = FORMALIZE.appendix_overseas_rows(data)
        self.assertEqual(2, len(rows))
        self.assertEqual({"9663904", "1234567"}, {FORMALIZE.formal_overseas_story_token(row) for row in rows})

    def test_risk_summary_has_neutral_attribution_without_changing_atomic_source(self) -> None:
        row = {'formal_include': True, 'meeting_relevance': True, 'source': '境外媒体甲',
               'title_cn': '公共服务政策的实施条件', 'url': 'https://example.test/risk',
               'overseas_category': '借题炒作/风险解读',
               'summary_cn': '政策效果仍取决于地方资金安排。'}
        original = json.loads(json.dumps(row))
        text = ''.join(FORMALIZE.overseas_media_body_paragraphs({'appendices': {'overseas_reports': [row]}}))
        self.assertIn('文章《公共服务政策的实施条件》称，政策效果仍取决于地方资金安排', text)
        self.assertEqual(original, row)


if __name__ == "__main__":
    unittest.main()
