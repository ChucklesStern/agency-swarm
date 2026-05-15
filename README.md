# 🐝 Agency Swarm

![Framework](https://firebasestorage.googleapis.com/v0/b/vrsen-ai/o/public%2Fgithub%2FLOGO_BG_large_bold_shadow%20(1).jpg?alt=media&token=8c681331-2a7a-4a69-b21b-3ab1f9bf1a23)

## Overview

The **Agency Swarm** is a framework for building multi-agent applications. It leverages and extends the [OpenAI Agents SDK](https://github.com/openai/openai-agents-python), providing specialized features for creating, orchestrating, and managing collaborative swarms of AI agents.

This framework continues the original vision of Arsenii Shatokhin (aka VRSEN) to simplify the creation of AI agencies by thinking about automation in terms of real-world organizational structures, making it intuitive for both agents and users.

**Migrating from v0.x?** Please see our [Migration Guide](https://agency-swarm.ai/migration/guide) for details on adapting your project to this new SDK-based version.

[![Docs](https://img.shields.io/website?label=Docs&up_message=available&url=https://agency-swarm.ai/)](https://agency-swarm.ai)
[![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)](https://github.com/VRSEN/agency-swarm/actions?query=branch%3Amain+event%3Apush)
[![Subscribe on YouTube](https://img.shields.io/youtube/channel/subscribers/UCSv4qL8vmoSH7GaPjuqRiCQ)](https://youtube.com/@vrsen/)
[![Follow on Twitter](https://img.shields.io/twitter/follow/__vrsen__.svg?style=social&label=Follow%20%40__vrsen__)](https://twitter.com/__vrsen__)
[![Join our Discord!](https://img.shields.io/discord/1200037936352202802?label=Discord)](https://discord.gg/cw2xBaWfFM)
[![Agents-as-a-Service](https://img.shields.io/website?label=Agents-as-a-Service&up_message=For%20Business&url=https%3A%2F%2Fvrsen.ai)](https://agents.vrsen.ai)

### Key Features

- **Customizable Agent Roles**: Define distinct agent roles (e.g., CEO, Virtual Assistant, Developer) with tailored instructions, tools, and capabilities within the Agency Swarm framework, leveraging the underlying OpenAI Agents SDK.
- **Full Control Over Prompts/Instructions**: Maintain complete control over each agent’s guiding prompts (instructions) for precise behavior customization.
- **Type-Safe Tools**: Develop tools using Pydantic models for automatic argument validation, compatible with the OpenAI Agents SDK’s `FunctionTool` format.
- **Orchestrated Agent Communication**: Agents communicate via a dedicated `send_message` tool, with interactions governed by explicit, directional `communication_flows` defined on the `Agency`.
- **Flexible State Persistence**: Manage conversation history by providing `load_threads_callback` and `save_threads_callback` to the `Agency`, enabling persistence across sessions (e.g., DB/file storage).
- **Multi-Agent Orchestration**: Build agent workflows on the OpenAI Agents SDK foundation, enhanced by Agency Swarm’s structured orchestration layer.
- **Production-Ready Focus**: Built for reliability and designed for easy deployment in real-world environments.

## Installation

Clone the repository and install from source:

```bash
git clone https://github.com/ChucklesStern/agency-swarm.git
cd agency-swarm
```

**With uv (recommended):**

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies and make the agency-swarm command available globally
uv sync --all-extras
uv tool install --editable .
```

**With pip:**

```bash
pip install -e .
```

> **Note:** Python 3.12+ is required. On macOS, if `pip` is not found, use `python3 -m pip install -e .` instead.

> **v1.x note:** The framework targets the OpenAI Agents SDK + Responses API.
> Migrating from v0.x? See the [Migration Guide](https://agency-swarm.ai/migration/guide).

### Compatibility
- **Python**: 3.12+
- **Model backends:**
  - **OpenAI (native):** GPT-5 family, GPT-4o, etc.
  - **Via LiteLLM (router):** Anthropic (Claude), Google (Gemini), Grok (xAI), Azure OpenAI, **OpenRouter (gateway)**, etc.
- **OS**: macOS, Linux, Windows

## Getting Started

Agency Swarm is a framework — you write an `agency.py` that defines your agents, then launch it with the CLI. Here is the complete first-boot flow.

### Step 1 — Set your OpenAI key

Create a `.env` file in your project directory (auto-loaded on startup):

```
OPENAI_API_KEY=your_key_here
```

Or export it in your shell:

```bash
export OPENAI_API_KEY="your_key_here"
```

### Step 2 — Create your project

```bash
mkdir my-agency && cd my-agency
```

Create `agency.py`:

```python
from agency_swarm import Agency, Agent

assistant = Agent(
    name="Assistant",
    instructions="You are a helpful assistant.",
    model="gpt-4o",
)

agency = Agency(assistant)
```

### Step 3 — Launch the TUI

```bash
agency-swarm tui
```

The CLI discovers the `agency` variable in `agency.py` and launches the terminal UI automatically. On first run it sets up the terminal app, then reuses it on later runs.

You can also point it at any file explicitly:

```bash
agency-swarm tui path/to/my_agency.py
```

Or use a factory function instead of a global variable:

```python
def create_agency() -> Agency:
    return Agency(assistant)
```

---

### Building a real agency

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

This creates a `MyAgent/` directory with `instructions.md`, a `tools/` folder, and a ready-to-import agent class.

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

### Persistent sessions

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

### Project folder (shared workspace)

Give every agent in the agency access to a shared on-disk workspace:

```python
agency = Agency(
    [agent],
    project_folder="./workspace",       # created automatically
    enable_project_shell=True,          # opt-in shell access for agents
)
```

Files in `project_folder` are ingested into a vector store so agents can search them. With `enable_project_shell=True`, agents also get a persistent shell whose working directory starts at the project folder.

### Folder Structure

Recommended agent folder structure:

```
/your-specified-path/
│
├── agency_manifesto.md or .txt # Agency's guiding principles (created if not present)
└── AgentName/                  # Directory for the specific agent
    ├── files/                  # Directory for files that will be uploaded to OpenAI
    ├── schemas/                # Directory for OpenAPI schemas to be converted into tools
    ├── tools/                  # Directory for tools to be imported by default.
    ├── AgentName.py            # The main agent class file
    ├── __init__.py             # Initializes the agent folder as a Python package
    ├── instructions.md or .txt # Instruction document for the agent
    └── tools.py                # Custom tools specific to the agent's role.

```

This structure ensures that each agent has its dedicated space with all necessary files to start working on its specific tasks. The `tools.py` can be customized to include tools and functionalities specific to the agent's role.

## Learn More

- Installation: https://agency-swarm.ai/welcome/installation
- From Scratch guide: https://agency-swarm.ai/welcome/getting-started/from-scratch
- Cursor IDE workflow: https://agency-swarm.ai/welcome/getting-started/cursor-ide
- Tools overview: https://agency-swarm.ai/core-framework/tools/overview
- Agents overview: https://agency-swarm.ai/core-framework/agents/overview
- Agencies overview: https://agency-swarm.ai/core-framework/agencies/overview
- Communication flows: https://agency-swarm.ai/core-framework/agencies/communication-flows
- Running an agency: https://agency-swarm.ai/core-framework/agencies/running-agency
- Agent Swarm CLI: https://agency-swarm.ai/core-framework/agencies/agent-swarm-cli
- Observability: https://agency-swarm.ai/additional-features/observability

## Contributing

For details on how to contribute to Agency Swarm, please refer to the [Contributing Guide](CONTRIBUTING.md).

## License

Agency Swarm is open-source and licensed under [MIT](https://opensource.org/licenses/MIT).



## Need Help?

If you need help creating custom agent swarms for your business, check out our [Agents-as-a-Service](https://agents.vrsen.ai/) subscription, or schedule a consultation with me at https://calendly.com/vrsen/ai-readiness-call
