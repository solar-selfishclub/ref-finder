---
name: ref-finder
description: AI 영상 크리에이터를 위한 레퍼런스 자동 수집 스킬. 사용자가 키워드·장면 묘사·의뢰서를 말하면 (1) 시네마틱 톤이 필요하면 Claude가 어울리는 영화·드라마 후보를 떠올려 TMDB에서 진짜 영화 스틸을 가져오고, (2) 일반 stock 비주얼이면 Pexels/Pixabay에서 검색합니다. 트리거 키워드 — "레퍼런스 찾아줘", "광고 컨셉용 자료", "무드보드", "영상 레퍼런스", "비주얼 자료", "스틸 모아줘", "moodboard", "reference", "시네마틱 톤", "영화 같은 분위기", "이런 장면". 영상·이미지 제작 전에 시각 레퍼런스가 필요할 때 발동.
---

# ref-finder Skill

영상 크리에이터의 OS 첫 부품. 한 컷 레퍼런스 찾는 데 30분 → 5분.

## 두 가지 모드 — 어떤 걸 쓸지 자동 판단

### 모드 A: TMDB (영화 스틸) — 시네마틱 톤이 핵심일 때 ⭐
사용자가 "시네마틱", "영화 같은", "드라마처럼", "OO 톤" 같이 말하거나, 광고 영상 제작이 명백한 맥락이면 **이 모드 우선**.

**Claude가 해야 할 일**:
1. 사용자 장면 묘사를 듣고 **그런 장면·톤이 있을 법한 영화·드라마 5~10개 떠올림**
2. `find_ref.py --titles "<영화1>,<영화2>,..."` 호출
3. TMDB가 그 영화들의 진짜 스틸을 가져옴

**예시**:
| 사용자 발화 | Claude가 떠올릴 영화 |
|---|---|
| "한인마트 야채 코너에서 장보는 인물" | Minari, Parasite, The Farewell, Past Lives, Pachinko |
| "K-드라마 카페 신 분위기" | 도깨비, 사랑의 불시착, 호텔 델루나, 별에서 온 그대 |
| "어두운 비 오는 도시 야경" | Blade Runner 2049, Drive, John Wick, 올드보이 |
| "노스탤지어한 80년대 미국 가족 식탁" | Stranger Things, Lady Bird, Boyhood, Eighth Grade |
| "감각적인 스킨케어 광고 톤" | Call Me By Your Name, Lost in Translation, In the Mood for Love |

**호출**:
```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --open `
   --project <프로젝트명> --limit 8 `
   --titles "Parasite,Minari,The Farewell,Past Lives,Pachinko"
```

### 모드 B: Pexels/Pixabay (stock 이미지) — 일반 비주얼·소재
사용자가 "음식 사진", "제품 클로즈업", "추상적 텍스처" 같이 시네마틱이 아닌 단순 비주얼을 원하면 이 모드.

**호출**:
```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --open `
   --project <프로젝트명> "<영문 키워드>"
```

### 모드 혼합
TMDB(영화 스틸) + Pexels(키워드)를 동시에 가져올 수도 있음 — `--titles`와 query를 둘 다 주면 됨.

## 자연어 → 검색 키워드 / 영화 변환

| 사용자 발화 | 추출 |
|---|---|
| "30대 여성 자연주의 화장품 미니멀" | 모드 A: Lost in Translation, Call Me By Your Name |
| "어두운 시네마틱 클로즈업 제품샷" | 모드 A: Drive, Blade Runner 2049 + 모드 B 보조: `cinematic dark moody product close-up` |
| "추상적 액체 텍스처" | 모드 B만: `abstract liquid texture macro` |

**판단 기준**:
- 사용자가 **인물·장면·분위기**를 묘사 → 모드 A 우선
- 사용자가 **소재·물건·텍스처**를 묘사 → 모드 B 우선

## 첫 실행 점검

`~/.claude/skills/ref-finder/.env`가 없으면 자동 설치:

```powershell
if (-not (Test-Path "$HOME\.claude\skills\ref-finder\.env")) {
    powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\install.ps1"
}
```

`install.ps1`이 Python 자동 설치 + 패키지 + .env 생성. 사용자에게 API 키(Pexels, TMDB) 발급 안내.

## 결과 제시 가이드

`find_ref.py` 출력에 갤러리 경로가 나옴. `--open`이 자동으로 브라우저를 띄워줌. 사용자에게:

> "갤러리가 브라우저에서 열렸습니다. 좋아하는 레퍼런스에 별표를 눌러주세요. 별표는 자동 저장됩니다(localStorage)."

## 후속 액션

- "다른 영화 추천": Claude가 다른 영화 후보를 떠올려 다시 호출
- "더 어두운 톤": 영화 후보를 더 어두운 작품으로 바꿔 재호출 (Drive, Blade Runner 등)
- "특정 영화의 다른 스틸": `--titles "Parasite"` 단일로 호출하면 그 영화 스틸 다양하게

## 주의사항

- **TMDB 스틸 양은 영화마다 다름** — 인기작은 풍부, 마이너작은 빈약
- **저작권**: TMDB 스틸은 영화사 자료. 개인 레퍼런스 OK, 외부 공개는 주의
- **한국어 검색은 약함** (Pexels/Pixabay) — 영어로 변환. TMDB는 한글 영화명도 OK
- **Mac/Linux는 install.ps1 미지원** — 수동으로 `pip install mcp httpx python-dotenv` 후 사용

## API 키 발급 가이드 (사용자에게 안내할 때)

| 서비스 | 가입 URL | 받아야 할 값 | .env 키 |
|---|---|---|---|
| TMDB ⭐ | https://www.themoviedb.org/settings/api | "API 키" (짧은 16진수) | `TMDB_API_KEY` |
| Pexels | https://www.pexels.com/api/ | API key | `PEXELS_API_KEY` |
| Pixabay (선택) | https://pixabay.com/api/docs/ | API key | `PIXABAY_API_KEY` |

**TMDB가 시네마틱 톤의 핵심이므로 강력 권장**.

## 다음 부품 (로드맵)

- 이미지 프롬프트 생성기 (별표 레퍼런스 → 나노바나나 프롬프트)
- 영상 직전 AI 1차 검수기 (크레딧 절감)
- 영상 프롬프트 생성기 (Kling)
