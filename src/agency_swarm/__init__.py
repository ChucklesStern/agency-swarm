import importlib
import importlib.util

import agents as _agents
from dotenv import load_dotenv

# Automatically load environment variables from .env when the package is imported
load_dotenv(override=True)

# Re-export Agents SDK utilities for simpler imports in docs/examples.
_SDK_SHADOWED_EXPORTS = {"Agent", "Handoff", "function_tool", "__version__"}
_SDK_EXPORT_ALIASES = {"Agent": "SDKAgent", "Handoff": "SDKHandoff"}

for _sdk_name in _agents.__all__:
    if _sdk_name in _SDK_EXPORT_ALIASES:
        globals()[_SDK_EXPORT_ALIASES[_sdk_name]] = getattr(_agents, _sdk_name)
    elif _sdk_name not in _SDK_SHADOWED_EXPORTS:
        globals()[_sdk_name] = getattr(_agents, _sdk_name)

# Optional: LitellmModel requires the litellm extra
try:
    from agents.extensions.models.litellm_model import LitellmModel  # noqa: E402, F401

    _LITELLM_AVAILABLE = True
except ImportError:
    _LITELLM_AVAILABLE = False

_JUPYTER_AVAILABLE = importlib.util.find_spec("jupyter_client") is not None
_OPENCLAW_DEPS_AVAILABLE = (
    importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None
)
_OPENCLAW_AGENT_DEPS_AVAILABLE = importlib.util.find_spec("httpx") is not None

from agents.model_settings import Headers, MCPToolChoice, ToolChoice  # noqa: E402
from openai._types import Body, Query  # noqa: E402
from openai.types.responses import ResponseIncludable  # noqa: E402
from openai.types.shared import Reasoning  # noqa: E402

from .agency.core import Agency  # noqa: E402
from .agent.core import AgencyContext, Agent  # noqa: E402
from .agent.execution_streaming import StreamingRunResponse  # noqa: E402
from .context import MasterContext  # noqa: E402
from .hooks import PersistenceHooks  # noqa: E402
from .integrations.fastapi import run_fastapi  # noqa: E402
from .integrations.mcp_server import run_mcp  # noqa: E402
from .tools import (  # noqa: E402
    BaseTool,
    CodeInterpreter,
    CodeInterpreterContainer,
    CodeInterpreterContainerCodeInterpreterToolAuto,
    Handoff,
    ImageGeneration,
    ImageGenerationInputImageMask,
    LoadFileAttachment,
    Mcp,
    McpAllowedTools,
    McpRequireApproval,
    PersistentShellTool,
    SendMessage,
    ToolOutputFileContent,
    ToolOutputFileContentDict,
    ToolOutputImage,
    ToolOutputImageDict,
    ToolOutputText,
    ToolOutputTextDict,
    function_tool,
    tool_output_file_from_file_id,
    tool_output_file_from_path,
    tool_output_file_from_url,
    tool_output_image_from_file_id,
    tool_output_image_from_path,
)
from .utils.persistence import FileSystemPersistence  # noqa: E402
from .utils.thread import ThreadManager  # noqa: E402

__all__ = [
    "Agent",
    "Agency",
    "AgencyContext",
    "StreamingRunResponse",
    "BaseTool",
    "MasterContext",
    "FileSystemPersistence",
    "ThreadManager",
    "PersistenceHooks",
    "SendMessage",
    "Handoff",
    "run_fastapi",
    "run_mcp",
    # Local names that intentionally shadow or alias Agents SDK exports
    "function_tool",
    "SDKAgent",
    "SDKHandoff",
    # Additional OpenAI/OpenAI SDK response types
    "Reasoning",
    "CodeInterpreter",
    "ImageGeneration",
    "Mcp",
    "CodeInterpreterContainer",
    "CodeInterpreterContainerCodeInterpreterToolAuto",
    "ImageGenerationInputImageMask",
    "Computer",
    "AsyncComputer",
    "McpAllowedTools",
    "McpRequireApproval",
    "Headers",
    "ToolChoice",
    "MCPToolChoice",
    "Query",
    "Body",
    "ResponseIncludable",
    "LoadFileAttachment",
    "PersistentShellTool",
    "ToolOutputText",
    "ToolOutputTextDict",
    "ToolOutputImage",
    "ToolOutputImageDict",
    "ToolOutputFileContent",
    "ToolOutputFileContentDict",
    "tool_output_image_from_path",
    "tool_output_image_from_file_id",
    "tool_output_file_from_path",
    "tool_output_file_from_url",
    "tool_output_file_from_file_id",
]
__all__.extend(name for name in _agents.__all__ if name not in _SDK_SHADOWED_EXPORTS and name not in __all__)

_OPENCLAW_EXPORTS = {
    "OpenClawIntegrationConfig",
    "OpenClawRuntime",
    "create_openclaw_proxy_router",
    "attach_openclaw_to_fastapi",
    "build_openclaw_responses_model",
}
if _OPENCLAW_DEPS_AVAILABLE:
    __all__.extend(sorted(_OPENCLAW_EXPORTS))
if _OPENCLAW_AGENT_DEPS_AVAILABLE:
    __all__.append("OpenClawAgent")

# Conditionally add LitellmModel if available
if _LITELLM_AVAILABLE:
    __all__.append("LitellmModel")

# Conditionally add IPythonInterpreter if available
if _JUPYTER_AVAILABLE:
    __all__.append("IPythonInterpreter")


def __getattr__(name: str):
    """Provide helpful error messages for optional dependencies."""
    if name == "LitellmModel" and not _LITELLM_AVAILABLE:
        raise ImportError(
            "`litellm` is required to use the LitellmModel. "
            "You can install it via the optional dependency group: "
            "`pip install 'openai-agents[litellm]'`."
        )
    if name == "IPythonInterpreter":
        from .tools import IPythonInterpreter

        globals()[name] = IPythonInterpreter
        return IPythonInterpreter
    if name in _OPENCLAW_EXPORTS:
        if not _OPENCLAW_DEPS_AVAILABLE:
            raise ImportError(
                "OpenClaw FastAPI integration requires optional dependencies. "
                "Install with `pip install 'agency-swarm[fastapi]'`."
            )
        try:
            module = importlib.import_module(".integrations.openclaw", package=__name__)
        except ModuleNotFoundError as exc:
            raise ImportError(
                "OpenClaw FastAPI integration requires optional dependencies. "
                "Install with `pip install 'agency-swarm[fastapi]'`."
            ) from exc
        value = getattr(module, name)
        globals()[name] = value
        return value
    if name == "OpenClawAgent":
        try:
            module = importlib.import_module(".agents", package=__name__)
        except ModuleNotFoundError as exc:
            raise ImportError(
                "OpenClawAgent requires optional dependencies. Install with `pip install 'agency-swarm[fastapi]'`."
            ) from exc
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
