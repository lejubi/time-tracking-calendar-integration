
import os.path
import uuid

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# ----------------------------------
# CONFIGURATION
# ----------------------------------

DESTINATION_CALENDAR_ID = "primary"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]

# Colors for the custom event labels
LABEL_COLORS = {
    "self-maintenance": "#ee8873",
    "commute": "#f0a67a",
    "school": "#8cacb9",
    "clubs": "#dfcc85",
    "studying": "#bcbe9c",
    "hobbies": "#eb7c89",
    "eating": "#8cb9b7",
    "family": "#a1b1a2",
    "friends": "#b889c0",
    "other": "#e282ab",
}

# Original calendar name -> destination label name
SOURCE_TO_LABEL = {
    "clubs": "clubs",
    "commute": "commute",
    "eating": "eating",
    "family": "family",
    "friends": "friends",
    "school": "school",
    "studying": "studying",
    "tests": "school",
    "wellness": "self-maintenance",
}

# These calendars should remain separate.
# Matching is case-sensitive.
EXCLUDED_CALENDARS = {
    "birthdays",
    "Birthdays",
    "Family",
    "Tasks",
}


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

calendar_service = build(
    "calendar", "v3", credentials=creds
)


# ----------------------------------
# HELPER: GET ALL PAGES
# ----------------------------------

