from typing import Literal
from agency_swarm.tools import BaseTool
from pydantic import Field

from helpers import execute_composio_tool
import json


class DeleteDraft(BaseTool):
    """
    Permanently deletes an email draft by its ID.
    
    Use this to clean up drafts that are no longer needed.
    This action cannot be undone.
    """
    
    provider: Literal["gmail", "outlook"] = Field(
        ...,
        description="Email provider: 'gmail' or 'outlook'"
    )
    
    draft_id: str = Field(
        ...,
        description="The draft ID to delete (obtained from DraftEmail tool)"
    )
    
    def run(self):
        try:
            if self.provider == "gmail":
                return self._delete_gmail_draft(execute_composio_tool)
            else:
                return self._delete_outlook_draft(execute_composio_tool)
                
        except Exception as e:
            return f"Error deleting draft: {str(e)}"
    
    def _delete_gmail_draft(self, execute_tool) -> str:
        """Deletes a Gmail draft."""
        result = execute_tool(
            tool_name="GMAIL_DELETE_DRAFT",
            arguments={
                "user_id": "me",
                "draft_id": self.draft_id
            },
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error deleting Gmail draft: {result.get('error')}"

        return json.dumps({
            "provider": "gmail",
            "success": True,
            "message": "Draft deleted successfully",
            "draft_id": self.draft_id
        }, indent=2)
    
    def _delete_outlook_draft(self, execute_tool) -> str:
        """Deletes an Outlook draft."""
        result = execute_tool(
            tool_name="OUTLOOK_DELETE_MESSAGE",
            arguments={
                "user_id": "me",
                "message_id": self.draft_id
            },
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error deleting Outlook draft: {result.get('error')}"

        return json.dumps({
            "provider": "outlook",
            "success": True,
            "message": "Draft deleted successfully",
            "draft_id": self.draft_id
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("DeleteDraft Test Suite")
    print("=" * 60)
    print()
    print("To test DeleteDraft, first create a draft using DraftEmail,")
    print("then use the draft_id to delete it.")
    print()
    print("Example:")
    print("  tool = DeleteDraft(provider='gmail', draft_id='r12345...')")
    print("  result = tool.run()")
    print()
    print("=" * 60)

