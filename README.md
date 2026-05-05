# ref-finder

AI 영상 크리에이터를 위한 **레퍼런스 자동 수집 도구**.

키워드를 던지면 [Pexels](https://www.pexels.com)(+선택 Pixabay)에서 광고·시네마틱 톤 사진 5장을 모아 로컬 HTML 갤러리로 보여줍니다. 한 컷 레퍼런스 찾는 데 30분 → 5분.

> 🧽 OS 청사진의 첫 부품 — "나는 의도와 최종 디렉팅만 하고, 나머지는 시스템이 한다"

---

## 🚀 가장 쉬운 사용법 — Claude Code에서 자연어로

### 한 번만: 새 컴퓨터/계정에 스킬 설치

Claude Code를 열고 다음과 같이 말하세요:

> **"https://github.com/solar-selfishclub/ref-finder 이거 스킬로 깔아줘"**

Claude가 자동으로:
1. `~/.claude/skills/ref-finder/`로 git clone
2. (Windows) install.ps1 실행 → Python 자동 설치 + 패키지 설치
3. 끝

> Claude가 헤매면 더 명확하게: *"이 GitHub 레포를 ~/.claude/skills/ref-finder/ 로 git clone하고 install.ps1을 PowerShell로 실행해줘"*

### 그 다음부터: 자연어로 호출

어느 Claude Code 세션에서든:

> **"30대 여성 자연주의 화장품 미니멀 톤으로 광고 레퍼런스 찾아줘"**
> **"어두운 시네마틱한 클로즈업 제품샷 모아줘"**
> **"방금 거 말고 더 밝은 톤으로 다시 (프로젝트 이름: ad-spring)"**

Claude가 알아서 영문 키워드로 변환 → 실행 → 갤러리를 브라우저에서 열어줍니다.

---

## 직접 PowerShell로 쓰는 방법 (Claude 없이)

### 새 컴퓨터에서 시작 (Windows)

PowerShell을 열고:

```powershell
cd $HOME
git clone https://github.com/solar-selfishclub/ref-finder.git
cd ref-finder
.\ref.ps1 "natural cosmetic minimal"
```

`ref.ps1`이 첫 실행 시 자동으로 Python·패키지·환경파일을 셋업합니다. 그 다음부터는 바로 검색 실행.

> **git이 없으면**: https://git-scm.com/download/win 에서 설치.
> **"스크립트 신뢰할 수 없음" 에러**: 한 번만 `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 실행.

---

## 자주 쓰는 명령어 모음 (PowerShell 직접 사용)

```powershell
# 가장 기본 — 5장 받고 갤러리 자동 열기 (ref.ps1 권장)
.\ref.ps1 "moody product close-up"

# 프로젝트별 폴더로 분리
.\ref.ps1 --project ad-cosmetic-spring "natural minimal cosmetic"

# 더 많이 받기 (5장이 부족할 때만)
.\ref.ps1 --limit 10 "cinematic dark night street"

# find_ref.py 직접 호출 (자동 설치 점검 없음)
py find_ref.py --open "minimal cosmetic"
```

결과는 `~/refs/<프로젝트명>/<날짜시간>/`에 저장됩니다. `index.html`을 더블클릭해서 언제든 다시 열 수 있어요.

---

## 한 번 더 짧은 단축키 만들기 (선택)

매번 `cd`나 `py find_ref.py`가 귀찮으면 PowerShell에 짧은 별명 등록:

```powershell
notepad $PROFILE
```

(파일 없다고 뜨면 "예" 선택)

다음 한 줄을 추가하고 저장:

```powershell
function ref { py "$HOME\ref-finder\find_ref.py" --open @args }
```

이제 새 PowerShell 창에서 어디서든:

```powershell
ref "minimal cosmetic"
ref --project ad-X "moody close-up"
```

---

## API 키 발급 (무료, 5분)

### Pexels (필수) — 영상 크리에이터에게 가장 보편적
1. https://www.pexels.com/api/ 접속
2. "Get Started" 또는 "Your API Key" → 가입 (이메일·비밀번호 또는 Google)
3. 발급받은 API key를 `.env`의 `PEXELS_API_KEY=` 뒤에 붙여넣기

### Pixabay (선택) — 더 다양한 출처 추가
1. https://pixabay.com/api/docs/ 접속
2. 가입 후 "Your API key" 확인
3. `.env`의 `PIXABAY_API_KEY=` 뒤에 붙여넣기

### 왜 filmvibes·Pinterest가 빠져있나요?
- **Pinterest**: Standard Access 미승인 앱은 검색 API 401 차단 (2025 정책)
- **filmvibes.io**: 무로그인 검색이 차단되어 Google OAuth 흐름이 필요. 작업량 대비 안정성 낮음
- 둘 다 v0.2에서 별도 부품으로 추적 가능

---

## 폴더 구조

```
ref-finder/
├── install.ps1          ← 새 컴퓨터에서 한 줄로 설치
├── find_ref.py          ← 메인 CLI
├── mcp/
│   └── ref_finder.py    ← 검색 + 다운로드 + 갤러리 생성 로직
├── templates/
│   └── gallery.html     ← 별표 토글 가능한 갤러리 UI
├── commands/
│   └── find-ref.md      ← Claude Code slash 커맨드 정의
├── plugin.json          ← Claude Code 플러그인 메타
├── .env.example         ← 환경 변수 자리 (실제 .env는 git에 포함되지 않음)
└── README.md
```

---

## 문제 해결

**"py가 인식되지 않습니다"**
→ Python 설치 후 PowerShell을 새로 여세요. 그래도 안 되면 `install.ps1` 다시 실행.

**갤러리가 빈 채로 뜸**
→ 키워드를 영어로 바꿔보세요. filmvibes는 한국어 검색이 약합니다.

**`.env` 토큰을 GitHub에 실수로 올렸어요**
→ Pinterest 토큰은 어차피 차단된 상태라 큰 문제는 아니지만, 발급한 곳에서 토큰 회전(regenerate)하세요.

---

## 다음 부품 (로드맵)

이 도구는 더 큰 OS의 첫 부품입니다:

1. ✅ **ref-finder** (이거) — 레퍼런스 자동 수집
2. 이미지 프롬프트 생성기 — 별표 레퍼런스 + 기획 → 나노바나나 프롬프트
3. **영상 직전 AI 1차 검수기** ⭐ — 크레딧 절약 핵심
4. 영상 프롬프트 생성기 — Kling 프롬프트 (1~2번에 끝)

---

## 라이선스

MIT — [LICENSE](LICENSE)
