$ErrorActionPreference = 'Stop'

$dataDir = Join-Path $env:APPDATA 'AutoBeat5'
$profilePath = Join-Path $dataDir 'profile.json'
if (-not (Test-Path -LiteralPath $profilePath)) {
    throw "profile.json was not found: $profilePath"
}

$fakeHashes = @(
    (('a' * 64) -join ''),
    (('b' * 64) -join ''),
    (('c' * 64) -join ''),
    (('d' * 64) -join '')
)
$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$backupPath = Join-Path $dataDir "profile.json.before_mock_cleanup_$timestamp.bak"
Copy-Item -LiteralPath $profilePath -Destination $backupPath -Force

$profile = Get-Content -LiteralPath $profilePath -Raw | ConvertFrom-Json
$profile.recent_songs = @($profile.recent_songs | Where-Object { $fakeHashes -notcontains [string]$_.music_hash })

foreach ($collectionName in @('rankings', 'high_scores')) {
    $collection = $profile.$collectionName
    if ($null -eq $collection) { continue }
    $remove = @($collection.PSObject.Properties | Where-Object {
        $key = [string]$_.Name
        $fakeHashes | Where-Object { $key.StartsWith("${_}:") }
    })
    foreach ($property in $remove) {
        $collection.PSObject.Properties.Remove($property.Name)
    }
}

$profile.play_history = @($profile.play_history | Where-Object {
    $key = [string]$_.chart_hash
    -not ($fakeHashes | Where-Object { $key.StartsWith("${_}:") })
})

if ($profile.last_play_ranking) {
    $key = [string]$profile.last_play_ranking.chart_key
    if ($fakeHashes | Where-Object { $key.StartsWith("${_}:") }) {
        $profile.last_play_ranking = $null
    }
}

$profile | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $profilePath -Encoding utf8
Write-Output "Removed mock library entries. Backup: $backupPath"
