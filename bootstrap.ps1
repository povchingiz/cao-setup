<#
  bootstrap.ps1 — Windows entry point for the CAO setup.

  Native Windows cannot run CAO (no tmux / POSIX ptys). This helper ensures
  WSL2 + Ubuntu are present, then runs the Linux bootstrap INSIDE WSL, on the
  WSL-native filesystem. It does not configure CAO itself — the real work is
  bootstrap.sh running in Ubuntu.

  Usage (from an Administrator PowerShell, in this repo folder):
      .\bootstrap.ps1

  It will:
    1. Verify / install WSL2 + Ubuntu (may require a reboot the first time).
    2. Clone this repo into the Ubuntu home (~/cao-setup) if not already there.
    3. Drop you into Ubuntu so you can set .env and run ./bootstrap.sh.

  No secrets are handled here. LOCAL_API_KEY is set later inside WSL, in .env.
#>

$ErrorActionPreference = 'Stop'

function Info($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Warn($m) { Write-Host "[!] $m"  -ForegroundColor Yellow }
function Ok($m)   { Write-Host "[ok] $m" -ForegroundColor Green }

Info "Checking for WSL..."
$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    Warn "WSL not found. Installing WSL2 + Ubuntu (requires admin; may reboot)."
    wsl --install -d Ubuntu
    Warn "If Windows asks to reboot, reboot, then open 'Ubuntu' from Start once"
    Warn "to create your Linux user, and re-run this script."
    exit 0
}

# Ensure a distro is actually installed (wsl.exe can exist with no distro).
$distros = (wsl.exe --list --quiet) 2>$null | Where-Object { $_ -and $_.Trim() -ne '' }
if (-not $distros -or ($distros -join '') -eq '') {
    Warn "WSL present but no Linux distro installed. Installing Ubuntu..."
    wsl --install -d Ubuntu
    Warn "Open 'Ubuntu' from Start once to create your user, then re-run this."
    exit 0
}
Ok "WSL distro(s): $($distros -join ', ')"

Info "Ensuring git + curl inside WSL..."
wsl.exe -e bash -lc "command -v git >/dev/null 2>&1 && command -v curl >/dev/null 2>&1 || (sudo apt-get update && sudo apt-get install -y git curl)"

# Determine this repo's git URL so we can clone it inside WSL home.
$repoUrl = ""
try { $repoUrl = (git config --get remote.origin.url) 2>$null } catch {}
if (-not $repoUrl) {
    Warn "Could not read this repo's origin URL from Windows git."
    Warn "Inside WSL, clone it manually into ~/cao-setup."
} else {
    Info "Cloning $repoUrl into WSL ~/cao-setup (if absent)..."
    $clone = "if [ ! -d `$HOME/cao-setup/.git ]; then git clone '$repoUrl' `$HOME/cao-setup; else echo 'already cloned'; fi"
    wsl.exe -e bash -lc "$clone"
}

Ok "WSL is ready."
Write-Host ""
Write-Host "Next, inside Ubuntu (this drops you in):" -ForegroundColor Cyan
Write-Host "    cd ~/cao-setup" -ForegroundColor White
Write-Host "    cp .env.example .env   # set LOCAL_API_KEY" -ForegroundColor White
Write-Host "    ./bootstrap.sh" -ForegroundColor White
Write-Host ""
Write-Host "Keep the repo in WSL home (/home/...), NOT on /mnt/c — see WINDOWS.md." -ForegroundColor Yellow
Write-Host ""

# Hand off into WSL home.
wsl.exe -e bash -lc "cd `$HOME/cao-setup 2>/dev/null || cd `$HOME; exec bash -l"
