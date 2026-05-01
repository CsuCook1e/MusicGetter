# MusicGetter one-click starter for Windows PowerShell.
param(
    [switch]$SkipPlaywrightInstall,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$Port = 7860
$Url = "http://127.0.0.1:$Port"
$VenvDir = Join-Path $Root ".venv"
$VenvScripts = Join-Path $VenvDir "Scripts"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$InstallStamp = Join-Path $VenvDir ".musicgetter-install.stamp"
$PlaywrightStamp = Join-Path $VenvDir ".playwright-chromium.stamp"

function Write-Step {
    param([string]$Message)
    Write-Host "[MusicGetter] $Message" -ForegroundColor Cyan
}

function Write-Note {
    param([string]$Message)
    Write-Host "[MusicGetter] $Message" -ForegroundColor Yellow
}

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Assert-NativeSuccess {
    param([string]$Message)
    if ($LASTEXITCODE -ne 0) {
        throw $Message
    }
}

function Get-PythonLauncher {
    $candidates = @(
        @{ Exe = "py"; Args = @("-3.11") },
        @{ Exe = "py"; Args = @("-3") },
        @{ Exe = "python"; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if (-not (Test-Command $candidate.Exe)) {
            continue
        }

        & $candidate.Exe @($candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }

    throw "Python 3.10+ was not found. Install Python, then run this script again."
}

function Invoke-BasePython {
    param([string[]]$Arguments)
    $launcher = Get-PythonLauncher
    & $launcher.Exe @($launcher.Args) @Arguments
}

function Test-AppHealth {
    try {
        $response = Invoke-WebRequest -Uri "$Url/api/health" -UseBasicParsing -TimeoutSec 2
        return ($response.StatusCode -eq 200 -and $response.Content -match '"ok"\s*:\s*true')
    } catch {
        return $false
    }
}

function Test-PortInUse {
    try {
        return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return $false
    }
}

function Ensure-ExternalRepo {
    param(
        [string]$Path,
        [string]$RepoUrl,
        [string]$Probe
    )

    if (Test-Path $Probe) {
        return
    }

    if (-not (Test-Command "git")) {
        throw "Git was not found, and $Path is missing. Install Git or clone this repository with --recurse-submodules."
    }

    if (Test-Path ".git") {
        Write-Step "Initializing git submodules..."
        git submodule update --init --recursive
        Assert-NativeSuccess "Failed to initialize git submodules."
    }

    if (Test-Path $Probe) {
        return
    }

    if (Test-Path $Path) {
        $children = @(Get-ChildItem -LiteralPath $Path -Force -ErrorAction SilentlyContinue)
        if ($children.Count -gt 0) {
            throw "$Path exists but does not look complete. Remove or fix it, then run this script again."
        }
    }

    Write-Step "Cloning $Path..."
    git clone $RepoUrl $Path
    Assert-NativeSuccess "Failed to clone $RepoUrl."
}

function Get-DependencyFingerprint {
    $files = @(
        "requirements-web.txt",
        ".gitmodules",
        "musicdl\requirements.txt",
        "musicdl\setup.py"
    )

    $parts = foreach ($file in $files) {
        if (Test-Path $file) {
            $hash = Get-FileHash $file -Algorithm SHA256
            "$file=$($hash.Hash)"
        }
    }

    return ($parts -join "`n")
}

function Test-PythonImports {
    & $VenvPython -c "import flask, requests, pathvalidate, av; import playwright; import musicdl" *> $null
    return ($LASTEXITCODE -eq 0)
}

function Open-BrowserWhenReady {
    if ($NoBrowser) {
        return
    }

    $script = @"
for (`$i = 0; `$i -lt 30; `$i++) {
    try {
        `$response = Invoke-WebRequest -UseBasicParsing -TimeoutSec 1 -Uri "$Url/api/health"
        if (`$response.StatusCode -eq 200) {
            Start-Process "$Url"
            break
        }
    } catch {}
    Start-Sleep -Seconds 1
}
"@
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    Start-Process powershell -WindowStyle Hidden -ArgumentList "-NoProfile", "-EncodedCommand", $encoded | Out-Null
}

try {
    if (Test-AppHealth) {
        Write-Step "MusicGetter is already running at $Url"
        if (-not $NoBrowser) {
            Start-Process $Url
        }
        exit 0
    }

    Ensure-ExternalRepo -Path "musicdl" -RepoUrl "https://github.com/CharlesPikachu/musicdl.git" -Probe "musicdl\setup.py"
    Ensure-ExternalRepo -Path "amemv-crawler" -RepoUrl "https://github.com/loadchange/amemv-crawler.git" -Probe "amemv-crawler\fuck-byted-acrawler.js"

    if (-not (Test-Path $VenvPython)) {
        Write-Step "Creating Python virtual environment..."
        Invoke-BasePython -Arguments @("-m", "venv", $VenvDir)
        Assert-NativeSuccess "Failed to create the Python virtual environment."
    }

    if (Test-Path $VenvScripts) {
        $env:PATH = "$VenvScripts;$env:PATH"
    }

    $expectedFingerprint = Get-DependencyFingerprint
    $actualFingerprint = if (Test-Path $InstallStamp) { Get-Content $InstallStamp -Raw } else { "" }
    $needInstall = ($actualFingerprint.Trim() -ne $expectedFingerprint.Trim())

    if (-not $needInstall) {
        $needInstall = -not (Test-PythonImports)
    }

    if ($needInstall) {
        Write-Step "Installing Python dependencies..."
        & $VenvPython -m pip install -U pip
        Assert-NativeSuccess "Failed to upgrade pip."
        & $VenvPython -m pip install -r requirements-web.txt
        Assert-NativeSuccess "Failed to install Python dependencies."
        Set-Content -Path $InstallStamp -Value $expectedFingerprint -Encoding ASCII
    } else {
        Write-Step "Python dependencies are ready."
    }

    if (-not (Test-Command "node")) {
        Write-Note "Node.js was not found on PATH. The legacy Douyin fallback may be unavailable."
    }

    if (-not $SkipPlaywrightInstall -and -not (Test-Path $PlaywrightStamp)) {
        Write-Step "Installing Playwright Chromium. This can take a while on the first run..."
        & $VenvPython -m playwright install chromium
        if ($LASTEXITCODE -eq 0) {
            Set-Content -Path $PlaywrightStamp -Value (Get-Date).ToString("s") -Encoding ASCII
        } else {
            Write-Note "Playwright Chromium install failed. You can retry with: .\.venv\Scripts\python.exe -m playwright install chromium"
        }
    }

    if (Test-PortInUse) {
        if (Test-AppHealth) {
            Write-Step "MusicGetter is already running at $Url"
            if (-not $NoBrowser) {
                Start-Process $Url
            }
            exit 0
        }
        throw "Port $Port is already in use, but MusicGetter did not answer /api/health."
    }

    Write-Step "Starting MusicGetter at $Url"
    Open-BrowserWhenReady
    & $VenvPython app.py
} catch {
    Write-Host ""
    Write-Host "[MusicGetter] Startup failed:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
