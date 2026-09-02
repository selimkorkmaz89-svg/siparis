# Pull the latest changes and bring the local environment back in sync.
#   PS> .\scripts\update.ps1
# Safe to run any time: each step is a no-op when nothing changed.
$ErrorActionPreference = "Stop"

Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "`n[1/4] Yerel degisiklikler kontrol ediliyor..." -ForegroundColor Cyan
# Only tracked edits can collide with a pull; new files of your own are fine.
$dirty = git status --porcelain --untracked-files=no
if ($dirty) {
    Write-Host "Takip edilen dosyalarda kaydedilmemis degisiklik var:" -ForegroundColor Yellow
    git status --short --untracked-files=no
    Write-Host "`nDevam ederseniz 'git pull' bu dosyalarda catisma verebilir." -ForegroundColor Yellow
    $answer = Read-Host "Yine de devam edilsin mi? (e/h)"
    if ($answer -ne "e") { Write-Host "Iptal edildi."; exit 1 }
}

Write-Host "`n[2/4] GitHub'dan son surum cekiliyor..." -ForegroundColor Cyan
git pull

$python = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }

Write-Host "`n[3/4] Bagimliliklar kontrol ediliyor..." -ForegroundColor Cyan
& $python -m pip install --quiet -r requirements.txt

Write-Host "`n[4/4] Veritabani guncelleniyor..." -ForegroundColor Cyan
& $python manage.py migrate

Write-Host "`nHazir. Sunucuyu baslatmak icin:" -ForegroundColor Green
Write-Host "  $python manage.py runserver`n"
