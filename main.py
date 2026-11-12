
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
        "Event ID",
        "Title",
        "Start",
        "End",
        "Location",
        "Description"
    ]]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'{SHEET_NAME}'!A1:F1",
        valueInputOption="RAW",
        body={"values": headers}
    ).execute()

# ----------------------------------
# PROCESS NEW EVENTS
# ----------------------------------

new_rows = []

for event in events:

    # Skip cancelled events
    if event.get("status") == "cancelled":
        continue

    event_id = event.get("id")

    # Skip events already in spreadsheet
    if not event_id or event_id in existing_ids:
        continue

    start = event.get("start", {})
    end = event.get("end", {})

    start_time = start.get(
        "dateTime", start.get("date", "")
    )

    end_time = end.get(
        "dateTime", end.get("date", "")
    )

    row = [
        event_id,
        event.get("summary", ""),
        start_time,
        end_time,
        event.get("location", ""),
        event.get("description", ""),
        event.get("calendar_name", "")
    ]

    # Only include events that start and end on the same day in 2027
    if start_time and end_time:
        start_date = start_time[:10]
        end_date = end_time[:10]

        if start_date == end_date and start_date.startswith("2027"):
            new_rows.append(row)

# ----------------------------------
# WRITE TO GOOGLE SHEETS
# ----------------------------------

if new_rows:

    sheets_service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=sheet_range,
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": new_rows}
    ).execute()

    print(f"Added {len(new_rows)} new events!")

else:
    print("No new events to add.")

print("Number of events retrieved:", len(events))

for event in events[:5]:
    print(
        event.get("summary"),
        event.get("start")
    )

print("Finished!")
