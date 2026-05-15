#!/usr/bin/env python3
"""OpenSwarm interactive setup wizard.

Run directly:           python onboard.py
Re-enter all add-ons:   python onboard.py --reconfigure
Re-enter one add-on:    python onboard.py --reconfigure fal
Auto-launched:          python run.py  (when no provider key is found)
"""

import argparse
import getpass
import sys
from pathlib import Path

from dotenv import dotenv_values, set_key
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

try:
    import questionary
    import questionary.prompts.common as _qc_common
    from questionary import Choice, Style as QStyle

    # Swap filled circle → checkmark for selected state.
    _qc_common.INDICATOR_SELECTED = "✓"

    _HAS_QUESTIONARY = True
except ImportError:
    _HAS_QUESTIONARY = False

console = Console()

ENV_PATH = Path(__file__).parent / ".env"

# ── questionary theme ─────────────────────────────────────────────────────────
_QSTYLE = None
if _HAS_QUESTIONARY:
    _QSTYLE = QStyle(
        [
            ("qmark", "fg:#4fc3f7 bold"),
            ("question", "bold"),
            ("answer", "fg:#4fc3f7 bold"),
            ("pointer", "fg:#4fc3f7 bold noreverse"),
            ("highlighted", "noreverse"),
            ("selected", "fg:#4fc3f7 bold noreverse"),
            ("separator", "fg:#555555 noreverse"),
            ("instruction", "fg:#555555 italic noreverse"),
            ("text", "noreverse"),
        ]
    )

# ── provider definitions ──────────────────────────────────────────────────────
PROVIDERS = [
    {
        "name": "OpenAI",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-5.2",
        "url": "https://platform.openai.com/api-keys",
    },
    {
        "name": "Anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "litellm/claude-sonnet-4-6",
        "url": "https://console.anthropic.com/settings/keys",
    },
    {
        "name": "Google Gemini",
        "env_key": "GOOGLE_API_KEY",
        "default_model": "litellm/gemini/gemini-3-flash",
        "url": "https://aistudio.google.com/app/apikey",
    },
]

# ── add-on definitions ────────────────────────────────────────────────────────
# exclude_for: list of provider names that already cover this key
ADD_ONS = [
    {
        "id": "search",
        "name": "Web Search",
        "description": "Web, Scholar & product search for all agents",
        "keys": [
            {"env": "SEARCH_API_KEY", "label": "SearchAPI key", "url": "https://www.searchapi.io"},
        ],
        "exclude_for": [],
    },
    {
        "id": "anthropic",
        "name": "Anthropic Claude  —  better slides quality",
        "description": "Claude produces significantly better slide HTML output",
        "keys": [
            {
                "env": "ANTHROPIC_API_KEY",
                "label": "Anthropic API key",
                "url": "https://console.anthropic.com/settings/keys",
            },
        ],
        "exclude_for": ["Anthropic"],
    },
    {
        "id": "composio",
        "name": "Composio  —  10,000+ integrations",
        "description": "Gmail, Slack, GitHub, HubSpot, Google Calendar and more",
        "keys": [
            {"env": "COMPOSIO_API_KEY", "label": "Composio API key", "url": "https://composio.dev"},
            {"env": "COMPOSIO_USER_ID", "label": "Composio user ID", "url": "https://composio.dev"},
        ],
        "exclude_for": [],
    },
    {
        "id": "google",
        "name": "Google Gemini  —  image gen & Veo video",
        "description": "Gemini image generation/editing and Veo video generation",
        "keys": [
            {"env": "GOOGLE_API_KEY", "label": "Google AI API key", "url": "https://aistudio.google.com/app/apikey"},
        ],
        "exclude_for": ["Google Gemini"],
    },
    {
        "id": "fal",
        "name": "Fal.ai  —  Seedance video & background removal",
        "description": "Seedance 1.5 Pro video gen, video editing, background removal",
        "keys": [
            {"env": "FAL_KEY", "label": "Fal.ai API key", "url": "https://fal.ai/dashboard/keys"},
        ],
        "exclude_for": [],
    },
    {
        "id": "stock",
        "name": "Stock photos  —  Pexels / Pixabay / Unsplash",
        "description": "Image search for the Slides Agent",
        "keys": [
            {"env": "PEXELS_API_KEY", "label": "Pexels API key", "url": "https://www.pexels.com/api"},
            {"env": "PIXABAY_API_KEY", "label": "Pixabay API key", "url": "https://pixabay.com/api/docs"},
            {"env": "UNSPLASH_ACCESS_KEY", "label": "Unsplash access key", "url": "https://unsplash.com/developers"},
        ],
        "exclude_for": [],
    },
]

