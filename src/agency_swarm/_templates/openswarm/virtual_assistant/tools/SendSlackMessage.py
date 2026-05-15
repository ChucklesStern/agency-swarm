from typing import Optional
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class SendSlackMessage(BaseTool):
    """
    Sends a message to a Slack channel or DM. Supports threaded replies.
    Use channel ID or name. For replies, provide the parent message timestamp.
    """
    
    channel: str = Field(
        ...,
        description="Channel ID or name (e.g., 'C06NX4Q1ACE', '#general', or '@username')"
    )
    
    text: str = Field(
        ...,
        description="Message text to send. Use Slack formatting."
    )
    
    thread_ts: Optional[str] = Field(
        default=None,
        description="Parent message timestamp to reply in thread. Leave empty for new message."
    )
    
    def run(self):
        try:
            # Resolve channel
            channel_id = self._resolve_channel(execute_composio_tool, self.channel)
            if channel_id.startswith("Error"):
                return channel_id
            
            # Send message
            args = {
                "channel": channel_id,
                "text": self.text
            }
            
            if self.thread_ts:
                args["thread_ts"] = self.thread_ts
            
            result = execute_composio_tool(
                tool_name="SLACK_SEND_MESSAGE",
                arguments=args,
            )
            
            if result.get("error"):
                return f"Error sending message: {result.get('error')}"
            
            data = result.get("data", {})
            msg = data.get("message", {})
            
            return json.dumps({
                "success": True,
                "channel_id": channel_id,
                "ts": msg.get("ts"),
                "thread_ts": self.thread_ts,
                "permalink": self._build_permalink(data, channel_id, msg.get("ts"))
            }, indent=2)
            
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _resolve_channel(self, execute_tool, channel: str) -> str:
        """Resolves channel/user name to ID."""
        # Already an ID
        if channel.startswith(("C", "D", "G")):
            return channel
        
        # Handle @username for DMs
        if channel.startswith("@"):
            return self._find_user_dm(execute_tool, channel[1:])
        
        # Remove # prefix and find channel
        name = channel.lstrip("#")
        
        result = execute_tool(
            tool_name="SLACK_FIND_CHANNELS",
            arguments={"query": name},
        )
        
        if result.get("error"):
            return f"Error: Could not find channel '{name}'"
        
        channels = result.get("data", {}).get("channels", [])
        for ch in channels:
            if ch.get("name") == name:
                return ch.get("id")
        
        return f"Error: Channel '{name}' not found"
    
    def _find_user_dm(self, execute_tool, username: str) -> str:
        """Finds DM channel for a user."""
        # Find user
        result = execute_tool(
            tool_name="SLACK_FIND_USERS",
            arguments={"query": username},
        )
        
        if result.get("error"):
            return f"Error: Could not find user '{username}'"
        
        members = result.get("data", {}).get("members", [])
        target_user = None
        
        for member in members:
            name = member.get("name", "").lower()
            display = member.get("profile", {}).get("display_name", "").lower()
            real = member.get("profile", {}).get("real_name", "").lower()
            
            if username.lower() in [name, display, real]:
                target_user = member.get("id")
                break
        
        if not target_user:
            return f"Error: User '{username}' not found"
        
        # Find existing DM or it will be created when sending
        # For now, return a marker that we need to send to user
        # Slack's SEND_MESSAGE can accept user IDs for DMs
        return target_user
    
    def _build_permalink(self, data: dict, channel_id: str, ts: str) -> str:
        """Builds message permalink if available."""
        # Some responses include permalink directly
        if "permalink" in data:
            return data["permalink"]
        
        # Otherwise return empty - would need workspace URL
        return ""


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("SendSlackMessage Test")
    print("-" * 40)
    print("Skipping actual send to avoid spam")
    print("Example usage:")
    print('  SendSlackMessage(channel="#random", text="Hello!")')
    print('  SendSlackMessage(channel="C123", text="Reply", thread_ts="1234.5678")')

