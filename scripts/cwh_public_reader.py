"""Bounded unauthenticated public-page reader; no private hosts or access bypass."""
from concurrent.futures import ThreadPoolExecutor
from html.parser import HTMLParser
import ipaddress
import re
import socket
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from cwh_pipeline_runtime import utc_now


def check_public_url(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password or not host:
        raise ValueError("Only public unauthenticated HTTP(S) URLs are allowed")
    if host == "ydata.woa.com" or host.endswith(".ydata.woa.com"):
        raise ValueError("Enterprise-restricted host requires its approved MCP")
    for address in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise ValueError("Non-public network destination is forbidden")
    return url


class PublicRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.title_parts, self.skip, self.in_title = [], [], 0, False

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip += 1
        if tag == "title":
            self.in_title = True
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "article", "section"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self.skip = max(0, self.skip - 1)
        if tag == "title":
            self.in_title = False
        if tag in {"p", "div", "li", "article", "section"}:
            self.parts.append("\n")

    def handle_data(self, text):
        if not self.skip:
            self.parts.append(text)
            if self.in_title:
                self.title_parts.append(text)


def read_public_page(url, timeout=12):
    result = {"url": url, "captured_at": utc_now(), "capture_method": "unauthenticated_public_http_html_text"}
    try:
        check_public_url(url)
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 CWH-EvidenceReader/1.0"})
        with build_opener(PublicRedirect()).open(request, timeout=timeout) as response:
            data = response.read(3_000_001)
            if len(data) > 3_000_000:
                raise ValueError("Page exceeds bounded reader size; not treated as full text")
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml", "text/plain"}:
                raise ValueError("Not a supported complete text page")
            charset = response.headers.get_content_charset()
            match = re.search(br"charset\s*=\s*[\"']?([\w-]+)", data[:5000], re.I)
            charset = charset or (match.group(1).decode("ascii") if match else "utf-8")
            raw_text = data.decode(charset, errors="strict")
            page = PageText()
            page.feed(raw_text)
            text = "\n".join(line.strip() for line in "".join(page.parts).splitlines() if line.strip())
            if len(text) < 100 or any(x in text[:500] for x in ("访问过于频繁", "访问验证", "安全验证", "验证码", "Access Denied")):
                raise ValueError("No readable full page, or an access challenge was returned")
            result.update(status="completed", source_text=text, page_title="".join(page.title_parts).strip(), final_url=response.geturl())
    except Exception as exc:
        result.update(status="access_failed", blocker=f"{type(exc).__name__}: {exc}")
    return result


def read_public_pages(urls, timeout=12):
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(lambda url: read_public_page(url, timeout), list(dict.fromkeys(urls))))
