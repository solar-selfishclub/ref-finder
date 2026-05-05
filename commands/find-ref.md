---
name: find-ref
description: 의도/기획 텍스트로 Pinterest + filmvibes.io에서 레퍼런스 후보 5장을 수집해 로컬 HTML 갤러리로 출력
---

# /find-ref

AI 영상 크리에이터를 위한 레퍼런스 자동 수집 커맨드.

## 사용법

```
/find-ref "자연주의 화장품, 미니멀, 30대 여성"
/find-ref --more                              # 같은 의도로 추가 5장
/find-ref --refine "더 어두운 톤으로"           # 직전 결과를 기반으로 좁혀서 5장
/find-ref --project "ad-cosmetic-spring"       # 프로젝트 폴더 지정
```

## 입력 형식 (자유 텍스트, 자동 판별)

| 상황 | 형식 |
|---|---|
| 기획 단계 | (a) 한 줄 키워드: `"자연주의 화장품, 미니멀, 30대 여성"` |
| 기획 단계 | (b) 의뢰서 전체 텍스트 붙여넣기 |
| 본격 이미지 제작 | (c) 컷별 스토리보드: `씬1: ___ / 씬2: ___` |

## 흐름

1. 입력 텍스트를 분석 → 검색 쿼리 추출 (LLM)
2. MCP `ref-finder` 서버에 쿼리 전달
3. Pinterest + filmvibes.io 어댑터 병렬 호출 → 각각 후보 수집
4. 5장으로 간추림 (출처 균형 + 다양성)
5. `~/refs/<프로젝트명>/<YYYYMMDD-HHMM>/` 폴더 생성
6. 이미지 다운로드 + `index.html` 생성 + `meta.json` 기록
7. 사용자에게 폴더 경로 + index.html 경로 응답

## 출력 위치

```
~/refs/<프로젝트명>/<YYYYMMDD-HHMM>/
├── images/
│   ├── 001-pinterest-<hash>.jpg
│   └── 002-filmvibes-<hash>.jpg
├── index.html      ← 더블클릭으로 갤러리 열기 (별표 토글, 출처 링크)
└── meta.json       ← 출처 URL, 검색 쿼리, 태그
```

## 사용자 워크플로우

1. `/find-ref "..."` → 5장 받음
2. `index.html` 열어서 검토 → 마음에 드는 것 별표
3. 부족하면 `/find-ref --more` 또는 `/find-ref --refine "..."`
4. 별표 표시한 것은 다음 부품(프롬프트 생성기)의 입력이 됨

## 환경 설정

`.env`에 다음 키 필요:
- `PINTEREST_ACCESS_TOKEN`: Pinterest 개발자 콘솔에서 발급
- `REFS_OUTPUT_DIR`: 기본 `~/refs` (선택)

filmvibes.io는 공개 페이지 스크레이핑이라 API 키 불필요 (robots.txt 준수).
