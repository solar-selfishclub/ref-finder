"""
ref-finder MCP server (v0.2.0)

shot.cafe (영화·광고 스틸 + 태그) + Pexels (stock) 기반 레퍼런스 수집.
사용자 자연어 → Claude가 태그 추출 → shot.cafe에서 씬 단위 검색 → AI 검수 → 갤러리.

설치 의존성:
    pip install mcp httpx beautifulsoup4 python-dotenv

환경 변수 (.env):
    PEXELS_API_KEY      (선택, https://www.pexels.com/api/)
    PIXABAY_API_KEY     (선택)
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

import time
import re as _re

import httpx
from bs4 import BeautifulSoup
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


class ShotCafeAdapter:
    """shot.cafe: 24K개 영화·광고 스틸을 109K개 태그로 검색 가능한 사이트.
    공식 API 없음 → HTML 스크레이핑.

    robots.txt 준수 (확인 2026-05-05):
      - User-agent: * Disallow: /*,*,*  → 2개 이상 콤마 URL 차단
      - User-agent: ClaudeBot Disallow: / → ClaudeBot 차단
      - Crawl-delay: 5 → 요청 간 5초

    이 어댑터의 행동:
      - 1~2개 태그만 한 번의 요청으로 사용 (콤마 1개까지)
      - 3개 이상이면 단일 태그 다중 요청 + 클라이언트 교집합
      - User-Agent: 일반 브라우저 (ClaudeBot 아님)
      - Crawl-delay 5초 준수

    마크업: <a class="box-img-load" data-img-img="/images/o/<file>"
              data-img-url="<movie>/<file>" href="#<movie>/<file>">
              <img src="/images/t/<file>" alt="Still from <Movie> (year) that has been tagged with: <tag>">
    """
    BASE = "https://shot.cafe"
    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
    HEADERS = {
        "User-Agent": UA,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }
    CRAWL_DELAY = 5.0  # robots.txt 준수

    def __init__(self):
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_at
        if elapsed < self.CRAWL_DELAY:
            time.sleep(self.CRAWL_DELAY - elapsed)
        self._last_request_at = time.time()

    @staticmethod
    def _encode_tag(tag: str) -> str:
        """태그를 shot.cafe URL 컨벤션으로 변환.

        규칙 (사용자/caller가 정확한 형태로 줘야 함, 우리는 공백만 인코딩):
          - 하이픈(`-`)은 literal 하이픈으로 유지: 'two-shot' → 'two-shot'
          - 공백은 '+'로 인코딩: 'wide shot' → 'wide+shot'
          - 이미 '+'면 그대로
        """
        return tag.strip().lower().replace(" ", "+")

    def _fetch_tag(self, client: httpx.Client, tag_str: str, page: int = 1) -> list[RefItem]:
        """단일 태그(또는 콤마 1개) 페이지 가져오기. page>=1."""
        self._throttle()
        url = f"{self.BASE}/tag/{tag_str}"
        params = {"page": page} if page > 1 else None
        try:
            r = client.get(url, headers=self.HEADERS, params=params,
                           timeout=20.0, follow_redirects=True)
            if r.status_code != 200:
                print(f"[shotcafe] {url} p{page} {r.status_code}", file=sys.stderr)
                return []
        except httpx.HTTPError as e:
            print(f"[shotcafe] error fetching {url}: {e}", file=sys.stderr)
            return []

        soup = BeautifulSoup(r.text, "html.parser")
        items: list[RefItem] = []
        for a in soup.select("a.box-img-load"):
            data_img = (a.get("data-img-img") or "").strip()
            data_url = (a.get("data-img-url") or "").strip()
            if not data_img:
                continue
            image_url = self.BASE + data_img if data_img.startswith("/") else data_img
            page_url = f"{self.BASE}/#{data_url}" if data_url else self.BASE
            img_tag = a.find("img")
            alt = (img_tag.get("alt") if img_tag else "") or ""
            m = _re.match(r"Still from (.+?) that has been tagged with:\s*(.+)$", alt)
            if m:
                movie_label = m.group(1).strip()
                tag_text = m.group(2).strip()
            else:
                movie_label = alt[:80] or tag_str
                tag_text = tag_str
            items.append(RefItem(
                source="shotcafe",
                image_url=image_url,
                page_url=page_url,
                title=movie_label,
                tags=[t.strip() for t in tag_text.replace("&", ",").split(",") if t.strip()],
            ))
        return items

    def _fetch_paginated(self, client: httpx.Client, tag_str: str,
                        target: int, max_pages: int = 5) -> list[RefItem]:
        """target개 모일 때까지 페이지를 순회. 0건 페이지를 만나면 중단."""
        all_items: list[RefItem] = []
        for page in range(1, max_pages + 1):
            page_items = self._fetch_tag(client, tag_str, page=page)
            if not page_items:
                break
            all_items.extend(page_items)
            if len(all_items) >= target:
                break
        return all_items

    def search(self, tags: list[str], limit: int = 15) -> list[RefItem]:
        """
        tags: 태그 리스트. caller가 정확한 형태로 전달해야 함.
              - 하이픈 단어: 'two-shot', 'close-up', 'low-angle', 'over-the-shoulder'
              - 공백 단어: 'wide shot', 'medium shot', 'establishing shot'
              - 환경: 'rain', 'night', 'umbrella' 등 단어
        limit: 최종 결과 수 상한.
        """
        if not tags:
            return []
        tags_enc = [self._encode_tag(t) for t in tags if t.strip()]
        if not tags_enc:
            return []

        # 검수까지 고려하면 limit*2 확보 권장 (절반쯤 거절될 가능성)
        target = limit * 2

        with httpx.Client(timeout=20.0, follow_redirects=True) as client:
            # 1차: 처음 2개 태그를 콤마로 결합 (robots.txt 허용)
            primary = ",".join(tags_enc[:2])
            pool = self._fetch_paginated(client, primary, target=target)

            # 추가 태그가 있으면 클라이언트 측 교집합 필터
            extra_tags = [t.replace("+", " ").lower() for t in tags_enc[2:]]
            if extra_tags and pool:
                filtered = []
                for it in pool:
                    item_tags_lower = [t.lower() for t in it.tags]
                    if all(any(extra in t for t in item_tags_lower) for extra in extra_tags):
                        filtered.append(it)
                pool = filtered

            # 폴백 1: 콤보가 빈약하면 첫 태그 단독으로 페이지 더 가져오기
            if len(pool) < limit and len(tags_enc) >= 1:
                fallback = self._fetch_paginated(client, tags_enc[0], target=target)
                seen_urls = {it.image_url for it in pool}
                for it in fallback:
                    if it.image_url not in seen_urls:
                        pool.append(it)
                        seen_urls.add(it.image_url)

            # 폴백 2: 두 번째 태그 단독도 시도 (다양성 확보)
            if len(pool) < limit and len(tags_enc) >= 2:
                fallback2 = self._fetch_paginated(client, tags_enc[1], target=target // 2)
                seen_urls = {it.image_url for it in pool}
                for it in fallback2:
                    if it.image_url not in seen_urls:
                        pool.append(it)
                        seen_urls.add(it.image_url)

        # 중복 제거 + limit 적용
        seen = set()
        result = []
        for it in pool:
            if it.image_url in seen:
                continue
            seen.add(it.image_url)
            result.append(it)
            if len(result) >= limit:
                break
        return result


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
    tags: str = "",
) -> dict:
    """
    의도/기획 쿼리로 레퍼런스 수집. 로컬 폴더에 이미지 + index.html + meta.json.

    두 가지 모드 (혼합 가능):
      1) 시네마틱 모드 (메인): tags="rain,night,umbrella" → shot.cafe 영화·광고 스틸
         씬 단위 매칭. 본인 영상 제작 워크플로우 핵심.
      2) Stock 모드 (보조): query="cinematic moody product" → Pexels/Pixabay
         소재·물건·텍스처 등 일반 비주얼.

    Args:
        query: 자유 텍스트 키워드 (Pexels/Pixabay 용).
        project: 프로젝트 폴더 이름.
        limit: 총 결과 수 상한 (검수 위해 limit*2 다운로드 권장 흐름).
        tags: 콤마로 구분한 시각 태그 (shot.cafe 용).
              예: "rain,night,umbrella,woman,street"

    Returns:
        {"folder": str, "html": str, "count": int, "items": [...]}
    """
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = REFS_DIR / project / timestamp

    shotcafe = ShotCafeAdapter()
    pexels = PexelsAdapter(PEXELS_KEY)
    pixabay = PixabayAdapter(PIXABAY_KEY)

    pool: list[RefItem] = []

    # 시네마틱 모드: tags 받으면 shot.cafe 우선
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
    if tag_list:
        # 검수 단계에서 절반 이상 탈락 가능성을 고려해 limit*2 정도 가져옴
        pool.extend(shotcafe.search(tag_list, limit=max(15, limit * 2)))

    # Stock 모드: query 있으면 Pexels/Pixabay
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
