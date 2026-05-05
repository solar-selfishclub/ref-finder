"""
ref-finder MCP server (v0.1 skeleton)

Pinterest + filmvibes.io 어댑터를 같은 인터페이스로 노출.
Claude Code가 /find-ref 커맨드로 호출.

설치 의존성:
    pip install mcp httpx beautifulsoup4 python-dotenv

환경 변수 (.env):
    PINTEREST_ACCESS_TOKEN
    REFS_OUTPUT_DIR  (기본: ~/refs)
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

REFS_DIR = Path(os.getenv("REFS_OUTPUT_DIR", str(Path.home() / "refs"))).expanduser()
PINTEREST_TOKEN = os.getenv("PINTEREST_ACCESS_TOKEN", "")

mcp = FastMCP("ref-finder")


# ---------- Common types ----------

@dataclass
class RefItem:
    source: str            # "pinterest" | "filmvibes"
    image_url: str         # 다운로드 대상
    page_url: str          # 원본 페이지 (출처 링크)
    title: str
    tags: list[str]


# ---------- Adapters ----------

class PinterestAdapter:
    """Pinterest API v5. 무료 토큰으로 검색·핀 메타 가능."""
    BASE = "https://api.pinterest.com/v5"

    def __init__(self, token: str):
        self.token = token

    def search(self, query: str, limit: int = 5) -> list[RefItem]:
        if not self.token:
            return []
        # Pinterest v5는 Standard Access 승인 앱만 검색 호출 가능.
        # 401(consumer type not supported) 등 권한 오류 시 조용히 빈 리스트.
        headers = {"Authorization": f"Bearer {self.token}"}
        params = {"query": query, "page_size": limit}
        try:
            with httpx.Client(timeout=10.0) as client:
                r = client.get(f"{self.BASE}/pins/search", params=params, headers=headers)
                if r.status_code != 200:
                    print(f"[pinterest] skipped ({r.status_code}): {r.text[:160]}", file=sys.stderr)
                    return []
                data = r.json()
        except httpx.HTTPError as e:
            print(f"[pinterest] error: {e}", file=sys.stderr)
            return []
        items = []
        for pin in data.get("items", [])[:limit]:
            media = (pin.get("media") or {}).get("images", {}).get("originals") or {}
            items.append(RefItem(
                source="pinterest",
                image_url=media.get("url", ""),
                page_url=f"https://www.pinterest.com/pin/{pin.get('id')}/",
                title=pin.get("title", "") or pin.get("description", "")[:80],
                tags=[],
            ))
        return [it for it in items if it.image_url]


class FilmVibesAdapter:
    """filmvibes.io: 검색 페이지(`/?query=...`)에서 결과 카드 추출.

    검색 결과 마크업: <a href="/video?...&hhash=..."><img src="./init-page-content/..."></a>
    robots.txt: /video/, /still/ 등은 차단되지만 루트 검색 페이지는 허용.
    """
    BASE = "https://filmvibes.io"

    def search(self, query: str, limit: int = 5) -> list[RefItem]:
        try:
            with httpx.Client(timeout=15.0, follow_redirects=True,
                              headers={"User-Agent": "Mozilla/5.0 (ref-finder/0.1)"}) as client:
                r = client.get(f"{self.BASE}/", params={"query": query})
                r.raise_for_status()
        except httpx.HTTPError:
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        items: list[RefItem] = []
        seen: set[str] = set()

        # 결과 = <a class="reference-video-wrapper" href="/video?..."><video poster="./init-page-content/..."></video></a>
        for a in soup.select("a.reference-video-wrapper, a"):
            href = (a.get("href") or "").strip()
            if "/video?" not in href and "/video/" not in href:
                continue
            video = a.find("video")
            poster = ""
            if video is not None:
                poster = (video.get("poster") or "").strip()
            if not poster:
                # 일부는 img 태그를 쓸 수도 있음
                img = a.find("img")
                if img:
                    poster = (img.get("data-src") or img.get("src") or "").strip()
            if not poster:
                continue

            # 상대 경로(./init-page-content/...) → 절대 URL
            if poster.startswith("./"):
                poster = self.BASE + poster[1:]
            elif poster.startswith("/"):
                poster = self.BASE + poster

            if poster in seen:
                continue
            seen.add(poster)

            page_url = href
            if page_url.startswith("/"):
                page_url = self.BASE + page_url

            items.append(RefItem(
                source="filmvibes",
                image_url=poster,
                page_url=page_url,
                title=query[:60],
                tags=[],
            ))
            if len(items) >= limit:
                break
        return items


# ---------- Output (HTML gallery) ----------

GALLERY_TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "gallery.html"


def slugify(s: str) -> str:
    s = re.sub(r"[^\w\s-]", "", s, flags=re.UNICODE).strip().lower()
    s = re.sub(r"[-\s]+", "-", s)
    return s[:60] or "untitled"


def download(items: Iterable[RefItem], out_dir: Path) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    images_dir = out_dir / "images"
    images_dir.mkdir(exist_ok=True)
    saved = []
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        for i, it in enumerate(items, 1):
            try:
                r = client.get(it.image_url)
                r.raise_for_status()
            except httpx.HTTPError:
                continue
            ext = ".jpg"
            ctype = r.headers.get("content-type", "")
            if "png" in ctype:
                ext = ".png"
            elif "webp" in ctype:
                ext = ".webp"
            fname = f"{i:03d}-{it.source}-{slugify(it.title) or 'ref'}{ext}"
            (images_dir / fname).write_bytes(r.content)
            saved.append({
                "filename": fname,
                "source": it.source,
                "page_url": it.page_url,
                "title": it.title,
                "tags": it.tags,
            })
    return saved


def write_gallery(out_dir: Path, query: str, saved: list[dict]) -> None:
    template = GALLERY_TEMPLATE_PATH.read_text(encoding="utf-8")
    cards_html = []
    for item in saved:
        cards_html.append(f"""
        <div class="card" data-id="{item['filename']}">
          <button class="star" aria-label="별표" onclick="toggleStar(this)">☆</button>
          <a href="{item['page_url']}" target="_blank">
            <img src="images/{item['filename']}" alt="{item['title']}" loading="lazy">
          </a>
          <div class="meta">
            <span class="source">{item['source']}</span>
            <span class="title">{item['title']}</span>
          </div>
        </div>
        """)
    html = (template
            .replace("{{QUERY}}", query)
            .replace("{{TIMESTAMP}}", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("{{CARDS}}", "\n".join(cards_html)))
    (out_dir / "index.html").write_text(html, encoding="utf-8")


# ---------- MCP tool ----------

@mcp.tool()
def find_references(
    query: str,
    project: str = "default",
    limit: int = 5,
) -> dict:
    """
    의도/기획 쿼리로 Pinterest + filmvibes.io에서 레퍼런스 후보 수집.
    로컬 폴더에 이미지 다운로드 + index.html 생성 + meta.json 기록.

    Args:
        query: 자유 텍스트 (키워드 / 의뢰서 / 스토리보드)
        project: 프로젝트 폴더 이름 (기본 default)
        limit: 출처별 후보 수 (기본 5)

    Returns:
        {"folder": str, "html": str, "count": int, "items": [...]}
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = REFS_DIR / project / timestamp

    pinterest = PinterestAdapter(PINTEREST_TOKEN)
    filmvibes = FilmVibesAdapter()

    pool: list[RefItem] = []
    pool.extend(pinterest.search(query, limit=limit))
    pool.extend(filmvibes.search(query, limit=limit))

    # 출처 균형: 한 출처가 모두 차지하지 않도록 인터리브
    by_source: dict[str, list[RefItem]] = {}
    for it in pool:
        by_source.setdefault(it.source, []).append(it)
    interleaved: list[RefItem] = []
    while sum(len(v) for v in by_source.values()) and len(interleaved) < limit:
        for src in list(by_source.keys()):
            if by_source[src]:
                interleaved.append(by_source[src].pop(0))
                if len(interleaved) >= limit:
                    break

    saved = download(interleaved, out_dir)
    write_gallery(out_dir, query, saved)

    meta = {
        "query": query,
        "project": project,
        "timestamp": timestamp,
        "items": saved,
    }
    (out_dir / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return {
        "folder": str(out_dir),
        "html": str(out_dir / "index.html"),
        "count": len(saved),
        "items": saved,
    }


if __name__ == "__main__":
    mcp.run()
