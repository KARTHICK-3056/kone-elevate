# --------------------------------------------------------------------------
# KONE ELEVATE - Windows task runner (the Makefile's equivalent)
#
# Run through the make.cmd wrapper, which works from cmd and PowerShell
# regardless of the script execution policy:
#
#   .\make doctor           check this machine has everything it needs
#   .\make install-prereqs  install missing Python / Node.js with winget
#   .\make setup            create backend\.venv + install all dependencies
#   .\make demo             committed models -> reseed -> demo accounts
#   .\make retrain          regenerate the dataset and retrain both models
#   .\make dev              run backend and frontend together
#   .\make start            one click (setup-and-run.cmd): set up whatever is
#                           missing, start both servers, open the web app
#   .\make stop             stop the servers `start` launched (stop.cmd)
#   .\make help             list every target
#
# Unlike the Makefile, every Python target runs inside backend\.venv, so
# nothing depends on which python.exe happens to be first on PATH.
#
# Targets only use what ships with Windows 10/11 (Windows PowerShell 5.1,
# cmd.exe, taskkill) plus Python and Node.js themselves.
#
# Environment overrides:
#   KE_PYTHON   interpreter used to create backend\.venv, e.g. "py -3.12"
#               or "C:\Python313\python.exe" (default: newest supported)
# --------------------------------------------------------------------------
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string] $Target = "help",
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)] [string[]] $Rest
)

$ErrorActionPreference = "Stop"
$Rest = @($Rest | Where-Object { $_ })
# This file lives in tools\windows\; the project root is two levels up.
$Root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).ProviderPath
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvDir = Join-Path $Backend ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

# Minimums. Python: backend\requirements.lock pins numpy 2.5 (needs 3.12+),
# and those exact pins are what make the committed models loadable.
# Node: vitest 5 / vite 8 engines ("^22.12.0 || >=24").
$MinPython = [version]"3.12"
$MinNode = [version]"22.12.0"
$BackendPort = 8000
$FrontendPort = 5173
$AppUrl = "http://localhost:$FrontendPort"

# Hash of the dependency manifest each install was made from, so `start`
# reinstalls only when requirements.lock / package-lock.json changed.
$BackendStamp = Join-Path $VenvDir ".ke-requirements.sha256"
$FrontendStamp = Join-Path $Frontend "node_modules\.ke-lock.sha256"
# PIDs of the server windows `start` opened, for `stop`.
$ServersFile = Join-Path $Root ".ke-servers.json"

# Scripts print box-drawing and non-ASCII text; never let a legacy console
# code page (437, 850, 1252, ...) turn that into a UnicodeEncodeError.
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
# Keep pip's "new version available" notice out of the setup output.
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

# ----------------------------------------------------------------- helpers
function Write-Ok([string] $m) { Write-Host "  [ok]   $m" -ForegroundColor Green }
function Write-Warn([string] $m) { Write-Host "  [warn] $m" -ForegroundColor Yellow }
function Write-Bad([string] $m) { Write-Host "  [FAIL] $m" -ForegroundColor Red }

function Invoke-Checked {
    param([string] $Exe, [string[]] $Arguments, [string] $WorkDir)
    Push-Location $WorkDir
    try {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "'$Exe $($Arguments -join ' ')' failed with exit code $LASTEXITCODE" }
    } finally { Pop-Location }
}

function Get-Sha([string] $Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return "" }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Test-StampCurrent([string] $Stamp, [string] $Manifest) {
    if (-not (Test-Path -LiteralPath $Stamp)) { return $false }
    return ((Get-Content -LiteralPath $Stamp -Raw).Trim() -eq (Get-Sha $Manifest))
}

function Test-Http([string] $Url) {
    # HttpWebRequest with no proxy: a corporate/system proxy must not
    # intercept localhost, and Invoke-WebRequest on PowerShell 5.1 needs
    # Internet Explorer's engine unless -UseBasicParsing is remembered.
    try {
        $req = [System.Net.HttpWebRequest]::Create($Url)
        $req.Proxy = $null
        $req.Timeout = 3000
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return ($code -ge 200 -and $code -lt 400)
    } catch { return $false }
}

