# 🎭 Doppelchatter

Real-time digital twin theatre — watch two AI characters talk to each other.

## What Is This?

Load personality profiles for two characters. Press play. Watch them text each other in real-time with streaming responses, turn-by-turn conversation, and natural timing. Intervene by injecting thoughts into either character's mind, or drop a third character into the scene.

Ships with **four character pairs** and **eight scenarios** — from bartender-poets and astrophysicists to regression manhwa office mysteries, anonymous hacker rivals, and a funeral director who out-sunshines a wedding photographer.

## Quick Start

```bash
# 1. Set your API key (OpenRouter or Anthropic direct)
export DOPPEL_API_KEY=sk-or-your-key-here
# or
export ANTHROPIC_API_KEY=sk-ant-your-key

# 2. Install
pip install -e ".[dev]"

# 3. Launch
doppel chatter
```

Browser opens automatically to `http://127.0.0.1:8420`.

## Alternative: Run Without Installing

```bash
export DOPPEL_API_KEY=sk-or-your-key-here
python doppel.py chatter
```

## Commands

| Command | Description |
|---------|-------------|
| `doppel chatter` | Launch the theatre (server + browser) |
| `doppel list` | List available twin profiles |
| `doppel lint` | Validate profiles and configuration |
| `doppel export SESSION_ID` | Export a session transcript |
| `doppel version` | Show version |

### CLI Options

```bash
doppel chatter --port 9000          # Custom port
doppel chatter --model openai/gpt-4o  # Override model
doppel chatter --no-browser         # Don't auto-open browser
doppel chatter --debug              # Debug logging
doppel export abc123 --format html  # Export as HTML
```

## Character Pairs

### 🖤 Morri × 🔭 Sol — *The Poet and the Stargazer*

**Morri** (Morrigan) — Brooklyn bartender at The Velvet Coffin. Writes poetry on napkins. Dark humor, lowercase everything, rapid-fire texts. Intimidating exterior, soft interior.

**Sol** (Solaris Vega) — Chilean astrophysicist, works nights at an observatory. Earnest, precise, accidentally poetic. Science metaphors for feelings he doesn't realize are devastating.

*They met when he wandered in looking for somewhere quiet. She made him a drink he didn't order. He stayed until close.*

### 🔄 Jin × 📋 Hana — *The Returner and the Investigator*

**Jin** (Park Jinwoo) — Senior analyst at a Seoul consulting firm. Carries himself like someone who's already lived through everything once. Says things he shouldn't know. Dry humor masking something heavy. *(Regression manhwa energy — Omniscient Reader meets office thriller.)*

**Hana** (Choi Hana) — Junior analyst. Bright, relentlessly curious. Keeps a spreadsheet called "Jin Anomaly Log" tracking all the impossible things he seems to predict. 31 entries and counting. She's going to figure him out. *(The protagonist energy of someone who pulls at threads until reality unravels.)*

*She noticed. Nobody else ever noticed. That's either the best or the worst thing that could have happened to him.*

### 👻 GHOST × 💡 neon.exe — *The Rivals Behind the Mask*

**GHOST** — Ranked #2 in the DARKNET CTF league. Methodical, precise, perfect punctuation. Types "." when something makes them laugh. IRL: a 23-year-old grad student in Taipei living on onigiri. *(Solo Leveling's quiet power meets cyberpunk anonymity.)*

**neon.exe** — Ranked #1 (on a good day). ALL CAPS energy, chaotic exploits with comments like `// lmao what if`, aggressive emoji. IRL: a 21-year-old art school dropout in São Paulo. *(The chaotic shonen rival who shouldn't be this good but IS.)*

*Three seasons of rivalry. In public: trash talk. In DMs: the only conversations that feel real. Neither knows the other's name. Both could find out. Neither will.*

### 🌻 Sable × 📸 Kai — *Sunshine and Melancholy*

