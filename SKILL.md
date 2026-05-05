---
name: ref-finder
description: AI 영상 크리에이터를 위한 레퍼런스 자동 수집 + AI 검수 스킬. 사용자가 장면을 묘사하면 (1) Claude가 시각 태그를 추출해 shot.cafe(영화·광고 스틸 24K장, 109K 태그)에서 씬 단위로 검색하고, (2) 다운로드된 이미지를 직접 보고 사용자 의도와 맞는지 검수하여 통과한 것만 갤러리에 남깁니다. (3) stock 비주얼은 Pexels/Pixabay 보조. 트리거 — "레퍼런스 찾아줘", "광고 컨셉 자료", "무드보드", "영상 레퍼런스", "스틸 모아줘", "moodboard", "reference", "시네마틱 톤", "이런 장면". 영상 제작 전에 시각 레퍼런스가 필요할 때 발동.
---

# ref-finder Skill

영상 크리에이터의 OS 첫 부품. 한 컷 레퍼런스 찾는 데 30분 → 5분.
**v0.2.0부터 shot.cafe 기반** — 영화·광고 스틸 24K장을 109K개 태그로 씬 단위 검색.

---

## 핵심 흐름 (5단계)

사용자가 장면을 묘사하면 **반드시 다음 5단계를 거치세요**. 검수 단계 생략 금지.

### Step 1 — 태그 추출

사용자 묘사를 듣고 **시각 태그 3~6개**를 영문으로 추출. 추상적 감정·톤보다는 **눈에 보이는 시각 요소** 위주.

**좋은 추출 예** (사용자: "밤에 비 오는 거리, 우산 쓴 외로운 여인 뒷모습"):
- ✅ `rain, night, umbrella, woman, street`
- ❌ `lonely, melancholic, atmospheric` (shot.cafe는 추상 태그 약함)

**자주 쓰이는 태그 카테고리**:
- 환경: `rain, snow, fog, night, day, sunset, dawn, beach, forest, desert, city, street, alley, tunnel, bridge`
- 인물: `woman, man, child, couple, crowd, silhouette, back+turned`
- 빛/색: `neon, candle, fire, sunlight, moonlight, blue, red, golden+hour`
- 도구: `umbrella, car+interior, train, gun, mirror, window`
- 분위기: `silhouette, reflection, shadow`

확실하지 않은 태그는 단일로 시도해서 결과 확인 후 조합.

### Step 2 — 후보 다운로드 (15~20장)

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --project <프로젝트명> --limit 20 `
   --tags "<tag1>,<tag2>,<tag3>"
```

- `--limit 20` 정도가 적절 (검수 후 절반 이상 통과 가능, 부족하면 재호출)
- shot.cafe **robots.txt 준수**: 어댑터가 자동으로 1~2개 태그 콤마 결합 + 추가 태그는 클라이언트 측 교집합. Crawl-delay 5초 자동 적용.
- **이 단계에서는 `--open` 쓰지 말 것** (검수 전 갤러리는 사용자에게 보여주지 않음)

출력의 `folder` 경로 기록.

### Step 3 — 검수 (Read tool로 이미지 확인)

다운로드된 이미지들을 하나씩 Read tool로 보면서 사용자 의도와 매칭 평가.

**평가 기준**:
- 핵심 시각 요소 모두 또는 대부분 일치 → ✅ 통과
- 톤만 강하게 일치 (요소 일부만) → ✅ 통과 (톤 reference 가치)
- 명확히 부정 조건 위반 (예: 사용자 "공포 아님" + 결과는 호러 씬) → ❌ 거절
- 환경 완전 불일치 (예: 사용자 "야경" + 결과는 정글) → ❌ 거절

각 이미지 한 줄 판단을 사용자에게 보여줘 투명성 확보.

### Step 4 — curate (검수 결과 적용)

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --curate "<Step 2 folder>" `
   --keep "001,003,007,012,014,016,018" `
   --note "20장 중 7장 통과. 비·야경·우산 톤 일치." `
   --open
```

거절된 이미지는 자동으로 `_rejected/` 하위 폴더로 이동 (보존).

### Step 5 — 사용자에게 보고

- 후보 N장 → 통과 M장 (통과율 %)
- 가장 강한 매칭 영화 1~2개 강조
- 거절 사유 요약
- 갤러리는 자동으로 본인 브라우저에 열림

---

## 트리거별 분기

### A) 시네마틱 톤 (위 5단계 — 메인)
키워드: 시네마틱, 영화 같은, 드라마 톤, 인물·장면 묘사 → shot.cafe

### B) 단순 stock 비주얼 (검수 생략 가능)
키워드: 텍스처, 매크로, 추상, 제품, 음식 정물 → Pexels/Pixabay
```powershell
py find_ref.py --open --project <프로젝트> "<영문 키워드>"
```

### C) 혼합
```powershell
py find_ref.py --project <프로젝트> --limit 20 --tags "..." "<영문 키워드>"
```

---

## 첫 실행 점검

`~/.claude/skills/ref-finder/.env`가 없으면 자동 설치:

```powershell
if (-not (Test-Path "$HOME\.claude\skills\ref-finder\.env")) {
    powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\install.ps1"
}
```

shot.cafe는 **API 키 불필요** (공개 사이트). Pexels/Pixabay는 선택.

---

## 후속 액션 가이드

### "결과가 부족하다"
- 태그 수 줄이기 (3개 → 2개) — 더 많은 결과
- 다른 태그 시도 — 사용자 묘사를 다른 각도로 추출

### "더 어두운/밝은/특정 분위기"
- 태그 갈아끼우기 (`night` 추가, `day` 제거 등)
- `silhouette`, `reflection` 같은 분위기 태그 추가

### "특정 영화의 다른 씬"
- shot.cafe는 영화별 페이지도 있음 (예: `/movie/<slug>`) — v0.2.1에서 지원 예정

---

## 주의사항

- **shot.cafe robots.txt 준수**: 어댑터가 자동으로 5초 crawl-delay + 1~2개 태그 결합 제한 처리. 코드 수정 시 이 규칙 깨지 말 것.
- **태그 결합은 영문 콤마, 공백은 +로** (예: `car interior` → `car+interior`)
- **사용자 한국어 묘사 → Claude가 영문 태그로 변환** 필수
- **검수 단계 생략 = 사용자에게 톤 안 맞는 30~40% 이미지 떠넘기기**. 그러면 안 됨.

---

## 다음 부품 (로드맵)

- 이미지 프롬프트 생성기 (별표 레퍼런스 → 나노바나나 프롬프트)
- 영상 직전 AI 1차 검수기 (크레딧 절감)
- 영상 프롬프트 생성기 (Kling)
