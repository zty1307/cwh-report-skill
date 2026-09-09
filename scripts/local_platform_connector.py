"""Open login-protected CWH sources in persistent local browser profiles.

The With workbench cannot read a colleague's browser cookies.  This loopback
helper opens a real Edge/Chrome window with the existing CWH CDP profile.  All
platforms reuse that local collection profile (cookies remain domain-scoped),
and the CWH article-search adapters receive the same profile explicitly.
"""

from __future__ import annotations

import argparse
import base64
import html
import json
import os
import socket
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class PlatformSpec:
    label: str
    url: str
    kind: str = "mediaspider"


PLATFORMS = {
    "wb": PlatformSpec("微博", "https://weibo.com/"),
    "dy": PlatformSpec("抖音", "https://www.douyin.com/"),
    "ks": PlatformSpec("快手", "https://www.kuaishou.com/"),
    "bili": PlatformSpec("哔哩哔哩", "https://www.bilibili.com/"),
    "zhihu": PlatformSpec("知乎", "https://www.zhihu.com/"),
    "baijiahao": PlatformSpec(
        "百家号",
        "https://www.baidu.com/s?wd=site%3Abaijiahao.baidu.com%20国务院常务会议",
        "public_source",
    ),
    "wechat_weread": PlatformSpec(
        "微信读书（公众号）",
        "https://weread.qq.com/",
        "public_source",
    ),
}


def browser_candidates(browser: str) -> list[Path]:
    program_files = Path(os.environ.get("PROGRAMFILES") or r"C:\Program Files")
    program_files_x86 = Path(os.environ.get("PROGRAMFILES(X86)") or r"C:\Program Files (x86)")
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    edge = [
        program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
        program_files / "Microsoft/Edge/Application/msedge.exe",
    ]
    chrome = [
        program_files / "Google/Chrome/Application/chrome.exe",
        program_files_x86 / "Google/Chrome/Application/chrome.exe",
        local / "Google/Chrome/Application/chrome.exe",
    ]
    return chrome + edge if browser == "chrome" else edge + chrome


