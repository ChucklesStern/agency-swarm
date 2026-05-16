# Agency Swarm (agency-swarm-custom)

A fork of [VRSEN/agency-swarm](https://github.com/VRSEN/agency-swarm) that adds first-class [FAL.AI](https://fal.ai) integration (text-to-image, image edit, and video generation) on top of the upstream multi-agent framework built around the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python). Use it to build collaborative agencies (CEO, Developer, Designer, …) the same way upstream does, but with FAL models wired into the OpenSwarm image and video agents out of the box.

<details>
<summary>Badges</summary>

[![Docs](https://img.shields.io/website?label=Docs&up_message=available&url=https://agency-swarm.ai/)](https://agency-swarm.ai)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/VRSEN/agency-swarm/actions?query=branch%3Amain+event%3Apush)

</details>

---

## Quick start — macOS (5-minute path)

This is the path the project is tested on. Linux and Windows users see [Alternative install: pip + venv](#alternative-install-pip--venv).

### 1. Prerequisites (one-time)

Install the Xcode Command Line Tools. If macOS reports "already installed", skip.

```bash
xcode-select --install
```

Install [Homebrew](https://brew.sh) if you don't have it.

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Install Python 3.13 and `uv` with Homebrew. Use `brew install uv` rather than the upstream `curl ... | sh` installer — the curl installer writes to `~/.local/bin` but does not update your current shell's PATH, so the very next `uv` command would error with "command not found." Homebrew puts both binaries on PATH immediately.

```bash
brew install python@3.13 uv
```

Verify:

```bash
python3 --version
uv --version
```

> **Note:** Pin Python 3.13 throughout this guide. The `[openswarm]` extra transitively requires `onnxruntime`, which ships wheels only for Python 3.12 and 3.13. If `uv` auto-selects Python 3.14 from a newer Homebrew install, the install fails midway with a cryptic wheel-tag error.

### 2. Clone and install

```bash
git clone https://github.com/ChucklesStern/agency-swarm.git
cd agency-swarm
```

Install with the `[openswarm]` extras pre-bundled so the `agency-swarm init openswarm` command works without a second install step. `--force` overwrites any leftover `agency-swarm` wrapper from a previous (e.g. curl-installed) `uv` install.

```bash
uv tool install --editable ".[openswarm]" --python 3.13 --force
```

> **Note:** If you skip `[openswarm]`, `agency-swarm init openswarm` later prints `OpenSwarm dependencies appear to be missing (could not import: questionary). Install with: pip install ...`. The suggested `pip install` then fails with `error: externally-managed-environment` (PEP 668) on macOS, because Homebrew's Python refuses system-wide installs. Use the command above and you avoid both traps.

Make the `agency-swarm` command discoverable, then open a fresh terminal.

```bash
uv tool update-shell
```

Open a new terminal window or tab, then verify:

```bash
agency-swarm --help
```

You should see subcommands `tui`, `init`, `create-agent-template`, `migrate-agent`, `import-tool`. If you still see `command not found: agency-swarm`, double-check that `~/.local/bin` (or your shell's reported uv tool dir) is on PATH; `uv tool update-shell` writes that line to your shell rc file.

### 3. Provider API key

You need an OpenAI API key for the default model. Get one at <https://platform.openai.com/api-keys>, then save it to a `.env` next to where you'll scaffold the project.

```bash
printf 'OPENAI_API_KEY=sk-...\n' > .env
```

Replace `sk-...` with your real key.

### 4. Scaffold the OpenSwarm starter

Create a fresh directory (the scaffold refuses to overwrite an existing `agency.py`), `cd` into it, and run the OpenSwarm init.

```bash
mkdir -p ~/agencies/my-first-swarm
cd ~/agencies/my-first-swarm
agency-swarm init openswarm
```

This scaffolds the full OpenSwarm project (orchestrator plus seven specialist agents: research, documents, slides, data analysis, image generation, video generation, and a coordinator) into the current directory, then runs an interactive setup wizard before opening the TUI.

### 5. The wizard — the one trap to know about

The wizard runs in four steps:

1. **AI Provider** — pick OpenAI, Anthropic, or Google Gemini. Arrow keys + Enter.
2. **API Key** — paste your provider key (or keep the existing one).
3. **Add-ons** — **this is the trap**.
4. **Add-on Keys** — only runs if Step 3 selected at least one add-on.

> **Heads up — Space vs. Enter:** Step 3 is a multi-select checkbox. **Press SPACE to toggle each add-on you want** (Fal.ai, Google, Composio, Anthropic, Web Search, Stock photos). **Then press Enter to confirm.** If you press Enter without first pressing Space, the wizard records an empty selection, skips Step 4 entirely, and your `FAL_KEY` / `GOOGLE_API_KEY` / etc. never get a chance to be entered. The wizard prints a dim "No add-ons selected" line but does not block you — and many users miss it.

If you hit that trap, recover from inside the scaffold directory without re-running the whole wizard:

```bash
python onboard.py --reconfigure fal
```

That re-enters just the FAL key. Use `--reconfigure` with no arguments to re-enter every add-on. Other ids: `search`, `anthropic`, `composio`, `google`, `stock`.

### 6. First TUI launch

After the wizard, the Node TUI starts. **The first launch bootstraps a project `.venv` inside the scaffold directory** by running `pip install --upgrade -r requirements.txt` against the project's own `requirements.txt`. Expect a few hundred MB and 5–10 minutes the first time. The `.venv` is reused on subsequent launches in the same directory, so the cost is once per project.

### 7. Verify FAL works

Once the TUI is open, send this prompt to confirm FAL is wired correctly. The explicit `./generated/` path matters — see [§ 12 about save paths](#12-explicit-save-paths-for-image--video-agents).

```
Use the image_generation_agent to create one 1024x1024 image with model
fal:flux-schnell of a small red apple on a white background, and save it
to ./generated/apple.png. Confirm the file path in your reply.
```

If you get back a real file path under `./generated/`, FAL is working. If the agent says "FAL is unavailable" or "missing key", jump to [Troubleshooting](#troubleshooting).

---

## Architecture: two Python environments

OpenSwarm runs in **two distinct Python environments**, and a lot of debugging trouble disappears once you know which is which.

| Environment | Where it lives | What runs in it |
|---|---|---|
| **Tool environment** | `~/.local/share/uv/tools/agency-swarm-custom/` (or wherever `uv tool install` put it) | The `agency-swarm` CLI itself, `agency-swarm init openswarm`, the scaffolding logic, the onboarding wizard. |
| **Project `.venv`** | `<scaffold-dir>/.venv` | `launch_agency.py`, your scaffolded `agency.py`, every agent's runtime, the FastAPI bridge, FAL adapter, OpenSwarm tools. |

The Node TUI (`agentswarm-cli`) creates the project `.venv` the first time it launches in a scaffolded directory by running `pip install --upgrade -r requirements.txt` against the scaffold's [`requirements.txt`](src/agency_swarm/_templates/openswarm/requirements.txt). That `requirements.txt` lists `agency-swarm[fastapi,jupyter,litellm]>=1.9.7` on line 1 — which means **the project `.venv` pulls the upstream `agency-swarm` from PyPI, not your local `agency-swarm-custom` fork**.

The fork's customizations still reach your agents because **the FAL adapter and other custom tools live inside the scaffold itself** (`<scaffold>/shared_tools/fal_adapter/`, etc.), not inside the `agency_swarm` package. So the path is:

- `agency_swarm` package internals → installed from upstream PyPI into the project `.venv`.
- Scaffold-side code (FAL adapter, OpenSwarm agents, GenerateImages, etc.) → copied from the fork's [`src/agency_swarm/_templates/openswarm/`](src/agency_swarm/_templates/openswarm/) into the scaffold dir.

This works today because the FAL integration is entirely scaffold-side. If you fork `agency-swarm-custom` and change anything inside the `agency_swarm` package proper (e.g. `Agency`, `Agent`, `BaseTool`, the FastAPI bridge in `agency_swarm/...`), those changes will **not** reach the running agents unless you also patch the scaffold's `requirements.txt` line 1 to point at your fork. This is a known fragility — see [Known limitations](#known-limitations).

---

## Updating after agency-swarm-custom upgrades

**Existing scaffolds are snapshots.** `agency-swarm init openswarm` copies the scaffold template once and never updates it. If you upgrade `agency-swarm-custom` (e.g. a new FAL model is added or the FAL adapter is improved), your existing `~/agencies/my-first-swarm/` directory will not pick up those changes. There is no `agency-swarm sync` or `agency-swarm migrate` command yet.

The recommended workflow today:

1. Upgrade the tool environment:

   ```bash
   git -C /path/to/agency-swarm pull
   uv tool install --editable ".[openswarm]" --python 3.13 --force
   ```

2. Re-scaffold into a fresh directory:

   ```bash
   mkdir -p ~/agencies/my-first-swarm-v2
   cd ~/agencies/my-first-swarm-v2
   agency-swarm init openswarm
   ```

3. Copy your `.env` over from the old scaffold:

   ```bash
   cp ~/agencies/my-first-swarm/.env .
   ```

4. If you customized agent prompts or wrote your own tools inside the old scaffold, diff and merge them by hand into the new scaffold.

> **Note:** If your only customization was add-on keys in `.env`, step 3 is all you need. Anything beyond that is currently a manual merge. See [Known limitations](#known-limitations) for the missing `agency-swarm sync` command.

---

## Alternative install: pip + venv

For users who can't use `uv`. The bare `pip install -e .` against system or Homebrew Python on modern macOS fails with `error: externally-managed-environment` (PEP 668), so a project-local virtual environment is mandatory.

```bash
git clone https://github.com/ChucklesStern/agency-swarm.git
cd agency-swarm
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[openswarm]"
```

The `agency-swarm` command is then available only while the `.venv` is activated. Run `source .venv/bin/activate` in each new terminal.

> **Note:** If you mix `uv` and `pip`, do **not** run bare `pip install` inside a `uv`-managed `.venv`. `uv` venvs don't ship `pip`; bare `pip` falls through to system/Homebrew pip and you get PEP 668 again. Inside a uv venv, always use `uv pip install ".[openswarm]"`.

---

## Configuration and add-on keys

All keys live in the **scaffold's `.env` file** ([scaffold-dir]/.env), next to [onboard.py:36](src/agency_swarm/_templates/openswarm/onboard.py:36). The runtime helper in [model_availability.py:21](src/agency_swarm/_templates/openswarm/shared_tools/model_availability.py:21) reloads `Path.cwd() / .env` on each tool call, so the working directory at TUI launch must match the scaffold directory. Editing the `.env` in the cloned `agency-swarm/` repo root does nothing — that file is not what the runtime reads.

| Env var | Used by | Get one at |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI provider, `gpt-image-1.5`, `sora-2`, `sora-2-pro` | <https://platform.openai.com/api-keys> |
| `ANTHROPIC_API_KEY` | Anthropic via LiteLLM, Slides agent (preferred for HTML output) | <https://console.anthropic.com/settings/keys> |
| `GOOGLE_API_KEY` | Gemini, `gemini-2.5-flash-image`, `gemini-3-pro-image-preview`, `veo-3.1-*` | <https://aistudio.google.com/app/apikey> |
| `FAL_KEY` | All `fal:*` models, background removal, video edit | <https://fal.ai/dashboard/keys> |
| `COMPOSIO_API_KEY`, `COMPOSIO_USER_ID` | Composio integrations (Gmail, Slack, GitHub, …) | <https://composio.dev> |
| `SEARCH_API_KEY` | Web Search add-on | <https://www.searchapi.io> |
| `PEXELS_API_KEY`, `PIXABAY_API_KEY`, `UNSPLASH_ACCESS_KEY` | Stock photo lookups in Slides Agent | linked from `python onboard.py` |

To add or change a single key without re-running the full wizard, from the scaffold directory:

```bash
python onboard.py --reconfigure fal
```

Replace `fal` with any add-on id from: `search`, `anthropic`, `composio`, `google`, `fal`, `stock`. Or run `python onboard.py --reconfigure` with no id to re-enter all of them.

---

## FAL.AI quick reference

These are the FAL model IDs wired into the scaffold's image and video agents. All require `FAL_KEY` in the scaffold's `.env`.

### Text-to-image (5 models)

Pass any of these as the `model` field on the `image_generation_agent`.

| Model ID | Notes |
|---|---|
| `fal:flux-schnell` | Budget tier, fast. Good default for quick iterations. |
| `fal:flux-1.1-pro-ultra` | Premium tier, single variant only. |
| `fal:ideogram-v3` | Premium tier, single variant only. Strong typography. |
| `fal:recraft-v3` | Standard tier. Vector-style and design output. |
| `fal:nano-banana-2` | Standard tier. |

### Image edit / I2I (1 model)

Used by the `image_generation_agent`'s `EditImages` tool.

| Model ID | Notes |
|---|---|
| `fal:flux-pro-kontext` | Image-conditioned edit. |

### Video (7 models)

Used by the `video_generation_agent`.

| Model ID | Notes |
|---|---|
| `fal:kling-v3-pro-t2v` | Text-to-video. |
| `fal:kling-v3-pro-i2v` | Image-to-video. |
| `fal:hailuo-02-standard-t2v` | Text-to-video. |
| `fal:hailuo-02-pro-i2v` | Image-to-video, higher quality. |
| `fal:luma-ray-2-t2v` | Text-to-video. |
| `fal:wan-2.5-t2v` | Text-to-video. |
| `fal:seedance-1.5-pro` | Image-to-video. |

### Example prompts

T2I with explicit save path:

```
image_generation_agent: generate one 16:9 image of a snowy mountain at
sunrise using model fal:ideogram-v3, save to ./generated/mountain.png
```

I2V with explicit save path:

```
video_generation_agent: take ./generated/mountain.png and animate gentle
drifting clouds for 5 seconds using fal:seedance-1.5-pro, save to
./generated/mountain.mp4
```

> **Note:** Always include an explicit `./...` save path in the prompt. Without one, the agent often invents a `/mnt/image_agent/...` path inherited from a Linux container default. Those paths don't exist on macOS, the file vanishes, and the agent reports success anyway. See [§ 12 below](#12-explicit-save-paths-for-image--video-agents).

---

## Compatibility

- **Python:** 3.12 or 3.13. 3.14 will fail the `[openswarm]` install today (no `onnxruntime` wheel).
- **OS:** macOS (primary), Linux, Windows.
- **Model providers:** OpenAI (native), Anthropic, Google, Grok/xAI, Azure OpenAI, OpenRouter — all via LiteLLM. FAL.AI via the bundled adapter.

---

## Building a real agency

Same surface as upstream agency-swarm. Define agents, wire them into an `Agency`, and the OpenAI Agents SDK does the rest.

**Define agent roles:**

```python
from agency_swarm import Agent, ModelSettings

ceo = Agent(
    name="CEO",
    description="Responsible for client communication, task planning and management.",
    instructions="You must converse with other agents to ensure complete task execution.",
    files_folder="./files",
    schemas_folder="./schemas",
    tools=[my_custom_tool],
    model="gpt-5.4-mini",
    model_settings=ModelSettings(max_tokens=25000),
)
```

**Define communication flows:**

```python
from agency_swarm import Agency
from Developer import Developer
from VirtualAssistant import VirtualAssistant

dev = Developer()
va = VirtualAssistant()

agency = Agency(
    ceo,
    communication_flows=[
        ceo > dev,
        ceo > va,
        dev > va,
    ],
    shared_instructions="agency_manifesto.md",
)
```

Communication flows are directional — `>` means the left agent can initiate a conversation with the right agent.

**Scaffold an agent folder:**

```bash
agency-swarm create-agent-template MyAgent
```

This creates `MyAgent/` with `instructions.md`, a `tools/` folder, and a ready-to-import agent class.

**Run as web UI:**

```python
agency.copilot_demo()
```

**Run programmatically (async):**

```python
import asyncio

async def main():
    resp = await agency.get_response("Create a project skeleton.")
    print(resp.final_output)

asyncio.run(main())
```

`agency.get_response_sync(...)` exists for sync contexts, but async is recommended.

**Create tools:**

```python
from agency_swarm import function_tool

@function_tool
def my_custom_tool(example_field: str) -> str:
    """A brief description of what the custom tool does."""
    return f"Result: {example_field}"
```

Or extend `BaseTool`:

```python
from agency_swarm.tools import BaseTool
from pydantic import Field

class MyCustomTool(BaseTool):
    """Tool description used by the agent to decide when to call it."""
    example_field: str = Field(..., description="What this field is for.")

    def run(self) -> str:
        return f"Result: {self.example_field}"
```

---

## Persistent sessions

Use `FileSystemPersistence` to save and restore conversation history across runs:

```python
from agency_swarm import Agency, Agent
from agency_swarm.utils.persistence import FileSystemPersistence

persistence = FileSystemPersistence(".agency_swarm/threads")

agency = Agency(
    [agent],
    **persistence.callbacks("my-session"),
)
```

Each `chat_id` gets its own JSON file. The same session ID picks up where it left off on the next run.

---

## Project folder (shared workspace)

Give every agent in the agency access to a shared on-disk workspace:

```python
agency = Agency(
    [agent],
    project_folder="./workspace",
    enable_project_shell=True,
)
```

Files in `project_folder` are ingested into a vector store so agents can search them. With `enable_project_shell=True`, agents also get a persistent shell whose working directory starts at the project folder.

---

## Folder structure

Recommended layout for an agent module:

```
/your-specified-path/
|
|-- agency_manifesto.md or .txt # Agency's guiding principles
`-- AgentName/                  # Directory for the specific agent
    |-- files/                  # Files uploaded to OpenAI
    |-- schemas/                # OpenAPI schemas converted to tools
    |-- tools/                  # Tools imported by default
    |-- AgentName.py            # The main agent class file
    |-- __init__.py             # Marks the folder as a Python package
    |-- instructions.md or .txt # Instruction document for the agent
    `-- tools.py                # Custom tools specific to this agent
```

---

## Troubleshooting

### `zsh: command not found: #`

You pasted a multi-line `bash` snippet that included a line starting with `#`. Modern macOS uses zsh; without `setopt interactive_comments`, pasted `#` lines run as commands. **This README intentionally puts no `#` comments inside `bash` code blocks.** Other sources may. Fix once with:

```bash
echo 'setopt interactive_comments' >> ~/.zshrc
source ~/.zshrc
```

### `command not found: agency-swarm`

Either `uv tool update-shell` was never run, or the current terminal predates that change. Run `uv tool update-shell`, then close and reopen the terminal.

### `command not found: uv`

You used the `curl ... | sh` installer, which puts uv in `~/.local/bin` without modifying PATH. Either add `~/.local/bin` to PATH in your shell rc and source it, or uninstall and use `brew install uv` (recommended).

### `error: externally-managed-environment`

You ran bare `pip install ...` against system or Homebrew Python. Modern macOS enforces PEP 668 to prevent this. Use the `uv tool install` path above, or create a project-local venv first (`python3 -m venv .venv && source .venv/bin/activate`) and `pip install` inside it.

### `error: Executable already exists: agency-swarm`

A previous `uv tool install` (often from a curl-installed `uv`) left a wrapper behind. Force overwrite:

```bash
uv tool install --editable ".[openswarm]" --python 3.13 --force
```

Or remove first:

```bash
uv tool uninstall agency-swarm
uv tool install --editable ".[openswarm]" --python 3.13
```

### `error: Distribution onnxruntime==... can't be installed because it doesn't have a source distribution or wheel for the current platform`

`uv` picked Python 3.14. `onnxruntime` ships wheels only for cp312/cp313. Pass `--python 3.13` to every `uv` command, as shown above.

### `OpenSwarm dependencies appear to be missing (could not import: questionary). Install with: pip install ...`

The tool environment was installed without the `[openswarm]` extras. **Do not follow the suggested `pip install` line** — it will hit `externally-managed-environment` on macOS. Instead:

```bash
uv tool install --editable ".[openswarm]" --python 3.13 --force
```

### "I added `FAL_KEY` but the agent still says FAL is unavailable"

Two common causes:

1. **The key is in the wrong `.env`.** It must live in `<scaffold-dir>/.env`, not the cloned `agency-swarm/` repo's `.env`. The runtime reads `Path.cwd() / ".env"` and the scaffold's `.env` ([onboard.py:36](src/agency_swarm/_templates/openswarm/onboard.py:36)).
2. **The scaffold is from a pre-FAL release.** Your scaffold may have been created before this fork added FAL — and `agency-swarm init` does not retroactively update existing scaffolds. Re-scaffold into a new directory (see [Updating after agency-swarm-custom upgrades](#updating-after-agency-swarm-custom-upgrades)).

After fixing, restart the TUI so the new env is reloaded.

---

## Known limitations

Tracked here because they affect new-user setup but are code-side, not doc-side, fixes.

- **No `agency-swarm sync` or `agency-swarm migrate` command.** Existing scaffolds are snapshots; they do not auto-update when `agency-swarm-custom` upgrades. Workaround: re-scaffold into a fresh directory and copy `.env` over.
- **Project `.venv` installs upstream `agency-swarm`, not the fork.** [`requirements.txt:1`](src/agency_swarm/_templates/openswarm/requirements.txt:1) pins `agency-swarm[fastapi,jupyter,litellm]>=1.9.7` from PyPI. Customizations to `agency_swarm` package internals in the fork do not reach the running agents. FAL works only because the FAL adapter lives in the scaffold (`shared_tools/fal_adapter/`), not in the `agency_swarm` package.
- **`/auth` is a ghost command.** Error messages from `image_model_availability_message` and `video_model_availability_message` ([model_availability.py:82](src/agency_swarm/_templates/openswarm/shared_tools/model_availability.py:82)) tell the user to "run `/auth`". That slash command is a literal string only — it is not wired into the TUI. To re-enter keys, use `python onboard.py --reconfigure <addon-id>` from the scaffold directory.
- **Linux-container save paths.** The image/video agents will default to `/mnt/image_agent/...` if you don't supply one. Always pass an explicit `./...` path in your prompt.

---

## Learn more

- Installation: <https://agency-swarm.ai/welcome/installation>
- From-scratch guide: <https://agency-swarm.ai/welcome/getting-started/from-scratch>
- Tools overview: <https://agency-swarm.ai/core-framework/tools/overview>
- Agents overview: <https://agency-swarm.ai/core-framework/agents/overview>
- Agencies overview: <https://agency-swarm.ai/core-framework/agencies/overview>
- Communication flows: <https://agency-swarm.ai/core-framework/agencies/communication-flows>
- Running an agency: <https://agency-swarm.ai/core-framework/agencies/running-agency>
- Observability: <https://agency-swarm.ai/additional-features/observability>

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. The bundled OpenSwarm scaffold is also MIT with attribution; see `OPENSWARM_LICENSE` and `OPENSWARM_NOTICE.md` written into your project directory by `agency-swarm init openswarm`.

## Need help?

Upstream support: [VRSEN Discord](https://discord.gg/cw2xBaWfFM), [Agents-as-a-Service](https://agents.vrsen.ai/), or schedule a call at <https://calendly.com/vrsen/ai-readiness-call>.

<a name="12-explicit-save-paths-for-image--video-agents"></a>
