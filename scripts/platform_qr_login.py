"""Create a real platform QR login session for the CWH shared workbench."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from playwright.async_api import Browser, BrowserContext, Locator, Page, async_playwright


PLATFORMS = {
    "bili": {
        "name": "哔哩哔哩",
        "url": "https://www.bilibili.com/",
        "auth_cookies": {"SESSDATA", "bili_jct", "DedeUserID"},
    },
    "dy": {
        "name": "抖音",
        "url": "https://www.douyin.com/",
        "auth_cookies": {"sessionid", "sessionid_ss", "sid_tt", "uid_tt"},
    },
    "wb": {
        "name": "微博",
        "url": "https://weibo.com/",
        "auth_cookies": {"SUB", "SUBP"},
    },
    "ks": {
        "name": "快手",
        "url": "https://www.kuaishou.com/",
        "auth_cookies": {"did", "userId", "kuaishou.server.web_st"},
    },
    "zhihu": {
        "name": "知乎",
        "url": "https://www.zhihu.com/",
        "auth_cookies": {"z_c0"},
    },
}


def write_state(path: Path, **changes) -> dict:
    current = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    current.update(changes, updated_at=datetime.now().isoformat(timespec="seconds"))
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)
    return current


async def is_authenticated(context: BrowserContext, platform: str) -> bool:
    names = {row["name"] for row in await context.cookies()}
    return bool(names & PLATFORMS[platform]["auth_cookies"])


async def click_login_entry(page: Page) -> None:
    selectors = [
        "text=登录",
        "button:has-text('登录')",
        "[class*='login']:has-text('登录')",
        "[data-e2e*='login']",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        count = await locator.count()
        for index in range(min(count, 12)):
            item = locator.nth(index)
            try:
                if await item.is_visible():
                    await item.click(timeout=3000)
                    return
            except Exception:
                continue


async def candidate_score(item: Locator) -> float:
    try:
        if not await item.is_visible():
            return -1
        box = await item.bounding_box()
        if not box:
            return -1
        width = float(box["width"])
        height = float(box["height"])
        if min(width, height) < 100 or max(width, height) > 520:
            return -1
        ratio = min(width, height) / max(width, height)
        if ratio < 0.72:
            return -1
        src = str(await item.get_attribute("src") or "").lower()
        label = " ".join(
            [
                str(await item.get_attribute("alt") or "").lower(),
                str(await item.get_attribute("class") or "").lower(),
            ]
        )
        hint = 120 if any(token in src + " " + label for token in ("qr", "qrcode", "scan", "二维码")) else 0
        return min(width, height) * ratio + hint
    except Exception:
        return -1


async def find_qr_image(page: Page) -> Locator | None:
    images = page.locator("img")
    count = await images.count()
    best: Locator | None = None
    best_score = -1.0
    for index in range(min(count, 120)):
        item = images.nth(index)
        score = await candidate_score(item)
        if score > best_score:
            best = item
            best_score = score
    return best if best_score >= 100 else None


async def consume_actions(page: Page, action_path: Path, processed: int) -> int:
    if not action_path.exists():
        return processed
    lines = action_path.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines[processed:]:
        try:
            action = json.loads(line)
            action_type = action.get("type")
            if action_type not in {"click", "drag"}:
                continue
            start = action.get("start") or {}
            end = action.get("end") or {}
            x1, y1 = float(start["x"]), float(start["y"])
            x2, y2 = float(end["x"]), float(end["y"])
            if action_type == "click":
                await page.mouse.click(x1, y1)
            else:
                await page.mouse.move(x1, y1)
                await page.mouse.down()
                await page.mouse.move(x2, y2, steps=28)
                await page.mouse.up()
        except Exception:
            continue
    return len(lines)


async def run_login(platform: str, profile: Path, qr_path: Path, state_path: Path, action_path: Path, timeout_sec: int) -> int:
    settings = PLATFORMS[platform]
    profile.mkdir(parents=True, exist_ok=True)
    # A container restart can leave Chromium's singleton files behind even
    # though the owning process no longer exists. They prevent a fresh
    # persistent context from opening and otherwise leave the UI at starting.
    for lock_name in ("SingletonLock", "SingletonSocket", "SingletonCookie", "DevToolsActivePort"):
        lock_path = profile / lock_name
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass
    storage_state_path = profile / "storage_state.json"
    launch_timeout_sec = max(45, int(os.environ.get("CWH_BROWSER_LAUNCH_TIMEOUT_SEC") or 90))
    write_state(
        state_path,
        status="starting",
        qr_ready=False,
        login_protocol=3,
        message="正在启动平台登录浏览器…",
    )
    async with async_playwright() as playwright:
        browser: Browser | None = None
        context: BrowserContext | None = None
        try:
            executable_path = Path(playwright.chromium.executable_path)
            if not executable_path.is_file():
                raise RuntimeError(f"Chromium browser executable is missing: {executable_path}")
            browser = await asyncio.wait_for(
                playwright.chromium.launch(
                    executable_path=str(executable_path),
                    headless=True,
                    chromium_sandbox=False,
                    args=[
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--disable-software-rasterizer",
                        "--no-zygote",
                        "--disable-background-networking",
                        "--disable-breakpad",
                        "--disable-crash-reporter",
                        "--disable-extensions",
                        "--disable-sync",
                        "--metrics-recording-only",
                        "--mute-audio",
                    ],
                    timeout=launch_timeout_sec * 1000,
                ),
                timeout=launch_timeout_sec + 5,
            )
            context_options = {
                "viewport": {"width": 1280, "height": 900},
                "locale": "zh-CN",
            }
            if storage_state_path.exists():
                context_options["storage_state"] = str(storage_state_path)
            context = await browser.new_context(**context_options)
            write_state(state_path, status="starting", qr_ready=False, message="平台登录页正在加载…")
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(settings["url"], wait_until="commit", timeout=30000)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            if await is_authenticated(context, platform):
                write_state(state_path, status="connected", qr_ready=False, message=f"{settings['name']}账号已连接。", connected_at=datetime.now().isoformat(timespec="seconds"))
                return 0
            await click_login_entry(page)
            await page.wait_for_timeout(5000)
            preview_path = state_path.parent / "login_page_preview.png"
            await page.screenshot(path=str(preview_path), full_page=False)
            deadline = asyncio.get_running_loop().time() + timeout_sec
            captured = False
            processed_actions = 0
            while asyncio.get_running_loop().time() < deadline:
                processed_actions = await consume_actions(page, action_path, processed_actions)
                if await is_authenticated(context, platform):
                    write_state(state_path, status="connected", qr_ready=captured, message=f"{settings['name']}账号已连接。", connected_at=datetime.now().isoformat(timespec="seconds"))
                    return 0
                candidate = await find_qr_image(page)
                if candidate:
                    try:
                        await candidate.screenshot(path=str(qr_path))
                        captured = True
                        write_state(state_path, status="awaiting_scan", qr_ready=True, message=f"请使用{settings['name']}手机客户端扫码。")
                    except Exception:
                        pass
                if not captured:
                    await page.screenshot(path=str(preview_path), full_page=False)
                    write_state(
                        state_path,
                        status="awaiting_verification",
                        preview_ready=True,
                        message="平台要求安全验证，请在登录页预览中亲手拖动滑块。",
                    )
                await asyncio.sleep(1.2)
            write_state(state_path, status="failed", qr_ready=captured, message="二维码已过期或未确认登录，请重新连接。")
            return 3
        except Exception as exc:
            screenshot = state_path.parent / "login_page_error.png"
            try:
                if context and context.pages:
                    await context.pages[0].screenshot(path=str(screenshot), full_page=True)
            except Exception:
                pass
            write_state(state_path, status="failed", message=f"平台登录页启动失败：{type(exc).__name__}: {exc}")
            return 2
        finally:
            if context:
                try:
                    await context.storage_state(path=str(storage_state_path))
                except Exception:
                    pass
                await context.close()
            if browser:
                await browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Open a real platform login page and expose its QR image")
    parser.add_argument("--platform", choices=sorted(PLATFORMS), required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--qr-path", type=Path, required=True)
    parser.add_argument("--state-path", type=Path, required=True)
    parser.add_argument("--action-path", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=int, default=180)
    args = parser.parse_args()
    return asyncio.run(
        run_login(
            args.platform,
            args.profile.resolve(),
            args.qr_path.resolve(),
            args.state_path.resolve(),
            args.action_path.resolve(),
            max(30, args.timeout_sec),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
