# Jarvis systemd units (Linux)

User-level systemd unit templates for running Jarvis on a Linux box. These
mirror the Windows Startup-folder launchers in `scripts/install-services.ps1`
and add two PC-specific units (`jarvis-vllm.service` and
`jarvis-ollama.service`) that come into play once the dual-3090 PC is up.

## How to install

```bash
# From the project root:
bash scripts/install-services.sh

# Or pick a subset:
bash scripts/install-services.sh --units api,sentinel
```

The installer:

1. Renders the `*.service.in` templates with the local user's paths
   (`@JARVIS_ROOT@`, `@PYTHON@`, `@PNPM@`, `@VLLM@`, `@OLLAMA@`,
   `@API_PORT@`, `@WEB_PORT@`).
2. Writes the resolved units to `~/.config/systemd/user/`.
3. Reloads systemd (`systemctl --user daemon-reload`).
4. Enables + starts the requested units.

## How to uninstall

```bash
bash scripts/install-services.sh --uninstall
```

Stops + disables every Jarvis unit and removes the unit files. State under
`~/.local/share/jarvis/` is left untouched.

## How to inspect

```bash
systemctl --user status jarvis-api
systemctl --user status jarvis-sentinel
journalctl --user -u jarvis-sentinel -f      # follow logs

# Or read the log files directly:
tail -f ~/.local/share/jarvis/logs/sentinel.log
```

## Why user-level (not system-level)?

Jarvis is single-operator. It runs as your user, reads your `.env`, writes
state to your home directory, and listens on localhost only. There is no
multi-user contract. User-level units (under `~/.config/systemd/user/`)
require no root, are wiped if your account is removed, and don't fight with
the system package manager.

If you ever want a multi-user deployment, the same templates work as
system-level units with one tweak — replace `WantedBy=default.target` with
`WantedBy=multi-user.target` and install under `/etc/systemd/system/`.

## When to enable each unit

| Unit | Always on | Enable when |
|---|---|---|
| `jarvis-api` | yes | day one |
| `jarvis-sentinel` | yes | day one |
| `jarvis-dashboard` | optional | you want the web UI running by default |
| `jarvis-voice` | optional | `VOICE_ENABLED=true` in your env file |
| `jarvis-vllm` | dual-3090 only | local LLM migration (after PC arrival) |
| `jarvis-ollama` | dual-3090 only | local LLM migration (after PC arrival) |

## Notes on `linger`

User-level units only run when the user is logged in unless `loginctl
enable-linger $USER` is set. The bootstrap script enables linger by default
so Jarvis keeps running across logout/login cycles — the same behavior you
get from the Windows Startup folder.