class BrowserTarget:
    def __init__(self, profile: Path, port: int) -> None:
        self.profile = profile.resolve()
        self.port = port
        self.profile.mkdir(parents=True, exist_ok=True)

    def cdp(self, path: str, *, method: str = "GET", timeout: float = 3) -> object:
        request = Request(f"http://127.0.0.1:{self.port}{path}", method=method)
        with urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            try:
                return json.loads(body)
            except ValueError:
                # Chromium's /json/activate endpoint returns plain text.
                return body

    def ready(self) -> bool:
        try:
            return bool(self.cdp("/json/version"))
        except Exception:
            return False

    def pages(self) -> list[dict]:
        try:
            rows = self.cdp("/json/list")
            return [row for row in rows if isinstance(row, dict) and row.get("type") == "page"]
        except Exception:
            return []

    def open(self, url: str, browser: str) -> str:
        if self.ready():
            target = self.cdp("/json/new?" + quote(url, safe=""), method="PUT", timeout=15)
            target_id = str(target.get("id") or "") if isinstance(target, dict) else ""
            if target_id:
                # Creating a CDP target does not necessarily focus its window.
                # Activate it so a user-requested login page is actually visible.
                self.cdp(f"/json/activate/{quote(target_id, safe='')}", timeout=10)
            return "已运行的采集浏览器"
        executable = next((path for path in browser_candidates(browser) if path.is_file()), None)
        if not executable:
            raise FileNotFoundError("未找到 Edge 或 Chrome")
        command = [
            str(executable),
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            url,
        ]
        subprocess.Popen(command, close_fds=True)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.ready():
                return executable.stem
            time.sleep(0.25)
        raise RuntimeError("浏览器已经启动，但调试端口尚未就绪")

    def evaluate(self, page: dict, expression: str) -> object:
        if not page.get("webSocketDebuggerUrl"):
            return None
        parsed = urlparse(str(page["webSocketDebuggerUrl"]))
        sock = socket.create_connection((parsed.hostname or "127.0.0.1", parsed.port or 80), timeout=3)
        try:
            key = base64.b64encode(os.urandom(16)).decode("ascii")
            request = (
                f"GET {parsed.path or '/'}{('?' + parsed.query) if parsed.query else ''} HTTP/1.1\r\n"
                f"Host: {parsed.hostname}:{parsed.port or 80}\r\n"
                "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
                "Origin: http://127.0.0.1\r\n\r\n"
            ).encode("ascii")
            sock.sendall(request)
            headers = b""
            while b"\r\n\r\n" not in headers:
                chunk = sock.recv(4096)
                if not chunk:
                    raise ConnectionError("CDP WebSocket handshake failed")
                headers += chunk
            if b" 101 " not in headers.split(b"\r\n", 1)[0]:
                raise ConnectionError("CDP WebSocket upgrade was rejected")
            self._send_ws_text(
                sock,
                json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": expression, "returnByValue": True}}),
            )
            while True:
                payload = json.loads(self._recv_ws_text(sock))
                if payload.get("id") == 1:
                    return (((payload.get("result") or {}).get("result") or {}).get("value"))
        except (OSError, ValueError, ConnectionError):
            return None
        finally:
            sock.close()

    @staticmethod
    def _read_exact(sock: socket.socket, size: int) -> bytes:
        output = bytearray()
        while len(output) < size:
            chunk = sock.recv(size - len(output))
            if not chunk:
                raise ConnectionError("CDP WebSocket closed")
            output.extend(chunk)
        return bytes(output)

    @staticmethod
    def _send_ws_text(sock: socket.socket, value: str) -> None:
        payload = value.encode("utf-8")
        mask = os.urandom(4)
        length = len(payload)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length <= 0xFFFF:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        masked = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
        sock.sendall(bytes(header) + mask + masked)

    @classmethod
    def _recv_ws_text(cls, sock: socket.socket) -> str:
        fragments = bytearray()
        while True:
            first, second = cls._read_exact(sock, 2)
            opcode = first & 0x0F
            length = second & 0x7F
            if length == 126:
                length = struct.unpack("!H", cls._read_exact(sock, 2))[0]
            elif length == 127:
                length = struct.unpack("!Q", cls._read_exact(sock, 8))[0]
            mask = cls._read_exact(sock, 4) if second & 0x80 else b""
            payload = cls._read_exact(sock, length)
            if mask:
                payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
            if opcode == 0x8:
                raise ConnectionError("CDP WebSocket closed")
            if opcode in {0x1, 0x0}:
                fragments.extend(payload)
                if first & 0x80:
                    return fragments.decode("utf-8")


