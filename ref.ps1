# ref-finder · 한 줄 호출 wrapper
#
# 첫 실행 시: install.ps1을 자동으로 돌려서 Python·패키지·.env를 셋업.
# 이후 실행 시: 바로 find_ref.py 호출.
#
# 사용:
#   .\ref.ps1 "minimal cosmetic natural"
#   .\ref.ps1 --project ad-X "moody close-up"
#   .\ref.ps1 --limit 10 "cinematic dark"

$ErrorActionPreference = "Stop"
$here = $PSScriptRoot

# 첫 실행 점검: .env가 없으면 install.ps1 실행
$envPath = Join-Path $here ".env"
if (-not (Test-Path $envPath)) {
    Write-Host "==> 첫 실행: 자동 설치 시작..." -ForegroundColor Cyan
    & (Join-Path $here "install.ps1")
    Write-Host ""
}

# PATH 새로고침 (방금 설치된 Python을 잡기 위해)
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","User") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","Machine")

# find_ref.py 호출
& py (Join-Path $here "find_ref.py") --open @args
