# Forward all arguments unchanged; relative user paths belong to the caller's directory.
$toolArguments = @($args)
$toolCandidates = @((Join-Path $PSScriptRoot '.venv\Scripts\python.exe'))
# Project-local worktrees may reuse the main checkout's environment without installing anything.
$toolCandidates += Join-Path $PSScriptRoot '..\..\.venv\Scripts\python.exe'
foreach ($toolName in @('python', 'py')) {
    $toolCommand = Get-Command $toolName -ErrorAction SilentlyContinue
    if ($toolCommand) { $toolCandidates += $toolCommand.Source }
}
$toolPython = $null
foreach ($toolCandidate in ($toolCandidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $toolCandidate -PathType Leaf)) { continue }
    try {
        $toolPreviousErrorPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        & $toolCandidate -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' 2>$null
        if ($LASTEXITCODE -eq 0) { $toolPython = $toolCandidate; break }
    }
    catch { continue }
    finally { $ErrorActionPreference = $toolPreviousErrorPreference }
}
if (-not $toolPython) {
    Write-Error 'Python 3.11+ was not found. Create .venv or run counterexamples.py with an existing Python interpreter.'
    exit 2
}
# UTF-8 makes Chinese experiment summaries readable in both PowerShell versions.
$toolPreviousUtf8 = $env:PYTHONUTF8
$toolPreviousEncoding = [Console]::OutputEncoding
try {
    $env:PYTHONUTF8 = '1'
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    & $toolPython -B (Join-Path $PSScriptRoot 'counterexamples.py') @toolArguments
    $toolExitCode = $LASTEXITCODE
}
finally {
    $env:PYTHONUTF8 = $toolPreviousUtf8
    [Console]::OutputEncoding = $toolPreviousEncoding
}
exit $toolExitCode