# ── ui helpers ────────────────────────────────────────────────────────────────


def _step(n: int, label: str) -> None:
    console.print()
    console.print(Rule(f"[bold]Step {n}  ·  {label}[/bold]", style="cyan"))
    console.print()


def _ask_select(message: str, choices: list) -> object:
    if _HAS_QUESTIONARY:
        return questionary.select(message, choices=choices, style=_QSTYLE).ask()
    # plain fallback
    titles = [c.title if isinstance(c, Choice) else c for c in choices]
    values = [c.value if isinstance(c, Choice) else c for c in choices]
    console.print(f"\n[bold]{message}[/bold]")
    for i, title in enumerate(titles, 1):
        console.print(f"  [cyan]{i}.[/cyan] {title}")
    while True:
        raw = input("Enter number: ").strip()
        if raw.isdigit() and 1 <= int(raw) <= len(titles):
            return values[int(raw) - 1]
        console.print("[red]Invalid choice, try again.[/red]")


def _ask_checkbox(message: str, choices: list) -> list:
    if _HAS_QUESTIONARY:
        # `instruction=` surfaces a one-line hint under the question; without it,
        # new users often press Enter without first toggling with Space and the
        # wizard records an empty selection. That silent fall-through is the
        # most common reason add-on keys never get a chance to be entered.
        selected = (
            questionary.checkbox(
                message,
                choices=choices,
                style=_QSTYLE,
                pointer="❯",
                instruction="(Space to toggle, Enter to confirm)",
            ).ask()
            or []
        )
        if not selected:
            console.print(
                "  [dim]No add-ons selected — skipping add-on key setup. "
                "Re-run `python onboard.py --reconfigure` later to add them.[/dim]"
            )
        return selected
    # plain fallback — comma-separated numbers
    titles = [c.title if isinstance(c, Choice) else c for c in choices]
    values = [c.value if isinstance(c, Choice) else c for c in choices]
    console.print(f"\n[bold]{message}[/bold]")
    console.print("[dim]  Enter comma-separated numbers, or press Enter to skip[/dim]")
    for i, title in enumerate(titles, 1):
        console.print(f"  [cyan]{i}.[/cyan] {title}")
    raw = input("Selection: ").strip()
    if not raw:
        return []
    result = []
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit() and 1 <= int(part) <= len(titles):
            result.append(values[int(part) - 1])
    return result


def _ask_secret(label: str, url: str) -> str:
    console.print(f"  [dim]Get yours at[/dim] [link={url}]{url}[/link]")
    if _HAS_QUESTIONARY:
        val = questionary.password(f"  {label}: ", style=_QSTYLE).ask()
        return (val or "").strip()
    # getpass deliberately hides typed characters. On some terminals this looks
    # identical to "the input is frozen" — surface the behaviour explicitly so
    # the user knows their keystrokes are being captured.
    console.print("  [dim](input will be hidden as you type)[/dim]")
    return getpass.getpass(f"  {label}: ").strip()


def _warn_empty_key(env_name: str, addon_label: str) -> None:
    """Print a visible warning when an add-on key was prompted for but left empty.

    Without this, the wizard silently moves on and the add-on remains unusable,
    leaving the user to wonder why FAL/Composio/etc. features later fail.
    """
    console.print(
        f"  [yellow]⚠️  No value entered for {env_name} — {addon_label} features "
        f"will remain unavailable. Re-run with `python onboard.py --reconfigure "
        f"{env_name.lower().rstrip('_key').rstrip('_api')}` to retry.[/yellow]"
    )


