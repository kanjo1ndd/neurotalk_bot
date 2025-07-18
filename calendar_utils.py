import datetime
from typing import List
from google.oauth2 import service_account
from googleapiclient.discovery import build

CALENDAR_ID = 'dangbang568@gmail.com'
CREDENTIALS_FILE = 'credentials.json'

WORK_START = datetime.time(10, 0)
WORK_END = datetime.time(18, 0)

def get_calendar_service():
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=['https://www.googleapis.com/auth/calendar']
    )
    return build('calendar', 'v3', credentials=creds)

def list_free_slots(specialist: str, start_iso: str, end_iso: str, duration_minutes: int) -> List[dict]:
    service = get_calendar_service()

    start_dt = datetime.datetime.fromisoformat(start_iso)
    end_dt = datetime.datetime.fromisoformat(end_iso)

    events_result = service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_iso,
        timeMax=end_iso,
        singleEvents=True,
        orderBy='startTime'
    ).execute()

    events = events_result.get('items', [])
    busy_times = []
    for event in events:
        s = datetime.datetime.fromisoformat(event['start']['dateTime'].replace('Z', '+00:00'))
        e = datetime.datetime.fromisoformat(event['end']['dateTime'].replace('Z', '+00:00'))
        busy_times.append((s, e))

    free_slots = []
    current_day = start_dt.date()
    tz = start_dt.tzinfo or datetime.timezone.utc  # берём часовой пояс из start_iso

    while current_day <= end_dt.date():
        day_start = datetime.datetime.combine(current_day, WORK_START, tz)
        day_end = datetime.datetime.combine(current_day, WORK_END, tz)

        slot_start = max(day_start, start_dt)
        while slot_start + datetime.timedelta(minutes=duration_minutes) <= day_end:
            slot_end = slot_start + datetime.timedelta(minutes=duration_minutes)
            conflict = any(bs < slot_end and slot_start < be for bs, be in busy_times)

            if not conflict:
                free_slots.append({
                    "start": slot_start.isoformat(),
                    "end": slot_end.isoformat(),
                    "duration": duration_minutes,
                    "specialist": specialist
                })

            slot_start += datetime.timedelta(minutes=15)

        current_day += datetime.timedelta(days=1)

    return free_slots

def create_appointment(specialist: str, start_iso: str, end_iso: str,
                       summary: str, description: str, attendee_email: str = None):
    
    service = get_calendar_service()

    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_iso,
            'timeZone': 'Europe/Kyiv',
        },
        'end': {
            'dateTime': end_iso,
            'timeZone': 'Europe/Kyiv',
        },
        'status': 'confirmed',
        'transparency': 'opaque',
    }

    return service.events().insert(calendarId=CALENDAR_ID, body=event).execute()