function Get-LongPathWarning {
    # With Windows' 260-character MAX_PATH limit in force (the default unless
    # LongPathsEnabled=1), pip/npm fail on the deepest dependency files, which
    # sit ~150 characters below the project folder.
    try {
        $enabled = (Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    } catch { $enabled = 0 }
    if ($enabled -eq 1 -or $Root.Length -le 100) { return $null }
    return "The project path is $($Root.Length) characters long and Windows long paths are disabled, so installing dependencies may fail with 'path too long'. Move the folder somewhere shorter (e.g. C:\kone-elevate) or, as administrator, run: reg add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f"
}

function Update-SessionPath {
    # winget installs update the registry PATH, not this process's copy.
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Get-PythonInfo {
    # Returns @{ Cmd = @(exe, args...); Version = [version]; Arch = "AMD64" }
    # for a working interpreter, or $null. Catches the Microsoft Store
    # "python.exe" stub, which exists on PATH but only opens the Store.
    param([string[]] $Cmd)
    $exe = $Cmd[0]; $pre = @($Cmd | Select-Object -Skip 1)
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { return $null }
    try {
        $out = & $exe @pre -c "import sys, platform; print('%d.%d.%d %s' % (sys.version_info[:3] + (platform.machine(),)))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
        $parts = "$out".Trim().Split(" ")
        return @{ Cmd = $Cmd; Version = [version]$parts[0]; Arch = $parts[1] }
    } catch { return $null }
}

function Find-BasePython {
    if ($env:KE_PYTHON) {
        $cmd = if (Test-Path -LiteralPath $env:KE_PYTHON) { , $env:KE_PYTHON } else { $env:KE_PYTHON -split "\s+" }
        $info = Get-PythonInfo $cmd
        if (-not $info) { throw "KE_PYTHON='$env:KE_PYTHON' is not a working Python interpreter." }
        if ($info.Version -lt $MinPython) { throw "KE_PYTHON is Python $($info.Version); $MinPython or newer is required." }
        return $info
    }
    # Most-tested first (Python 3.13 locally, 3.12 in CI and Docker). 3.14 is
    # after them because brand-new interpreters can lag on scientific wheels.
    $candidates = @(
        @("py", "-3.13"), @("py", "-3.12"), @("py", "-3.14"),
        @("python3.13"), @("python3.12"), @("python3.14"),
        @("python"), @("python3"), @("py", "-3")
    )
    foreach ($c in $candidates) {
        $info = Get-PythonInfo $c
        if ($info -and $info.Version -ge $MinPython) { return $info }
    }
    return $null
}

function Get-NodeVersion {
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { return $null }
    try {
        $v = (& node --version 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        return [version]("$v".Trim().TrimStart("v"))
    } catch { return $null }
}

function Get-PortOwner([int] $Port) {
    # Name of the process listening on $Port, or $null if the port is free.
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction Stop | Select-Object -First 1
        $proc = Get-Process -Id $conn.OwningProcess -ErrorAction SilentlyContinue
        if ($proc) { return "$($proc.ProcessName) (PID $($conn.OwningProcess))" }
        return "PID $($conn.OwningProcess)"
    } catch [Microsoft.PowerShell.Cmdletization.Cim.CimJobException] {
        return $null  # "No matching MSFT_NetTCPConnection objects" = free
    } catch {
        # Get-NetTCPConnection unavailable (stripped-down images): netstat.
        # Match the 0.0.0.0:0 / [::]:0 foreign address, not the word
        # "LISTENING", which netstat translates on non-English Windows.
        $hit = & netstat.exe -ano | Select-String -Pattern "^\s*TCP\s+\S+:$Port\s+(?:0\.0\.0\.0:0|\[::\]:0)\s+\S+\s+(\d+)\s*$"
        if ($hit) { return "PID $($hit[0].Matches[0].Groups[1].Value)" }
        return $null
    }
}

function Assert-PortFree([int] $Port, [string] $What) {
    $owner = Get-PortOwner $Port
    if ($owner) {
        throw "Port $Port ($What) is already in use by $owner. Stop it first, e.g.: taskkill /PID <pid> /T /F"
    }
}

function Test-VenvHealthy {
    if (-not (Test-Path -LiteralPath $VenvPython)) { return $false }
    # The venv's python.exe is a launcher pointing at its base interpreter;
    # it fails if that interpreter was uninstalled or the venv was copied
    # from another machine.
    try {
        & $VenvPython -c "import sys" 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch { return $false }
}

function Assert-Venv {
    if (-not (Test-VenvHealthy)) {
        throw "backend\.venv is missing or broken (created on another machine/OS?). Run '.\make setup' first."
    }
}

function Assert-Node {
    $node = Get-NodeVersion
    if (-not $node) { throw "Node.js not found. Install Node.js $MinNode+ (LTS) - or run '.\make install-prereqs'." }
    if ($node -lt $MinNode) { throw "Node.js $node is too old; $MinNode+ is required (vite 8 / vitest 5). Install the current LTS from https://nodejs.org/ or run '.\make install-prereqs'." }
}

function Py { param([string[]] $Arguments) Assert-Venv; Invoke-Checked $VenvPython $Arguments $Backend }
function Npm { param([string[]] $Arguments) Assert-Node; Invoke-Checked "npm.cmd" $Arguments $Frontend }

# ----------------------------------------------------------------- targets
function Invoke-Doctor {
    $failed = $false
    Write-Host ""
    Write-Host "KONE ELEVATE - environment check"
    Write-Host "--------------------------------------------------------------"
    $os = [Environment]::OSVersion.Version
    Write-Ok "Windows $os, $env:PROCESSOR_ARCHITECTURE, PowerShell $($PSVersionTable.PSVersion)"
    if ($os.Build -lt 17763) { Write-Warn "Windows 10 1809 or newer is recommended." }
    $longPath = Get-LongPathWarning
    if ($longPath) { Write-Warn $longPath }

    $py = Find-BasePython
    if ($py) {
        Write-Ok "Python $($py.Version) ($($py.Arch)) via '$($py.Cmd -join ' ')'"
        if ($py.Arch -eq "ARM64") {
            Write-Warn "ARM64 Python: some ML packages (numba/shap) may have no ARM64 wheels. If setup fails, install x64 Python - it runs under Windows emulation."
        }
    } else {
        Write-Bad "Python $MinPython+ not found. Run '.\make install-prereqs' or install from https://www.python.org/downloads/ (tick 'Add python.exe to PATH')."
        $failed = $true
    }

    $node = Get-NodeVersion
    if (-not $node) { Write-Bad "Node.js not found. Run '.\make install-prereqs' or install the LTS from https://nodejs.org/"; $failed = $true }
    elseif ($node -lt $MinNode) { Write-Bad "Node.js $node is too old; $MinNode+ required. Install the current LTS from https://nodejs.org/"; $failed = $true }
    else { Write-Ok "Node.js $node" }

    if (Get-Command npm.cmd -ErrorAction SilentlyContinue) { Write-Ok "npm $((& npm.cmd --version) | Select-Object -First 1)" }
    elseif ($node) { Write-Bad "npm not found (it ships with Node.js - reinstall Node)."; $failed = $true }

    if (Get-Command git -ErrorAction SilentlyContinue) { Write-Ok "$(& git --version)" } else { Write-Warn "git not found (only needed to clone/commit)." }
    if (Get-Command docker -ErrorAction SilentlyContinue) { Write-Ok "docker available (optional)" } else { Write-Warn "docker not found (optional - only for .\make docker-up)." }

    if (Test-VenvHealthy) { Write-Ok "backend\.venv ready" }
    elseif (Test-Path -LiteralPath $VenvDir) { Write-Warn "backend\.venv is broken or from another OS - '.\make setup' will rebuild it." }
    else { Write-Warn "backend\.venv not created yet - run '.\make setup'." }

    if (Test-Path -LiteralPath (Join-Path $Frontend "node_modules\.package-lock.json")) { Write-Ok "frontend\node_modules installed" }
    else { Write-Warn "frontend\node_modules not installed - run '.\make setup'." }

    if ((Test-Path -LiteralPath (Join-Path $Backend ".env")) -or (Test-Path -LiteralPath (Join-Path $Root ".env"))) { Write-Ok ".env present" }
    else { Write-Warn "no .env yet - '.\make setup' creates backend\.env from .env.example." }

    $model = Join-Path $Backend "models\random_forest.joblib"
    if (Test-Path -LiteralPath $model) { Write-Ok "trained model present (verify with .\make check-models)" } else { Write-Warn "no trained model - run '.\make models'." }

    foreach ($p in @(@($BackendPort, "backend"), @($FrontendPort, "frontend"))) {
        $owner = Get-PortOwner $p[0]
        if ($owner) { Write-Warn "port $($p[0]) ($($p[1])) in use by $owner" } else { Write-Ok "port $($p[0]) ($($p[1])) free" }
    }
    Write-Host ""
    if ($failed) { throw "Missing prerequisites (see [FAIL] above)." }
    Write-Host "All required tools found." -ForegroundColor Green
}

function Invoke-InstallPrereqs {
    param([switch] $Continue)
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "winget is not available on this machine. Install manually: Python 3.13 from https://www.python.org/downloads/ (tick 'Add python.exe to PATH') and Node.js LTS from https://nodejs.org/"
    }
    if (-not (Find-BasePython)) {
        Write-Host "Installing Python 3.13 with winget..."
        & winget install -e --id Python.Python.3.13 --source winget
        if ($LASTEXITCODE -ne 0) { throw "winget could not install Python (exit $LASTEXITCODE)." }
    } else { Write-Ok "Python already installed" }

    $node = Get-NodeVersion
    if (-not $node) {
        Write-Host "Installing Node.js LTS with winget..."
        & winget install -e --id OpenJS.NodeJS.LTS --source winget
        if ($LASTEXITCODE -ne 0) { throw "winget could not install Node.js (exit $LASTEXITCODE)." }
    } elseif ($node -lt $MinNode) {
        Write-Host "Upgrading Node.js $node with winget..."
        & winget upgrade -e --id OpenJS.NodeJS.LTS --source winget
        if ($LASTEXITCODE -ne 0) {
            throw "Could not upgrade Node.js $node automatically (it may have been installed another way, e.g. nvm). Install $MinNode+ from https://nodejs.org/"
        }
    } else { Write-Ok "Node.js $node already installed" }

    Update-SessionPath
    if ($Continue) { return }
    Write-Host ""
    Write-Host "Done. Open a NEW terminal (so PATH is refreshed), then run: .\make setup" -ForegroundColor Green
}

function Test-PrereqsOk {
    $node = Get-NodeVersion
    return ((Find-BasePython) -or (Test-VenvHealthy)) -and $node -and ($node -ge $MinNode)
}

function Start-ServerWindow([string] $Title, [string] $WorkDir, [string] $Command) {
    # cmd /k keeps the window (and any crash output) open; /s makes cmd
    # strip exactly the outer quotes so quoted paths inside survive.
    $p = Start-Process -PassThru -WindowStyle Minimized -WorkingDirectory $WorkDir -FilePath "cmd.exe" `
        -ArgumentList "/s /k `"title $Title & $Command`""
    return @{ pid = $p.Id; started = "$($p.StartTime.Ticks)" }
}

function Invoke-EnsureModels {
    # The trained models are committed, so a new machine normally uses them
    # as-is. Retrain only when they are missing or were pickled by different
    # scikit-learn/joblib versions than backend\requirements.lock installed.
    Assert-Venv
    Push-Location $Backend
    try { & $VenvPython scripts/check_models.py; $code = $LASTEXITCODE } finally { Pop-Location }
    if ($code -eq 0) { Write-Ok "using the committed models - no training needed"; return }
    Write-Warn "Committed models are missing or incompatible with the installed libraries - retraining (a few minutes)."
    if (-not (Test-Path -LiteralPath (Join-Path $Backend "data\synthetic\dataset.csv"))) { Run "data" }
    Run "train"
    Run "train-forecast"
}

function Invoke-Start {
    $noWait = $Rest -contains "--no-wait"
    $noBrowser = $Rest -contains "--no-browser"
    # These flags are start's own; the sub-targets it runs (data, train, ...)
    # forward $Rest to their scripts, which would reject them.
    $script:Rest = @()
    Write-Host ""
    Write-Host "KONE ELEVATE - one-click setup and run" -ForegroundColor Cyan
    Write-Host "--------------------------------------------------------------"

    # Already up (a second double-click)? Just open the browser.
    if ((Test-Http "http://127.0.0.1:$BackendPort/") -and (Test-Http $AppUrl)) {
        Write-Ok "Servers are already running."
        if (-not $noBrowser) { Start-Process $AppUrl }
        Write-Host "Opened $AppUrl  (stop them with stop.cmd or .\make stop)"
        return
    }
    Assert-PortFree $BackendPort "backend"
    Assert-PortFree $FrontendPort "frontend"

    # 1. Tools
    Write-Host "[1/5] Checking Python and Node.js ..." -ForegroundColor Cyan
    if (-not (Test-PrereqsOk)) {
        Write-Host "Python $MinPython+ and/or Node.js $MinNode+ are missing - installing them with winget." -ForegroundColor Yellow
        Write-Host "(Windows may ask for permission; accept to continue.)"
        Invoke-InstallPrereqs -Continue
        if (-not (Test-PrereqsOk)) {
            throw "Python/Node.js were installed but are not visible to this window yet. Close this window and run setup-and-run.cmd again."
        }
    }
    Write-Ok "tools ready"
    $longPath = Get-LongPathWarning
    if ($longPath) { Write-Warn $longPath }

    # 2. Dependencies - only when missing or the manifest changed.
    Write-Host "[2/5] Installing dependencies (first run takes a few minutes) ..." -ForegroundColor Cyan
    if (-not (Test-VenvHealthy) -or -not (Test-StampCurrent $BackendStamp (Join-Path $Backend "requirements.lock"))) {
        Run "setup-backend"
    } else { Write-Ok "backend dependencies up to date" }
    if (-not (Test-StampCurrent $FrontendStamp (Join-Path $Frontend "package-lock.json"))) {
        Run "setup-frontend"
    } else { Write-Ok "frontend dependencies up to date" }

    # 3. Models - trained once, reused afterwards.
    Write-Host "[3/5] Checking the ML models ..." -ForegroundColor Cyan
    Invoke-EnsureModels

    # 4. Demo data - both scripts leave an existing database untouched.
    Write-Host "[4/5] Preparing demo data and sign-in accounts ..." -ForegroundColor Cyan
    Py @("scripts/seed_database.py", "--quiet")
    Py @("scripts/seed_users.py") | Out-Null
    Write-Ok "database ready"

    # 5. Servers
    Write-Host "[5/5] Starting servers ..." -ForegroundColor Cyan
    $servers = @{
        backend  = Start-ServerWindow "KONE ELEVATE backend" $Backend "`"$VenvPython`" -m uvicorn app.main:app --host 127.0.0.1 --port $BackendPort"
        frontend = Start-ServerWindow "KONE ELEVATE frontend" $Frontend "npm.cmd run dev"
    }
    $servers | ConvertTo-Json | Set-Content -LiteralPath $ServersFile -Encoding ASCII

    $deadline = (Get-Date).AddSeconds(120)
    $backendUp = $false; $frontendUp = $false
    while ((Get-Date) -lt $deadline -and -not ($backendUp -and $frontendUp)) {
        Start-Sleep -Milliseconds 700
        if (-not $backendUp) { $backendUp = Test-Http "http://127.0.0.1:$BackendPort/" }
        if (-not $frontendUp) { $frontendUp = Test-Http $AppUrl }
        foreach ($name in "backend", "frontend") {
            if (-not (Get-Process -Id $servers[$name].pid -ErrorAction SilentlyContinue)) {
                throw "The $name server window closed unexpectedly. Run '.\make $name' to see the error."
            }
        }
    }
    if (-not $backendUp) { throw "Backend did not answer on port $BackendPort within 2 minutes - check the 'KONE ELEVATE backend' window." }
    if (-not $frontendUp) { throw "Frontend did not answer on port $FrontendPort within 2 minutes - check the 'KONE ELEVATE frontend' window." }

    if (-not $noBrowser) { Start-Process $AppUrl }
    Write-Host ""
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host " KONE ELEVATE is running" -ForegroundColor Green
    Write-Host "   Web app : $AppUrl"
    Write-Host "   API docs: http://localhost:$BackendPort/docs"
    Write-Host "   Sign in : pick a demo account on the sign-in screen"
    Write-Host "             password elevate-demo-2026"
    Write-Host "==============================================================" -ForegroundColor Green
    Write-Host "The two servers run in minimized 'KONE ELEVATE' windows."
    if ($noWait) { Write-Host "Stop them later with stop.cmd or .\make stop"; return }
    Write-Host ""
    Read-Host "Press Enter here to stop both servers (or just close this window to leave them running)" | Out-Null
    Invoke-Stop
}

function Invoke-Stop {
    if (-not (Test-Path -LiteralPath $ServersFile)) {
        Write-Host "No servers started by setup-and-run.cmd are recorded as running."
        foreach ($p in $BackendPort, $FrontendPort) {
            $owner = Get-PortOwner $p
            if ($owner) { Write-Warn "port $p is in use by $owner (not started by this launcher - left alone)" }
        }
        return
    }
    $servers = Get-Content -LiteralPath $ServersFile -Raw | ConvertFrom-Json
    foreach ($name in "backend", "frontend") {
        $entry = $servers.$name
        if (-not $entry) { continue }
        $proc = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
        # Compare start times so a recycled PID never kills an unrelated process.
        if ($proc -and "$($proc.StartTime.Ticks)" -eq "$($entry.started)") {
            & taskkill.exe /PID $entry.pid /T /F | Out-Null
            Write-Ok "stopped $name"
        } else {
            Write-Ok "$name was not running"
        }
    }
    Remove-Item -LiteralPath $ServersFile -Force
}

function Invoke-SetupBackend {
    if ((Test-Path -LiteralPath $VenvDir) -and -not (Test-VenvHealthy)) {
        Write-Host "backend\.venv is broken or was not created on this machine - recreating it." -ForegroundColor Yellow
        Remove-Item -Recurse -Force -LiteralPath $VenvDir
    }
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        $py = Find-BasePython
        if (-not $py) { throw "Python $MinPython+ not found. Run '.\make install-prereqs' or install from https://www.python.org/downloads/" }
        $exe = $py.Cmd[0]; $pre = @($py.Cmd | Select-Object -Skip 1)
        Write-Host "Creating backend\.venv with Python $($py.Version) ($($py.Cmd -join ' '))"
        Invoke-Checked $exe ($pre + @("-m", "venv", ".venv")) $Backend
    }
    Py @("-m", "pip", "install", "--upgrade", "pip")
    # The lock, not requirements.txt: the committed models only load under the
    # exact scikit-learn/joblib versions that trained them.
    Py @("-m", "pip", "install", "-r", "requirements.lock")
    Set-Content -LiteralPath $BackendStamp -Value (Get-Sha (Join-Path $Backend "requirements.lock")) -Encoding ASCII
    $envFile = Join-Path $Backend ".env"
    $example = Join-Path $Root ".env.example"
    if (-not (Test-Path -LiteralPath $envFile) -and -not (Test-Path -LiteralPath (Join-Path $Root ".env")) -and (Test-Path -LiteralPath $example)) {
        Copy-Item -LiteralPath $example -Destination $envFile
        Write-Host "Created backend\.env from .env.example (development defaults, no SMTP)." -ForegroundColor Yellow
    }
}

function Invoke-SetupFrontend {
    Assert-Node
    # A running Vite server holds its native binaries open, and Windows will
    # not let npm replace a file that is open.
    Assert-PortFree $FrontendPort "the Vite dev server - stop it before reinstalling"
    # node_modules copied from another OS carries the wrong native
    # esbuild/rolldown binaries; npm ci always rebuilds from the lockfile.
    Npm @("ci", "--no-fund", "--no-audit")
    Set-Content -LiteralPath $FrontendStamp -Value (Get-Sha (Join-Path $Frontend "package-lock.json")) -Encoding ASCII
}

function Invoke-Dev {
    Assert-Venv
    Assert-Node
    Assert-PortFree $BackendPort "backend"
    Assert-PortFree $FrontendPort "frontend"
    Write-Host "Backend  -> http://localhost:$BackendPort/docs  (separate window)"
    Write-Host "Frontend -> http://localhost:$FrontendPort"
    $backendProc = Start-Process -PassThru -WorkingDirectory $Backend -FilePath $VenvPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "$BackendPort"
    try { Npm @("run", "dev") }
    finally {
        if (-not $backendProc.HasExited) {
            # /T also stops uvicorn's --reload worker process.
            & taskkill.exe /PID $backendProc.Id /T /F | Out-Null
        }
    }
}

$Targets = [ordered]@{
    "help"            = @("Show this help", { Show-Help })
    "doctor"          = @("Check Python, Node.js, ports and project state", { Invoke-Doctor })
    "install-prereqs" = @("Install missing Python 3.13 / Node.js LTS with winget", { Invoke-InstallPrereqs })
    "setup"           = @("Create backend\.venv and install all dependencies", { Run "setup-backend"; Run "setup-frontend" })
    "setup-backend"   = @("Create backend\.venv (if needed) and install Python deps", { Invoke-SetupBackend })
    "setup-frontend"  = @("Install Node dependencies (npm ci)", { Invoke-SetupFrontend })
    "data"            = @("Generate the synthetic degradation dataset", { Py (@("scripts/generate_data.py") + $Rest) })
    "train"           = @("Train, evaluate and save the Random Forest model", { Py (@("scripts/train_model.py") + $Rest) })
    "train-forecast"  = @("Train the Weibull end-of-life forecast model", { Py (@("scripts/train_forecast.py") + $Rest) })
    "migrate"         = @("Apply database migrations", { Py @("-m", "alembic", "upgrade", "head") })
    "migration"       = @("Create a migration: .\make migration `"add x`"", { Py @("-m", "alembic", "revision", "--autogenerate", "-m", ($Rest -join " ")) })
    "seed"            = @("Seed the demo portfolio (60 components)", { Py (@("scripts/seed_database.py") + $Rest) })
    "reset-seed"      = @("Drop everything and reseed from scratch", { Py @("scripts/seed_database.py", "--reset") })
    "seed-users"      = @("Create the five demo sign-in accounts", { Py @("scripts/seed_users.py") })
    "verify-chain"    = @("Verify the SHA-256 audit chain", { Py @("scripts/verify_chain.py") })
    "models"          = @("Use the committed models; retrain only if missing/incompatible", { Invoke-EnsureModels })
    "retrain"         = @("Regenerate the dataset and retrain both models", {
        foreach ($t in "data", "train", "train-forecast") { Run $t }
    })
    "check-models"    = @("Check the model files load under the installed versions", { Py @("scripts/check_models.py") })
    "demo"            = @("Demo prep: check models, reseed components, demo accounts", {
        foreach ($t in "models", "reset-seed", "seed-users") { Run $t }
        Write-Host ""
        Write-Host "Demo data ready. Start the stack with: .\make dev" -ForegroundColor Green
        Write-Host "Sign in at http://localhost:$FrontendPort - password for every demo account: elevate-demo-2026"
    })
    "all"             = @("First run: setup + demo + test", { Run "setup"; Run "demo"; Run "test" })
    "start"           = @("One click: install what is missing, start both servers, open the app", { Invoke-Start })
    "stop"            = @("Stop the servers 'start' launched", { Invoke-Stop })
    "backend"         = @("Run the FastAPI server (http://localhost:8000)", {
        Assert-PortFree $BackendPort "backend"
        Py @("-m", "uvicorn", "app.main:app", "--reload", "--host", "0.0.0.0", "--port", "$BackendPort")
    })
    "frontend"        = @("Run the Vite dev server (http://localhost:5173)", {
        Assert-PortFree $FrontendPort "frontend"
        Npm @("run", "dev")
    })
    "dev"             = @("Run backend (new window) and frontend (this window)", { Invoke-Dev })
    "test"            = @("Run every test suite", { Run "test-backend"; Run "test-frontend" })
    "test-backend"    = @("Run the pytest suite", { Py (@("-m", "pytest", "-q") + $Rest) })
    "test-frontend"   = @("Run the Vitest suite", { Npm @("run", "test") })
    "build"           = @("Production build of the frontend", { Npm @("run", "build") })
    "lint"            = @("Lint the frontend", { Npm @("run", "lint") })
    "docker-up"       = @("Start the whole stack with Docker Compose", { Invoke-Checked "docker" @("compose", "up", "--build") $Root })
    "docker-down"     = @("Stop the stack", { Invoke-Checked "docker" @("compose", "down") $Root })
    "docker-rebuild"  = @("Rebuild images from scratch and start", {
        Invoke-Checked "docker" @("compose", "build", "--no-cache") $Root
        Invoke-Checked "docker" @("compose", "up") $Root
    })
    "docker-logs"     = @("Tail service logs", { Invoke-Checked "docker" @("compose", "logs", "-f") $Root })
    "clean"           = @("Remove caches, build output and the SQLite database", {
        Get-ChildItem -LiteralPath $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notlike "*\.venv\*" -and $_.FullName -notlike "*\node_modules\*" } |
            Remove-Item -Recurse -Force
        foreach ($p in "backend\.pytest_cache", "frontend\dist", "frontend\dev-dist", "frontend\.vite", "backend\kone_elevate.db") {
            $full = Join-Path $Root $p
            if (Test-Path -LiteralPath $full) { Remove-Item -Recurse -Force -LiteralPath $full }
        }
        Write-Host "Cleaned. Regenerate the model and demo data with: .\make demo"
    })
}

function Show-Help {
    Write-Host ""
    Write-Host "KONE ELEVATE - Component Passport (prototype)  [Windows]"
    Write-Host "--------------------------------------------------------------"
    foreach ($k in $Targets.Keys) { Write-Host ("  {0,-18} {1}" -f $k, $Targets[$k][0]) }
    Write-Host ""
    Write-Host "First time on this machine:  .\make doctor   then   .\make all"
    Write-Host ""
}

function Run([string] $Name) {
    if (-not $Targets.Contains($Name)) { throw "Unknown target '$Name'. Run '.\make help'." }
    Write-Host "==> $Name" -ForegroundColor Cyan
    & $Targets[$Name][1]
}

try { Run $Target } catch { Write-Host "ERROR: $_" -ForegroundColor Red; exit 1 }
