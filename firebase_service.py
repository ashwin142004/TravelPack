import firebase_admin
from firebase_admin import credentials, firestore
import os

db = None

import json

def initialize_firebase():
    global db
    try:
        # 1. Check for environment variable (Production)
        firebase_creds = os.getenv('FIREBASE_CREDENTIALS')
        if firebase_creds:
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase initialized from Environment Variable.")
            return True
            
        # 2. Check for service account file (Local Development)
        cred_path = 'serviceAccountKey.json'
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase initialized from File.")
            return True
        else:
            print("Warning: serviceAccountKey.json not found and FIREBASE_CREDENTIALS not set.")
            return False
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
        return False

def get_all_trips(user_id, user_email=None):
    if not db:
        return []
    try:
        trips_ref = db.collection('trips')
        
        # 1. Fetch owned trips
        owned_query = trips_ref.where('user_id', '==', user_id).stream()
        
        trips_dict = {}
        for doc in owned_query:
            trips_dict[doc.id] = doc.to_dict()
            trips_dict[doc.id]['id'] = doc.id
            trips_dict[doc.id]['is_owner'] = True

        # 2. Fetch shared trips (if email provided)
        if user_email:
            shared_query = trips_ref.where('shared_with', 'array_contains', user_email).stream()
            for doc in shared_query:
                if doc.id not in trips_dict:
                    trips_dict[doc.id] = doc.to_dict()
                    trips_dict[doc.id]['id'] = doc.id
                    trips_dict[doc.id]['is_owner'] = False
        
        return list(trips_dict.values())
    except Exception as e:
        print(f"Error fetching trips: {e}")
        return []

def get_trip(trip_id):
    if not db:
        return None
    try:
        doc = db.collection('trips').document(trip_id).get()
        if doc.exists:
            trip = doc.to_dict()
            trip['id'] = doc.id
            if 'categories' not in trip:
                trip['categories'] = ['General', 'Clothing', 'Toiletries', 'Electronics', 'Documents']
            return trip
        return None
    except Exception as e:
        print(f"Error fetching trip: {e}")
        return None

