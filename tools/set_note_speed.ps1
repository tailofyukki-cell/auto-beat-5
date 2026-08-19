param(
    [ValidateRange(250, 1200)]
    [double]$Speed = 625
)

$settingsPath = Join-Path $env:APPDATA 'AutoBeat5\settings.json'
if (-not (Test-Path $settingsPath)) {
    throw "設定ファイルが見つかりません: $settingsPath"
}

$settings = Get-Content -Raw -Path $settingsPath | ConvertFrom-Json
$settings.note_speed = $Speed
$temporaryPath = "$settingsPath.tmp"
$settings | ConvertTo-Json -Depth 8 | Set-Content -Path $temporaryPath -Encoding utf8
Move-Item -Path $temporaryPath -Destination $settingsPath -Force
Write-Output "NOTE_SPEED_UPDATED=$Speed"
Write-Output "SETTINGS=$settingsPath"
