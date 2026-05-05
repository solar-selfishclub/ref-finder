"""ref-finder CLI

사용 예:
    py find_ref.py "자연주의 화장품 미니멀 30대 여성"
    py find_ref.py --project ad-spring "자연주의 화장품 미니멀"
    py find_ref.py --limit 10 "어두운 톤 시네마틱"
    py find_ref.py --open "minimal cosmetic"   (생성 후 갤러리 자동 열기)
"""
import argparse
import os
import sys
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "mcp"))
import ref_finder

def main():
    p = argparse.ArgumentParser(description="ref-finder: 의도/기획 → 레퍼런스 갤러리")
    p.add_argument("query", help="자유 텍스트 (키워드/의뢰서/스토리보드)")
    p.add_argument("--project", default="default", help="프로젝트 폴더 이름 (기본: default)")
    p.add_argument("--limit", type=int, default=5, help="후보 수 (기본: 5)")
    p.add_argument("--open", action="store_true", help="생성 후 갤러리 자동으로 브라우저에서 열기")
    args = p.parse_args()

    # Windows 콘솔에서도 한글이 안전하게 출력되도록
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    fn = getattr(ref_finder.find_references, "fn", ref_finder.find_references)
    print(f"[search] {args.query!r}")
    result = fn(query=args.query, project=args.project, limit=args.limit)

    print(f"\n[done] {result['count']}장 수집 완료")
    print(f"  folder : {result['folder']}")
    print(f"  gallery: {result['html']}")

    sources = {}
    for it in result["items"]:
        sources[it["source"]] = sources.get(it["source"], 0) + 1
    if sources:
        print(f"  source : {', '.join(f'{k}={v}' for k, v in sources.items())}")

    if args.open and result["count"] > 0:
        webbrowser.open(f"file:///{result['html'].replace(os.sep, '/')}")
        print(f"\n[open] 갤러리를 브라우저에서 열었습니다.")
    elif result["count"] == 0:
        print("\n[warn] 결과 없음. 쿼리를 더 영어로 바꿔보거나 키워드를 줄여보세요.")
        sys.exit(1)


if __name__ == "__main__":
    main()
