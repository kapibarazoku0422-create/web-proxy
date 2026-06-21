from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse, quote
import os

app = FastAPI(title="Web Proxy")

AUTH_TOKEN = os.environ.get("PROXY_TOKEN", "")

def proxy_url(url: str, base_url: str = "") -> str:
    """URLをプロキシ経由に変換"""
    if not url or url.startswith(("data:", "javascript:", "#", "mailto:")):
        return url
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith(("http://", "https://")):
        if base_url:
            url = urljoin(base_url, url)
        else:
            return url
    return f"/proxy?url={quote(url, safe='')}"

def rewrite_html(content: bytes, base_url: str) -> bytes:
    """HTMLのリンクを全部プロキシ経由に書き換え"""
    soup = BeautifulSoup(content, "html.parser")

    # <a href>
    for tag in soup.find_all("a", href=True):
        tag["href"] = proxy_url(tag["href"], base_url)

    # <form action>
    for tag in soup.find_all("form", action=True):
        tag["action"] = proxy_url(tag["action"], base_url)

    # <link href> (CSS等)
    for tag in soup.find_all("link", href=True):
        tag["href"] = proxy_url(tag["href"], base_url)

    # <script src>
    for tag in soup.find_all("script", src=True):
        tag["src"] = proxy_url(tag["src"], base_url)

    # <img src>
    for tag in soup.find_all("img", src=True):
        tag["src"] = proxy_url(tag["src"], base_url)

    # <img srcset>
    for tag in soup.find_all("img", srcset=True):
        new_srcset = []
        for part in tag["srcset"].split(","):
            part = part.strip()
            if not part:
                continue
            pieces = part.split()
            pieces[0] = proxy_url(pieces[0], base_url)
            new_srcset.append(" ".join(pieces))
        tag["srcset"] = ", ".join(new_srcset)

    # <source src/srcset>
    for tag in soup.find_all("source"):
        if tag.get("src"):
            tag["src"] = proxy_url(tag["src"], base_url)
        if tag.get("srcset"):
            new_srcset = []
            for part in tag["srcset"].split(","):
                part = part.strip()
                if not part:
                    continue
                pieces = part.split()
                pieces[0] = proxy_url(pieces[0], base_url)
                new_srcset.append(" ".join(pieces))
            tag["srcset"] = ", ".join(new_srcset)

    # <base href> を削除（相対パス解決の邪魔になる）
    for tag in soup.find_all("base"):
        tag.decompose()

    return str(soup).encode("utf-8", errors="replace")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.api_route("/proxy", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def proxy(request: Request):
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
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in skip_headers
    }

    params = {
        k: v for k, v in request.query_params.items()
        if k not in ("url", "token")
    }

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
        raise HTTPException(status_code=504, detail="Target server timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {str(e)}")

    content_type = resp.headers.get("content-type", "")
    content = resp.content

    # HTMLのみ書き換え
    if "text/html" in content_type:
        content = rewrite_html(content, str(resp.url))

    skip_resp_headers = {"transfer-encoding", "content-encoding", "content-length", "content-security-policy"}
    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in skip_resp_headers
    }

    return Response(
        content=content,
        status_code=resp.status_code,
        headers=resp_headers,
    )
