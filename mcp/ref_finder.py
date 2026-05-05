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
TMDB_KEY = os.getenv("TMDB_API_KEY", "").strip()

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


class TMDBAdapter:
    """TMDB API: 영화 제목 → 영화 ID → 그 영화의 backdrops/stills.
    https://developer.themoviedb.org/reference/

    사용 흐름:
      1) Claude(또는 사용자)가 장면 묘사를 영화 제목 후보 5~10개로 변환
      2) 각 영화를 TMDB에서 검색 → 영화 ID
      3) 영화 ID로 /movie/{id}/images → backdrops 가져오기
      4) 영화당 1~2장씩 추려서 모음
    """
    BASE = "https://api.themoviedb.org/3"
    IMG_BASE = "https://image.tmdb.org/t/p/w1280"

    def __init__(self, key: str):
        self.key = key

    def _get(self, client: httpx.Client, path: str, params: dict | None = None) -> dict:
        p = {"api_key": self.key}
        if params:
            p.update(params)
        r = client.get(f"{self.BASE}{path}", params=p)
        if r.status_code != 200:
            print(f"[tmdb] {path} {r.status_code}: {r.text[:160]}", file=sys.stderr)
            return {}
        return r.json()

    def _find_movie(self, client: httpx.Client, title: str) -> dict | None:
        # 영화 → TV 순으로 시도. 둘 다 같은 endpoint 패턴.
        for kind in ("movie", "tv"):
            data = self._get(client, f"/search/{kind}", {"query": title, "language": "en-US"})
            results = data.get("results", [])
            if results:
                top = results[0]
                top["_kind"] = kind
                return top
        return None

    def fetch_stills_by_titles(self, titles: list[str], per_movie: int = 2,
                               total_limit: int = 10) -> list[RefItem]:
        if not self.key or not titles:
            return []
        items: list[RefItem] = []
        try:
            with httpx.Client(timeout=15.0) as client:
                for title in titles:
                    if len(items) >= total_limit:
                        break
                    movie = self._find_movie(client, title)
                    if not movie:
                        print(f"[tmdb] not found: {title}", file=sys.stderr)
                        continue
                    kind = movie.get("_kind", "movie")
                    mid = movie.get("id")
                    display_title = (movie.get("title") or movie.get("name") or title)
                    year = (movie.get("release_date") or movie.get("first_air_date") or "")[:4]

                    images = self._get(client, f"/{kind}/{mid}/images",
                                       {"include_image_language": "en,null"})
                    backdrops = images.get("backdrops") or []
                    # 평점·해상도 정렬
                    backdrops.sort(
                        key=lambda b: (b.get("vote_average", 0), b.get("width", 0)),
                        reverse=True,
                    )
                    taken = 0
                    for bd in backdrops:
                        if taken >= per_movie or len(items) >= total_limit:
                            break
                        path = bd.get("file_path")
                        if not path:
                            continue
                        items.append(RefItem(
                            source="tmdb",
                            image_url=f"{self.IMG_BASE}{path}",
                            page_url=f"https://www.themoviedb.org/{kind}/{mid}",
                            title=f"{display_title}{' (' + year + ')' if year else ''}",
                            tags=[display_title, kind],
                        ))
                        taken += 1
        except httpx.HTTPError as e:
            print(f"[tmdb] error: {e}", file=sys.stderr)
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


def write_gallery(out_dir: Path, query: str, saved: list[dict], note: str = "") -> None:
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
    note_html = ""
    if note:
        note_html = (
            f'<div style="background:#1f2a1f;border-left:3px solid #6ec46e;'
            f'padding:10px 14px;margin:12px 0;border-radius:6px;font-size:13px;color:#c8e6c8">'
            f'<strong>✓ 검수 통과:</strong> {note}</div>'
        )
    html = (template
            .replace("{{QUERY}}", query)
            .replace("{{TIMESTAMP}}", datetime.now().strftime("%Y-%m-%d %H:%M"))
            .replace("{{CARDS}}", "\n".join(cards_html))
            .replace("{{NOTE}}", note_html))
    (out_dir / "index.html").write_text(html, encoding="utf-8")


