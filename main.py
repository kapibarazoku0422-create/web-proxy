from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response, HTMLResponse, FileResponse

import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, quote
import re
import os

app = FastAPI()

@app.get("/favicon.ico")
async def favicon():
    return FileResponse("favicon.ico")

AUTH_TOKEN = os.environ.get("PROXY_TOKEN", "")
RATE_LIMIT_HEADER = {"X-Robots-Tag": "noindex, nofollow"}



HOME_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<link rel="icon" href="/favicon.ico">
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>kapibara home</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    min-height: 100vh;
    background: #0f0f0f;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    color: #e0e0e0;
  }
  .logo { font-size: 48px; font-weight: 700; letter-spacing: -2px; color: #fff; margin-bottom: 8px; }
  .sub { font-size: 14px; color: #555; margin-bottom: 48px; letter-spacing: 2px; text-transform: uppercase; }
  .search-box {
    display: flex; align-items: center;
    background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 12px;
    padding: 6px 6px 6px 20px; width: 560px; max-width: 90vw; gap: 8px;
    transition: border-color 0.2s;
  }
  .search-box:focus-within { border-color: #444; }
  .search-box input {
    flex: 1; background: none; border: none; outline: none;
    font-size: 16px; color: #e0e0e0; min-width: 0;
  }
  .search-box input::placeholder { color: #444; }
  .search-box button {
    background: #fff; color: #000; border: none; border-radius: 8px;
    padding: 10px 20px; font-size: 14px; font-weight: 600; cursor: pointer;
    white-space: nowrap; transition: opacity 0.2s;
  }
  .search-box button:hover { opacity: 0.85; }
  .hint { margin-top: 20px; font-size: 13px; color: #333; }
</style>
</head>
<body>
<div class="logo">kapibara home</div>
<div class="sub">browse anywhere</div>
<form class="search-box" onsubmit="go(event)">
  <input id="url" type="text" placeholder="https://example.com" autocomplete="off" autofocus />
  <button type="submit">開く</button>
</form>
<p class="hint">URLを入力してEnterまたは「開く」を押してください</p>
<script>
function go(e) {
  e.preventDefault();
  let url = document.getElementById('url').value.trim();
  if (!url) return;
  if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url;
  window.location.href = '/view?url=' + encodeURIComponent(url);
}
</script>
</body>
</html>"""

HOME_BUTTON = """
<div id="__kh_home" style="position:fixed;top:12px;left:12px;z-index:2147483647;">
  <a href="/" title="kapibara home" style="
    display:flex;align-items:center;justify-content:center;
    width:40px;height:40px;border-radius:10px;
    background:rgba(15,15,15,0.85);backdrop-filter:blur(8px);
    border:1px solid rgba(255,255,255,0.12);
    text-decoration:none;color:#fff;font-size:20px;
    box-shadow:0 2px 12px rgba(0,0,0,0.4);
  " onmouseover="this.style.background='rgba(40,40,40,0.95)'"
     onmouseout="this.style.background='rgba(15,15,15,0.85)'">⌂</a>
</div>
"""

def rewrite_url(url: str, base_url: str = "") -> str:
    if not url or url.startswith(("data:", "javascript:", "#", "mailto:", "tel:", "/view?")):
        return url
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        if base_url:
            url = urljoin(base_url, url)
        else:
            return url
    return f"/view?url={quote(url, safe='')}"

def rewrite_js(js: str, base_url: str) -> str:
    """JS内のURLっぽい文字列をプロキシ経由に書き換え"""
    def replace_url(m):
        quote_char = m.group(1)
        url = m.group(2)
        if url.startswith(("data:", "javascript:", "/view?")):
            return m.group(0)
        rewritten = rewrite_url(url, base_url)
        return f"{quote_char}{rewritten}{quote_char}"

    # "https://..." や 'https://...' を置換
    js = re.sub(r'(["\'])(https?://[^"\'<>\s]{4,})(["\'])', 
                lambda m: f'{m.group(1)}{rewrite_url(m.group(2), base_url)}{m.group(3)}', js)
    return js

def rewrite_html(content: bytes, base_url: str) -> bytes:
    try:
        soup = BeautifulSoup(content, "html.parser")

        for tag in soup.find_all("a", href=True):
            tag["href"] = rewrite_url(tag["href"], base_url)
        for tag in soup.find_all("form", action=True):
            tag["action"] = rewrite_url(tag["action"], base_url)
        for tag in soup.find_all("link", href=True):
            tag["href"] = rewrite_url(tag["href"], base_url)
        for tag in soup.find_all("script", src=True):
            tag["src"] = rewrite_url(tag["src"], base_url)
        for tag in soup.find_all("img", src=True):
            tag["src"] = rewrite_url(tag["src"], base_url)
        for tag in soup.find_all("img", srcset=True):
            parts = []
            for p in tag["srcset"].split(","):
                p = p.strip()
                if not p: continue
                pieces = p.split()
                pieces[0] = rewrite_url(pieces[0], base_url)
                parts.append(" ".join(pieces))
            tag["srcset"] = ", ".join(parts)
        for tag in soup.find_all("source"):
            if tag.get("src"):
                tag["src"] = rewrite_url(tag["src"], base_url)
            if tag.get("srcset"):
                parts = []
                for p in tag["srcset"].split(","):
                    p = p.strip()
                    if not p: continue
                    pieces = p.split()
                    pieces[0] = rewrite_url(pieces[0], base_url)
                    parts.append(" ".join(pieces))
                tag["srcset"] = ", ".join(parts)
        for tag in soup.find_all("base"):
            tag.decompose()

        # インラインJSも書き換え
        for tag in soup.find_all("script", src=False):
            if tag.string:
                tag.string = rewrite_js(tag.string, base_url)

        body = soup.find("body")
        if body:
            body.insert(0, BeautifulSoup(HOME_BUTTON, "html.parser"))

        return str(soup).encode("utf-8", errors="replace")
    except Exception:
        return content

def rewrite_css(content: bytes, base_url: str) -> bytes:
    """CSS内のurl()を書き換え"""
    try:
        text = content.decode("utf-8", errors="replace")
        def replace(m):
            url = m.group(1).strip("'\"")
            return f"url({rewrite_url(url, base_url)})"
        text = re.sub(r'url\(([^)]+)\)', replace, text)
        return text.encode("utf-8", errors="replace")
    except Exception:
        return content

@app.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=HOME_HTML)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.api_route("/view", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def view(request: Request):
    if AUTH_TOKEN:
        token = request.headers.get("X-Proxy-Token") or request.query_params.get("token")
        if token != AUTH_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized")

    target_url = request.query_params.get("url")
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing 'url' query parameter")
    if not target_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL scheme")

    body = await request.body()
    skip_headers = {"host", "x-proxy-token", "content-length", "accept-encoding"}
    headers = {k: v for k, v in request.headers.items() if k.lower() not in skip_headers}
    params = {k: v for k, v in request.query_params.items() if k not in ("url", "token")}

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=params,
                content=body,
            )
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Upstream timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {e}")

    content_type = resp.headers.get("content-type", "")
    content = resp.content

    if "text/html" in content_type:
        content = rewrite_html(content, str(resp.url))
    elif "javascript" in content_type or "ecmascript" in content_type:
        try:
            content = rewrite_js(content.decode("utf-8", errors="replace"), str(resp.url)).encode("utf-8", errors="replace")
        except Exception:
            pass
    elif "text/css" in content_type:
        content = rewrite_css(content, str(resp.url))

    skip_resp = {"transfer-encoding", "content-encoding", "content-length",
                 "content-security-policy", "x-frame-options", "strict-transport-security"}
    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in skip_resp}
    resp_headers.update(RATE_LIMIT_HEADER)

    return Response(content=content, status_code=resp.status_code, headers=resp_headers)
