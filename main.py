
import os.path

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# ----------------------------------
# CONFIGURATION
# ----------------------------------

SPREADSHEET_ID = "1jGdf22xdBxKTba6TvLkqqP4Hhds35umPqsVR6mYSkx8"
SHEET_NAME = "2027"
CALENDAR_ID = "primary"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/spreadsheets"
]

from datetime import datetime, timedelta

def round_to_half_hour(time_string):
    dt = datetime.fromisoformat(time_string)

    minutes = dt.minute

    if minutes < 15:
        dt = dt.replace(minute=0, second=0, microsecond=0)
    elif minutes < 45:
        dt = dt.replace(minute=30, second=0, microsecond=0)
    else:
        dt = dt.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

    return dt.isoformat()

def get_time_column(time_string):
    dt = datetime.fromisoformat(time_string)

    # Number of half-hour increments since midnight
    increment = (dt.hour * 60 + dt.minute) // 30

    # D is column 4, so add 4
    return 4 + increment

# ----------------------------------
# AUTHENTICATION
# ----------------------------------

creds = None

if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file(
        "token.json", SCOPES
    )

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)

    with open("token.json", "w") as token:
        token.write(creds.to_json())

# Connect to Google APIs
calendar_service = build(
    "calendar", "v3", credentials=creds
)

sheets_service = build(
    "sheets", "v4", credentials=creds
)

# ----------------------------------
# RETRIEVE EVENTS FROM ALL CALENDARS
# ----------------------------------

events = []

# Get all calendars accessible to your account
calendar_list = calendar_service.calendarList().list().execute()

calendars = calendar_list.get("items", [])

print(f"Found {len(calendars)} calendars.")

for calendar in calendars:

    calendar_id = calendar["id"]
    calendar_name = calendar.get("summary", "Unknown")

    if (calendar_name in ["school", "clubs", "tests", "other", "friends", "classes", "family"]):

        print(f"Retrieving events from: {calendar_name}")

        page_token = None

        while True:

            result = calendar_service.events().list(
                calendarId=calendar_id,
                maxResults=2500,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token
            ).execute()

            calendar_events = result.get("items", [])

            # Track which calendar each event came from
            for event in calendar_events:
                event["calendar_name"] = calendar_name

            events.extend(calendar_events)

            page_token = result.get("nextPageToken")

            if not page_token:
                break

print(f"Retrieved {len(events)} events across all calendars.")

# ----------------------------------
# READ EXISTING SPREADSHEET DATA
# ----------------------------------

sheet_range = f"'{SHEET_NAME}'!A:G"

existing = sheets_service.spreadsheets().values().get(
    spreadsheetId=SPREADSHEET_ID,
    range=f"'{SHEET_NAME}'!A:A"
).execute()

existing_values = existing.get("values", [])

# First column contains event IDs
existing_ids = {
    row[0] for row in existing_values[1:] if row
}

# Add headers if the sheet is empty
if not existing_values:
    headers = [[
        "이주나",
        "",
        "date",
    ] + [
        f"{(i // 2):02d}:{'00' if i % 2 == 0 else '30'}"
        for i in range(48)
    ]]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A1:AY1",
        valueInputOption="RAW",
        body={"values": headers}
    ).execute()

# ----------------------------------
# PROCESS EVENTS INTO DAILY GRID
# ----------------------------------

# Create 365 rows, each with 51 columns (A:AY)
# First 3 columns are blank
# Last 48 columns represent half-hour increments
year_data = [[""] * 51 for _ in range(365)]

for event in events:
    event_id = event["id"]
    title = event.get("summary", "")

    start = event["start"]
    end = event["end"]

    start_time = start.get("dateTime", start.get("date", ""))
    end_time = end.get("dateTime", end.get("date", ""))

    # Skip all-day events
    if "T" not in start_time or "T" not in end_time:
        continue

    # Get original dates
    original_start_date = start_time[:10]
    original_end_date = end_time[:10]

    # Only include events in 2027 that start and end on the same day
    if original_start_date != original_end_date:
        continue

    if not original_start_date.startswith("2027"):
        continue

    # Round start and end times
    start_time = round_to_half_hour(start_time)
    end_time = round_to_half_hour(end_time)

    # Get the day of the year (January 1 = 1)
    event_date = datetime.fromisoformat(original_start_date)
    day_index = event_date.timetuple().tm_yday - 1

    # Determine occupied half-hour slots
    start_col = get_time_column(start_time)
    end_col = get_time_column(end_time)

    for col in range(start_col, end_col):

        # Only allow columns D through AY
        if 4 <= col <= 51:

            # Mark occupied time slot
            year_data[day_index][col - 1] = 1
# ----------------------------------
# WRITE TO GOOGLE SHEETS
# ----------------------------------

sheets_service.spreadsheets().values().update(
    spreadsheetId=SPREADSHEET_ID,
    range=f"'{SHEET_NAME}'!A2:AY366",
    valueInputOption="RAW",
    body={"values": year_data}
).execute()

print("Successfully updated the 2027 calendar grid!")
