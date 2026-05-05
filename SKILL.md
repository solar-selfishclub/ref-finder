---
name: ref-finder
description: AI 영상 크리에이터를 위한 레퍼런스 자동 수집 + AI 검수 스킬. 사용자가 장면을 묘사하면 (1) Claude가 어울리는 영화·드라마를 떠올려 TMDB에서 스틸을 가져오고, (2) 다운로드된 이미지들을 직접 보고 사용자 의도와 맞는지 검수하여 통과한 것만 갤러리에 남깁니다. (3) 시네마틱이 아닌 단순 비주얼은 Pexels/Pixabay 검색. 트리거 — "레퍼런스 찾아줘", "광고 컨셉용 자료", "무드보드", "영상 레퍼런스", "스틸 모아줘", "moodboard", "reference", "시네마틱 톤", "이런 장면". 영상·이미지 제작 전에 시각 레퍼런스가 필요할 때 발동.
---

# ref-finder Skill

영상 크리에이터의 OS 첫 부품. 한 컷 레퍼런스 찾는 데 30분 → 5분.
**v0.1.3부터 AI 검수 단계 빌트인** — 톤 안 맞는 후보는 자동 제거.

---

## 핵심 흐름 (5단계)

사용자가 장면을 묘사하면 **반드시 다음 5단계를 거치세요**. 검수 단계 생략 금지.

### Step 1 — 영화 후보 큐레이션

사용자 묘사를 듣고 **그 장면·톤이 실제로 있을 법한 영화·드라마 6~10개**를 떠올림. 단순히 분위기 비슷한 게 아니라 **묘사한 씬이 영화 안에 있을 가능성이 높은 작품**으로 골라야 함.

**좋은 큐레이션 예** (사용자: "밤에 비 오는 거리, 우산 쓴 외로운 여인"):
- ✅ Atonement, Match Point, Joker(2019), Carol, 헤어질 결심, Drive, Memento, The Worst Person in the World
- ❌ Past Lives, Lost in Translation (낮·실내 위주)

**나쁜 큐레이션 = 톤만 비슷한 작품**: 사용자 묘사한 씬이 그 영화에 없으면 TMDB 검수에서 다 떨어짐. 버려진 다운로드는 시간 낭비.

### Step 2 — 후보 다운로드 (15~20장)

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --project <프로젝트명> --limit 20 `
   --titles "<영화1>,<영화2>,...,<영화6~10>"
```

- `--limit 20` 또는 더 큼 (검수에서 절반 이상 떨어질 가능성 큼)
- 영화당 2장씩 가져옴
- **이 단계에서는 `--open` 쓰지 말 것** (검수 전 갤러리는 사용자에게 보여주지 않음)

출력 결과의 `folder` 경로 기록 — 다음 단계에서 사용.

### Step 3 — 검수 (Read tool로 이미지 확인)

다운로드된 이미지들을 하나씩 Read tool로 보면서 사용자 의도와 매칭 평가.

```
폴더: <Step 2 folder>/images/
파일: 001-tmdb-*.jpg, 002-tmdb-*.jpg, ... 020-tmdb-*.jpg
```

**평가 기준** (사용자 묘사에서 추출):
- 핵심 시각 요소 (예: "밤", "비", "우산", "여인 뒷모습", "가로등")
- 톤 (예: "외로움", "멜랑콜리")
- 부정 조건 (예: "공포 분위기 아님")

**판정**:
- 모든 핵심 요소 일치 → ✅ 통과
- 일부 요소 + 강한 톤 일치 → ✅ 통과
- 톤만 일치, 핵심 시각 요소 없음 → ❌ 거절
- 톤도 안 맞음 (예: 낮 씬, 실내 클로즈업) → ❌ 거절

각 이미지에 대해 한 줄 판단을 사용자에게 짧게 보여주는 게 좋음 (투명성).

### Step 4 — 검수 결과 적용 (curate)

통과한 파일명 prefix(예: 001, 005, 012)를 모아 curate 호출:

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --curate "<Step 2 folder>" `
   --keep "001,005,012,015" `
   --note "비 우산 야경 외로움 톤 일치 (4/20 통과)" `
   --open
```