class Connector:
    def __init__(self, profile: Path, port: int, *, public_state_dir: Path | None = None) -> None:
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        state_dir = (public_state_dir or local / "cwh-report-skill").resolve()
        state_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = state_dir / "platform_connection_state.json"
        self.profile_path = state_dir / "platform_profile.json"
        self._lock = threading.Lock()
        shared_target = BrowserTarget(profile, port)
        # One CDP port is intentionally reused. Some managed Edge installations
        # allow only the configured collection port; cookie storage is still
        # isolated by website domain inside this local-only profile.
        self.targets = {
            "mediaspider": shared_target,
            "baijiahao": shared_target,
            "wechat_weread": shared_target,
        }
        self.profile_path.write_text(
            json.dumps({"profile_dir": str(shared_target.profile), "cdp_port": shared_target.port}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def target_for(self, platform: str) -> BrowserTarget:
        if platform not in PLATFORMS:
            raise ValueError("不支持的平台")
        return self.targets.get(platform) or self.targets["mediaspider"]

    def ready(self) -> bool:
        return self.targets["mediaspider"].ready()

    def _read_state(self) -> dict:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, ValueError):
            return {}

    def _remember_connected(self, platform: str) -> None:
        with self._lock:
            state = self._read_state()
            state[platform] = {
                "status": "connected",
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
            temp = self.state_path.with_suffix(".tmp")
            temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.state_path)

    def open_platform(self, platform: str, browser: str) -> dict:
        spec = PLATFORMS.get(platform)
        if not spec:
            raise ValueError("不支持的平台")
        used_browser = self.target_for(platform).open(spec.url, browser)
        status = self.platform_status(platform)
        return {
            "status": "opened",
            "connection_status": status["status"],
            "platform": platform,
            "label": spec.label,
            "browser": used_browser,
            "terminal": False,
        }

    def platform_status(self, platform: str) -> dict:
        spec = PLATFORMS.get(platform)
        if not spec:
            raise ValueError("不支持的平台")
        target = self.target_for(platform)
        if spec.kind == "mediaspider":
            return {
                "platform": platform,
                "label": spec.label,
                "status": "opened" if target.ready() else "disconnected",
                "message": "采集浏览器已打开，请在页面内完成登录。" if target.ready() else "尚未打开登录页。",
                "terminal": False,
            }

        pages = target.pages()
        relevant = [row for row in pages if self._is_relevant(platform, str(row.get("url") or ""))]
        live_status = self._inspect_public_source(platform, target, relevant)
        if live_status == "connected":
            self._remember_connected(platform)
        remembered = (self._read_state().get(platform) or {}).get("status") == "connected"
        if not relevant and remembered:
            live_status = "connected"
        messages = {
            "disconnected": "尚未打开验证页。",
            "waiting_login": "验证页已打开，请完成滑块或扫码；完成前不是任务终点。",
            "connected": "验证已完成，会话已保存；关闭验证浏览器后可由检索任务复用。",
            "opened": "页面已打开，正在检查连接状态。",
        }
        return {
            "platform": platform,
            "label": spec.label,
            "status": live_status,
            "message": messages[live_status],
            "terminal": live_status == "connected",
            "browser_open": target.ready(),
        }

    @staticmethod
    def _is_relevant(platform: str, url: str) -> bool:
        if platform == "baijiahao":
            return any(host in url for host in ("baidu.com", "baijiahao.baidu.com"))
        return any(host in url for host in ("weread.qq.com", "search.weixin.qq.com"))

    @staticmethod
    def _inspect_public_source(platform: str, target: BrowserTarget, pages: list[dict]) -> str:
        if not target.ready():
            return "disconnected"
        if not pages:
            return "opened"
        for page in reversed(pages):
            url = str(page.get("url") or "")
            body = target.evaluate(
                page,
                "JSON.stringify({text:(document.body&&document.body.innerText||'').slice(0,12000),items:document.querySelectorAll('.search_list_item').length,cookie:document.cookie||''})",
            )
            try:
                snapshot = json.loads(body) if isinstance(body, str) else {}
            except ValueError:
                snapshot = {}
            text = str(snapshot.get("text") or "")
            if platform == "baijiahao":
                if any(token in url.lower() for token in ("captcha", "verify", "passport.baidu.com")):
                    return "waiting_login"
                if any(token in text for token in ("安全验证", "完成验证", "拖动滑块", "访问异常", "请输入验证码")):
                    return "waiting_login"
                if ("baidu.com/s" in url or "baijiahao.baidu.com" in url) and (text or body is None):
                    return "connected"
            else:
                if "wr_vid=" in str(snapshot.get("cookie") or ""):
                    return "connected"
                if any(token in url.lower() for token in ("login", "passport", "oauth")):
                    return "waiting_login"
                if int(snapshot.get("items") or 0) > 0:
                    return "connected"
                if any(token in text for token in ("扫码", "登录微信读书", "微信登录", "请先登录", "扫码登录")):
                    return "waiting_login"
                # The logged-in home exposes the personal shelf/actions while
                # the anonymous home exposes a prominent standalone “登录”.
                if any(token in text for token in ("继续阅读", "我的书架", "传书到手机")) and "\n登录\n" not in f"\n{text}\n":
                    return "connected"
                if "\n登录\n" in f"\n{text}\n":
                    return "waiting_login"
                if text and "weread.qq.com" in url:
                    return "opened"
                if text and "search.weixin.qq.com" in url:
                    # A completed search can validly have zero results.
                    return "connected"
        return "opened"


def page(title: str, message: str, platform: str = "", ok: bool = True) -> bytes:
    color = "#17618d" if ok else "#a33a3a"
    platform_json = json.dumps(platform, ensure_ascii=False)
    script = ""
    if ok and platform:
        script = f"""
<script>
const platform={platform_json};
async function poll(){{
  try{{
    const response=await fetch('/status?platform='+encodeURIComponent(platform));
    const data=await response.json();
    document.getElementById('state').textContent=data.message||data.status;
    if(data.status==='connected') document.getElementById('state').className='connected';
  }}catch(_){{}}
}}
poll();setInterval(poll,1500);
</script>"""
    body = f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>body{{margin:0;background:#eef2f4;color:#102433;font:16px 'Microsoft YaHei',sans-serif}}
main{{max-width:680px;margin:12vh auto;background:#fff;border-top:4px solid {color};padding:34px 38px;box-shadow:0 10px 30px #10243318}}
h1{{margin:0 0 14px;font-size:24px}}p{{line-height:1.8;color:#526774}}.connected{{color:#0b7a52;font-weight:700}}button{{border:1px solid #17618d;background:#17618d;color:#fff;padding:10px 18px;font:inherit;cursor:pointer}}</style>
<main><h1>{html.escape(title)}</h1><p>{html.escape(message)}</p><p id="state">正在检查连接状态…</p><button onclick="window.close()">关闭本页</button></main>{script}</html>"""
    return body.encode("utf-8")


def handler_factory(connector: Connector):
    class Handler(BaseHTTPRequestHandler):
        def cors(self) -> None:
            origin = str(self.headers.get("Origin") or "")
            allowed = (
                (origin.startswith("https://") and origin.endswith(".with.woa.com"))
                or origin.startswith("http://127.0.0.1")
                or origin.startswith("http://localhost")
            )
            if allowed:
                self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Private-Network", "true")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

        def send_json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.cors()
            self.end_headers()
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            self.send_response(204)
            self.cors()
            self.end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/health"}:
                self.send_json({"status": "ok", "cdp_ready": connector.ready(), "platforms": list(PLATFORMS)})
                return
            if parsed.path == "/status":
                platform = str((parse_qs(parsed.query).get("platform") or [""])[0]).lower()
                try:
                    self.send_json(connector.platform_status(platform))
                except Exception as exc:
                    self.send_json({"status": "error", "error": f"{type(exc).__name__}: {exc}"}, 400)
                return
            if parsed.path == "/connect":
                query = parse_qs(parsed.query)
                platform = str((query.get("platform") or [""])[0]).lower()
                browser = str((query.get("browser") or ["edge"])[0]).lower()
                try:
                    result = connector.open_platform(platform, browser)
                    body = page(
                        f"连接{result['label']}",
                        f"已在本机 {result['browser']} 中打开真实验证页。请完成登录、滑块或扫码；验证完成前只是等待状态，不会被当成任务终点。",
                        platform,
                    )
                    status = 200
                except Exception as exc:
                    body = page("平台连接失败", f"{type(exc).__name__}: {exc}", ok=False)
                    status = 500
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.cors()
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_error(404)

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def main() -> int:
    parser = argparse.ArgumentParser(description="CWH local platform connector")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8791)
    parser.add_argument("--cdp-port", type=int, default=9222)
    parser.add_argument("--profile", type=Path, default=Path.home() / ".cwh" / "browser_profile")
    parser.add_argument("--public-state-dir", type=Path)
    args = parser.parse_args()
    if args.host not in {"127.0.0.1", "localhost"}:
        raise ValueError("连接器只允许监听本机回环地址")
    connector = Connector(args.profile, args.cdp_port, public_state_dir=args.public_state_dir)
    server = ThreadingHTTPServer((args.host, args.port), handler_factory(connector))
    print(f"CWH platform connector: http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
