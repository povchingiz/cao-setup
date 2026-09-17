# Windows

**Native Windows is not supported.** CAO drives worker CLIs through **tmux** and
uses POSIX terminal APIs (`fifo` / `pty` / `termios`) that do not exist on native
Windows. There is no tmux backend for `cmd.exe` or PowerShell, so `cao-server`
cannot spawn or read worker terminals there.

## The supported path: WSL2

Run everything inside **WSL2 (Ubuntu)**. Inside WSL it is a real Linux
environment, so the Linux bootstrap in this repo works unchanged.

### 1. Install WSL2 + Ubuntu (once)

In an **Administrator PowerShell**:

```powershell
wsl --install -d Ubuntu
```

Reboot if asked, then open **Ubuntu** from the Start menu and create your Linux
user. (Or run `.\bootstrap.ps1` from this repo — it does this step for you.)

### 2. Work inside the WSL HOME filesystem — NOT /mnt/c

This is the one thing that matters for paths.

- **Do:** clone and run under your Linux home, e.g. `~/cao-setup`
  (`/home/<you>/cao-setup`). All setup paths are `$HOME`-relative
  (`~/.aws`, `~/.config`, `~/.local`) and resolve to the **native** WSL
  filesystem — fast, normal POSIX permissions, identical to plain Ubuntu.
- **Don't:** `cd /mnt/c/Users/...` and run there. `/mnt/c` is the mounted
  Windows drive: slow I/O and broken Unix permissions/symlinks. tmux, uv, and
  the pyte patch all misbehave from `/mnt/c`. This repo contains **no** `/mnt`
  paths; the only way you'd touch it is by putting the clone there yourself.

Quick check you are in the right place:

```bash
pwd          # should start with /home/…  (NOT /mnt/…)
echo "$HOME" # /home/<you>
```

### 3. Run the Linux bootstrap

Inside Ubuntu (WSL):

```bash
sudo apt-get update && sudo apt-get install -y git curl
git clone <this-repo> ~/cao-setup
cd ~/cao-setup
cp .env.example .env    # set LOCAL_API_KEY
./bootstrap.sh
```

Then the interactive logins and `cao-run` — exactly the Linux flow in the main
README.

## Browser logins from WSL

`codex login` and the Antigravity (`agy`) Google sign-in open a browser. WSL2 can
open the Windows browser if `wslu` is installed:

```bash
sudo apt-get install -y wslu
```

If a login still doesn't pop a browser, it prints a URL — copy it into your
Windows browser, complete the sign-in, and the CLI finishes. Tokens are stored
inside WSL (`~/.codex/auth.json`, `~/.gemini/...`), so you log in once per WSL
distro.

## Editing config from Windows (optional)

You can edit `~/cao-setup/cao.config.toml` with VS Code on Windows via the
**WSL extension** (`code .` from inside `~/cao-setup` opens it in the WSL
context, keeping files on the Linux filesystem). Do not copy the repo onto a
`C:\` path to edit it — keep it in WSL home and edit in place.
