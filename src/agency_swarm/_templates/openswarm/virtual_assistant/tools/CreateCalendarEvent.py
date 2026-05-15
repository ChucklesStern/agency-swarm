from typing import Literal, Optional, List
from agency_swarm.tools import BaseTool
from pydantic import Field
import json

from helpers import execute_composio_tool


class CreateCalendarEvent(BaseTool):
    """
    Creates a calendar event in Google Calendar or Outlook.
    
    The event is automatically accepted for the user after creation.
    Returns the event ID and a link to view the event.
    """
    
    provider: Literal["google", "outlook"] = Field(
        ...,
        description="Calendar provider: 'google' (Google Calendar) or 'outlook'"
    )
    
    title: str = Field(
        ...,
        description="Title/subject of the event"
    )
    
    start_datetime: str = Field(
        ...,
        description="Start date and time in ISO 8601 format (e.g., '2026-01-15T14:00:00')"
    )
    
    duration_hours: int = Field(
        default=1,
        ge=0,
        description="Duration in hours (default 1). Use with duration_minutes for partial hours."
    )
    
    duration_minutes: int = Field(
        default=0,
        ge=0,
        le=59,
        description="Duration in minutes (0-59). Combined with duration_hours."
    )
    
    timezone: str = Field(
        default="UTC",
        description="Timezone in IANA format (e.g., 'America/New_York', 'Europe/London', 'Asia/Dubai')"
    )
    
    description: Optional[str] = Field(
        default=None,
        description="Description/notes for the event"
    )
    
    location: Optional[str] = Field(
        default=None,
        description="Location of the event (address or meeting room)"
    )
    
    attendees: Optional[List[str]] = Field(
        default=None,
        description="List of attendee email addresses to invite"
    )
    
    create_meeting_link: bool = Field(
        default=False,
        description="If True, creates a video meeting link (Google Meet or Teams)"
    )
    
    def run(self):
        try:
            if self.provider == "google":
                return self._create_google_event(execute_composio_tool)
            else:
                return self._create_outlook_event(execute_composio_tool)
                
        except Exception as e:
            return f"Error creating calendar event: {str(e)}"
    
    def _create_google_event(self, execute_tool) -> str:
        """Creates a Google Calendar event and accepts it."""
        arguments = {
            "calendar_id": "primary",
            "start_datetime": self.start_datetime,
            "event_duration_hour": self.duration_hours,
            "event_duration_minutes": self.duration_minutes,
            "timezone": self.timezone,
            "summary": self.title,
            "create_meeting_room": self.create_meeting_link,
            "exclude_organizer": False,  # Include organizer as attendee
            "send_updates": True
        }
        
        if self.description:
            arguments["description"] = self.description
        
        if self.location:
            arguments["location"] = self.location
        
        if self.attendees:
            arguments["attendees"] = self.attendees
        
        result = execute_tool(
            tool_name="GOOGLECALENDAR_CREATE_EVENT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Google Calendar event: {result.get('error')}"

        data = result.get("data", {})
        if "response_data" in data:
            data = data["response_data"]
        event_id = data.get("id")

        if event_id:
            accept_result = execute_tool(
                tool_name="GOOGLECALENDAR_PATCH_EVENT",
                arguments={
                    "calendar_id": "primary",
                    "event_id": event_id,
                    "rsvp_response": "accepted",
                    "send_updates": "none"
                },
            )
            
            accepted = not (isinstance(accept_result, dict) and accept_result.get("error"))
        else:
            accepted = False
        
        meeting_link = None
        conference_data = data.get("conferenceData", {})
        entry_points = conference_data.get("entryPoints", [])
        for entry in entry_points:
            if entry.get("entryPointType") == "video":
                meeting_link = entry.get("uri")
                break
        
        return json.dumps({
            "provider": "google",
            "success": True,
            "event_id": event_id,
            "title": self.title,
            "start": data.get("start", {}).get("dateTime"),
            "end": data.get("end", {}).get("dateTime"),
            "accepted": accepted,
            "meeting_link": meeting_link,
            "html_link": data.get("htmlLink", "")
        }, indent=2)
    
    def _create_outlook_event(self, execute_tool) -> str:
        """Creates an Outlook calendar event."""
        from datetime import datetime, timedelta
        
        try:
            start_dt = datetime.fromisoformat(self.start_datetime.replace("Z", "+00:00"))
        except ValueError:
            start_dt = datetime.fromisoformat(self.start_datetime)
        
        duration = timedelta(hours=self.duration_hours, minutes=self.duration_minutes)
        end_dt = start_dt + duration
        end_datetime = end_dt.strftime("%Y-%m-%dT%H:%M:%S")
        
        arguments = {
            "user_id": "me",
            "subject": self.title,
            "start_datetime": self.start_datetime,
            "end_datetime": end_datetime,
            "time_zone": self.timezone,
            "is_html": False
        }
        
        if self.description:
            arguments["body"] = self.description
        
        if self.location:
            arguments["location"] = self.location
        
        if self.attendees:
            arguments["attendees_info"] = [{"email": email} for email in self.attendees]
        
        if self.create_meeting_link:
            arguments["is_online_meeting"] = True
            arguments["online_meeting_provider"] = "teamsForBusiness"
        
        result = execute_tool(
            tool_name="OUTLOOK_CALENDAR_CREATE_EVENT",
            arguments=arguments,
        )
        
        if isinstance(result, dict) and result.get("error"):
            return f"Error creating Outlook event: {result.get('error')}"

        data = result.get("data", {})
        
        # Extract meeting link if created
        meeting_link = None
        online_meeting = data.get("onlineMeeting", {})
        if online_meeting:
            meeting_link = online_meeting.get("joinUrl")
        
        return json.dumps({
            "provider": "outlook",
            "success": True,
            "event_id": data.get("id"),
            "title": self.title,
            "start": data.get("start", {}).get("dateTime"),
            "end": data.get("end", {}).get("dateTime"),
            "accepted": True,  # Organizer is automatically accepted
            "meeting_link": meeting_link,
            "web_link": data.get("webLink", "")
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    print("=" * 60)
    print("CreateCalendarEvent Test Suite")
    print("=" * 60)
    print()
    
    # Test 1: Create Google Calendar event
    print("Test 1: Create Google Calendar event")
    print("-" * 60)
    tool = CreateCalendarEvent(
        provider="google",
        title="Test Event from Virtual Assistant",
        start_datetime="2026-01-08T15:00:00",
        duration_hours=0,
        duration_minutes=30,
        timezone="Asia/Dubai",
        description="This is a test event created by the Virtual Assistant tool.",
        create_meeting_link=False
    )
    result = tool.run()
    print(result)
    print()
    
    # Test 2: Create Outlook event
    print("Test 2: Create Outlook Calendar event")
    print("-" * 60)
    tool = CreateCalendarEvent(
        provider="outlook",
        title="Test Outlook Event",
        start_datetime="2026-01-08T16:00:00",
        duration_hours=1,
        duration_minutes=0,
        timezone="UTC",
        description="This is a test Outlook event."
    )
    result = tool.run()
    print(result)
    print()
    
    print("=" * 60)
    print("Tests completed! Remember to delete test events from calendars.")
    print("=" * 60)

