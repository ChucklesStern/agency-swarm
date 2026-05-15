from typing import Literal
from agency_swarm.tools import BaseTool
from pydantic import Field
import json
from datetime import datetime

from helpers import execute_composio_tool


class CheckEventsForDate(BaseTool):
    """
    Retrieves all calendar events for a specific date (Google Calendar or Outlook).
    
    Returns event details including title, start/end times, and event IDs.
    Events are returned in chronological order by start time.
    """
    
    provider: Literal["google", "outlook"] = Field(
        ...,
        description="Calendar provider to use: 'google' (Google Calendar) or 'outlook'"
    )
    
    date: str = Field(
        ...,
        description="Date to check for events in YYYY-MM-DD format (e.g., '2026-01-07')"
    )
    
    timezone: str = Field(
        default="UTC",
        description="Timezone for the date and event times. Use IANA format (e.g., 'America/New_York', 'Europe/London', 'Asia/Dubai')"
    )
    
    def run(self):
        try:
            try:
                parsed_date = datetime.strptime(self.date, "%Y-%m-%d")
            except ValueError:
                return f"Error: Invalid date format '{self.date}'. Use YYYY-MM-DD format."
            
            if self.provider == "google":
                return self._fetch_google_calendar_events(execute_composio_tool, parsed_date)
            else:
                return self._fetch_outlook_events(execute_composio_tool, parsed_date)
                
        except Exception as e:
            return f"Error fetching calendar events: {str(e)}"
    
    def _fetch_google_calendar_events(self, execute_tool, date: datetime) -> str:
        """Fetches events from Google Calendar for the specified date."""
        time_min = f"{date.strftime('%Y-%m-%d')}T00:00:00Z"
        time_max = f"{date.strftime('%Y-%m-%d')}T23:59:59Z"

        result = execute_tool(
            tool_name="GOOGLECALENDAR_EVENTS_LIST",
            arguments={
                "calendarId": "primary",
                "timeMin": time_min,
                "timeMax": time_max,
                "singleEvents": True,
                "orderBy": "startTime",
                "timeZone": self.timezone
            },
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error fetching Google Calendar events: {result.get('error')}"

        events = result.get("data", {}).get("items", [])

        if not events:
            return json.dumps({
                "provider": "google",
                "date": self.date,
                "timezone": self.timezone,
                "count": 0,
                "events": []
            }, indent=2)

        formatted_events = []
        for event in events:
            start = event.get("start", {})
            end = event.get("end", {})
            
            # Handle all-day events (have 'date') vs timed events (have 'dateTime')
            start_time = start.get("dateTime") or start.get("date", "")
            end_time = end.get("dateTime") or end.get("date", "")
            is_all_day = "date" in start and "dateTime" not in start
            
            formatted_events.append({
                "title": event.get("summary", "(No title)"),
                "event_id": event.get("id"),
                "start": start_time,
                "end": end_time,
                "all_day": is_all_day,
                "description": event.get("description", ""),
                "location": event.get("location", ""),
                "status": event.get("status", ""),
                "html_link": event.get("htmlLink", "")
            })
        
        return json.dumps({
            "provider": "google",
            "date": self.date,
            "timezone": self.timezone,
            "count": len(formatted_events),
            "events": formatted_events
        }, indent=2)
    
    def _fetch_outlook_events(self, execute_tool, date: datetime) -> str:
        """Fetches events from Outlook Calendar for the specified date."""
        start_datetime = f"{date.strftime('%Y-%m-%d')}T00:00:00Z"
        end_datetime = f"{date.strftime('%Y-%m-%d')}T23:59:59Z"

        result = execute_tool(
            tool_name="OUTLOOK_GET_CALENDAR_VIEW",
            arguments={
                "user_id": "me",
                "start_datetime": start_datetime,
                "end_datetime": end_datetime,
                "timezone": self.timezone,
                "top": 100
            },
        )

        if isinstance(result, dict) and result.get("error"):
            return f"Error fetching Outlook events: {result.get('error')}"

        events = result.get("data", {}).get("value", [])

        if not events:
            return json.dumps({
                "provider": "outlook",
                "date": self.date,
                "timezone": self.timezone,
                "count": 0,
                "events": []
            }, indent=2)

        formatted_events = []
        for event in events:
            start = event.get("start", {})
            end = event.get("end", {})
            
            # Extract body/description content
            body_data = event.get("body", {})
            description = body_data.get("content", "") if isinstance(body_data, dict) else ""
            
            formatted_events.append({
                "title": event.get("subject", "(No title)"),
                "event_id": event.get("id"),
                "start": start.get("dateTime", ""),
                "end": end.get("dateTime", ""),
                "all_day": event.get("isAllDay", False),
                "description": description,
                "location": event.get("location", {}).get("displayName", ""),
                "status": event.get("showAs", ""),
                "web_link": event.get("webLink", "")
            })
        
        return json.dumps({
            "provider": "outlook",
            "date": self.date,
            "timezone": self.timezone,
            "count": len(formatted_events),
            "events": formatted_events
        }, indent=2)


if __name__ == "__main__":
    import sys
    import os
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
    
    from datetime import date as dt_date
    
    print("=" * 60)
    print("CheckEventsForDate Test Suite")
    print("=" * 60)
    print()
    
    today = dt_date.today().strftime("%Y-%m-%d")
    
    # Test 1: Google Calendar for today
    print(f"Test 1: Google Calendar - Today ({today})")
    print("-" * 60)
    tool = CheckEventsForDate(provider="google", date=today)
    result = tool.run()
    print(result)
    print()
    
    # Test 2: Google Calendar with custom timezone
    print("Test 2: Google Calendar - Today with timezone")
    print("-" * 60)
    tool = CheckEventsForDate(provider="google", date=today, timezone="Asia/Dubai")
    result = tool.run()
    print(result)
    print()
    
    # Test 3: Outlook for today
    print(f"Test 3: Outlook - Today ({today})")
    print("-" * 60)
    tool = CheckEventsForDate(provider="outlook", date=today)
    result = tool.run()
    print(result)
    print()
    
    # Test 4: Invalid date format
    print("Test 4: Invalid date format")
    print("-" * 60)
    tool = CheckEventsForDate(provider="google", date="01-07-2026")
    result = tool.run()
    print(result)
    print()
    
    print("=" * 60)
    print("All tests completed!")
    print("=" * 60)

