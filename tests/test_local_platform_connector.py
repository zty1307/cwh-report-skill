from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import sys


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import local_platform_connector as connector_module


class FakeTarget:
    def __init__(self, *, ready: bool, pages: list[dict] | None = None, snapshots: dict[str, str] | None = None) -> None:
        self._ready = ready
        self._pages = pages or []
        self._snapshots = snapshots or {}

    def ready(self) -> bool:
        return self._ready

    def pages(self) -> list[dict]:
        return self._pages

    def evaluate(self, page: dict, expression: str) -> object:
        return self._snapshots.get(str(page.get("url") or ""))


class LocalPlatformConnectorTests(unittest.TestCase):
    def make_connector(self, directory: Path) -> connector_module.Connector:
        with mock.patch.dict("os.environ", {"LOCALAPPDATA": str(directory / "local")}, clear=False):
            return connector_module.Connector(directory / "media", 9222, public_state_dir=directory / "cwh")

    def test_public_article_platforms_reuse_the_cwh_collection_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            connector = self.make_connector(directory)
            self.assertIn("baijiahao", connector_module.PLATFORMS)
            self.assertIn("wechat_weread", connector_module.PLATFORMS)
            self.assertIs(connector.targets["baijiahao"], connector.targets["mediaspider"])
            self.assertIs(connector.targets["wechat_weread"], connector.targets["mediaspider"])
            marker = connector_module.json.loads(connector.profile_path.read_text(encoding="utf-8"))
            self.assertEqual(str((directory / "media").resolve()), marker["profile_dir"])
            self.assertEqual(9222, marker["cdp_port"])

    def test_existing_browser_activates_the_new_login_tab(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = connector_module.BrowserTarget(Path(temp), 9222)
            calls: list[tuple[str, str, float]] = []

            def fake_cdp(path: str, *, method: str = "GET", timeout: float = 3) -> object:
                calls.append((path, method, timeout))
                if path == "/json/version":
                    return {"Browser": "Edge"}
                if path.startswith("/json/new?"):
                    return {"id": "target-123"}
                return {"status": "activated"}

            target.cdp = fake_cdp  # type: ignore[method-assign]
            target.open("https://www.baidu.com/", "edge")
            self.assertIn(("/json/activate/target-123", "GET", 10), calls)

    def test_baijiahao_slider_is_waiting_login_and_nonterminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            connector = self.make_connector(Path(temp))
            url = "https://wappass.baidu.com/static/captcha/tuxing.html"
            connector.targets["baijiahao"] = FakeTarget(ready=True, pages=[{"url": url}])
            status = connector.platform_status("baijiahao")
            self.assertEqual(status["status"], "waiting_login")
            self.assertFalse(status["terminal"])

    def test_weread_search_results_mark_connection_and_persist_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            connector = self.make_connector(Path(temp))
            url = "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump"
            connector.targets["wechat_weread"] = FakeTarget(
                ready=True,
                pages=[{"url": url}],
                snapshots={url: '{"text":"搜索结果","items":3}'},
            )
            status = connector.platform_status("wechat_weread")
            self.assertEqual(status["status"], "connected")
            self.assertTrue(status["terminal"])
            connector.targets["wechat_weread"] = FakeTarget(ready=False)
            self.assertEqual(connector.platform_status("wechat_weread")["status"], "connected")

    def test_weread_qr_is_waiting_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            connector = self.make_connector(Path(temp))
            url = "https://search.weixin.qq.com/cgi-bin/newsearchweb/userclientjump"
            connector.targets["wechat_weread"] = FakeTarget(
                ready=True,
                pages=[{"url": url}],
                snapshots={url: '{"text":"请扫码登录微信读书","items":0}'},
            )
            status = connector.platform_status("wechat_weread")
            self.assertEqual(status["status"], "waiting_login")
            self.assertFalse(status["terminal"])

    def test_weread_personal_shelf_marks_logged_in_home(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            connector = self.make_connector(Path(temp))
            url = "https://weread.qq.com/"
            connector.targets["wechat_weread"] = FakeTarget(
                ready=True,
                pages=[{"url": url}],
                snapshots={url: '{"text":"继续阅读\\n我的书架\\n传书到手机","items":0,"cookie":"wr_gid=1"}'},
            )
            self.assertEqual(connector.platform_status("wechat_weread")["status"], "connected")

    def test_weread_anonymous_home_remains_waiting_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            connector = self.make_connector(Path(temp))
            url = "https://weread.qq.com/"
            connector.targets["wechat_weread"] = FakeTarget(
                ready=True,
                pages=[{"url": url}],
                snapshots={url: '{"text":"大家都在看\\n登录\\n榜单","items":0,"cookie":"wr_gid=1"}'},
            )
            status = connector.platform_status("wechat_weread")
            self.assertEqual(status["status"], "waiting_login")
            self.assertFalse(status["terminal"])


if __name__ == "__main__":
    unittest.main()
