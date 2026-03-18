# 🎭 Doppelchatter

Real-time digital twin theatre — watch two AI versions of fictional people talk to each other.

## What Is This?

Load personality profiles for two characters. Press play. Watch them text each other in real-time with streaming responses, turn-by-turn conversation, and natural timing. Intervene by injecting thoughts into either character's mind, or drop a third character into the scene.

Ships with **Morri & Sol** — a Brooklyn bartender-poet and a Chilean astrophysicist, 3am texters, circling something neither of them has named yet. Three scenarios included: *The Witching Hour*, *The Morning After*, and *The Napkin*.

> ⚠️ **Content warning:** The included profiles and scenarios contain adult themes, explicit language, and sexual content. The characters are fictional.

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

### Included Characters

**🖤 Morrigan (Morri)** — Bartender at The Velvet Coffin. Brooklyn-born, Puerto Rican. Writes poetry on napkins. Dark humor, zero filter. Texts in lowercase bursts. Direct about desire.

**🔭 Sol (Solaris Vega)** — Astrophysicist working nights at an observatory. Chilean. Earnest, precise, accidentally poetic. Uses science metaphors for feelings. Devastating when the control slips.

## Scenarios

YAML files in `scenarios/`. Set the scene with mood overrides, extra memories, and opening prompts:

```yaml
name: "The Witching Hour"
description: "3am. She just closed the bar. He's at the observatory..."
twins:
  a: morrigan
  b: sol
context:
  a:
    current_mood: "Just locked up. Mezcal in hand. Phone in hand."
  b:
    current_mood: "Staring at a spectrogram. Not seeing it."
opening_prompt: "Type something before the careful version of you can stop it."
```

### Included Scenarios

| Scenario | Description |
|----------|-------------|
| **The Witching Hour** | 3am. She's at the bar, he's at the observatory. The conversation drifts toward everything they've been avoiding. |
| **The Morning After** | 10am. He's in her apartment. She's making coffee in his shirt. Neither is talking about why he didn't leave. |
| **The Napkin** | He found one of her poems. It's about light from dead stars. She's pretending she didn't leave it for him. |

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
| `DOPPEL_HOST` | Override server host |
| `DOPPEL_MODEL` | Override default model |
| `DOPPEL_DEBUG` | Enable debug logging |
| `DOPPEL_NO_BROWSER` | Don't auto-open browser |

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
2. Optionally add a `.md` file with deep personality reference (used for rich backstory)
3. Create scenarios in `scenarios/` that reference your characters
4. Run `doppel lint` to validate

Characters work best when they have:
- A distinctive texting style (all lowercase? proper sentences? emoji habits?)
- Clear emotional stakes (what do they want? what are they afraid of?)
- Shared history with the other character (memories, inside jokes, unresolved tension)
- A vulnerability they protect (the thing they deflect from)

## License

MIT

## Credits

Built on the [Doppelchatter](https://github.com/AntreasAntoniou/doppelchatter) engine by Antreas Antoniou. Character profiles and scenarios by [Axiotic AI](https://axiotic.ai).
