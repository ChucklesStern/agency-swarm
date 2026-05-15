from typing import Optional
from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from datetime import datetime

from helpers import execute_composio_tool


class ReadSlackMessages(BaseTool):
    """
    Reads messages from a Slack channel or DM. Use channel ID (e.g., C06NX4Q1ACE) 
    or channel name (e.g., #general). For threads, provide the parent message timestamp.
    """
    
    channel: str = Field(
        ...,
        description="Channel ID or name (e.g., 'C06NX4Q1ACE' or '#general')"
    )
    
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of messages to fetch (1-50). Default: 10"
    )
    
    thread_ts: Optional[str] = Field(
        default=None,
        description="Thread parent timestamp to read replies. Leave empty for main channel."
    )
    
    include_replies: bool = Field(
        default=False,
        description="Include thread replies for messages that have them. Default: False"
    )
    
    def run(self):
        try:
            # Resolve channel name to ID if needed
            channel_id = self._resolve_channel(execute_composio_tool, self.channel)
            if channel_id.startswith("Error"):
                return channel_id
            
            # Fetch messages
            if self.thread_ts:
                messages = self._fetch_thread(execute_composio_tool, channel_id)
            else:
                messages = self._fetch_channel(execute_composio_tool, channel_id)
            
            if not messages:
                return json.dumps({"count": 0, "messages": []}, indent=2)
            
            # Format output
            formatted = []
            for msg in messages[:self.limit]:
                formatted_msg = self._format_message(msg)
                
                # Fetch thread replies if requested and message has replies
                if self.include_replies and msg.get("reply_count", 0) > 0:
                    replies = self._fetch_thread_replies(execute_composio_tool, channel_id, msg.get("ts"))
                    if replies:
                        formatted_msg["thread"] = [self._format_message(r) for r in replies]
                
                formatted.append(formatted_msg)
            
            return json.dumps({
                "count": len(formatted),
                "channel_id": channel_id,
                "messages": formatted
            }, indent=2)
            
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _resolve_channel(self, execute_tool, channel: str) -> str:
        """Resolves channel name to ID."""
        # Already an ID
        if channel.startswith(("C", "D", "G")):
            return channel
        
        # Remove # prefix
        name = channel.lstrip("#")
        
        # Search for channel
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
    
    def _fetch_channel(self, execute_tool, channel_id: str) -> list:
        """Fetches messages from channel."""
        result = execute_tool(
            tool_name="SLACK_FETCH_CONVERSATION_HISTORY",
            arguments={
                "channel": channel_id,
                "limit": self.limit
            },
        )
        
        if result.get("error"):
            return []
        
        return result.get("data", {}).get("messages", [])
    
    def _fetch_thread(self, execute_tool, channel_id: str) -> list:
        """Fetches thread replies for thread_ts parameter."""
        result = execute_tool(
            tool_name="SLACK_FETCH_MESSAGE_THREAD_FROM_A_CONVERSATION",
            arguments={
                "channel": channel_id,
                "ts": self.thread_ts,
                "limit": self.limit
            },
        )
        
        if result.get("error"):
            return []
        
        return result.get("data", {}).get("messages", [])
    
    def _fetch_thread_replies(self, execute_tool, channel_id: str, parent_ts: str) -> list:
        """Fetches thread replies for a specific message."""
        result = execute_tool(
            tool_name="SLACK_FETCH_MESSAGE_THREAD_FROM_A_CONVERSATION",
            arguments={
                "channel": channel_id,
                "ts": parent_ts,
                "limit": 20
            },
        )
        
        if result.get("error"):
            return []
        
        messages = result.get("data", {}).get("messages", [])
        # Skip the parent message (first one), return only replies
        return messages[1:] if len(messages) > 1 else []
    
    def _format_message(self, msg: dict) -> dict:
        """Formats message for output."""
        files = msg.get("files", [])
        attachments = [f.get("name") or "file" for f in files] if files else None
        
        formatted = {
            "sender": msg.get("user", msg.get("bot_id", "unknown")),
            "text": msg.get("text", ""),
            "ts": msg.get("ts"),
            "time": self._format_ts(msg.get("ts"))
        }
        
        if msg.get("reply_count"):
            formatted["replies"] = msg.get("reply_count")
        
        if attachments:
            formatted["attachments"] = attachments
        
        return formatted
    
    def _format_ts(self, ts: str) -> str:
        """Formats timestamp."""
        if not ts:
            return ""
        try:
            return datetime.fromtimestamp(float(ts.split(".")[0])).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return ts


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("ReadSlackMessages Test")
    print("-" * 40)
    
    # Test reading from aaas-gains-ai with replies
    tool = ReadSlackMessages(channel="#aaas-gains-ai", limit=3, include_replies=True)
    print(tool.run())

