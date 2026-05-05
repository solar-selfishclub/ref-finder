---
name: ref-finder
description: AI 영상 크리에이터를 위한 레퍼런스 자동 수집 + AI 검수 스킬. 사용자가 장면을 묘사하면 (1) Claude가 시각 태그를 추출해 shot.cafe(영화·광고 스틸 24K장, 109K 태그)에서 씬 단위로 검색하고, (2) **서브에이전트가 내부적으로 검수**(메인 채팅에 이미지 안 보임)하여 통과한 것만 갤러리에 남깁니다. (3) stock 비주얼은 Pexels/Pixabay 보조. 트리거 — "레퍼런스 찾아줘", "광고 컨셉 자료", "무드보드", "영상 레퍼런스", "스틸 모아줘", "moodboard", "reference", "시네마틱 톤", "이런 장면". 영상 제작 전에 시각 레퍼런스가 필요할 때 발동.
---

# ref-finder Skill

영상 크리에이터의 OS 첫 부품. 한 컷 레퍼런스 찾는 데 30분 → 5분.
**v0.2.1부터 서브에이전트 검수** — 메인 채팅에 이미지 노출 없음.

---

## 핵심 흐름 (5단계, 메인 채팅 깨끗하게)

### Step 1 — 태그 추출 (메인 Claude)

사용자 묘사 → 시각 태그 3~5개 영문으로. 추상 톤보단 **눈에 보이는 시각 요소**.

**추출 예** (사용자: "밤에 비 오는 거리, 우산 쓴 외로운 여인 뒷모습"):
- ✅ `rain, night, umbrella, woman, street`
- ❌ `lonely, atmospheric` (shot.cafe 추상 태그 약함)

**⚠️ 태그 컨벤션 (반드시 정확하게)**: shot.cafe는 두 가지를 혼용함.

| 형태 | 사용 시 | 예시 |
|---|---|---|
| **하이픈** (`-`) | 사전적으로 한 단어로 쓰는 시네마토그래피 용어 | `two-shot`, `close-up`, `low-angle`, `high-angle`, `over-the-shoulder` |
| **공백** (CLI에는 그대로) | 두 단어로 쓰는 일반 표현 | `wide shot`, `medium shot`, `establishing shot` |
| **단일** | 환경·인물·소품 | `rain`, `night`, `umbrella`, `woman`, `street`, `neon` |

**검증된 작동 태그**:
- 시네마토그래피: `two-shot`, `close-up`, `low-angle`, `high-angle`, `over-the-shoulder`, `wide shot`, `medium shot`, `establishing shot`, `silhouette`, `reflection`
- 환경: `rain`, `snow`, `fog`, `night`, `day`, `sunset`, `beach`, `forest`, `city`, `street`, `alley`, `bridge`
- 인물: `woman`, `man`, `child`, `couple`, `crowd`
- 빛/색: `neon`, `candle`, `fire`, `moonlight`, `blue`, `red`, `golden hour`
- 도구: `umbrella`, `car interior`, `train`, `mirror`, `window`

**작동 안 하는 (확인됨, 쓰지 말 것)**: `long-shot`, `eye-level`, `master-shot`, `extreme-close-up`, `medium-close-up`, `two-people`, `profile`, `standing`, `facing`

확실하지 않으면 단일 태그부터 시도 후 결과 보고 조합.

### Step 2 — 후보 다운로드 (메인 Claude)

**기본 모드(C, 권장)**: 15장 다운로드 후 검수
```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --project <프로젝트명> --limit 15 `
   --tags "<tag1>,<tag2>,<tag3>"
```

**빠른 모드(A)**: 사용자가 "빨리 그냥 받아만 줘", "검수 없이" 같이 말하면 검수 생략하고 바로 `--open`
```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --open --project <프로젝트명> --limit 10 `
   --tags "<tag1>,<tag2>,<tag3>"
```
→ Step 3~4 건너뛰고 Step 5로

**꼼꼼 모드(B)**: 사용자가 "꼼꼼히 골라줘", "정확하게" 같이 말하면 25장으로
```powershell
... --limit 25 --tags "..."
```

### Step 3 — 서브에이전트 검수 ⭐ (메인 채팅에 이미지 노출 없음)

**Task tool로 서브에이전트 dispatch** (subagent_type=general-purpose):

