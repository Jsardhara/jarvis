# Jarvis Discord Setup Guide

## Step 1: Create Discord Bot Application

1. Go to https://discord.com/developers/applications
2. Click "New Application"
3. Name it "Jarvis" (or whatever you want)
4. Go to the "Bot" section on the left sidebar
5. Click "Add Bot"
6. Under "Privileged Gateway Intents", ENABLE:
   - ✅ Message Content Intent (REQUIRED -- bot needs to read messages)
   - ✅ Server Members Intent (optional, for user mentions)
   - ✅ Presence Intent (optional)
7. Click "Reset Token" and COPY THE TOKEN -- you'll need it in Step 3
8. Save it somewhere safe -- treat it like a password

## Step 2: Create Your Discord Server (if you don't have one)

1. Discord → "+" button on left sidebar → "Create My Own"
2. Name it "Jarvis" or "Home" or whatever
3. Create these channels (matching the Jarvis crew):

   TEXT CHANNELS:
   - #jarvis-main     → Talk to Jarvis directly (orchestrator)
   - #tempo           → Email, calendar, tasks, scheduling
   - #scholar         → Academic help, study plans
   - #lens            → Research, news, fact-checking
   - #forge           → Code work, PR reviews, debugging
   - #atlas           → Trading, portfolio, market analysis
   - #sentinel        → System alerts, health reports (read-only)
   - #me              → Private approvals channel (create as private)

   VOICE CHANNELS (optional):
   - jarvis-voice     → For voice interactions

4. Create channel categories:
   📋 COMMAND CENTER (jarvis-main, me)
   ⚡ OPERATIONS (tempo, sentinel)
   🧠 INTELLIGENCE (scholar, lens)
  🛠 BUILDERS (forge, atlas)

## Step 3: Give Me the Bot Token

Once you have the token, tell me:

"Jarvis discord token: <paste token here>"

I will:
1. Store it securely in Hermes auth
2. Configure the gateway to connect
3. Set up channel routing
4. Test the connection

## Step 4: Invite Bot to Server

1. In Discord Developer Portal → your app → OAuth2 → URL Generator
2. Select scopes: ✅ bot, ✅ applications.commands
3. Select bot permissions:
   - View Channels ✅
   - Send Messages ✅
   - Read Message History ✅
   - Manage Threads ✅ (for auto_thread feature)
   - Mention Everyone ✅ (for alerts)
   - Embed Links ✅
   - Attach Files ✅
   - Use Slash Commands ✅
4. Copy the generated URL
5. Open it in your browser
6. Select your server
7. Authorize

## Step 5: Verify

Once connected, test by:
1. Typing `/jarvis hello` in #jarvis-main
2. Typing `@Jarvis check system health` in #sentinel
3. Watch for Jarvis to respond in the correct channels

## Platform Config (for Hermes config.yaml)

Once the token is provided, this goes into config.yaml discord section:

```yaml
discord:
  require_mention: true          # Only respond when @mentioned
  allowed_channels: ''           # Empty = all channels in server
  channel_prompts:               # Per-channel personality hints
    jarvis-main: "You are Jarvis, Chief-of-Staff orchestrator."
    tempo: "You are Tempo. Focus on email, calendar, and scheduling."
    scholar: "You are Scholar. Focus on academics and study planning."
    lens: "You are Lens. Focus on research and evidence."
    forge: "You are Forge. Focus on code and implementation."
    atlas: "You are Atlas. Focus on markets and paper trading."
    sentinel: "You are Sentinel. Report system health only."
    me: "Respond as Jarvis privately for approvals."
  auto_thread: true              # Auto-create threads for long discussions
  history_backfill: true         # Read channel history for context
```

After you give me the token, the system is fully connected.