**Sable** — Apprentice funeral director. Somehow the most upbeat person alive. Uses `:)` instead of emoji because "they have more soul." Says accidentally profound things about death, then pivots to snacks. *(Spy × Family's tonal whiplash meets slice-of-life warmth.)*

**Kai** — Wedding photographer next door. Captures joy for a living, carries sadness he can't explain. Sees too much — the father who can't stop crying, the bridesmaid in love with the groom. Rarely initiates, but writes messages people screenshot. *(The quiet melancholic observer from every seinen manga.)*

*They share a wall. Celebration on one side, silence on the other. She brings him coffee. He leaves flowers from his wedding arrangements on her desk. Neither has acknowledged the ritual.*

## Scenarios

| Scenario | Pair | Setup |
|----------|------|-------|
| **The Witching Hour** | Morri × Sol | 3am. She's at the bar, he's at the observatory. Honesty happens when the city sleeps. |
| **The Napkin** | Morri × Sol | He found her poem. Four lines about light from dead stars. She's pretending she didn't leave it for him. |
| **Monday Morning** | Jin × Hana | Jin slipped in a meeting — used present tense about a future event. Hana is texting him from across the table. |
| **The Rooftop** | Jin × Hana | 11pm. Office building roof. 31 spreadsheet entries. Tonight she asks. |
| **Post-Match** | GHOST × neon | Season 8 semifinal just ended. neon won by 47 seconds. The DMs hit different after a close match. |
| **The Mask** | GHOST × neon | GHOST accidentally sent a photo — a convenience store in Taipei at 4am. Three years of anonymity cracked by one misclick. |
| **The Shared Wall** | Sable × Kai | A funeral and wedding happen simultaneously. Music bleeds through the wall. They text through it. |
| **The Photo** | Sable × Kai | Kai photographed her memorial garden at golden hour. She's never seen her own world through someone else's eyes before. |

## Configuration

`doppelchatter.yaml` (optional — defaults work):

```yaml
server:
  host: "127.0.0.1"
  port: 8420
llm:
  default_model: "anthropic/claude-sonnet-4-20250514"
  temperature: 0.88
  fallback_models:
    - "google/gemini-2.5-flash"
    - "openai/gpt-4o-mini"
engine:
  turn_delay:
    mode: "random"
    min_seconds: 1.5
    max_seconds: 4.0
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| `DOPPEL_API_KEY` | OpenRouter API key (required unless using Anthropic direct) |
| `OPENROUTER_API_KEY` | Fallback API key |
| `ANTHROPIC_API_KEY` | Anthropic API key (direct, no OpenRouter) |
| `DOPPEL_PORT` | Override server port |
| `DOPPEL_MODEL` | Override default model |
| `DOPPEL_DEBUG` | Enable debug logging |
| `DOPPEL_NO_BROWSER` | Don't auto-open browser |

## Twin Profiles

YAML files in `twins/`. Minimal profile:

```yaml
name: Alex
system_prompt: |
  You are Alex. Text naturally. Short messages.
avatar: "🌙"
color: "#C084FC"
```

Full profile supports: `display_name`, `description`, `background`, `memories`, `current_mood`, `tags`, per-twin `model` overrides, and `behavior` config (multi-message, max length).

## Interventions

During a live session:

- **💭 Thought Injection** — Plant a thought in one character's mind. Invisible to the other. Consumed on their next turn.
- **🎭 Third Agent** — Drop a new character into the conversation. Both characters see and react.

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Pause / Resume |
| `T` | Open thought injection |
| `A` | Open third agent |
| `E` | Export transcript |
| `1` / `2` | Target Twin A / B |
| `⌘+Enter` | Send intervention |
| `Esc` | Close drawer |
| `?` | Show shortcuts |

## Architecture

```
src/doppelchatter/
├── models.py          # State machine, messages, twin profiles, errors
├── config.py          # YAML + env var loading
├── llm.py             # Multi-provider streaming client with fallback
├── engine.py          # Conversation loop, context builder
├── interventions.py   # Thought injection, third agent
├── websocket.py       # WS manager, broadcast, resync
├── session.py         # Session controller
├── app.py             # FastAPI factory, REST API, WS handler
├── storage.py         # JSONL persistence, export (JSON/MD/HTML)
├── cli.py             # Click CLI
└── static/index.html  # The Theatre (dark-themed frontend)
```

## Development

```bash
make setup    # Install with dev dependencies
make test     # Run tests
make test-cov # Tests with coverage
make lint     # Ruff + mypy
make format   # Auto-format
make validate # Validate profiles
```

## Creating Your Own Characters

1. Create a YAML file in `twins/` with at minimum `name` and `system_prompt`
2. Optionally add a `.md` file with deep personality reference
3. Create scenarios in `scenarios/` that reference your characters
4. Run `doppel lint` to validate

Characters work best when they have:
- A distinctive texting style (all lowercase? proper sentences? ALL CAPS? emoji habits?)
- Clear emotional stakes (what do they want? what are they afraid of?)
- Shared history with the other character (memories, inside jokes, unresolved tension)
- A vulnerability they protect (the thing they deflect from)

## License

MIT

## Credits

Built on the [Doppelchatter](https://github.com/AntreasAntoniou/doppelchatter) engine by Antreas Antoniou. Character profiles and scenarios by [Axiotic AI](https://axiotic.ai).
