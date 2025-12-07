import firebase_admin
from firebase_admin import credentials, firestore
import os

db = None

def initialize_firebase():
    global db
    try:
        # Check if service account file exists
        cred_path = 'serviceAccountKey.json'
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            print("Firebase initialized successfully.")
            return True
        else:
            print("Warning: serviceAccountKey.json not found. Firebase features will not work.")
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
            return trip
        return None
    except Exception as e:
        print(f"Error fetching trip: {e}")
        return None

def add_trip(user_id, name, location, owner_email=None):
    if not db:
        return
    try:
        db.collection('trips').add({
            'user_id': user_id,
            'owner_email': owner_email,
            'shared_with': [],
            'name': name,
            'location': location,
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

# Packing List Functions
def get_packing_items(trip_id):
    if not db:
        return []
    try:
        items_ref = db.collection('packing_items')
        query = items_ref.where('trip_id', '==', trip_id).stream()
        items = []
        for doc in query:
            item = doc.to_dict()
            item['id'] = doc.id
            items.append(item)
        return items
    except Exception as e:
        print(f"Error fetching packing items: {e}")
        return []

def add_packing_item(trip_id, text, category='General'):
    if not db:
        return
    try:
        db.collection('packing_items').add({
            'trip_id': trip_id,
            'text': text,
            'category': category,
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
