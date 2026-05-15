from typing import Literal
from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from datetime import datetime

from helpers import execute_composio_tool

class CheckUnreadSlackMessages(BaseTool):
    """
    Retrieves unread Slack messages using the search API.
    
    Efficiently finds unread messages with minimal API calls:
    1. Searches for recent messages (1 call)
    2. Checks unread status for top conversations (max 10 calls)
    
    Returns sender, message preview, timestamp, permalink, and attachment info.
    """
    
    conversation_types: Literal["dm", "channels", "all"] = Field(
        default="dm",
        description=(
            "'dm' for direct messages only (default), "
            "'channels' for public/private channels only, "
            "'all' for both"
        )
    )
    
    max_messages: int = Field(
        default=20,
        ge=1,
        le=50,
        description="Maximum number of unread messages to return (1-50). Default is 20."
    )
    
    days_back: int = Field(
        default=7,
        ge=1,
        le=30,
        description="How many days back to search for messages (1-30). Default is 7."
    )
    
    include_bots: bool = Field(
        default=True,
        description="Include messages from bots. Default is True."
    )
    
    def run(self):
        try:
            search_results = self._search_recent_messages(execute_composio_tool)

            if not search_results:
                return json.dumps({
                    "total_unread": 0,
                    "messages": [],
                    "summary": "No recent messages found."
                }, indent=2)

            unread_messages = self._filter_unread(execute_composio_tool, search_results)
            
            # Sort by timestamp (newest first) and limit
            unread_messages.sort(key=lambda x: x.get("_ts", "0"), reverse=True)
            unread_messages = unread_messages[:self.max_messages]
            
            # Clean up internal fields
            for msg in unread_messages:
                msg.pop("_ts", None)
            
            # Build summary
            if not unread_messages:
                summary = "No unread messages."
            else:
                conv_ids = set(msg["conversation_id"] for msg in unread_messages)
                summary = f"{len(unread_messages)} unread message{'s' if len(unread_messages) > 1 else ''} from {len(conv_ids)} conversation{'s' if len(conv_ids) > 1 else ''}."
            
            return json.dumps({
                "total_unread": len(unread_messages),
                "messages": unread_messages,
                "summary": summary
            }, indent=2)
            
        except Exception as e:
            return f"Error fetching unread Slack messages: {str(e)}"
    
    def _search_recent_messages(self, execute_tool) -> list:
        """Searches for recent messages (1 API call)."""
        from datetime import timedelta
        
        start_date = (datetime.now() - timedelta(days=self.days_back)).strftime("%Y-%m-%d")
        
        if self.conversation_types == "dm":
            query = f"after:{start_date} is:dm"
        elif self.conversation_types == "channels":
            query = f"after:{start_date} -is:dm"
        else:
            query = f"after:{start_date}"
        
        result = execute_tool(
            tool_name="SLACK_SEARCH_MESSAGES",
            arguments={
                "query": query,
                "sort": "timestamp",
                "sort_dir": "desc",
                "count": min(self.max_messages * 2, 100)
            },
        )
        
        if isinstance(result, dict) and result.get("error"):
            return []
        
        return result.get("data", {}).get("messages", {}).get("matches", [])
    
    def _filter_unread(self, execute_tool, messages: list) -> list:
        """Filters to unread messages only (max 2 API calls for last_read checks)."""
        # Group messages by channel
        by_channel = {}
        for msg in messages:
            channel = msg.get("channel", {})
            channel_id = channel.get("id")
            if not channel_id:
                continue
            
            # Filter bots if needed
            if not self.include_bots and (msg.get("bot_id") or msg.get("subtype")):
                continue
            
            if channel_id not in by_channel:
                by_channel[channel_id] = {
                    "name": self._get_display_name(channel),
                    "messages": []
                }
            by_channel[channel_id]["messages"].append(msg)
        
        # Check last_read for top 10 channels (to limit API calls)
        unread_messages = []
        channels_checked = 0
        
        for channel_id, conv_data in by_channel.items():
            if channels_checked >= 10:
                break
            
            channels_checked += 1
            
            # Get last_read timestamp
            info_result = execute_tool(
                tool_name="SLACK_RETRIEVE_CONVERSATION_INFORMATION",
                arguments={"channel": channel_id},
            )
            
            if isinstance(info_result, dict) and info_result.get("error"):
                continue
            
            last_read = info_result.get("data", {}).get("channel", {}).get("last_read", "0")
            
            # Filter to messages after last_read
            for msg in conv_data["messages"]:
                ts = msg.get("ts", "0")
                if ts > last_read:
                    unread_messages.append(self._format_message(
                        msg, conv_data["name"], channel_id
                    ))
        
        return unread_messages
    
    def _get_display_name(self, channel: dict) -> str:
        """Gets display name for channel."""
        if channel.get("is_im"):
            return channel.get("name", "Direct Message")
        return f"#{channel.get('name', 'Unknown')}"
    
    def _format_message(self, msg: dict, conv_name: str, channel_id: str) -> dict:
        """Formats a message for output."""
        files = msg.get("files", [])
        attachments = [f.get("name") or f.get("title") or "file" for f in files] if files else None
        
        text = msg.get("text", "")
        if len(text) > 200:
            text = text[:197] + "..."
        
        return {
            "conversation": conv_name,
            "conversation_id": channel_id,
            "sender": msg.get("username", "Unknown"),
            "text": text,
            "timestamp": self._format_timestamp(msg.get("ts")),
            "permalink": msg.get("permalink", ""),
            "has_attachment": len(files) > 0,
            "attachments": attachments,
            "_ts": msg.get("ts")
        }
    
    def _format_timestamp(self, ts: str) -> str:
        """Formats Slack timestamp."""
        if not ts:
            return ""
        try:
            unix_ts = float(ts.split(".")[0])
            return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            return ts


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("CheckUnreadSlackMessages Test")
    print("-" * 40)
    
    tool = CheckUnreadSlackMessages(
        conversation_types="all",
        max_messages=10,
        days_back=7
    )
    print(tool.run())
