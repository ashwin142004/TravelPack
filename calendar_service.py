from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import datetime
import dateutil.parser

def create_calendar_event(token_info, summary, description, start_time_str):
    """
    Creates an event.
    token_info: dict from session['token']
    start_time_str: ISO format string from HTML datetime-local input
    """
    try:
        # Construct Credentials from the token info
        # Flask-Authlib's token dict has 'access_token', 'token_type', 'expires_in', etc.
        creds = Credentials(
            token=token_info.get('access_token'),
            refresh_token=token_info.get('refresh_token'),
            token_uri=token_info.get('uri'),
            client_id=token_info.get('client_id'), # Might not be in token dict, but access_token is usually enough for immediate calls
            client_secret=token_info.get('client_secret'),
            scopes=token_info.get('scope')
        )
        
        service = build('calendar', 'v3', credentials=creds)

        # Parse start time
        # UI datetime-local sends 'YYYY-MM-DDTHH:MM'
        start_dt = dateutil.parser.parse(start_time_str)
        end_dt = start_dt + datetime.timedelta(hours=1)
        
        event = {
            'summary': summary,
            'description': description,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'Asia/Kolkata', # Hardcoded for now per user context (IST)
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'Asia/Kolkata',
            },
        }

        event_result = service.events().insert(calendarId='primary', body=event).execute()
        return event_result.get('htmlLink')
    except Exception as e:
        print(f"Error creating calendar event: {e}")
        return None