def get_all_calendars():
    calendars = []
    page_token = None

    while True:
        result = calendar_service.calendarList().list(
            maxResults=250,
            pageToken=page_token
        ).execute()

        calendars.extend(result.get("items", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return calendars


def get_all_events(calendar_id, single_events=True):
    events = []
    page_token = None

    while True:
        result = calendar_service.events().list(
            calendarId=calendar_id,
            maxResults=2500,
            singleEvents=single_events,
            showDeleted=False,
            pageToken=page_token
        ).execute()

        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")

        if not page_token:
            break

    return events


# ----------------------------------
# CREATE / RETRIEVE EVENT LABELS
# ----------------------------------

def setup_labels():

    destination = calendar_service.calendars().get(
        calendarId=DESTINATION_CALENDAR_ID
    ).execute()

    label_properties = destination.get(
        "labelProperties", {}
    )

    labels = label_properties.get("eventLabels", [])

    # Find existing labels by name
    label_ids = {
        label["name"].strip().lower(): label["id"]
        for label in labels
        if label.get("name") and label.get("id")
    }

    # Create missing labels and update their colors
    for name, color in LABEL_COLORS.items():

        normalized_name = name.strip().lower()

        if normalized_name in label_ids:

            # Update the color of an existing label
            for label in labels:
                if label.get("name", "").strip().lower() == normalized_name:
                    label["backgroundColor"] = color
                    break

        else:

            new_label = {
                "id": str(uuid.uuid4()),
                "name": name,
                "backgroundColor": color
            }

            labels.append(new_label)
            label_ids[normalized_name] = new_label["id"]

    # Save labels to the destination calendar
    calendar_service.calendars().patch(
        calendarId=DESTINATION_CALENDAR_ID,
        body={
            "labelProperties": {
                "eventLabels": labels
            }
        }
    ).execute()

    return label_ids


# ----------------------------------
# RETRIEVE CALENDARS
# ----------------------------------

calendars = get_all_calendars()

# Only select calendars explicitly included in SOURCE_TO_LABEL.
# The primary calendar (Juna Lee) is not copied into itself.

source_calendars = [
    calendar for calendar in calendars
    if not calendar.get("primary", False)
    and calendar.get("summary", "") in SOURCE_TO_LABEL
    and calendar.get("summary", "") not in EXCLUDED_CALENDARS
]

print(f"Found {len(source_calendars)} source calendars.")

print("\nCalendars that will be copied:")
for calendar in source_calendars:
    name = calendar.get("summary", "")
    print(f"  {name} -> {SOURCE_TO_LABEL[name]}")

print("\nCalendars being kept separate:")
for calendar in calendars:
    name = calendar.get("summary", "")
    if name in EXCLUDED_CALENDARS:
        print(f"  {name}")

label_ids = setup_labels()

# Existing events in Juna Lee (formerly Classes)
# should receive the school label.
school_label_id = label_ids["school"]


# ----------------------------------
# LABEL EXISTING PRIMARY EVENTS
# ----------------------------------

print("\nLabeling existing primary calendar events...")

primary_events = get_all_events(
    DESTINATION_CALENDAR_ID,
    single_events=False
)

for event in primary_events:

    if event.get("status") == "cancelled":
        continue

    # Do not change labels on events previously copied
    private_properties = event.get(
        "extendedProperties", {}
    ).get("private", {})

    if private_properties.get("copiedFromCalendarId"):
        continue

    # Only process regular calendar events
    if event.get("eventType", "default") != "default":
        continue

    calendar_service.events().patch(
        calendarId=DESTINATION_CALENDAR_ID,
        eventId=event["id"],
        eventLabelVersion=1,
        body={
            "eventLabelId": school_label_id
        }
    ).execute()

print("Finished labeling existing events.")


# ----------------------------------
# FIND ALREADY-COPIED EVENTS
# ----------------------------------

print("\nChecking for existing copies...")

destination_events = get_all_events(
    DESTINATION_CALENDAR_ID,
    single_events=True
)

existing_copies = set()

for event in destination_events:

    private_properties = event.get(
        "extendedProperties", {}
    ).get("private", {})

    source_calendar_id = private_properties.get(
        "copiedFromCalendarId"
    )

    source_event_id = private_properties.get(
        "copiedFromEventId"
    )

    if source_calendar_id and source_event_id:
        existing_copies.add(
            (source_calendar_id, source_event_id)
        )


# ----------------------------------
# COPY EVENTS
# ----------------------------------

copied_count = 0
skipped_count = 0

for calendar in source_calendars:

    source_calendar_id = calendar["id"]
    calendar_name = calendar.get("summary", "")

    # Determine the destination label
    category_name = SOURCE_TO_LABEL[calendar_name]
    category_label_id = label_ids[category_name]

    print(f"\nCopying events from: {calendar_name}")
    print(f"Assigning label: {category_name}")

    events = get_all_events(
        source_calendar_id,
        single_events=True
    )

    for event in events:

        if event.get("status") == "cancelled":
            continue

        # Skip unsupported special event types
        if event.get("eventType", "default") != "default":
            skipped_count += 1
            continue

        event_key = (
            source_calendar_id,
            event["id"]
        )

        # Prevent duplicate copies
        if event_key in existing_copies:
            skipped_count += 1
            continue

        # Fields to preserve
        event_body = {}

        fields_to_copy = [
            "summary",
            "description",
            "location",
            "start",
            "end",
            "transparency",
            "visibility",
            "reminders",
        ]

        for field in fields_to_copy:
            if field in event:
                event_body[field] = event[field]

        # Assign the category label
        event_body["eventLabelId"] = category_label_id

        # Record original event IDs for duplicate prevention
        event_body["extendedProperties"] = {
            "private": {
                "copiedFromCalendarId": source_calendar_id,
                "copiedFromEventId": event["id"]
            }
        }

        # Create the copy in the primary calendar
        calendar_service.events().insert(
            calendarId=DESTINATION_CALENDAR_ID,
            body=event_body,
            eventLabelVersion=1
        ).execute()

        existing_copies.add(event_key)
        copied_count += 1

    print(f"Finished {calendar_name}.")


# ----------------------------------
# SUMMARY
# ----------------------------------

print("\n----------------------------------")
print("CALENDAR COPYING COMPLETE")
print("----------------------------------")
print("New events copied:", copied_count)
print("Events skipped:", skipped_count)
print("Destination: Juna Lee (primary)")