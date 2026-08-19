<#
.SYNOPSIS
    Install hanzidraw on Windows. Idempotent: safe to re-run.

.DESCRIPTION
    Installs uv (which supplies the right Python), installs hanzidraw with the GUI
    and mouse extras, puts the character database in place, and verifies the result.

.PARAMETER Db
    Import a prebuilt database instead of downloading: a .sqlite or .sqlite.gz file.

.PARAMETER NoData
    Skip the database step. Run 'hanzidraw fetch-data' yourself later.

.PARAMETER NoExtras
    Base install only: no drawing window (PySide6), no mouse backend (pynput).

.PARAMETER Yes
    Never prompt. Assume yes to installing uv and to downloading the datasets.

.EXAMPLE
    .\install.ps1
.EXAMPLE
    .\install.ps1 -Db .\hanzidraw.sqlite.gz -Yes
#>
[CmdletBinding()]
param(
    [string] $Db,
    [switch] $NoData,
    [switch] $NoExtras,
    [switch] $Yes,
    # PySide6 has no wheels for 3.13+ yet. Do not "upgrade" this without checking.
    [string] $Python = '3.12'
)

$ErrorActionPreference = 'Stop'
$Here     = Split-Path -Parent $PSCommandPath
$Extras   = if ($NoExtras) { '' } else { '[gui,mouse]' }
$RepoUrl  = 'https://github.com/xiangfengyepan/hanzidraw'

function Say  { param([string]$m) Write-Host "==> $m" -ForegroundColor Cyan }
function Warn { param([string]$m) Write-Host "warning: $m" -ForegroundColor Yellow }
function Die  { param([string]$m) Write-Host "error: $m" -ForegroundColor Red; exit 1 }

function Ask {
    param([string]$Question)
    if ($Yes) { return $true }
    # A non-interactive host must not hang waiting for input.
    if ([Console]::IsInputRedirected) { Warn "not interactive, assuming no: $Question"; return $false }
    $reply = Read-Host "$Question [y/N]"
    return $reply -match '^[yY]'
}

function Refresh-Path {
    # uv installs to %USERPROFILE%\.local\bin, which an already-open shell does not
    # know about yet. Add it for this session so the rest of the script can proceed.
    $userBin = Join-Path $env:USERPROFILE '.local\bin'
    if (Test-Path $userBin) { $env:PATH = "$userBin;$env:PATH" }
    $machine = [Environment]::GetEnvironmentVariable('PATH', 'Machine')
    $user    = [Environment]::GetEnvironmentVariable('PATH', 'User')
    $env:PATH = (@($env:PATH, $machine, $user) | Where-Object { $_ }) -join ';'
}

# ------------------------------------------------------------------ uv
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Say 'uv is not installed. It manages the Python version and installs the app.'
    if (-not (Ask 'Install uv from https://astral.sh/uv (official installer)?')) {
        Die 'uv is required. Install it yourself, then re-run this script.'
    }
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    Refresh-Path
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Die 'uv installed but not on PATH. Open a new PowerShell window and re-run this script.'
}
Say "uv $((uv --version) -split ' ' | Select-Object -Index 1)"

# --------------------------------------------------------- install the app
# Prefer this checkout, then a wheel next to the script, then GitHub.
$wheel = Get-ChildItem -Path $Here -Filter 'hanzidraw-*.whl' -ErrorAction SilentlyContinue | Select-Object -First 1
if (Test-Path (Join-Path $Here 'pyproject.toml')) {
    $target = $Here;             $source = 'this checkout'
} elseif ($wheel) {
    $target = $wheel.FullName;   $source = $wheel.Name
} else {
    $target = "git+$RepoUrl";    $source = $RepoUrl
}
Say "installing hanzidraw$Extras from $source"
# VIRTUAL_ENV would divert the install into an activated venv instead of a tool.
$savedVenv = $env:VIRTUAL_ENV
$env:VIRTUAL_ENV = $null
try {
    uv tool install --force --python $Python "$target$Extras"
    if ($LASTEXITCODE -ne 0) { Die "uv tool install failed (exit $LASTEXITCODE)" }
} finally {
    $env:VIRTUAL_ENV = $savedVenv
}
Refresh-Path