- `--keep`: 통과한 파일명 prefix 콤마로
- `--note`: 갤러리 상단에 표시할 메모. 검수 기준 + 통과율 명시
- `--open`: 검수 끝났으니 이제 사용자에게 보여줌
- 거절된 이미지는 자동으로 `_rejected/` 하위 폴더로 이동 (보존)

### Step 5 — 사용자에게 보고

검수 결과를 짧게 요약:
- 후보 N장 → 통과 M장
- 핵심 일치 요소 (예: "비/우산/야경 다 있는 4장")
- 거절 사유 요약 (예: "다른 16장은 낮 또는 실내 씬이라 제외")
- 갤러리는 자동으로 본인 브라우저에 열림

---

## 트리거별 분기

### A) 시네마틱 톤 (위 5단계 흐름)

키워드: 시네마틱, 영화 같은, 드라마 톤, OO 분위기, 인물·장면 묘사

→ Step 1~5 그대로

### B) 단순 stock 비주얼 (검수 생략 가능)

키워드: 텍스처, 매크로, 추상, 제품, 음식 정물

→ 검수 없이 Pexels/Pixabay만:
```powershell
py find_ref.py --open --project <프로젝트> "<영문 키워드>"
```

### C) 혼합

영화 + 키워드 둘 다 적용:
```powershell
py find_ref.py --project <프로젝트> --limit 20 --titles "..." "<영문 키워드>"
```
→ 검수 거치고 → curate

---

## 첫 실행 점검

`~/.claude/skills/ref-finder/.env`가 없으면 자동 설치:

```powershell
if (-not (Test-Path "$HOME\.claude\skills\ref-finder\.env")) {
    powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\install.ps1"
}
```

`install.ps1`이 Python 자동 설치 + 패키지 + .env 생성. 사용자에게 TMDB·Pexels API 키 발급 안내.

---

## 후속 액션 가이드

### "결과가 부족하다 / 다 떨어졌다"
- 영화 후보를 다시 큐레이션 (Step 1로 복귀)
- 더 정확한 키워드의 영화로 (예: 비 우산 → "Memento, Joker, Atonement" 같이 비 씬 풍부한 작품)
- 영화 수 늘리기 (10~15개)

### "특정 영화로만 더"
- 단일 영화: `--titles "Decision to Leave" --limit 12`
- 그 영화의 모든 backdrop을 다양하게 가져옴

### "다른 방향으로"
- 영화 리스트를 완전히 갈아끼움 (예: 어두운 → 밝은, 한국 → 미국)

---

## 주의사항

- **TMDB 스틸은 promotional 위주** — 영화 안 모든 씬이 있는 게 아니라 마케팅 대표 컷. 따라서 **검수 단계가 필수**.
- **검수 단계 생략 = 사용자에게 톤 안 맞는 70~90% 이미지 떠넘기기**. 그러면 안 됨.
- **한국어 검색은 약함** (Pexels/Pixabay) — 영어로 변환. TMDB는 한글 영화명도 OK.
- **저작권**: TMDB 스틸은 영화사 자료. 개인 레퍼런스 OK, 외부 공개 주의.

---

## API 키 발급 가이드 (사용자에게 안내할 때)

| 서비스 | URL | 받을 값 | .env 키 |
|---|---|---|---|
| TMDB ⭐ | https://www.themoviedb.org/settings/api | "API 키" (짧은 16진수) | `TMDB_API_KEY` |
| Pexels | https://www.pexels.com/api/ | API key | `PEXELS_API_KEY` |
| Pixabay (선택) | https://pixabay.com/api/docs/ | API key | `PIXABAY_API_KEY` |

**TMDB는 시네마틱 톤의 핵심**.

---

## 다음 부품 (로드맵)

- 이미지 프롬프트 생성기 (별표 레퍼런스 → 나노바나나 프롬프트)
- 영상 직전 AI 1차 검수기 (크레딧 절감)
- 영상 프롬프트 생성기 (Kling)
