from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class GetSlackUserInfo(BaseTool):
    """
    Gets Slack user details by ID, email, or name. Returns name, email, title, and status.
    """
    
    user: str = Field(
        ...,
        description="User ID (U06NF4U24KE), email, or display name to look up"
    )
    
    def run(self):
        try:
            # Determine lookup method
            if self.user.startswith("U") and len(self.user) == 11:
                return self._get_by_id(execute_composio_tool, self.user)
            elif "@" in self.user:
                return self._get_by_email(execute_composio_tool, self.user)
            else:
                return self._get_by_name(execute_composio_tool, self.user)
                
        except Exception as e:
            return f"Error: {str(e)}"
    
    def _get_by_id(self, execute_tool, slack_user_id: str) -> str:
        """Gets user by Slack user ID."""
        result = execute_tool(
            tool_name="SLACK_GET_USER_INFO",
            arguments={"user": slack_user_id},
        )
        
        if result.get("error"):
            return f"Error: User '{slack_user_id}' not found"
        
        user_data = result.get("data", {}).get("user", {})
        return self._format_user(user_data)
    
    def _get_by_email(self, execute_tool, email: str) -> str:
        """Gets user by email address."""
        result = execute_tool(
            tool_name="SLACK_FIND_USER_BY_EMAIL_ADDRESS",
            arguments={"email": email},
        )
        
        if result.get("error"):
            return f"Error: User with email '{email}' not found"
        
        user_data = result.get("data", {}).get("user", {})
        return self._format_user(user_data)
    
    def _get_by_name(self, execute_tool, name: str) -> str:
        """Gets user by name search."""
        result = execute_tool(
            tool_name="SLACK_FIND_USERS",
            arguments={"query": name},
        )
        
        if result.get("error"):
            return f"Error: Could not search for user '{name}'"
        
        members = result.get("data", {}).get("members", [])
        
        # Find best match
        name_lower = name.lower()
        for member in members:
            username = member.get("name", "").lower()
            display = member.get("profile", {}).get("display_name", "").lower()
            real = member.get("profile", {}).get("real_name", "").lower()
            
            if name_lower in [username, display, real] or name_lower in real:
                return self._format_user(member)
        
        if members:
            return self._format_user(members[0])
        
        return f"Error: User '{name}' not found"
    
    def _format_user(self, user: dict) -> str:
        """Formats user data for output."""
        profile = user.get("profile", {})
        
        info = {
            "id": user.get("id"),
            "name": profile.get("real_name") or user.get("name"),
            "display_name": profile.get("display_name") or None,
            "email": profile.get("email") or None,
            "title": profile.get("title") or None,
            "status": profile.get("status_text") or None,
            "timezone": user.get("tz_label") or None,
            "is_bot": user.get("is_bot", False),
            "is_admin": user.get("is_admin", False)
        }
        
        # Remove None values
        info = {k: v for k, v in info.items() if v is not None and v != ""}
        
        return json.dumps(info, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("GetSlackUserInfo Test")
    print("-" * 40)
    
    # Test by name
    tool = GetSlackUserInfo(user="test_user")
    print(tool.run())

