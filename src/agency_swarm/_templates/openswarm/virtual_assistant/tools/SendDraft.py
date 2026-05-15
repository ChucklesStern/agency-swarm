from typing import Literal
from agency_swarm.tools import BaseTool
from pydantic import Field, field_validator
import json

from helpers import execute_composio_tool


class SendDraft(BaseTool):
    """
    Sends an existing email draft by its ID.
    
    Use this after creating a draft with DraftEmail and getting user approval.
    The draft must have at least one recipient (to, cc, or bcc) to be sent.
    """
    
    provider: Literal["gmail", "outlook"] = Field(
        ...,
        description="Email provider: 'gmail' or 'outlook'"
    )
    
    draft_id: str = Field(
        ...,
        description="The draft ID to send (obtained from DraftEmail tool)"
    )

    @field_validator("draft_id")
    @classmethod
    def validate_draft_id(cls, v: str) -> str:
        if "noop" in v.lower():
            raise ValueError("This tool should used to send an existing EMAIL draft. REVIEW YOUR INSTRUCTIONS AND USE THE APPROPRIATE TOOLS TO COMPLETE YOUR TASKS.")
        return v
    
    def run(self):
        try:
            if self.provider == "gmail":
                return self._send_gmail_draft(execute_composio_tool)
            else:
                return self._send_outlook_draft(execute_composio_tool)
                
        except Exception as e:
            return f"Error sending draft: {str(e)}"
    
    def _send_gmail_draft(self, execute_tool) -> str:
        """Sends a Gmail draft."""
        result = execute_tool(
            tool_name="GMAIL_SEND_DRAFT",
            arguments={"user_id": "me", "draft_id": self.draft_id},
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error sending Gmail draft: {result.get('error')}"

        data = result.get("data", {})
        
        return json.dumps({
            "provider": "gmail",
            "success": True,
            "message": "Email sent successfully",
            "message_id": data.get("id"),
            "thread_id": data.get("threadId"),
            "labels": data.get("labelIds", [])
        }, indent=2)
    
    def _send_outlook_draft(self, execute_tool) -> str:
        """Sends an Outlook draft."""
        result = execute_tool(
            tool_name="OUTLOOK_SEND_DRAFT",
            arguments={"user_id": "me", "message_id": self.draft_id},
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error sending Outlook draft: {result.get('error')}"

        # Outlook send returns HTTP 202 with no body
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "message": "Email sent successfully",
            "draft_id": self.draft_id
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("SendDraft Test Suite")
    print("=" * 60)
    print()
    print("To test SendDraft, first create a draft using DraftEmail,")
    print("then use the draft_id to send it.")
    print()
    print("Example:")
    print("  tool = SendDraft(provider='gmail', draft_id='r12345...')")
    print("  result = tool.run()")
    print()
    print("=" * 60)