def _ask_confirm(message: str, default: bool = True) -> bool:
    if _HAS_QUESTIONARY:
        return questionary.confirm(message, default=default, style=_QSTYLE).ask()
    prompt = f"{message} [{'Y/n' if default else 'y/N'}]: "
    raw = input(prompt).strip().lower()
    return default if not raw else raw in ("y", "yes")


def _write_env(updates: dict) -> None:
    if not ENV_PATH.exists():
        ENV_PATH.write_text("", encoding="utf-8")
    for key, value in updates.items():
        if value:
            set_key(str(ENV_PATH), key, value)


def _collect_addon_keys(addons: list[dict], existing: dict, updates: dict) -> None:
    """Prompt for every key of every add-on in `addons`, writing into `updates`.

    Always prompts — never silently honors a stale `.env` value just because
    the user explicitly opted in via Step 3 (or `--reconfigure`). If the user
    submits an empty value AND a prior value exists, the prior value is kept
    so the wizard is non-destructive. If the value is empty AND no prior
    value exists, the user is warned loudly that the add-on will not work.
    """
    for addon in addons:
        console.print(f"\n  [bold]{addon['name'].split('  ')[0]}[/bold]")
        for key_spec in addon["keys"]:
            existing_val = existing.get(key_spec["env"], "")
            if existing_val:
                console.print(
                    f"  [dim]{key_spec['env']} is currently set. "
                    f"Press Enter to keep the existing value, or type a new "
                    f"value to overwrite.[/dim]"
                )
            val = _ask_secret(key_spec["label"], key_spec["url"])
            if val:
                updates[key_spec["env"]] = val
            elif existing_val:
                updates[key_spec["env"]] = existing_val
            else:
                _warn_empty_key(key_spec["env"], addon["name"])


