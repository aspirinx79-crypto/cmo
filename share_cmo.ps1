# CMO 기획 도구를 직원과 함께 쓰도록 임시 링크로 연다.
#
# 이 창이 열려 있고 이 PC가 켜져 있는 동안만 링크가 산다. 창을 닫으면 끝.
# 링크 주소는 열 때마다 바뀐다(Cloudflare 임시 터널). 비밀번호는 그대로다.
#
# 비밀번호는 share_password.txt 에 둔다(저장소에 올리지 않음). 없으면 새로 만든다.
# 바꾸고 싶으면 그 파일을 고치거나 지우고 다시 연다.

$ErrorActionPreference = 'Stop'
$Cmo = $PSScriptRoot
$Parent = Split-Path $Cmo -Parent
$PwFile = Join-Path $Cmo 'share_password.txt'

$Cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe'
if (-not (Test-Path $Cloudflared)) {
    $Cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
}
if (-not $Cloudflared) {
    Write-Host 'cloudflared 가 없습니다. 먼저 설치하십시오:' -ForegroundColor Red
    Write-Host '  winget install --id Cloudflare.cloudflared -e'
    Read-Host '엔터를 누르면 닫힙니다'; exit 1
}

if (-not (Test-Path $PwFile)) {
    $chars = 'abcdefghjkmnpqrstuvwxyz23456789'.ToCharArray()
    $pw = -join (1..10 | ForEach-Object { $chars | Get-Random })
    Set-Content -Path $PwFile -Value $pw -Encoding utf8 -NoNewline
}
$Password = (Get-Content $PwFile -Raw -Encoding utf8).Trim()

# 비밀번호 없이 떠 있는 서버(run_cmo.bat)가 있으면 터널이 그쪽에 붙어
# 문이 열린 채로 나간다. 먼저 내린다.
$busy = Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue
if ($busy) {
    Write-Host '이미 떠 있는 CMO 서버를 내리고 공유 모드로 다시 엽니다.'
    $busy | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
    Start-Sleep -Seconds 1
}

$Python = Join-Path $Parent 'automation\.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { $Python = 'python' }

$env:CMO_PASSWORD = $Password
# 둘 다 이 창에 붙여 띄운다(-NoNewWindow). 창을 X 로 닫아도 같이 꺼진다.
$serverLog = Join-Path $env:TEMP 'cmo_share_server.log'
$server = Start-Process -FilePath $Python -ArgumentList '-m', 'cmo.server' `
    -WorkingDirectory $Parent -NoNewWindow -PassThru `
    -RedirectStandardOutput $serverLog -RedirectStandardError "$serverLog.err"

$log = Join-Path $env:TEMP 'cmo_tunnel.log'
Remove-Item $log -ErrorAction SilentlyContinue
$tunnel = Start-Process -FilePath $Cloudflared `
    -ArgumentList 'tunnel', '--no-autoupdate', '--url', 'http://127.0.0.1:8765' `
    -NoNewWindow -PassThru -RedirectStandardOutput "$log.out" -RedirectStandardError $log

$url = $null
for ($i = 0; $i -lt 40 -and -not $url; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Path $log) {
        $m = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value }
    }
}

try {
    if (-not $url) {
        Write-Host '링크를 못 만들었습니다. 인터넷 연결을 확인하고 다시 여십시오.' -ForegroundColor Red
        Write-Host "기록: $log"
        Read-Host '엔터를 누르면 닫힙니다'
        return
    }
    $msg = "CMO 기획 도구`n링크: $url`n비밀번호: $Password  (아이디 칸은 아무거나)"
    Set-Clipboard -Value $msg
    Write-Host ''
    Write-Host '=== 공유 중 ===' -ForegroundColor Green
    Write-Host "링크     : $url"
    Write-Host "비밀번호 : $Password   (아이디 칸은 아무거나)"
    Write-Host ''
    Write-Host '위 내용이 클립보드에 복사됐습니다. 그대로 붙여 보내면 됩니다.'
    Write-Host '이 창을 닫거나 엔터를 누르면 공유가 끝납니다.' -ForegroundColor Yellow
    Read-Host | Out-Null
}
finally {
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
}
