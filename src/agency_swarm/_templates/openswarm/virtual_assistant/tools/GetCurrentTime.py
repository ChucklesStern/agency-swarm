from agency_swarm.tools import BaseTool
from pydantic import Field
from datetime import datetime
import pytz


class GetCurrentTime(BaseTool):
    """
    Retrieves the current date and time in a specified timezone.
    Use this when you need to know what time it is, or to provide accurate time-based information.
    """
    timezone: str = Field(
        default="UTC",
        description="The timezone to retrieve the current time in (e.g., 'UTC', 'US/Eastern', 'Europe/London', 'Asia/Tokyo'). Defaults to UTC."
    )
    include_day_of_week: bool = Field(
        default=True,
        description="If True, includes the day of the week in the output. Defaults to True."
    )

    def run(self):
        """Retrieves the current date and time in the specified timezone."""
        try:
            tz = pytz.timezone(self.timezone)
            current_time = datetime.now(tz)

            if self.include_day_of_week:
                formatted_time = current_time.strftime("%A, %B %d, %Y - %I:%M:%S %p %Z")
            else:
                formatted_time = current_time.strftime("%B %d, %Y - %I:%M:%S %p %Z")

            return f"Current time in {self.timezone}: {formatted_time}"
        
        except pytz.exceptions.UnknownTimeZoneError:
            return f"Error: Unknown timezone '{self.timezone}'. Please provide a valid timezone (e.g., 'UTC', 'US/Eastern', 'Europe/London')."
        except Exception as e:
            return f"Error retrieving current time: {str(e)}"


if __name__ == "__main__":
    # Test 1: Current time in UTC
    print("=== Test 1: Current time in UTC ===")
    tool = GetCurrentTime(timezone="UTC")
    print(tool.run())
    print()
    
    # Test 2: Current time in US/Eastern
    print("=== Test 2: Current time in US/Eastern ===")
    tool = GetCurrentTime(timezone="US/Eastern")
    print(tool.run())
    print()
    
    # Test 3: Current time in Europe/London without day of week
    print("=== Test 3: Current time in Europe/London (without day of week) ===")
    tool = GetCurrentTime(timezone="Europe/London", include_day_of_week=False)
    print(tool.run())
    print()
    
    # Test 4: Current time in Asia/Tokyo
    print("=== Test 4: Current time in Asia/Tokyo ===")
    tool = GetCurrentTime(timezone="Asia/Tokyo")
    print(tool.run())
    print()
    
    # Test 5: Invalid timezone
    print("=== Test 5: Invalid timezone ===")
    tool = GetCurrentTime(timezone="Invalid/Timezone")
    print(tool.run())

