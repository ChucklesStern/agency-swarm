"""
Agency Persistence Example
==========================

Demonstrates how to persist conversation history across sessions using
``FileSystemPersistence``.  After the first run, re-run this script and the
agent will recall information from the previous session.

Persistence directory
---------------------
Conversations are stored as JSON files under ``.agency_swarm/threads/`` in the
current working directory.  You can inspect or delete them at any time:

    ls .agency_swarm/threads/
    rm -rf .agency_swarm/threads/

Note on AGENCY_SWARM_CHATS_DIR
-------------------------------
``AGENCY_SWARM_CHATS_DIR`` is a **separate** environment variable that
controls the internal cache directory used for conversation-starter caching and
other framework internals.  It does **not** configure ``FileSystemPersistence``.
Set it if you want to move the internal cache; use ``FileSystemPersistence`` to
control where your conversation threads are stored.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

from agency_swarm import ModelSettings

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")

script_dir = Path(__file__).parent
project_root = script_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root / "src"))

from agency_swarm import Agency, Agent, FileSystemPersistence  # noqa: E402

# Store threads in a local, inspectable directory next to the working directory.
# Each chat session gets its own JSON file: .agency_swarm/threads/{chat_id}.json
PERSISTENCE_DIR = Path(".agency_swarm/threads")
persistence = FileSystemPersistence(PERSISTENCE_DIR)

# In production, derive chat_id from your session/user management system.
chat_id = "demo_session"

# Initialize agent
assistant_agent = Agent(
    name="AssistantAgent",
    instructions="You are a helpful assistant. Answer questions and help users with their tasks.",
    tools=[],
    model_settings=ModelSettings(temperature=0.0),
)

# Wire persistence into Agency using the callbacks helper.
# load_threads_callback and save_threads_callback are injected as keyword arguments.
agency = Agency(
    assistant_agent,
    shared_instructions="Be helpful and concise in your responses.",
    **persistence.callbacks(chat_id),
)

TEST_INFO = "blue and lucky number is 77"


async def run_persistent_conversation() -> None:
    """
    Demonstrates thread persistence in Agency Swarm v1.x.

    First run:  the agent learns and saves your favorite color and lucky number.
    Second run: a fresh agency instance loads the saved history and recalls them.
    """

    user_message_1 = (
        f"Hello. Please remember that my favorite color is {TEST_INFO}. I'll ask you about it later."
    )
    print(f"\n--- Turn 1 ---\nSending: {user_message_1}")
    response1 = await agency.get_response(message=user_message_1)
    print(f"Response: {response1.final_output}")
    print(f"\nConversation saved to: {PERSISTENCE_DIR / (chat_id + '.json')}")

    await asyncio.sleep(1)

    # Simulate an application restart by creating a new Agency instance.
    # The new instance loads the saved history via load_threads_callback.
    print("\n--- Simulating Application Restart ---")

    assistant_agent_reloaded = Agent(
        name="AssistantAgent",
        instructions="You are a helpful assistant. Answer questions and help users with their tasks.",
        tools=[],
        model_settings=ModelSettings(temperature=0.0),
    )

    persistence_reloaded = FileSystemPersistence(PERSISTENCE_DIR)
    agency_reloaded = Agency(
        assistant_agent_reloaded,
        shared_instructions="Be helpful and concise in your responses.",
        **persistence_reloaded.callbacks(chat_id),
    )

    user_message_2 = "What was my favorite color and lucky number I told you earlier?"
    print(f"\n--- Turn 2 ---\nSending: {user_message_2}")
    response2 = await agency_reloaded.get_response(message=user_message_2)
    print(f"Response: {response2.final_output}")

    if response2.final_output and "blue" in response2.final_output.lower() and "77" in response2.final_output.lower():
        print(f"\n✅ SUCCESS: Agent recalled '{TEST_INFO}' across the simulated restart.")
    else:
        print(f"\n❌ FAILURE: Agent did not recall '{TEST_INFO}'.")
        print(f"   Response was: {response2.final_output}")


if __name__ == "__main__":
    print("\n=== Agency Swarm v1.x File-Based Persistence Demo ===")
    print(f"Persistence directory: {PERSISTENCE_DIR.resolve()}")

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    asyncio.run(run_persistent_conversation())
