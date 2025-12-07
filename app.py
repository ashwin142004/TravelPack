from flask import Flask, render_template, redirect, url_for, session, request, flash
from authlib.integrations.flask_client import OAuth
from firebase_service import initialize_firebase, get_all_trips, add_trip, delete_trip
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')

# Firebase Setup
# Note: We need the service account key. For now, we'll handle the missing key gracefully.
firebase_app = initialize_firebase()

# OAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

@app.route('/')
def index():
    user = session.get('user')
    if user:
        return redirect(url_for('home'))
    return render_template('login.html')

@app.route('/login')
def login():
    redirect_uri = url_for('authorize', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()
    session['user'] = user_info
    # TODO: Save user to Firebase
    return redirect(url_for('home'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

@app.route('/home')
def home():
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
    
    # Google UserInfo uses 'sub' as the unique ID
    trips = get_all_trips(user.get('sub'), user.get('email'))
    return render_template('home.html', user=user, trips=trips)

@app.route('/add_trip', methods=['POST'])
def create_trip():
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
    
    name = request.form.get('name')
    location = request.form.get('location')
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    
    if name:
        add_trip(user.get('sub'), name, location, start_date=start_date, end_date=end_date)
    
    return redirect(url_for('home'))

@app.route('/delete_trip/<trip_id>')
def remove_trip(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
    
    delete_trip(trip_id)
    return redirect(url_for('home'))

@app.route('/trip/<trip_id>')
def trip_detail(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
    
    # Import here to avoid circular imports if any, or just convenience
    from firebase_service import get_trip, get_packing_items
    
    trip = get_trip(trip_id)
    if not trip:
        return redirect(url_for('home'))
        
    items = get_packing_items(trip_id)
    
    # Extract unique users for filter
    contributors = set()
    for item in items:
        if item.get('added_by_name'):
            contributors.add(item.get('added_by_name'))
    sorted_contributors = sorted(list(contributors))
    
    # Filter by user if requested
    filter_user = request.args.get('filter_user')
    if filter_user:
        items = [i for i in items if i.get('added_by_name') == filter_user]
    
    # Group items by category
    grouped_items = {}
    for item in items:
        cat = item.get('category', 'General')
        if cat not in grouped_items:
            grouped_items[cat] = []
        grouped_items[cat].append(item)
        
    # Sort categories
    # Use categories from trip if available (it should be now), or fallback to keys in grouped_items
    # But we want to show ALL categories available for the trip, even if empty
    available_categories = trip.get('categories', [])
    # Ensure all used categories are in the list (in case of legacy data not in array)
    for cat in grouped_items.keys():
        if cat not in available_categories:
            available_categories.append(cat)
            
    sorted_categories = sorted(available_categories)
    
    return render_template('trip_detail.html', user=user, trip=trip, grouped_items=grouped_items, sorted_categories=sorted_categories, contributors=sorted_contributors, active_filter=filter_user)

@app.route('/trip/<trip_id>/add_item', methods=['POST'])
def add_item(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    text_block = request.form.get('text')
    category = request.form.get('category', 'General')
    note = request.form.get('note')
    
    if text_block:
        from firebase_service import add_packing_item
        added_by_email = user.get('email')
        added_by_name = user.get('name', added_by_email)
        
        # Split text by newline to handle bulk entry
        items = [line.strip() for line in text_block.splitlines() if line.strip()]
        
        for item_text in items:
            add_packing_item(trip_id, item_text, category, added_by_email=added_by_email, added_by_name=added_by_name, note=note)
        
    filter_user = request.form.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

@app.route('/item/<item_id>/toggle/<trip_id>')
def toggle_item(item_id, trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    # We need current status to toggle. For simplicity, we'll just pass it or fetch it.
    # Actually, let's fetch the item in the service or just pass a param?
    # Better: The service can handle it if we pass the current state from UI?
    # Or just fetch it in service. Let's update service to just toggle.
    # Wait, my service `toggle_packing_item` takes `current_status`.
    # I should probably just fetch it in the service or pass it.
    # Let's pass it as a query param for simplicity.
    current_status = request.args.get('status') == 'True'
    
    from firebase_service import toggle_packing_item
    toggle_packing_item(item_id, current_status)
    
    filter_user = request.args.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

@app.route('/item/<item_id>/update_note/<trip_id>', methods=['POST'])
def update_note_route(item_id, trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    new_note = request.form.get('note')
    
    from firebase_service import update_packing_item_note
    update_packing_item_note(item_id, new_note)
    
    filter_user = request.form.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

@app.route('/trip/<trip_id>/share', methods=['POST'])
def share_trip_route(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    email = request.form.get('email')
    
    if email:
        from firebase_service import share_trip
        if share_trip(trip_id, email):
            flash(f'Access granted to {email}. They can now log in to see this trip!', 'success')
        else:
            flash('Error sharing trip.', 'danger')
        
    filter_user = request.form.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

@app.route('/trip/<trip_id>/add_category', methods=['POST'])
def add_category_route(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    category_name = request.form.get('category_name')
    
    if category_name:
        from firebase_service import add_category_to_trip
        add_category_to_trip(trip_id, category_name)
        
    filter_user = request.form.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

@app.route('/trip/<trip_id>/delete_category/<category_name>')
def delete_category_route(trip_id, category_name):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    from firebase_service import remove_category_from_trip
    remove_category_from_trip(trip_id, category_name)
    
    filter_user = request.args.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))



@app.route('/item/<item_id>/delete/<trip_id>')
def delete_item(item_id, trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    from firebase_service import delete_packing_item
    delete_packing_item(item_id)
    
    filter_user = request.args.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user))

if __name__ == '__main__':
    app.run(debug=True, port=5000)
