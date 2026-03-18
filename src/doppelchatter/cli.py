"""CLI — `doppel` command with Click."""

from __future__ import annotations

import logging
import os
import sys
import webbrowser
from pathlib import Path

import click
import yaml

from doppelchatter import __version__
from doppelchatter.config import load_config, load_profiles
from doppelchatter.models import TwinProfile


@click.group()
@click.option("--config", "config_path", type=click.Path(exists=False), default=None,
              help="Config file path (default: ./doppelchatter.yaml)")
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.pass_context
def main(ctx: click.Context, config_path: str | None, debug: bool) -> None:
    """🎭 Doppelchatter — Digital Twin Theatre"""
    ctx.ensure_object(dict)
    path = Path(config_path) if config_path else None
    ctx.obj["config"] = load_config(path)
    ctx.obj["debug"] = debug or bool(os.environ.get("DOPPEL_DEBUG"))

    level = logging.DEBUG if ctx.obj["debug"] else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s │ %(levelname)-7s │ %(name)-25s │ %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


@main.command()
@click.option("--twin-a", default=None, help="Twin A profile slug")
@click.option("--twin-b", default=None, help="Twin B profile slug")
@click.option("--scenario", default=None, help="Scenario slug")
@click.option("--model", default=None, help="Override default LLM model")
@click.option("--port", type=int, default=None, help="Server port")
@click.option("--no-browser", is_flag=True, help="Don't open browser automatically")
@click.pass_context
def chatter(
    ctx: click.Context,
    twin_a: str | None,
    twin_b: str | None,
    scenario: str | None,
    model: str | None,
    port: int | None,
    no_browser: bool,
) -> None:
    """Launch the theatre — start server and open browser."""
    import uvicorn

    from doppelchatter.app import create_app

    config = ctx.obj["config"]

    # Check API key — need at least one provider key
    api_key = config.llm.api_key
    anthropic_key = config.llm.anthropic_api_key
    if not api_key and not anthropic_key:
        click.echo("\n✗ No API key set.\n")
        click.echo("  Set one of:")
        click.echo("    export DOPPEL_API_KEY=sk-or-your-openrouter-key")
        click.echo("    export ANTHROPIC_API_KEY=sk-ant-your-key\n")
        click.echo("  Then: doppel chatter\n")
        sys.exit(1)

    # Port override
    actual_port = port or config.server.port

    # Load profiles for display
    profiles = load_profiles(Path(config.twins_dir))
    profile_names = ", ".join(profiles.keys()) or "(none)"

    click.echo("\n🎭 Doppelchatter")
    click.echo(f"   Server:   http://{config.server.host}:{actual_port}")
    click.echo(f"   Model:    {model or config.llm.default_model}")
    click.echo(f"   Profiles: {profile_names}")
    if twin_a and twin_b:
        click.echo(f"   Twins:    {twin_a}, {twin_b}")
    if scenario:
        click.echo(f"   Scenario: {scenario}")
    click.echo("\n   Ready. Press Ctrl+C to stop.\n")

    # Auto-open browser
    suppress_browser = no_browser or bool(os.environ.get("DOPPEL_NO_BROWSER"))
    if not suppress_browser:
        import threading
        url = f"http://{config.server.host}:{actual_port}"
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app = create_app(config)
    uvicorn.run(
        app,
        host=config.server.host,
        port=actual_port,
        log_level="debug" if ctx.obj["debug"] else "info",
    )


@main.command("list")
@click.pass_context
def list_profiles(ctx: click.Context) -> None:
    """List available twin profiles."""
    config = ctx.obj["config"]
    profiles = load_profiles(Path(config.twins_dir))

    if not profiles:
        click.echo("No profiles found. Create YAML files in twins/")
        return

    for slug, profile in profiles.items():
        desc = f"  {profile.description}" if profile.description else ""
        click.echo(f"  {slug:<15} {profile.avatar}  {profile.effective_display_name}{desc}")


@main.command()
@click.pass_context
def lint(ctx: click.Context) -> None:
    """Validate profiles and configuration."""
    config = ctx.obj["config"]
    errors = 0

    # Validate config
    click.echo(f"  ✓ Configuration loaded (port {config.server.port})")

    # Validate profiles
    profiles_dir = Path(config.twins_dir)
    if not profiles_dir.exists():
        click.echo(f"  ✗ Profiles directory not found: {profiles_dir}")
        errors += 1
    else:
        for path in sorted(profiles_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                TwinProfile(**data)
                click.echo(f"  ✓ {path.name} — valid")
            except Exception as e:
                click.echo(f"  ✗ {path.name} — {e}")
                errors += 1

    # Validate scenarios
    scenarios_dir = Path(config.scenarios_dir)
    if scenarios_dir.exists():
        for path in sorted(scenarios_dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict) or "name" not in data:
                    click.echo(f"  ✗ {path.name} — missing 'name' field")
                    errors += 1
                else:
                    click.echo(f"  ✓ {path.name} — valid")
            except Exception as e:
                click.echo(f"  ✗ {path.name} — {e}")
                errors += 1

    if errors:
        click.echo(f"\n  {errors} error(s) found.")
        sys.exit(1)
    else:
        click.echo("\n  All valid. ✓")


@main.command()
@click.argument("session_id")
@click.option("--format", "fmt", type=click.Choice(["json", "markdown", "html"]),
              default="markdown", help="Export format")
@click.option("--output", "-o", type=click.Path(), default=None,
              help="Output file (default: stdout)")
@click.pass_context
def export(ctx: click.Context, session_id: str, fmt: str, output: str | None) -> None:
    """Export a session transcript."""
    from doppelchatter.storage import (
        SessionStore,
        export_html,
        export_json,
        export_markdown,
    )

    config = ctx.obj["config"]
    store = SessionStore(Path(config.sessions_dir))
    data = store.load_session(session_id)

    if not data:
        click.echo(f"Session not found: {session_id}")
        sys.exit(1)

    exporters = {
        "json": export_json,
        "markdown": export_markdown,
        "html": export_html,
    }
    content = exporters[fmt](data)

    if output:
        Path(output).write_text(content)
        click.echo(f"Exported to {output}")
    else:
        click.echo(content)


@main.command()
def version() -> None:
    """Show version info."""
    click.echo(f"Doppelchatter v{__version__}")


if __name__ == "__main__":
    main()
