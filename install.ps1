# ref-finder · 새 컴퓨터에서 한 번에 설치하는 스크립트 (Windows)
#
# 이 파일이 자동으로 처리하는 것:
#   1. Python 3.12 설치 (이미 있으면 건너뜀)
#   2. pip 패키지 설치 (mcp, httpx, beautifulsoup4, python-dotenv)
#   3. .env 파일 만들기 (.env.example 복사 → 사용자가 토큰 채우기)
#   4. ~/refs 출력 폴더 생성
#
# 사용 (새 컴퓨터, ref-finder 폴더에서 PowerShell 열고):
#   .\install.ps1

$ErrorActionPreference = "Stop"

function Write-Step([string]$msg) {
    Write-Host "`n==> $msg" -ForegroundColor Cyan
}

function Test-Command([string]$name) {
    try { Get-Command $name -ErrorAction Stop | Out-Null; return $true }
    catch { return $false }
}

# ----------- 1. Python -----------
Write-Step "1/4 Python 확인"
$needsPython = -not (Test-Command "py") -and -not (Test-Command "python")

# python.exe가 Microsoft Store stub인지 확인 (실제로 동작 안 함)
if (-not $needsPython) {
    try {
        $ver = & py --version 2>$null
        if (-not $ver -or $ver.Trim() -eq "Python") { $needsPython = $true }
    } catch { $needsPython = $true }
}

if ($needsPython) {
    Write-Host "  Python을 winget으로 설치합니다 (1~2분)…"
    winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements | Out-Null
    # 새 PATH 반영
    $env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","Machine")
    Write-Host "  Python 설치 완료." -ForegroundColor Green
} else {
    Write-Host "  Python 이미 설치됨." -ForegroundColor Green
}

# ----------- 2. pip 패키지 -----------
Write-Step "2/4 Python 패키지 설치 (mcp, httpx, python-dotenv)"
& py -m pip install --quiet --upgrade pip
& py -m pip install --quiet mcp httpx python-dotenv
Write-Host "  패키지 설치 완료." -ForegroundColor Green

# ----------- 3. .env -----------
Write-Step "3/4 환경 설정 파일 (.env)"
$here = $PSScriptRoot
$envPath = Join-Path $here ".env"
$exPath  = Join-Path $here ".env.example"
if (-not (Test-Path $envPath)) {
    if (Test-Path $exPath) {
        Copy-Item $exPath $envPath
        Write-Host "  .env 파일을 만들었습니다." -ForegroundColor Green
        Write-Host ""
        Write-Host "  >>> 다음 단계: API 키를 .env에 넣어야 작동합니다 <<<" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  [강력 권장] TMDB - 영화 스틸 (시네마틱 톤)" -ForegroundColor Yellow
        Write-Host "    1. https://www.themoviedb.org/settings/api  → 가입 → API 키 발급" -ForegroundColor White
        Write-Host "    2. 짧은 쪽 'API 키' (16진수) 복사" -ForegroundColor White
        Write-Host "    3. .env 의 TMDB_API_KEY= 뒤에 붙여넣기" -ForegroundColor White
        Write-Host ""
        Write-Host "  [선택] Pexels - stock 이미지" -ForegroundColor Yellow
        Write-Host "    1. https://www.pexels.com/api/  → 가입 → API key" -ForegroundColor White
        Write-Host "    2. .env 의 PEXELS_API_KEY= 뒤에 붙여넣기" -ForegroundColor White
        Write-Host ""
        Write-Host "  .env 파일 위치: $envPath" -ForegroundColor Cyan
    } else {
        Write-Warning "  .env.example을 찾을 수 없음. 건너뜀."
    }
} else {
    Write-Host "  .env 이미 있음, 그대로 둠." -ForegroundColor Green
}

# ----------- 4. 출력 폴더 -----------
Write-Step "4/4 레퍼런스 출력 폴더 ($HOME\refs)"
$refsDir = Join-Path $HOME "refs"
if (-not (Test-Path $refsDir)) {
    New-Item -ItemType Directory -Force -Path $refsDir | Out-Null
    Write-Host "  $refsDir 폴더를 만들었습니다." -ForegroundColor Green
} else {
    Write-Host "  $refsDir 이미 있음." -ForegroundColor Green
}

# ----------- 끝 -----------
Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "  설치 완료!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "`n사용법:`n"
Write-Host "  py find_ref.py --open `"natural cosmetic minimal`"" -ForegroundColor White
Write-Host "  py find_ref.py --open --project ad-X `"moody close-up`"" -ForegroundColor White
Write-Host "`n자세한 설명은 README.md 참조.`n"
