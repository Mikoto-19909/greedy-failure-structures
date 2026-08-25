param(
    [ValidateSet("quick", "demo", "test", "test-fast", "typecheck", "full")]
    [string]$Action = "quick"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Candidates = @()
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
$PyCommand = Get-Command py -ErrorAction SilentlyContinue
if ($PythonCommand) { $Candidates += $PythonCommand.Source }
$LocalPythonRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\Python'
foreach ($VersionSuffix in '315', '314', '313', '312', '311') {
    $Candidates += Join-Path $LocalPythonRoot "Python$VersionSuffix\python.exe"
}
if ($PyCommand) { $Candidates += $PyCommand.Source }

function Test-PythonCandidate {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Candidate,
        [switch]$RequireMypy
    )

    $PreviousErrorActionPreference = $ErrorActionPreference
    $NativePreference = Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue
    $PreviousNativePreference = if ($NativePreference) { $NativePreference.Value } else { $null }
    try {
        # Candidate rejection is expected control flow, even when the caller has enabled
        # PowerShell's native-command error promotion.
        $ErrorActionPreference = "Continue"
        if ($NativePreference) { $PSNativeCommandUseErrorActionPreference = $false }

        & $Candidate -c "import sys; raise SystemExit(sys.version_info < (3, 11))"
        if ($LASTEXITCODE -ne 0) { return $false }
        if ($RequireMypy) {
            & $Candidate -c "import importlib.util; spec = importlib.util.find_spec('mypy'); raise SystemExit(spec is None or __import__('mypy.version', fromlist=['__version__']).__version__ != '2.3.0')"
            if ($LASTEXITCODE -ne 0) { return $false }
        }
        return $true
    }
    catch {
        return $false
    }
    finally {
        $ErrorActionPreference = $PreviousErrorActionPreference
        if ($NativePreference) {
            $PSNativeCommandUseErrorActionPreference = $PreviousNativePreference
        }
    }
}

$Python = $null
foreach ($Candidate in ($Candidates | Select-Object -Unique)) {
    if (-not (Test-Path -LiteralPath $Candidate)) { continue }
    if (-not (Test-PythonCandidate -Candidate $Candidate -RequireMypy:($Action -eq "typecheck"))) { continue }
    $Python = $Candidate
    break
}

if (-not $Python) {
    if ($Action -eq "typecheck") {
        throw 'Python 3.11+ with mypy was not found. Install the optional dependency with: python -m pip install -e ".[typecheck]"'
    }
    throw "Python 3.11 or newer was not found. Install Python, then run this command again."
}

Push-Location $ProjectRoot
try {
    switch ($Action) {
        "quick" { & $Python run_project.py quick }
        "demo"  { & $Python run_project.py demo }
        "test"  { & $Python -m unittest discover -s tests -v }
        "test-fast" {
            & $Python -m pytest -p no:cacheprovider -n 4 --tb=short -q
            if ($LASTEXITCODE -eq 0) {
                Write-Host "`nRunning serial-only tests (execnet serialization blocklist)..." -ForegroundColor Cyan
                & $Python -m pytest -p no:cacheprovider `
                    tests/test_solution_status.py::SolutionStatusTests::test_non_optimal_bound_must_leave_a_positive_gap `
                    tests/test_solution_status.py::SolutionStatusTests::test_non_error_status_requires_an_incumbent `
                    tests/test_p3_algorithms.py::EnhancedBranchAndBoundTests::test_edge_cases_and_all_ablation_options_remain_exact `
                    tests/test_p4_new_families.py::P43PreflightAndExactnessTests::test_cross_parameter_capacity_errors_are_rejected `
                    --tb=short -q
            }
        }
        "typecheck" { & $Python -m mypy }
        "full"  { & $Python run_project.py benchmark --config configs/full.json --output results/full }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "The project command failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}
