# Jarvis on Phone — Free Setup

End state: PWA on home screen, full Mission Control over Tailscale, free push via ntfy. PC must be powered on and on tailnet.

---

## 1. Tailscale (free, 100 devices)

1. Sign up: https://login.tailscale.com/start (use Google/Apple/Microsoft SSO).
2. **PC:** install desktop client → https://tailscale.com/download/windows. Sign in.
3. **Phone:** install Tailscale app — App Store / Play Store. Sign in same account.
4. Verify: in PowerShell, `tailscale status` lists both devices. Note your PC's tailnet hostname (e.g. `pc-name.tail-abcde.ts.net`).

Both devices now see each other on a private VPN, even off home Wi-Fi.

---

## 2. ntfy push (free, no account)

1. Phone: install **ntfy** — App Store / Play Store.
2. Pick a long random topic name (≥ 20 chars). This is your **only secret** — anyone who guesses it can push to your phone.
   ```
   jarvis-XXXXXXXXXXXXXXXX
   ```
3. In the ntfy app: **Add subscription** → enter the topic name. Leave server `ntfy.sh`.
4. Add to `.env` at project root:
   ```
   NTFY_TOPIC=jarvis-XXXXXXXXXXXXXXXX
   NTFY_SERVER=https://ntfy.sh
   ```

---

## 3. First boot

```pwsh
cd C:\Users\jyot2\jarvis
pwsh -File scripts/phone-setup.ps1            # dev mode
# or
pwsh -File scripts/phone-setup.ps1 -Mode prod # prod build (faster on phone)
```

The script:
- detects your tailnet hostname
- generates `web/.env.local` with a random `MC_API_TOKEN` (printed to console — copy it)
- writes `JARVIS_CORS_ORIGINS` for FastAPI
- starts FastAPI on `0.0.0.0:8765`
- starts Next.js on `0.0.0.0:3000`

Final console line will look like:
```
open on phone:  http://pc-name.tail-abcde.ts.net:3000
```

---

## 4. Phone install (PWA)

Open the URL above in mobile Safari (iOS) or Chrome (Android).

**iOS Safari:**
1. Share → **Add to Home Screen**
2. Tap **Jarvis** on home screen — opens fullscreen, no browser chrome.

**Android Chrome:**
1. Three-dot menu → **Install app** (or **Add to Home screen**)
2. Tap **Jarvis** on home screen.

On first boot the PWA shows a token prompt. Paste the `MC_API_TOKEN` printed earlier. Stored locally — only entered once per device.

---

## 5. Verify

- Inbox / status board / agents list load → frontend ↔ FastAPI working.
- Trigger an agent that pushes (e.g. sentinel watcher fires) → phone gets a banner.
- Kill Wi-Fi on phone → app still loads cached shell (service worker offline).

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Phone can't reach `*.ts.net` URL | Tailscale toggle off on phone. Toggle on. Also check PC: `tailscale up`. |
| Token prompt rejects valid token | Cleared `web/.env.local`? Re-run setup script. |
| WS / live updates dead | Check `NEXT_PUBLIC_JARVIS_API` matches actual tailnet host (FastAPI direct hits, not via Next). |
| ntfy push silent | Topic typo. Both env var + phone subscription must match exactly. |
| `ImageResponse` build fails | `pnpm install` (Next.js needs `next/og`). |
| iOS won't install PWA | Must open in **Safari**, not in-app browsers. |

---

## Costs

| Service | Tier | Limits |
|---------|------|--------|
| Tailscale | Free | 100 devices, unlimited bandwidth |
| ntfy.sh | Free | unlimited topics, 250 msg/5h per topic |
| Power | PC stays on | only cost is electricity |

Total $0/month if PC was already running.