```
prompt 예시:
  ref-finder 검수 작업.
  
  사용자 의도: "<사용자 원문 묘사 그대로>"
  부정 조건: 공포·폭력 분위기 강하면 무조건 거절.
  
  검수 대상 폴더: C:\Users\<USER>\refs\<프로젝트명>\<타임스탬프>\images\
  
  각 이미지를 Read tool로 보고 사용자 의도와 매칭 평가.
  통과 기준:
    - 핵심 시각 요소 모두 또는 대부분 일치 → 통과
    - 톤 강하게 일치 (요소 일부만) → 통과 (톤 reference 가치)
    - 부정 조건 위반 → 거절
    - 환경 완전 불일치 → 거절
  
  반환 형식 (JSON):
    {
      "keep": ["001", "003", "007"],     ← 통과한 파일명 prefix
      "note": "X장 중 N장 통과. <강한 매칭 영화 1~2개> + <거절 사유 요약>",
      "highlights": [                     ← 가장 강한 매칭 1~3개
        {"file": "001", "movie": "<영화명>", "why": "<한 줄>"}
      ]
    }
```

서브에이전트가 내부적으로 모든 이미지 Read → 텍스트 결과만 반환.
**메인 채팅에는 이미지 0장 표시.** 핵심.

### Step 4 — Curate 적용 (메인 Claude)

서브에이전트가 반환한 keep, note 사용:

```powershell
py "$HOME\.claude\skills\ref-finder\find_ref.py" --curate "<Step 2 folder>" `
   --keep "<comma list>" `
   --note "<note>" `
   --open
```

거절된 이미지는 자동으로 `_rejected/` 폴더로 이동 (보존).

### Step 5 — 사용자에게 짧게 보고

서브에이전트의 highlights로:
- 통과 N장 (X% 통과율)
- 가장 강한 매칭 1~2개 ("OO 영화의 — <한 줄 사유>")
- 갤러리 자동으로 본인 브라우저에 열림

**이미지는 사용자가 갤러리(브라우저)에서 봄. 채팅에는 한 장도 안 띄움.**

---

## 트리거별 분기

### A) 시네마틱 톤 (위 5단계 — 메인)
영화·드라마·시네마틱 분위기, 인물·장면 묘사 → shot.cafe + 서브에이전트 검수

### B) 단순 stock 비주얼 (검수 생략)
텍스처, 매크로, 추상, 제품, 음식 정물 → Pexels/Pixabay
```powershell
py find_ref.py --open --project <프로젝트> "<영문 키워드>"
```

### C) 혼합
```powershell
py find_ref.py --project <프로젝트> --limit 15 --tags "..." "<영문 키워드>"
```
→ 시네마틱이면 검수까지, 아니면 바로 open

---

## 사용자 발화별 모드 매핑

| 사용자 발화 | 모드 | 동작 |
|---|---|---|
| "이런 장면 레퍼런스" | C (기본) | 15장 → 검수 → 갤러리 |
| "꼼꼼히 골라줘" | B | 25장 → 검수 → 갤러리 |
| "빨리 그냥 받아만 줘" / "검수 없이" | A | 10장 → 바로 갤러리 |
| "텍스처/소재 사진" | stock | Pexels로, 검수 없음 |

---

## 첫 실행 점검

`~/.claude/skills/ref-finder/.env`가 없으면 자동 설치:

```powershell
if (-not (Test-Path "$HOME\.claude\skills\ref-finder\.env")) {
    powershell -ExecutionPolicy Bypass -File "$HOME\.claude\skills\ref-finder\install.ps1"
}
```

shot.cafe는 **API 키 불필요**. Pexels/Pixabay는 선택.

---

## 후속 액션 가이드

### "결과가 부족하다 / 다 떨어졌다"
- 태그 줄이기 (3개 → 2개)
- 다른 태그 시도

### "더 어두운/밝은/특정 분위기"
- 태그 갈아끼우기 (`night` 추가, `day` 제거)
- `silhouette`, `reflection` 추가

### "방금 거 말고 다른 방향"
- 같은 프로젝트 폴더로 새 호출 → 새 타임스탬프 폴더에 저장. 이전 결과 유지.

---

## 주의사항

- **shot.cafe robots.txt 준수**: 어댑터가 자동 처리 (5초 crawl-delay, 1~2 태그 결합)
- **태그**: 영문 콤마 결합, 공백은 `+`로 (예: `car+interior`)
- **사용자 한국어 → Claude가 영문 태그**로 변환
- **검수는 서브에이전트로** — 메인 채팅 깨끗하게. 직접 Read 금지.
- **부정 조건 엄격하게** — 사용자가 "공포 아님", "어둡지 않게" 같이 말하면 그 조건 위반은 무조건 거절

---

## 다음 부품 (로드맵)

- 이미지 프롬프트 생성기 (별표 레퍼런스 → 나노바나나 프롬프트)
- 영상 직전 AI 1차 검수기 (크레딧 절감)
- 영상 프롬프트 생성기 (Kling)
