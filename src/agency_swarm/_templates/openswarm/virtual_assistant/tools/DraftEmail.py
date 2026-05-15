from typing import Literal, Optional, List
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class DraftEmail(BaseTool):
    """
    Creates an email draft in the user's mailbox (Gmail or Outlook).
    
    The draft can be reviewed, edited, and sent later using SendDraft.
    Returns the draft ID which is needed to send or delete the draft.
    
    Supports creating replies within existing threads:
    - Gmail: Use thread_id to reply in a thread
    - Outlook: Use reply_to_message_id to reply to a specific message
    """
    
    provider: Literal["gmail", "outlook"] = Field(
        ...,
        description="Email provider: 'gmail' or 'outlook'"
    )
    
    to: Optional[List[str]] = Field(
        default=None,
        description="List of recipient email addresses (e.g., ['user@example.com']). Optional for drafts."
    )
    
    subject: Optional[str] = Field(
        default=None,
        description="Email subject line. Leave empty when replying to stay in the same thread."
    )
    
    body: str = Field(
        ...,
        description="Email body content (plain text)"
    )
    
    cc: Optional[List[str]] = Field(
        default=None,
        description="List of CC recipient email addresses"
    )
    
    bcc: Optional[List[str]] = Field(
        default=None,
        description="List of BCC recipient email addresses"
    )
    
    is_html: bool = Field(
        default=False,
        description="Set to True if body contains HTML formatting"
    )
    
    thread_id: Optional[str] = Field(
        default=None,
        description="Gmail only: Thread ID to reply to. Leave subject empty to stay in the same thread."
    )
    
    reply_to_message_id: Optional[str] = Field(
        default=None,
        description="Outlook only: Message ID to reply to. Creates a draft reply to that message."
    )
    
    def run(self):
        try:
            if self.provider == "gmail":
                return self._create_gmail_draft(execute_composio_tool)
            else:
                return self._create_outlook_draft(execute_composio_tool)
                
        except Exception as e:
            return f"Error creating draft: {str(e)}"
    
    def _create_gmail_draft(self, execute_tool) -> str:
        """Creates a Gmail draft."""
        arguments = {
            "user_id": "me",
            "body": self.body,
            "is_html": self.is_html
        }
        
        # Add subject (leave empty for thread replies to stay in same thread)
        if self.subject:
            arguments["subject"] = self.subject
        
        if self.to:
            arguments["recipient_email"] = self.to[0]
            if len(self.to) > 1:
                arguments["extra_recipients"] = self.to[1:]
        
        if self.cc:
            arguments["cc"] = self.cc
        
        if self.bcc:
            arguments["bcc"] = self.bcc
        
        # Add thread_id for replies
        if self.thread_id:
            arguments["thread_id"] = self.thread_id
        
        result = execute_tool(
            tool_name="GMAIL_CREATE_EMAIL_DRAFT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Gmail draft: {result.get('error')}"

        data = result.get("data", {})

        return json.dumps({
            "provider": "gmail",
            "success": True,
            "draft_id": data.get("id"),
            "message_id": data.get("message", {}).get("id"),
            "thread_id": data.get("message", {}).get("threadId"),
            "subject": self.subject,
            "to": self.to,
            "is_reply": self.thread_id is not None
        }, indent=2)
    
    def _create_outlook_draft(self, execute_tool) -> str:
        """Creates an Outlook draft."""
        # Check if this is a reply to an existing message
        if self.reply_to_message_id:
            return self._create_outlook_reply_draft(execute_tool)
        
        arguments = {
            "body": self.body,
            "is_html": self.is_html
        }
        
        if self.subject:
            arguments["subject"] = self.subject
        else:
            arguments["subject"] = "(No subject)"
        
        if self.to:
            arguments["to_recipients"] = self.to
        
        if self.cc:
            arguments["cc_recipients"] = self.cc
        
        if self.bcc:
            arguments["bcc_recipients"] = self.bcc
        
        result = execute_tool(
            tool_name="OUTLOOK_CREATE_DRAFT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Outlook draft: {result.get('error')}"

        data = result.get("data", {})

        return json.dumps({
            "provider": "outlook",
            "success": True,
            "draft_id": data.get("id"),
            "subject": self.subject,
            "to": self.to,
            "web_link": data.get("webLink", ""),
            "is_reply": False
        }, indent=2)
    
    def _create_outlook_reply_draft(self, execute_tool) -> str:
        """Creates an Outlook draft reply to an existing message."""
        arguments = {
            "user_id": "me",
            "message_id": self.reply_to_message_id,
            "comment": self.body
        }
        
        if self.cc:
            arguments["cc_emails"] = self.cc
        
        if self.bcc:
            arguments["bcc_emails"] = self.bcc
        
        result = execute_tool(
            tool_name="OUTLOOK_CREATE_DRAFT_REPLY",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Outlook reply draft: {result.get('error')}"

        data = result.get("data", {})
        
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "draft_id": data.get("id"),
            "reply_to_message_id": self.reply_to_message_id,
            "conversation_id": data.get("conversationId"),
            "web_link": data.get("webLink", ""),
            "is_reply": True
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("DraftEmail Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Create Gmail draft
    print("Test 1: Create Gmail draft")
    print("-" * 60)
    tool = DraftEmail(
        provider="gmail",
        to=["arseny9795@gmail.com"],
        subject="Test Draft from Virtual Assistant",
        body="This is a test draft created by the Virtual Assistant tool.\n\nPlease ignore this message."
    )
    result = tool.run()
    print(result)
    
    # Save draft_id for cleanup
    import json
    try:
        data = json.loads(result)
        gmail_draft_id = data.get("draft_id")
        print(f"\nDraft ID saved for cleanup: {gmail_draft_id}")
    except json.JSONDecodeError:
        gmail_draft_id = None
    print()
    
    print("=" * 60)
    print("Test completed! Remember to delete the draft.")
    print("=" * 60)

