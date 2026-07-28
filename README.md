# Jarvis AI — Desktop Assistant

A working desktop assistant with a chat GUI, optional voice in/out, and
real features — no paid API keys required to run it.

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

The first run creates a `data/` folder next to the code with:
- `config.json` — your settings (name, city, voice on/off, etc.)
- `memory.json` — chat history + facts you asked Jarvis to remember
- `reminders.json` — your reminders
- `jarvis.log` — running log for debugging

Edit `data/config.json` (or use `settings.py` from a Python shell) to set
your name and default city, e.g.:

```json
{ "user_name": "Sambit", "city": "Pune", "voice_enabled": true }
```

## What works right now

- **Chat GUI** (`gui.py` / `app.py`) — type or click the mic to talk to Jarvis.
- **Weather** — "weather in Mumbai", "weather" (uses your default city).
  Free [Open-Meteo](https://open-meteo.com) API, no key needed.
- **News** — "news", "news about elections". Free Google News RSS, no key.
- **Web/YouTube** — "open youtube", "search for python tutorials",
  "search for lofi beats on youtube".
- **System info & control** — "system status", "open app calculator",
  "lock the screen", "shutdown confirm" (requires the word "confirm" so
  it's never triggered by accident or a misheard command).
- **Reminders** — "remind me to check the oven in 10 minutes",
  "list my reminders".
- **Files** — "find files named invoice", "open file report.docx".
- **Memory** — "remember my wifi password is X", "what's my wifi
  password", "forget my wifi password".
- **Time/date** — "what's the time", "what day is it".
- **Calculator & unit conversion** — "calculate 12 * 7 + 3",
  "convert 100 f to c" (safe: only arithmetic on numbers is ever
  evaluated, never arbitrary code).
- **Jokes & help** — "tell me a joke", "help" (lists everything above).
- **Change settings by voice/chat** — "set my city to Mumbai",
  "call me Sam" — also editable from the GUI's ⚙ Settings panel.
- **Reminders, upgraded** — relative ("in 10 minutes") or absolute
  ("at 5pm" / "at 17:30", rolls to tomorrow if that time already
  passed today), each with a short id. "list my reminders",
  "cancel reminder <id>". Reminders persist across restarts and
  actually re-fire (and notify) on the next launch instead of being
  silently dropped.
- **Voice** — text-to-speech via `pyttsx3` (offline) and speech-to-text
  via `speech_recognition` (needs a mic; uses Google's free web
  recognizer). If either package or a mic isn't available, the app keeps
  working in text-only mode automatically — nothing crashes. The GUI
  also has an "Always listening" switch that keeps the mic on and
  reacts to whatever it hears, instead of one push-to-talk click at a
  time.
- **Reminder pop-ups** — when a reminder fires, the GUI shows a
  message box, drops a line in the chat, and speaks it — even for
  reminders that were still pending from before you closed the app.
- **Settings panel & live clock** in the GUI — change your name,
  city, and the assistant's name without touching `config.json`.
- **Chit-chat fallback** — anything that isn't a recognized command goes
  to `ai.py`, which does rule-based small talk offline. If you add an
  `openai_api_key` in `data/config.json`, it'll use that for richer
  replies instead (fully optional).

## Vision — Jarvis can look at things

Three ways to show Jarvis an image, all powered by Groq's vision model
(`qwen/qwen3.6-27b`) — **this needs a Groq API key**; there's no
offline fallback for actually understanding an image, only a clear
message telling you to add one if it's missing.

- **Upload an image** — desktop: click 📎 and pick a file. Web: click
  📎 in the browser and pick a file.
- **Webcam** — say "what am I looking at" (or click 📷). Desktop grabs
  a frame straight from the camera via OpenCV. Web asks the browser
  for camera permission, shows a live preview, and captures on
  "Capture".
- **Screen** — say "what's on my screen" (or click 🖥). Desktop grabs
  a screenshot via Pillow's `ImageGrab` (works out of the box on
  Windows/macOS; needs an X server on Linux, which most desktops
  have). Web uses `getDisplayMedia`, so the browser will ask you to
  pick a window/screen/tab to share, exactly like a video call.

All three end up in the same place: `vision.py`'s `analyze_image()`,
logged to memory like a normal chat turn, and (if voice replies are
on) spoken back to you.

**New voice/chat phrases:** "what am I looking at", "look through the
webcam", "what's on my screen", "take a screenshot" — see the
`_WEBCAM_TRIGGERS` / `_SCREEN_TRIGGERS` patterns in `assistant.py` if
you want to add more.

## Web version (browser chat UI, HTTPS)

There's now a browser-based version alongside the desktop GUI — same
brain (`assistant.py`, `commands.py`, `ai.py`), served over HTTP/HTTPS
via FastAPI instead of tkinter.

```bash
pip install -r requirements.txt
uvicorn server:app --reload --port 8000        # http://localhost:8000
```

Open `http://localhost:8000` — it's the same chat, but in a browser,
with a mic button and voice replies powered by the browser's own
Web Speech API (so no `pyttsx3`/mic setup needed server-side for the
web version).

### Adding your Groq API key

Groq is now the preferred chit-chat backend (checked before any OpenAI
key). Set it either:
- In the web UI: click ⚙ Settings → paste your key → Save. It's
  written to `data/config.json` on the server and never sent anywhere
  except `api.groq.com`.
- Or directly in `data/config.json`:
  ```json
  { "groq_api_key": "gsk_...", "groq_model": "llama-3.3-70b-versatile" }
  ```

Without a key, chit-chat falls back to the offline rule-based replies —
all the structured commands (weather, news, reminders, etc.) work
identically either way.

### Serving it over HTTPS

**Local/dev — self-signed certificate** (browsers will show a "not
secure" warning, click through it):

On macOS/Linux (needs `openssl` on your PATH):
```bash
./gen_cert.sh              # creates certs/cert.pem + certs/key.pem
```

On Windows (or anywhere without `openssl` — pure Python, no extra
tools needed):
```powershell
pip install cryptography
python gen_cert.py         # creates certs/cert.pem + certs/key.pem
```

Then either way:
```bash
uvicorn server:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile certs/key.pem --ssl-certfile certs/cert.pem
```

Then visit `https://<your-machine-ip>:8443` from any device on your
network.

**Real domain, no browser warning — Let's Encrypt.** If you're
pointing an actual domain at this server (e.g. on a VPS), the simplest
route is to put a reverse proxy in front of Jarvis and let it handle
certificates automatically, rather than passing cert files to uvicorn
yourself:

- [Caddy](https://caddyserver.com/) (easiest — auto-HTTPS in one line):
  ```
  # Caddyfile
  jarvis.yourdomain.com {
      reverse_proxy 127.0.0.1:8000
  }
  ```
  Run `caddy run`, done — it provisions and renews the Let's Encrypt
  cert automatically.
- Or Nginx + `certbot --nginx` if you'd rather manage Nginx directly.

Either way, run `uvicorn server:app --host 127.0.0.1 --port 8000`
(plain HTTP, not exposed directly) behind the proxy, which is the one
that terminates TLS on port 443.

### A note on exposing this beyond your own machine

`server.py` has no login/auth — it's built as a single-user personal
assistant. If you put it on the open internet (rather than just your
home network or a VPN/tailnet), add authentication in front of it —
e.g. Caddy's `basic_auth` directive, or an OAuth proxy — so a random
visitor can't chat as you, read your reminders, or see your API key
(the key itself is never returned by `/api/settings`, only a masked
version, but the chat/reminders endpoints are otherwise open).

## Deploying: GitHub + Render

The repo's already git-initialized locally with a first commit. To get
it on GitHub and live on Render:

### 1. Push to GitHub

```bash
# Create the repo on GitHub first (github.com/new — no README/license,
# you already have files), then:
git remote add origin https://github.com/<your-username>/jarvis.git
git branch -M main
git push -u origin main
```

(Or use the [GitHub CLI](https://cli.github.com/): `gh repo create jarvis --private --source=. --push`.)

### 2. Deploy on Render

Two ways — pick one:

**A. Blueprint (uses the included `render.yaml`, one click):**
1. [render.com](https://render.com) → **New +** → **Blueprint**
2. Connect the GitHub repo you just pushed
3. Render reads `render.yaml` and sets up the service automatically
4. In the service's **Environment** tab, set `GROQ_API_KEY` to your
   real key (left blank in `render.yaml` on purpose — never commit a
   real key to git)
5. Deploy — Render gives you a `https://jarvis-ai-xxxx.onrender.com`
   URL with HTTPS already handled, no cert setup needed

**B. Manual Web Service (if you'd rather not use the Blueprint):**
1. **New +** → **Web Service** → connect the repo
2. Runtime: **Python 3**
3. Build command: `pip install -r requirements-web.txt`
4. Start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`
5. Add environment variable `GROQ_API_KEY` = your key
6. Deploy

Note `requirements-web.txt` is a lighter dependency list than
`requirements.txt` — it deliberately skips `customtkinter`, `pyttsx3`,
`SpeechRecognition`, and `opencv-python`, since those need a
display/mic/camera that a headless Render container doesn't have and
aren't used by `server.py` anyway (voice and webcam happen client-side
in the browser). Use `requirements.txt` for local desktop-app installs.

**One important caveat:** Render's filesystem is ephemeral — anything
written to `data/` (memory, reminders, settings saved via the ⚙ panel)
is wiped on every redeploy or restart. That's fine for `GROQ_API_KEY`
(set as an env var, survives redeploys) but means reminders/memory
won't persist long-term on the free tier. If you want that to stick
around, add a paid [Render Disk](https://render.com/docs/disks) mounted
at `data/`, or swap `memory.py`/`reminders.py`/`config.py` for a small
external store (e.g. a free tier of Postgres or Redis) — not set up
here since it's outside what a personal single-user assistant usually
needs, but the three files above are the only place that'd change.

## Project layout

| File | Responsibility |
|---|---|
| `app.py` | Desktop entry point |
| `gui.py` | customtkinter chat window, wired to `assistant.py` |
| `server.py` | FastAPI web entry point — same assistant, browser UI, HTTP/HTTPS |
| `static/` | Browser chat UI (`index.html`, `style.css`, `app.js`) |
| `gen_cert.sh` | Generates a local self-signed TLS cert for dev HTTPS |
| `render.yaml` | Render Blueprint — one-click cloud deploy config |
| `requirements-web.txt` | Lean deps for cloud/Render (no desktop-only packages) |
| `assistant.py` | Orchestrator: routes text → commands → AI fallback → memory → speech |
| `commands.py` | Regex-based intent router mapping phrases to features |
| `ai.py` | Offline small talk + optional external LLM fallback |
| `vision.py` | Image understanding via Groq's vision model (upload/webcam/screen) |
| `webcam.py` | Desktop webcam frame capture (OpenCV) |
| `screen.py` | Desktop screenshot capture (Pillow ImageGrab) |
| `weather.py` | Open-Meteo current weather + forecast |
| `news.py` | Google News RSS headlines |
| `browser.py` | Open sites / web / YouTube search |
| `system.py` | CPU/RAM/disk/battery status, app launch, shutdown/restart/lock |
| `files.py` | Search/open/create/delete files (delete requires explicit confirm) |
| `reminders.py` | Timed reminders, persisted to disk |
| `memory.py` | Conversation history + remembered facts |
| `settings.py` / `config.py` | Persistent user settings |
| `speech.py` | Text-to-speech (pyttsx3, optional) |
| `voice.py` | Speech-to-text (speech_recognition, optional) |
| `utils.py` | Logging + optional-import helper |

## Running the tests

45 tests cover the command router, memory, reminders, settings, and
file operations offline (no network, no GUI, no mic needed):

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests run against a temporary data directory (see `tests/conftest.py`)
so they never touch your real `data/config.json` or `memory.json`.

## Extending it

Add a new command by registering a pattern in `commands.py`:

```python
@route(r"\bflip a coin\b")
def _coin_flip(m, text):
    import random
    return random.choice(["Heads!", "Tails!"])
```

Nothing else needs to change — `assistant.py` will pick it up automatically.

## Notes

- Voice input/output are optional. If `pyttsx3` or `speech_recognition`
  (or a microphone) aren't available, those two features silently
  no-op and everything else keeps working.
- `system.shutdown()` / `system.restart()` require the word "confirm"
  in your message so an accidental phrase or misheard voice command
  can't power off your machine.
- `files.delete_path()` is not currently exposed through a voice/chat
  command on purpose — call it directly from Python if you want file
  deletion, and only empty folders/single files can be removed.
- Vision (webcam/screen/upload) requires a Groq API key — there's no
  offline model for actually understanding an image, so without a key
  it just tells you to add one instead of guessing.
- Screen capture on Linux desktop needs an X server (most desktop
  environments have one); pure Wayland setups without XWayland may
  not support it — the web version's screen share works regardless
  since that's handled by the browser instead.
