from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/calendar.readonly"
]

creds = Credentials.from_authorized_user_file(
    "token.json", SCOPES
)

calendar_service = build(
    "calendar", "v3", credentials=creds
)

calendars = calendar_service.calendarList().list().execute()

for calendar in calendars.get("items", []):
    print(
        calendar["summary"],
        "| ID:", calendar["id"],
        "| Primary:", calendar.get("primary", False)
    )