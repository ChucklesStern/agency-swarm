from typing import Literal
from agency_swarm.tools import BaseTool
from pydantic import Field

from helpers import execute_composio_tool
import json


class DeleteCalendarEvent(BaseTool):
    """
    Deletes a calendar event.
    
    Supports both Google Calendar and Outlook.
    Use CheckEventsForDate first to get the event_id of the event to delete.
    
    WARNING: This action is irreversible. The event will be permanently deleted.
    """
    
    provider: Literal["google", "outlook"] = Field(
        ...,
        description="Calendar provider: 'google' or 'outlook'"
    )
    
    event_id: str = Field(
        ...,
        description="The unique ID of the event to delete (from CheckEventsForDate)"
    )
    
    send_notifications: bool = Field(
        default=True,
        description="Whether to send cancellation notifications to attendees"
    )
    
    def run(self):
        try:
            if self.provider == "google":
                return self._delete_google_event(execute_composio_tool)
            else:
                return self._delete_outlook_event(execute_composio_tool)
                
        except Exception as e:
            return f"Error deleting event: {str(e)}"
    
    def _delete_google_event(self, execute_tool) -> str:
        """Deletes a Google Calendar event."""
        result = execute_tool(
            tool_name="GOOGLECALENDAR_DELETE_EVENT",
            arguments={
                "calendar_id": "primary",
                "event_id": self.event_id
            },
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error deleting Google Calendar event: {result.get('error')}"
        
        return json.dumps({
            "provider": "google",
            "success": True,
            "event_id": self.event_id,
            "message": "Event deleted successfully"
        }, indent=2)
    
    def _delete_outlook_event(self, execute_tool) -> str:
        """Deletes an Outlook calendar event."""
        result = execute_tool(
            tool_name="OUTLOOK_DELETE_EVENT",
            arguments={
                "user_id": "me",
                "event_id": self.event_id,
                "send_notifications": self.send_notifications
            },
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error deleting Outlook event: {result.get('error')}"
        
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "event_id": self.event_id,
            "message": "Event deleted successfully",
            "notifications_sent": self.send_notifications
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("DeleteCalendarEvent Test Suite")
    print("=" * 60)
    print()
    
    # First, list events to find a test event
    from virtual_assistant.tools.CheckEventsForDate import CheckEventsForDate
    
    print("=== Getting events for tomorrow ===")
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    check_tool = CheckEventsForDate(provider="google", date=tomorrow)
    result = check_tool.run()
    
    import json
    data = json.loads(result)
    
    # Find a test event to delete
    test_events = [e for e in data.get("events", []) if "Test" in e.get("title", "")]
    
    if test_events:
        event = test_events[0]
        print(f"Found test event: {event['title']} (ID: {event['event_id']})")
        print()
        
        # Delete it
        print("=== Deleting test event ===")
        tool = DeleteCalendarEvent(
            provider="google",
            event_id=event["event_id"],
            send_notifications=False
        )
        result = tool.run()
        print(result)
    else:
        print("No test events found to delete")
        print("Available events:")
        for e in data.get("events", [])[:5]:
            print(f"  - {e['title']}")
    
    print()
    print("=" * 60)
    print("Test completed!")
    print("=" * 60)