def add_trip(user_id, name, location, start_date=None, end_date=None, owner_email=None):
    if not db:
        return
    try:
        db.collection('trips').add({
            'user_id': user_id,
            'owner_email': owner_email,
            'shared_with': [],
            'name': name,
            'location': location,
            'start_date': start_date,
            'end_date': end_date,
            'categories': ['General', 'Clothing', 'Toiletries', 'Electronics', 'Documents'],
            'created_at': firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print(f"Error adding trip: {e}")

def share_trip(trip_id, email):
    if not db:
        return False
    try:
        # Atomically add email to shared_with array
        db.collection('trips').document(trip_id).update({
            'shared_with': firestore.ArrayUnion([email])
        })
        return True
    except Exception as e:
        print(f"Error sharing trip: {e}")
        return False

def delete_trip(trip_id):
    if not db:
        return
    try:
        db.collection('trips').document(trip_id).delete()
    except Exception as e:
        print(f"Error deleting trip: {e}")

def add_category_to_trip(trip_id, category_name):
    if not db:
        return False
    try:
        db.collection('trips').document(trip_id).update({
            'categories': firestore.ArrayUnion([category_name])
        })
        return True
    except Exception as e:
        print(f"Error adding category: {e}")
        return False

def remove_category_from_trip(trip_id, category_name):
    if not db:
        return False
    try:
        db.collection('trips').document(trip_id).update({
            'categories': firestore.ArrayRemove([category_name])
        })
        return True
    except Exception as e:
        print(f"Error removing category: {e}")
        return False

# Packing List Functions
def get_packing_items(trip_id):
    if not db:
        return []
    try:
        items_ref = db.collection('packing_items')
        
        try:
            # Try fetching ordered by created_at (requires composite index)
            query = items_ref.where('trip_id', '==', trip_id).order_by('created_at', direction=firestore.Query.ASCENDING).stream()
            # Convert to list to trigger execution and potential error
            doc_list = list(query)
        except Exception:
            # Index missing or query failed. Falling back to in-memory sorting.
            # This is expected behavior until the index is built.
            query = items_ref.where('trip_id', '==', trip_id).stream()
            doc_list = list(query)
            # Sort manually by created_at (handling None values safely)
            doc_list.sort(key=lambda x: x.to_dict().get('created_at') or 0)

        items = []
        for doc in doc_list:
            item = doc.to_dict()
            item['id'] = doc.id
            # Format timestamp for display (IST: UTC+5:30)
            if 'created_at' in item and item['created_at']:
                # Convert Firestore Timestamp to datetime value 
                dt = item['created_at']
                # Check if it's already a datetime object (sometimes wrapper handles it) or Timestamp
                if hasattr(dt, 'strftime'):
                    # Create a fixed timezone offset for IST (UTC+5:30) without external deps if possible,
                    # but datetime.timezone is available in Python 3.2+
                    from datetime import timezone, timedelta
                    ist = timezone(timedelta(hours=5, minutes=30))
                    # dt from firestore is usually timezone-aware UTC. Convert to IST.
                    dt_ist = dt.astimezone(ist)
                    item['created_at_formatted'] = dt_ist.strftime('%b %d, %I:%M %p')
                else: 
                     item['created_at_formatted'] = ''
            else:
                 item['created_at_formatted'] = ''
            items.append(item)
        return items
    except Exception as e:
        print(f"Error fetching packing items: {e}")
        return []

def add_packing_item(trip_id, text, category='General', added_by_email=None, added_by_name=None, note=None):
    if not db:
        return
    try:
        db.collection('packing_items').add({
            'trip_id': trip_id,
            'text': text,
            'category': category,
            'added_by_email': added_by_email,
            'added_by_name': added_by_name,
            'note': note,
            'is_completed': False,
            'created_at': firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print(f"Error adding packing item: {e}")

def toggle_packing_item(item_id, current_status):
    if not db:
        return
    try:
        db.collection('packing_items').document(item_id).update({
            'is_completed': not current_status
        })
    except Exception as e:
        print(f"Error toggling item: {e}")


def delete_packing_item(item_id):
    if not db:
        return
    try:
        db.collection('packing_items').document(item_id).delete()
    except Exception as e:
        print(f"Error deleting item: {e}")

def delete_packing_item_by_text(trip_id, text):
    if not db:
        return
    try:
        # Find items with matching text in the trip
        # Limit to 1 to avoid accidental mass deletion, but ideally we'd pass an ID.
        # AI works with names, so we'll delete the first match.
        docs = db.collection('packing_items').where('trip_id', '==', trip_id).where('text', '==', text).stream()
        for doc in docs:
            doc.reference.delete()
            # Only delete one
            return
    except Exception as e:
        print(f"Error deleting item by text: {e}")

def update_packing_item_note(item_id, new_note):
    if not db:
        return False
    try:
        db.collection('packing_items').document(item_id).update({
            'note': new_note
        })
        return True
    except Exception as e:
        print(f"Error updating note: {e}")
        return False

# Private Notes Functions
def get_user_trip_note(trip_id, user_id):
    if not db:
        return []
    try:
        doc = db.collection('trips').document(trip_id).collection('private_notes').document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            # Return the list of notes, defaulting to empty list
            if 'notes' in data:
                notes = data['notes']
                # Ensure created_at is string
                for note in notes:
                    if 'created_at' in note and not isinstance(note['created_at'], str):
                         # Try simple string conversion or isoformat
                         try:
                             note['created_at'] = note['created_at'].isoformat()
                         except:
                             note['created_at'] = str(note['created_at'])
                return notes
            elif 'content' in data:
                # Migrate old single note to list
                created = data.get('updated_at')
                if created and not isinstance(created, str):
                    try:
                        created = created.isoformat()
                    except:
                        created = str(created)
                return [{'id': 'legacy', 'text': data['content'], 'created_at': created}]
        return []
    except Exception as e:
        print(f"Error fetching private notes: {e}")
        return []

def save_user_trip_note(trip_id, user_id, content):
    if not db:
        return False
    try:
        # Create a new note object
        import uuid
        from datetime import datetime
        
        new_note = {
            'id': str(uuid.uuid4()),
            'text': content,
            'created_at': datetime.now().isoformat()
        }
        
        doc_ref = db.collection('trips').document(trip_id).collection('private_notes').document(user_id)
        
        # Use array_union to append
        # Note: array_union might not work well if we want to store complex objects unless they are exact matches? 
        # Actually for appending new unique objects it's fine.
        # But to be safe and allow setting fields, let's use set with merge if doc doesn't exist, 
        # or update if it does.
        
        # Checking existence to decide between set (create) and update (append) is one way.
        # Or just use set(..., merge=True) with array_union.
        
        doc_ref.set({
            'notes': firestore.ArrayUnion([new_note]),
            'updated_at': firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        return True
    except Exception as e:
        print(f"Error saving private note: {e}")
        return False

def update_user_trip_note(trip_id, user_id, note_id, new_content):
    if not db:
        return False
    try:
        doc_ref = db.collection('trips').document(trip_id).collection('private_notes').document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            notes = data.get('notes', [])
            updated = False
            for note in notes:
                if note.get('id') == note_id:
                    note['text'] = new_content
                    # Update timestamp if desired
                    from datetime import datetime
                    note['updated_at'] = datetime.now().isoformat()
                    updated = True
                    break
            
            if updated:
                doc_ref.update({'notes': notes})
                return True
        return False
    except Exception as e:
        print(f"Error updating private note: {e}")
        return False

def delete_user_trip_note(trip_id, user_id, note_id):
    if not db:
        return False
    try:
        doc_ref = db.collection('trips').document(trip_id).collection('private_notes').document(user_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            notes = data.get('notes', [])
            # Filter out the note to delete
            new_notes = [n for n in notes if n.get('id') != note_id]
            
            if len(notes) != len(new_notes):
                doc_ref.update({'notes': new_notes})
                return True
        return False
    except Exception as e:
        print(f"Error deleting private note: {e}")
        return False

# Notification Functions
def get_upcoming_trips_for_notifications():
    """
    Returns a list of trips that are starting within the next few days
    and need notifications.
    """
    if not db:
        return []
        
    try:
        from datetime import datetime, timedelta
        now = datetime.now()
        # Look ahead up to 5 days
        upcoming_limit = now + timedelta(days=5)
        
        # We need to query trips. 
        # Ideally, we should filter by start_date >= now and start_date <= upcoming_limit.
        # However, start_date is stored as string 'YYYY-MM-DD' in this app (based on add_trip).
        # We can do string comparison if format is consistent.
        
        today_str = now.strftime('%Y-%m-%d')
        limit_str = upcoming_limit.strftime('%Y-%m-%d')
        
        trips = []
        # Querying all trips is inefficient but for this scale it might be ok.
        # Better: use range query on `start_date`.
        
        docs = db.collection('trips').where('start_date', '>=', today_str).where('start_date', '<=', limit_str).stream()
        
        for doc in docs:
            trip = doc.to_dict()
            trip['id'] = doc.id
            trips.append(trip)
            
        return trips
    except Exception as e:
        print(f"Error fetching upcoming trips: {e}")
        return []

def log_notification(trip_id, user_email, notification_type):
    if not db:
        return
    try:
        # Log to a subcollection 'notifications' in the trip or a global one
        # For this requirement, we mainly need to track WHEN we sent it to respect frequency.
        # We will update the trip document with 'last_notification_sent' and 'notification_count_today'
        # Resetting 'notification_count_today' needs to happen too, or we just track timestamps.
        
        # Simpler approach: Store 'last_notification_timestamp' on the trip.
        pass # Actual logic handled in update_trip_last_notification for the state
        
        # We can also add a record to a history collection
        db.collection('notification_logs').add({
            'trip_id': trip_id,
            'user_email': user_email,
            'type': notification_type,
            'timestamp': firestore.SERVER_TIMESTAMP
        })
        print(f"Logged notification for {trip_id} to {user_email}")

    except Exception as e:
        print(f"Error logging notification: {e}")

def update_trip_notification_status(trip_id, timestamp):
    if not db:
        return
    try:
        db.collection('trips').document(trip_id).update({
            'last_notification_sent': timestamp
        })
    except Exception as e:
        print(f"Error updating trip notification status: {e}")


