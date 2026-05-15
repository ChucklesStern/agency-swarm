from typing import Literal, Optional
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class RescheduleCalendarEvent(BaseTool):
    """
    Reschedules an existing calendar event to a new date/time.
    
    Supports both Google Calendar and Outlook. Can update:
    - Start and end times
    - Event title
    - Location
    - Description
    
    Use CheckEventsForDate first to get the event_id of the event to reschedule.
    """
    
    provider: Literal["google", "outlook"] = Field(
        ...,
        description="Calendar provider: 'google' or 'outlook'"
    )
    
    event_id: str = Field(
        ...,
        description="The unique ID of the event to reschedule (from CheckEventsForDate)"
    )
    
    new_start_datetime: Optional[str] = Field(
        default=None,
        description="New start date/time in ISO format (e.g., '2026-01-10T14:00:00'). Required for rescheduling."
    )
    
    new_end_datetime: Optional[str] = Field(
        default=None,
        description="New end date/time in ISO format. If not provided, will be calculated based on original duration."
    )
    
    timezone: Optional[str] = Field(
        default=None,
        description="IANA timezone (e.g., 'America/New_York', 'Asia/Dubai'). Uses event's current timezone if not specified."
    )
    
    new_title: Optional[str] = Field(
        default=None,
        description="New title/subject for the event. Leave empty to keep current title."
    )
    
    new_location: Optional[str] = Field(
        default=None,
        description="New location for the event. Leave empty to keep current location."
    )
    
    new_description: Optional[str] = Field(
        default=None,
        description="New description for the event. Leave empty to keep current description."
    )
    
    send_updates: Literal["all", "externalOnly", "none"] = Field(
        default="all",
        description="Who to notify about the change: 'all', 'externalOnly', or 'none'"
    )
    
    def run(self):
        try:
            if self.provider == "google":
                return self._reschedule_google_event(execute_composio_tool)
            else:
                return self._reschedule_outlook_event(execute_composio_tool)
                
        except Exception as e:
            return f"Error rescheduling event: {str(e)}"
    
    def _reschedule_google_event(self, execute_tool) -> str:
        """Reschedules a Google Calendar event."""
        # Build arguments - only include fields that are being updated
        arguments = {
            "calendar_id": "primary",
            "event_id": self.event_id
        }
        
        if self.new_start_datetime:
            arguments["start_time"] = self.new_start_datetime
        
        if self.new_end_datetime:
            arguments["end_time"] = self.new_end_datetime
        
        if self.timezone:
            arguments["timezone"] = self.timezone
        
        if self.new_title:
            arguments["summary"] = self.new_title
        
        if self.new_location:
            arguments["location"] = self.new_location
        
        if self.new_description:
            arguments["description"] = self.new_description
        
        arguments["send_updates"] = self.send_updates
        
        # Execute the patch
        result = execute_tool(
            tool_name="GOOGLECALENDAR_PATCH_EVENT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error rescheduling Google Calendar event: {result.get('error')}"
        
        data = result.get("data", {})
        
        # Extract updated event details
        start = data.get("start", {})
        end = data.get("end", {})
        
        return json.dumps({
            "provider": "google",
            "success": True,
            "event_id": data.get("id"),
            "title": data.get("summary", "(No title)"),
            "new_start": start.get("dateTime") or start.get("date"),
            "new_end": end.get("dateTime") or end.get("date"),
            "location": data.get("location", ""),
            "html_link": data.get("htmlLink", ""),
            "updates_sent_to": self.send_updates
        }, indent=2)
    
    def _reschedule_outlook_event(self, execute_tool) -> str:
        """Reschedules an Outlook calendar event."""
        # Build arguments - only include fields that are being updated
        arguments = {
            "user_id": "me",
            "event_id": self.event_id
        }
        
        if self.new_start_datetime:
            arguments["start_datetime"] = self.new_start_datetime
        
        if self.new_end_datetime:
            arguments["end_datetime"] = self.new_end_datetime
        
        if self.timezone:
            arguments["time_zone"] = self.timezone
        
        if self.new_title:
            arguments["subject"] = self.new_title
        
        if self.new_location:
            arguments["location"] = self.new_location
        
        if self.new_description:
            arguments["body"] = {
                "contentType": "Text",
                "content": self.new_description
            }
        
        # Execute the update
        result = execute_tool(
            tool_name="OUTLOOK_UPDATE_CALENDAR_EVENT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error rescheduling Outlook event: {result.get('error')}"
        
        data = result.get("data", {})
        
        # Extract updated event details
        start = data.get("start", {})
        end = data.get("end", {})
        
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "event_id": data.get("id"),
            "title": data.get("subject", "(No title)"),
            "new_start": start.get("dateTime"),
            "new_end": end.get("dateTime"),
            "location": data.get("location", {}).get("displayName", ""),
            "web_link": data.get("webLink", "")
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("RescheduleCalendarEvent Test Suite")
    print("=" * 60)
    print()
    
    # First, get an event to reschedule
    from virtual_assistant.tools.CheckEventsForDate import CheckEventsForDate
    
    print("=== Getting events for tomorrow ===")
    from datetime import datetime, timedelta
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    check_tool = CheckEventsForDate(provider="google", date=tomorrow)
    result = check_tool.run()
    print(result)
    print()
    
    import json
    try:
        data = json.loads(result)
        if data.get("events"):
            event = data["events"][0]
            event_id = event["event_id"]
            print(f"Found event: {event['title']} (ID: {event_id})")
        else:
            print("No events found for tomorrow to test with")
    except json.JSONDecodeError:
        print(f"Result: {result}")
    
    print()
    print("=" * 60)
    print("Test completed!")
    print("=" * 60)


