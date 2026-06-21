from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import Response
import httpx
import os

app = FastAPI(title="Web Proxy")

AUTH_TOKEN = os.environ.get("PROXY_TOKEN", "")

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

    skip_headers = {"host", "x-proxy-token", "content-length"}
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

    skip_resp_headers = {"transfer-encoding", "content-encoding", "content-length"}
    resp_headers = {
        k: v for k, v in resp.headers.items()
        if k.lower() not in skip_resp_headers
    }

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=resp_headers,
    )
