from typing import Literal, Optional, List
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class FindEmails(BaseTool):
    """
    Searches and retrieves emails with flexible filtering options.
    
    For Gmail: Uses Gmail's powerful query syntax (is:unread, from:, subject:, etc.)
    For Outlook: Uses structured filters for folder, read status, sender, etc.
    
    Common use cases:
    - Find unread emails: query="is:unread" (Gmail) or is_read=False (Outlook)
    - Find emails in inbox: query="in:inbox" or label_ids=["INBOX"]
    - Find starred emails: query="is:starred" or label_ids=["STARRED"]
    - Find emails from someone: query="from:someone@example.com"
    - Find emails with attachments: query="has:attachment"
    - Find emails after date: query="after:2026/01/01"
    """
    
    provider: Literal["gmail", "outlook"] = Field(
        ...,
        description="Email provider: 'gmail' or 'outlook'"
    )
    
    # Gmail-specific: flexible query
    query: Optional[str] = Field(
        default=None,
        description="Gmail search query. Examples: 'is:unread', 'from:user@example.com', 'subject:meeting', 'has:attachment', 'after:2026/01/01', 'in:inbox -in:trash'. Can combine with AND/OR."
    )
    
    # Common filters (work for both)
    label_ids: Optional[List[str]] = Field(
        default=None,
        description="Gmail: Label IDs to filter by (e.g., ['INBOX', 'UNREAD', 'STARRED']). Outlook: ignored, use folder instead."
    )
    
    # Outlook-specific filters
    folder: Optional[str] = Field(
        default="inbox",
        description="Outlook folder: 'inbox', 'archive', 'sentitems', 'drafts', 'deleteditems', 'junkemail'. Gmail: ignored."
    )
    
    is_read: Optional[bool] = Field(
        default=None,
        description="Outlook: Filter by read status (True=read, False=unread, None=all). Gmail: use query='is:unread' instead."
    )
    
    from_address: Optional[str] = Field(
        default=None,
        description="Filter by sender email address. Gmail: use query='from:...' instead."
    )
    
    subject_contains: Optional[str] = Field(
        default=None,
        description="Filter by subject containing text. Gmail: use query='subject:...' instead."
    )
    
    has_attachments: Optional[bool] = Field(
        default=None,
        description="Filter by attachment presence. Gmail: use query='has:attachment' instead."
    )
    
    received_after: Optional[str] = Field(
        default=None,
        description="Filter emails received after date (ISO format: 2026-01-01T00:00:00Z). Gmail: use query='after:2026/01/01' instead."
    )
    
    # Pagination and limits
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of emails to return (1-100)"
    )
    
    page_token: Optional[str] = Field(
        default=None,
        description="Token for fetching next page of results"
    )
    
    def run(self):
        try:
            if self.provider == "gmail":
                return self._find_gmail_emails(execute_composio_tool)
            else:
                return self._find_outlook_emails(execute_composio_tool)
                
        except Exception as e:
            return f"Error finding emails: {str(e)}"
    
    def _find_gmail_emails(self, execute_tool) -> str:
        """Finds emails in Gmail using query syntax."""
        arguments = {
            "user_id": "me",
            "max_results": self.limit,
            "include_payload": False,
            "verbose": False
        }
        
        # Add query if provided
        if self.query:
            arguments["query"] = self.query
        
        # Add label filtering
        if self.label_ids:
            arguments["label_ids"] = self.label_ids
        
        # Add pagination
        if self.page_token:
            arguments["page_token"] = self.page_token
        
        # Execute search
        result = execute_tool(
            tool_name="GMAIL_FETCH_EMAILS",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error searching Gmail: {result.get('error')}"
        
        data = result.get("data", {})
        messages = data.get("messages", [])
        next_page_token = data.get("nextPageToken")
        
        if not messages:
            return json.dumps({
                "provider": "gmail",
                "query": self.query,
                "count": 0,
                "emails": [],
                "next_page_token": None
            }, indent=2)
        
        # Sort by timestamp (newest first by default)
        messages_sorted = sorted(
            messages, 
            key=lambda m: m.get("messageTimestamp", ""),
            reverse=True
        )
        
        # Format output
        formatted_emails = []
        for msg in messages_sorted:
            formatted_emails.append({
                "subject": msg.get("subject", "(No subject)"),
                "from": msg.get("sender", "Unknown"),
                "message_id": msg.get("messageId"),
                "thread_id": msg.get("threadId"),
                "received_at": msg.get("messageTimestamp"),
                "labels": msg.get("labelIds", []),
                "snippet": msg.get("snippet", "")[:100] if msg.get("snippet") else ""
            })
        
        return json.dumps({
            "provider": "gmail",
            "query": self.query,
            "count": len(formatted_emails),
            "emails": formatted_emails,
            "next_page_token": next_page_token
        }, indent=2)
    
    def _find_outlook_emails(self, execute_tool) -> str:
        """Finds emails in Outlook using structured filters."""
        arguments = {
            "user_id": "me",
            "folder": self.folder or "inbox",
            "top": self.limit,
            "orderby": ["receivedDateTime desc"],
            "select": ["id", "subject", "from", "receivedDateTime", "conversationId", "categories", "isRead", "hasAttachments", "bodyPreview"]
        }
        
        # Apply filters
        if self.is_read is not None:
            arguments["is_read"] = self.is_read
        
        if self.from_address:
            arguments["from_address"] = self.from_address
        
        if self.subject_contains:
            arguments["subject_contains"] = self.subject_contains
        
        if self.has_attachments is not None:
            arguments["has_attachments"] = self.has_attachments
        
        if self.received_after:
            arguments["received_date_time_gt"] = self.received_after
        
        if self.label_ids:
            arguments["categories"] = self.label_ids
        
        # Add pagination
        if self.page_token:
            try:
                arguments["skip"] = int(self.page_token)
            except ValueError:
                return f"Error: Invalid page_token for Outlook. Expected a number."
        
        # Execute search
        result = execute_tool(
            tool_name="OUTLOOK_LIST_MESSAGES",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error searching Outlook: {result.get('error')}"
        
        data = result.get("data", {})
        messages = data.get("value", [])
        
        # Calculate next page token
        current_skip = int(self.page_token) if self.page_token else 0
        next_page_token = None
        if len(messages) == self.limit:
            next_page_token = str(current_skip + self.limit)
        
        if not messages:
            return json.dumps({
                "provider": "outlook",
                "folder": self.folder,
                "filters": {
                    "is_read": self.is_read,
                    "from_address": self.from_address,
                    "subject_contains": self.subject_contains,
                    "has_attachments": self.has_attachments
                },
                "count": 0,
                "emails": [],
                "next_page_token": None
            }, indent=2)
        
        # Format output
        formatted_emails = []
        for msg in messages:
            from_info = msg.get("from", {}).get("emailAddress", {})
            formatted_emails.append({
                "subject": msg.get("subject", "(No subject)"),
                "from": f"{from_info.get('name', '')} <{from_info.get('address', 'Unknown')}>",
                "message_id": msg.get("id"),
                "conversation_id": msg.get("conversationId"),
                "received_at": msg.get("receivedDateTime"),
                "categories": msg.get("categories", []),
                "is_read": msg.get("isRead"),
                "has_attachments": msg.get("hasAttachments"),
                "snippet": (msg.get("bodyPreview") or "")[:100]
            })
        
        return json.dumps({
            "provider": "outlook",
            "folder": self.folder,
            "filters": {
                "is_read": self.is_read,
                "from_address": self.from_address,
                "subject_contains": self.subject_contains,
                "has_attachments": self.has_attachments
            },
            "count": len(formatted_emails),
            "emails": formatted_emails,
            "next_page_token": next_page_token
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("FindEmails Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Gmail - Find unread emails
    print("Test 1: Gmail - Find unread emails")
    print("-" * 60)
    tool = FindEmails(provider="gmail", query="is:unread", limit=3)
    result = tool.run()
    data = json.loads(result)
    print(f"Query: {data.get('query')}")
    print(f"Count: {data.get('count')}")
    if data.get("emails"):
        print(f"First email: {data['emails'][0]['subject'][:50]}...")
    print()
    
    # Test 2: Gmail - Find starred emails
    print("Test 2: Gmail - Find starred emails in inbox")
    print("-" * 60)
    tool = FindEmails(provider="gmail", query="is:starred in:inbox", limit=3)
    result = tool.run()
    data = json.loads(result)
    print(f"Query: {data.get('query')}")
    print(f"Count: {data.get('count')}")
    print()
    
    # Test 3: Gmail - Find emails with attachments
    print("Test 3: Gmail - Find emails with attachments")
    print("-" * 60)
    tool = FindEmails(provider="gmail", query="has:attachment", limit=3)
    result = tool.run()
    data = json.loads(result)
    print(f"Query: {data.get('query')}")
    print(f"Count: {data.get('count')}")
    print()
    
    # Test 4: Gmail - Find emails from specific sender
    print("Test 4: Gmail - Find emails from specific sender")
    print("-" * 60)
    tool = FindEmails(provider="gmail", query="from:noreply", limit=3)
    result = tool.run()
    data = json.loads(result)
    print(f"Query: {data.get('query')}")
    print(f"Count: {data.get('count')}")
    print()
    
    # Test 5: Outlook - Find unread emails
    print("Test 5: Outlook - Find unread emails in inbox")
    print("-" * 60)
    tool = FindEmails(provider="outlook", folder="inbox", is_read=False, limit=3)
    result = tool.run()
    print(result[:500])
    print()
    
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)