# ---------- MCP tool ----------

@mcp.tool()
def find_references(
    query: str = "",
    project: str = "default",
    limit: int = 5,
    titles: str = "",
) -> dict:
    """
    의도/기획 쿼리로 레퍼런스 수집. 로컬 폴더에 이미지 + index.html + meta.json.

    두 가지 모드 (혼합 가능):
      1) 키워드 모드: query="cinematic asian supermarket" → Pexels/Pixabay 검색
      2) 영화 모드: titles="Parasite,Minari,The Farewell" → TMDB에서 그 영화들의 스틸

    영화 모드는 시네마틱 톤이 핵심일 때 사용. Claude가 사용자 장면 묘사를 영화
    후보로 변환해서 titles에 넣는 흐름이 권장.

    Args:
        query: 자유 텍스트 키워드 (Pexels/Pixabay 용). 영문 권장.
        project: 프로젝트 폴더 이름.
        limit: 총 결과 수 상한.
        titles: 콤마로 구분한 영화·드라마 제목 (TMDB 용). 영문 또는 원어 모두 가능.

    Returns:
        {"folder": str, "html": str, "count": int, "items": [...]}
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = REFS_DIR / project / timestamp

    pexels = PexelsAdapter(PEXELS_KEY)
    pixabay = PixabayAdapter(PIXABAY_KEY)
    tmdb = TMDBAdapter(TMDB_KEY)

    pool: list[RefItem] = []

    # TMDB 모드: titles 받으면 영화 스틸 우선
    title_list = [t.strip() for t in titles.split(",") if t.strip()] if titles else []
    if title_list:
        pool.extend(tmdb.fetch_stills_by_titles(title_list, per_movie=2, total_limit=limit * 2))

    # 키워드 모드: query 있으면 Pexels/Pixabay
    if query:
        per_source = max(2, limit)
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


@mcp.tool()
def curate_gallery(
    folder: str,
    keep: str,
    note: str = "",
) -> dict:
    """
    기존 갤러리에서 톤 일치하는 항목만 남기고 나머지는 _rejected/로 이동.
    Claude가 다운로드된 이미지들을 검수한 후 호출.

    Args:
        folder: 갤러리 폴더 절대 경로 (find_references 결과의 'folder')
        keep: 남길 항목의 파일명 prefix를 콤마로 (예: "001,005,007")
              또는 풀 파일명. prefix 매칭 지원.
        note: 갤러리 상단에 표시할 검수 메모 (예: "비 우산 야경 톤 일치")

    Returns:
        {"folder", "html", "kept", "removed", "kept_items"}
    """
    folder_path = Path(folder).expanduser()
    meta_path = folder_path / "meta.json"
    if not meta_path.exists():
        return {"error": f"meta.json not found in {folder_path}"}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))

    keep_set = {k.strip() for k in keep.split(",") if k.strip()}

    kept: list[dict] = []
    removed: list[dict] = []
    for item in meta.get("items", []):
        fn = item["filename"]
        matched = any(fn.startswith(k) or fn == k for k in keep_set)
        if matched:
            kept.append(item)
        else:
            removed.append(item)

    # 거절된 이미지는 _rejected/ 로 이동 (보존, 나중에 검토 가능)
    rejected_dir = folder_path / "_rejected"
    rejected_dir.mkdir(exist_ok=True)
    for item in removed:
        src = folder_path / "images" / item["filename"]
        if src.exists():
            try:
                src.rename(rejected_dir / item["filename"])
            except OSError:
                pass

    # meta 갱신
    meta["items"] = kept
    meta["curate_note"] = note
    meta["curated_at"] = datetime.now().strftime("%Y%m%d-%H%M%S")
    meta["removed_count"] = len(removed)
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    write_gallery(folder_path, meta.get("query", ""), kept, note=note)

    return {
        "folder": str(folder_path),
        "html": str(folder_path / "index.html"),
        "kept": len(kept),
        "removed": len(removed),
        "kept_items": [it["filename"] for it in kept],
    }


if __name__ == "__main__":
    mcp.run()
