"""OPENVID WebWorker — fetch pages / search the web.

Actions:
    web.fetch {url}           -> raw text (html stripped), max 20k chars
    web.search {query}        -> DuckDuckGo HTML search -> top results
No external deps; robots respected by convention (agent-level use only).
"""
from __future__ import annotations

import gzip
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OPENVID-agent/1.0"


def _get(url: str, timeout: float = 20.0) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
        if r.headers.get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        return data, r.headers.get("Content-Type", "")


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    html = re.sub(r"\s+", " ", html)
    return html.strip()


class WebWorker:
    name = "web"
    topics = ["agent.action"]
    actions = {"web.fetch", "web.search"}

    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "web.fetch":
            url = payload.get("url", "")
            if not re.match(r"^https?://", url):
                return {"ok": False, "error": "http(s) url required"}
            try:
                data, ctype = _get(url)
                text = data.decode("utf-8", errors="replace")
                if "html" in ctype:
                    title_m = re.search(r"<title[^>]*>(.*?)</title>", text, re.S | re.I)
                    return {"ok": True, "title": title_m.group(1).strip()[:200] if title_m else "",
                            "content": _strip_html(text)[:20000], "url": url}
                return {"ok": True, "content": text[:20000], "url": url}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if act == "web.search":
            query = payload.get("query", "").strip()
            if not query:
                return {"ok": False, "error": "query required"}
            try:
                url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
                data, _ = _get(url)
                html = data.decode("utf-8", errors="replace")
                results = []
                for m in re.finditer(
                        r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
                    href = urllib.parse.unquote(re.sub(r"^//duck\.co/l/\?uddg=", "", m.group(1)))
                    title = _strip_html(m.group(2))[:150]
                    results.append({"title": title, "url": href})
                    if len(results) >= 8:
                        break
                return {"ok": True, "results": results}
            except Exception as e:
                return {"ok": False, "error": f"{type(e).__name__}: {e}"}
        return {"ok": False, "error": f"unsupported: {act}"}