def run_reconfigure(target_ids: list[str] | None) -> None:
    """Skip the provider steps; re-enter add-on keys (optionally filtered).

    `target_ids` is the list of add-on ids passed on the CLI (e.g. `["fal"]`).
    `None` or empty list means "all add-ons". Unknown ids are reported and the
    wizard exits non-zero so typos don't silently no-op.
    """
    known_ids = {a["id"] for a in ADD_ONS}
    if target_ids:
        unknown = [t for t in target_ids if t not in known_ids]
        if unknown:
            console.print(
                f"[red]Unknown add-on id(s): {', '.join(unknown)}.[/red]\n"
                f"[dim]Known ids: {', '.join(sorted(known_ids))}[/dim]"
            )
            raise SystemExit(2)
        targets = [a for a in ADD_ONS if a["id"] in target_ids]
        header = f"Reconfiguring add-ons: {', '.join(t['id'] for t in targets)}"
    else:
        targets = list(ADD_ONS)
        header = "Reconfiguring all add-on keys"

    console.print()
    console.print(
        Panel.fit(
            f"[bold cyan]OpenSwarm[/bold cyan]  [dim]—  {header}[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )
    existing = dotenv_values(str(ENV_PATH)) if ENV_PATH.exists() else {}
    updates: dict[str, str] = {}
    _collect_addon_keys(targets, existing, updates)
    _write_env(updates)

    saved = [k for k in updates if updates.get(k)]
    console.print()
    console.print(Rule("[bold green]Reconfigure complete[/bold green]", style="green"))
    if saved:
        console.print(f"[dim]Updated keys:[/dim] [cyan]{', '.join(saved)}[/cyan]")
    console.print()


# ── main wizard ───────────────────────────────────────────────────────────────


def run_onboarding() -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]OpenSwarm[/bold cyan]  [dim]—  open-source multi-agent AI team[/dim]\n"
            "[dim]Let's get you set up in a few steps.[/dim]",
            border_style="cyan",
            padding=(1, 4),
        )
    )

    existing = dotenv_values(str(ENV_PATH)) if ENV_PATH.exists() else {}
    updates: dict[str, str] = {}

    # ── Step 1: provider ──────────────────────────────────────────────────────
    _step(1, "AI Provider")

    provider_choices = [Choice(title=p["name"], value=p) for p in PROVIDERS]
    provider = _ask_select("Choose your primary AI provider:", provider_choices)

    # ── Step 2: API key ───────────────────────────────────────────────────────
    _step(2, "API Key")

    existing_key = existing.get(provider["env_key"], "")
    if existing_key:
        console.print(f"  [dim]{provider['env_key']} is already configured.[/dim]")
        if _ask_confirm("  Update it?", default=False):
            key = _ask_secret(f"{provider['name']} API key", provider["url"])
            updates[provider["env_key"]] = key or existing_key
        else:
            updates[provider["env_key"]] = existing_key
    else:
        key = _ask_secret(f"{provider['name']} API key", provider["url"])
        if key:
            updates[provider["env_key"]] = key

    updates["DEFAULT_MODEL"] = provider["default_model"]

    # ── Step 3: add-ons ───────────────────────────────────────────────────────
    _step(3, "Add-ons  [dim](optional)[/dim]")

    available = [a for a in ADD_ONS if provider["name"] not in a["exclude_for"]]
    addon_choices = [
        Choice(
            title=(
                [
                    ("class:text", a["name"]),
                    ("fg:#555555", "  ·  "),
                    ("fg:#666666", a["description"]),
                ]
                if _HAS_QUESTIONARY
                else f"{a['name']}  —  {a['description']}"
            ),
            value=a["id"],
        )
        for a in available
    ]
    selected_ids = _ask_checkbox("Select add-ons to enable:", addon_choices)
    selected_addons = [a for a in available if a["id"] in selected_ids]

    # ── Step 4: add-on keys ───────────────────────────────────────────────────
    if selected_addons:
        _step(4, "Add-on Keys")
        _collect_addon_keys(selected_addons, existing, updates)

    # ── write .env ────────────────────────────────────────────────────────────
    _write_env(updates)

    # ── summary ───────────────────────────────────────────────────────────────
    console.print()
    console.print(Rule("[bold green]Setup complete[/bold green]", style="green"))
    console.print()

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column()
    table.add_row("Provider", f"[cyan]{provider['name']}[/cyan]")
    table.add_row("Model", f"[cyan]{provider['default_model']}[/cyan]")
    table.add_row(".env", f"[cyan]{ENV_PATH}[/cyan]")
    saved = [k for k, v in updates.items() if v and not k.startswith("DEFAULT_")]
    if saved:
        table.add_row("Keys saved", f"[cyan]{', '.join(saved)}[/cyan]")
    console.print(table)

    console.print()
    console.print(
        Panel(
            "[bold]python swarm.py[/bold]  [dim]launch interactive terminal[/dim]\n"
            "[bold]python server.py[/bold]  [dim]start the API server[/dim]",
            border_style="green",
            padding=(0, 3),
        )
    )
    console.print()


def _parse_cli(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="onboard.py",
        description="OpenSwarm interactive setup wizard.",
    )
    parser.add_argument(
        "--reconfigure",
        nargs="*",
        metavar="ADDON_ID",
        default=None,
        help=(
            "Skip provider selection and re-enter add-on keys. "
            "Pass one or more add-on ids (e.g. `fal search`) to limit the scope, "
            "or use `--reconfigure` with no value to re-enter every add-on key."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = _parse_cli(sys.argv[1:])
    try:
        if args.reconfigure is not None:
            # `nargs="*"` gives `[]` for `--reconfigure` alone, `["fal"]` for
            # `--reconfigure fal`, `None` when the flag is absent.
            run_reconfigure(args.reconfigure or None)
        else:
            run_onboarding()
    except KeyboardInterrupt:
        console.print("\n\n[dim]Setup cancelled.[/dim]\n")
        sys.exit(0)