# ---------------------------------------------------------- the database
$dbDir = Join-Path $env:LOCALAPPDATA 'hanzidraw'
$dbPath = Join-Path $dbDir 'hanzidraw.sqlite'

function Import-Database {
    param([string]$From)
    if (-not (Test-Path $From)) { Die "no such file: $From" }
    New-Item -ItemType Directory -Force -Path $dbDir | Out-Null
    $tmp = "$dbPath.tmp"
    Say "importing $(Split-Path -Leaf $From)"
    if ($From -like '*.gz') {
        # No gzip on stock Windows, so unpack with .NET rather than a shell tool.
        $in  = [System.IO.File]::OpenRead($From)
        $gz  = New-Object System.IO.Compression.GZipStream($in, [System.IO.Compression.CompressionMode]::Decompress)
        $out = [System.IO.File]::Create($tmp)
        try { $gz.CopyTo($out) } finally { $out.Dispose(); $gz.Dispose(); $in.Dispose() }
    } else {
        Copy-Item -Path $From -Destination $tmp -Force
    }
    Move-Item -Path $tmp -Destination $dbPath -Force   # swap in only once whole
}

if ($NoData) {
    Say "skipping the database step. Run 'hanzidraw fetch-data' when you want it."
} elseif ($Db) {
    Import-Database -From $Db
} elseif (Test-Path $dbPath) {
    $mb = [math]::Round((Get-Item $dbPath).Length / 1MB, 1)
    Say "database already present: $dbPath ($mb MB)"
} else {
    $local = @('hanzidraw.sqlite.gz', 'hanzidraw.sqlite') |
             ForEach-Object { Join-Path $Here $_ } | Where-Object { Test-Path $_ } | Select-Object -First 1
    if ($local) {
        Say "found a prebuilt database next to this script"
        Import-Database -From $local
    } elseif (Ask 'Download the datasets and build the database (~40 MB, roughly 20 minutes)?') {
        hanzidraw fetch-data
    } else {
        Warn "skipped. Run 'hanzidraw fetch-data' before using the app."
    }
}

# ------------------------------------------------------------- verify
Say 'verifying'
hanzidraw --version
if (Test-Path $dbPath) {
    $out = Join-Path ([System.IO.Path]::GetTempPath()) 'hanzidraw-check.svg'
    # Built from codepoints on purpose: this file stays pure ASCII so Windows
    # PowerShell 5.1, which reads a UTF-8 file without a BOM as ANSI, cannot
    # garble the characters. These are the four name characters the test suite
    # pins: U+6CA3 U+6F58 U+53F6 U+7965.
    $sample = -join (0x6CA3, 0x6F58, 0x53F6, 0x7965 | ForEach-Object { [char]::ConvertFromUtf32($_) })
    hanzidraw draw $sample -o $out 2>&1 | Out-Null
    if (Test-Path $out) {
        $n = ([regex]::Matches((Get-Content -Raw $out), '<polyline')).Count
        Write-Host "    rendered a test glyph sheet: $n polylines"
        Remove-Item $out -Force
    } else {
        Warn 'the test render failed; the app is installed but something is wrong with the database'
    }
}

Write-Host @'

Installed. Start the drawing window with:

    hanzidraw

Type pinyin, pick a candidate with the number keys, and the character is drawn
stroke by stroke. Ctrl+L clears, Ctrl+Z undoes, Ctrl+S saves a PNG.
Settings: %APPDATA%\hanzidraw\config.toml (reloads while running).

Windows note: to abort a mouse-backend draw use Esc. Ctrl+. is documented too,
but only Esc is verified on Windows -- the Win32 key backend usually reports
Ctrl+. without a character, so the listener can miss it.
'@
