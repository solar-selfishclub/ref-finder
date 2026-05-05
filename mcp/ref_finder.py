"""
ref-finder MCP server (v0.1.1)

Pexels API + (선택) Pixabay API로 안정적인 레퍼런스 수집.
Claude Code가 /find-ref 커맨드 또는 자연어로 호출.

설치 의존성:
    pip install mcp httpx python-dotenv

환경 변수 (.env):
    PEXELS_API_KEY      (필수, https://www.pexels.com/api/ 에서 무료 발급)
    PIXABAY_API_KEY     (선택, https://pixabay.com/api/docs/ 에서 무료 발급)
    REFS_OUTPUT_DIR     (선택, 기본: ~/refs)
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv(Path(__file__).parent.parent / ".env")

REFS_DIR = Path(os.getenv("REFS_OUTPUT_DIR", str(Path.home() / "refs"))).expanduser()
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY", "").strip()

mcp = FastMCP("ref-finder")


# ---------- Common types ----------

@dataclass
class RefItem:
    source: str            # "pexels" | "pixabay"
    image_url: str         # 다운로드 대상
    page_url: str          # 원본 페이지 (출처 링크)
    title: str
    tags: list[str]


# ---------- Adapters ----------

class PexelsAdapter:
    """Pexels API: 사진 검색. 무료 키, 헤더 한 줄 인증.
    https://www.pexels.com/api/documentation/
    """
    BASE = "https://api.pexels.com/v1"

    def __init__(self, key: str):
        self.key = key

    def search(self, query: str, limit: int = 5) -> list[RefItem]:
        if not self.key:
            return []
        headers = {"Authorization": self.key}
        params = {"query": query, "per_page": str(limit), "orientation": "landscape"}
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(f"{self.BASE}/search", params=params, headers=headers)
                if r.status_code != 200:
                    print(f"[pexels] skipped ({r.status_code}): {r.text[:160]}", file=sys.stderr)
                    return []
                data = r.json()
        except httpx.HTTPError as e:
            print(f"[pexels] error: {e}", file=sys.stderr)
            return []
        items = []
        for photo in data.get("photos", [])[:limit]:
            src = photo.get("src") or {}
            image_url = src.get("large2x") or src.get("large") or src.get("original", "")
            if not image_url:
                continue
            items.append(RefItem(
                source="pexels",
                image_url=image_url,
                page_url=photo.get("url", ""),
                title=(photo.get("alt") or photo.get("photographer", ""))[:80],
                tags=[],
            ))
        return items


class PixabayAdapter:
    """Pixabay API: 사진 검색. 무료 키, query string 인증.
    https://pixabay.com/api/docs/
    """
    BASE = "https://pixabay.com/api/"

    def __init__(self, key: str):
        self.key = key

    def search(self, query: str, limit: int = 5) -> list[RefItem]:
        if not self.key:
            return []
        params = {
            "key": self.key,
            "q": query,
            "per_page": str(max(3, limit)),  # Pixabay 최소 3
            "image_type": "photo",
            "orientation": "horizontal",
            "safesearch": "true",
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                r = client.get(self.BASE, params=params)
                if r.status_code != 200:
                    print(f"[pixabay] skipped ({r.status_code}): {r.text[:160]}", file=sys.stderr)
                    return []
                data = r.json()
        except httpx.HTTPError as e:
            print(f"[pixabay] error: {e}", file=sys.stderr)
            return []
        items = []
        for hit in data.get("hits", [])[:limit]:
            image_url = hit.get("largeImageURL") or hit.get("webformatURL", "")
            if not image_url:
                continue
            items.append(RefItem(
                source="pixabay",
                image_url=image_url,
                page_url=hit.get("pageURL", ""),
                title=(hit.get("tags") or "pixabay")[:80],
                tags=[t.strip() for t in (hit.get("tags") or "").split(",") if t.strip()],
            ))
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
    의도/기획 쿼리로 Pexels + Pixabay에서 레퍼런스 후보 수집.
    로컬 폴더에 이미지 다운로드 + index.html 생성 + meta.json 기록.

    Args:
        query: 자유 텍스트 (영문 키워드가 가장 결과 좋음)
        project: 프로젝트 폴더 이름 (기본 default)
        limit: 총 결과 수 상한 (기본 5)

    Returns:
        {"folder": str, "html": str, "count": int, "items": [...]}
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = REFS_DIR / project / timestamp

    pexels = PexelsAdapter(PEXELS_KEY)
    pixabay = PixabayAdapter(PIXABAY_KEY)

    # 각 출처에서 limit만큼 받아와서 인터리브 → 최종 limit개로 잘라냄
    per_source = max(2, limit)
    pool: list[RefItem] = []
    pool.extend(pexels.search(query, limit=per_source))
    pool.extend(pixabay.search(query, limit=per_source))

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
