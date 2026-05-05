---
name: ref-finder
description: AI 영상 크리에이터를 위한 레퍼런스 자동 수집 스킬. 사용자가 키워드·의뢰서·스토리보드를 말하면 Pexels(+선택 Pixabay)에서 광고·시네마틱 톤 사진 5장을 모아 로컬 HTML 갤러리로 출력. 트리거 키워드 — "레퍼런스 찾아줘", "광고 컨셉용 자료", "무드보드 만들어줘", "영상 레퍼런스", "비주얼 자료", "스틸 모아줘", "moodboard", "reference". 영상·이미지 제작 전에 시각 레퍼런스가 필요할 때 발동.
---

# ref-finder Skill

영상 크리에이터의 OS 첫 부품. 한 컷 레퍼런스 찾는 데 30분 → 5분.

## 어떻게 사용자 요청을 처리하는가

### 1. 자연어 → 검색 키워드 추출

사용자가 한국어로 의뢰를 주면 **영문 검색 키워드 3~6개**로 압축. filmvibes.io는 영어 검색이 결정적으로 강력.

| 사용자 발화 | 추출할 키워드 |
|---|---|
| "30대 여성 자연주의 화장품 미니멀 톤" | `natural cosmetic minimal woman` |
| "어두운 시네마틱 클로즈업 제품샷" | `cinematic dark moody product close-up` |
| "k-드라마 카페 신 같은 분위기" | `cafe morning drama korean coffee` |
| "비 오는 도시 야경 광고" | `rainy city night neon cinematic` |

### 2. 프로젝트 이름 추출

사용자가 광고 의뢰 이름을 말하면 `--project` 값으로 사용. 안 나오면 `default`.

### 3. 실행

이 스킬은 `~/.claude/skills/ref-finder/`에 설치되어있다고 가정.

**첫 실행 점검** — `.env` 파일이 없으면 자동 설치:

```powershell
# Windows: PowerShell에서
if (-not (Test-Path "$HOME\.claude\skills\ref-finder\.env")) {
    powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\install.ps1"
}
```

설치 스크립트가 자동으로:
- Python 3.12 설치 (없으면)
- pip 패키지 설치
- `.env` 파일 생성
- `~/refs` 폴더 생성

**메인 실행**:

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --open --project <프로젝트명> "<영문 키워드>"
```

또는 더 간단히 wrapper 사용:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\ref.ps1" --project <프로젝트명> "<영문 키워드>"
```

`ref.ps1`이 첫 실행 점검 + 메인 실행을 알아서 처리.

### 4. 결과 제시

`find_ref.py` 실행 시 출력되는 갤러리 경로를 사용자에게 알려줍니다. `--open` 플래그가 자동으로 브라우저를 띄워주므로, 사용자에게 안내:

> "갤러리가 브라우저에서 열렸습니다. 마음에 드는 레퍼런스에 별표를 눌러주세요. 별표 토글은 자동 저장돼요(localStorage)."

결과가 비어있으면 키워드를 더 줄이거나 더 일반적인 영어 단어로 재시도 권장.

## 후속 액션 가이드

사용자가 "다시", "다른 방향", "더 어둡게" 등 피드백을 주면 같은 프로젝트로 재호출:

```powershell
powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\ref.ps1" --project <같은-프로젝트명> "<수정된 영문 키워드>"
```

같은 프로젝트 폴더 아래 새 타임스탬프로 저장됨. 이전 결과는 그대로 유지.

## 주의사항

- **Pexels API 키 필요** — 무료 가입(https://www.pexels.com/api/) 후 `.env`에 `PEXELS_API_KEY=` 채우기.
- **Pinterest는 정책상 차단됨** (Standard Access 미승인 앱은 401). 사용 안 함.
- **filmvibes.io는 무로그인 검색 차단** — Google OAuth가 필요해서 v0.1.1에서는 제외.
- **한국어 검색은 약함**. 항상 영어로 변환 후 실행.
- **결과가 없을 때** = 키워드가 너무 구체적. 단어 1~2개 줄이고 재시도.
- **Mac/Linux는 install.ps1 미지원** — `pip install mcp httpx python-dotenv` 수동 실행 후 사용 가능.

## 관련 부품 (다음 인터뷰 주제)

이 스킬의 출력(`meta.json` + 별표 ID)은 다음 부품들의 입력:
1. 이미지 프롬프트 생성기 — 별표 레퍼런스 → 나노바나나 프롬프트
2. 영상 직전 AI 1차 검수기 — 크레딧 절감 핵심
3. 영상 프롬프트 생성기 — Kling 프롬프트

사용자가 ref-finder를 1주 이상 사용한 뒤 위 부품들을 만들 인터뷰를 진행할 수 있음.
