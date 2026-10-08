param([string]$Python)
$ErrorActionPreference = 'Stop'
if (-not $Python) {
    $localPython = Join-Path $PSScriptRoot '..\..\.venv\Scripts\python.exe'
    if (Test-Path -LiteralPath $localPython) { $Python = (Resolve-Path -LiteralPath $localPython).Path }
    else { $Python = (Get-Command python -ErrorAction Stop).Source }
}
Push-Location $PSScriptRoot
try {
    & $Python -B fixtures.py
    if ($LASTEXITCODE -ne 0) { throw 'Frozen input check failed' }
    & $Python -B -m unittest -v test_matching
    if ($LASTEXITCODE -ne 0) { throw 'Hand checks failed' }
    $devLines = @(& $Python -B run.py --split dev)
    if ($LASTEXITCODE -ne 0) { throw 'Development run failed' }
    $dev = $devLines[0].ToString().Trim()
    & $Python -B verify.py $dev
    if ($LASTEXITCODE -ne 0) { throw 'Development verification failed' }
    $evalLines = @(& $Python -B run.py --split eval)
    if ($LASTEXITCODE -ne 0) { throw 'Comparison run failed' }
    $evaluation = $evalLines[0].ToString().Trim()
    & $Python -B verify.py $evaluation
    if ($LASTEXITCODE -ne 0) { throw 'Comparison verification failed' }
    & $Python -B analyze.py --eval $evaluation --dev $dev
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed' }
    & $Python -B finalize.py $evaluation
    if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
    Write-Output "Completed: $evaluation"
} finally {
    Pop-Location
}
