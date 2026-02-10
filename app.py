from flask import Flask, render_template, redirect, url_for, session, request, flash
from authlib.integrations.flask_client import OAuth
from firebase_service import initialize_firebase, get_all_trips, add_trip, delete_trip, update_user_trip_note, delete_user_trip_note, get_upcoming_trips_for_notifications, update_trip_notification_status, log_notification
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'supersecretkey')

# Firebase Setup
firebase_app = initialize_firebase()

# Initialize Gemini Client (New SDK)
from google import genai
client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

# OAuth Setup
oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile https://www.googleapis.com/auth/calendar.events'},
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
    session['token'] = token
    resp = google.get('https://www.googleapis.com/oauth2/v3/userinfo')
    user_info = resp.json()
    session['user'] = user_info
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
    
    from firebase_service import get_trip, get_packing_items
    
    trip = get_trip(trip_id)
    if not trip:
        return redirect(url_for('home'))
        
    items = get_packing_items(trip_id)
    
    contributors = set()
    for item in items:
        if item.get('added_by_name'):
            contributors.add(item.get('added_by_name'))
    sorted_contributors = sorted(list(contributors))
    
    filter_user = request.args.get('filter_user')
    if filter_user:
        items = [i for i in items if i.get('added_by_name') == filter_user]
    
    grouped_items = {}
    for item in items:
        cat = item.get('category', 'General')
        if cat not in grouped_items:
            grouped_items[cat] = []
        grouped_items[cat].append(item)
        
    available_categories = trip.get('categories', [])
    for cat in grouped_items.keys():
        if cat not in available_categories:
            available_categories.append(cat)
            
    sorted_categories = sorted(available_categories)
    
    from firebase_service import get_user_trip_note
    private_note = get_user_trip_note(trip_id, user.get('sub'))
    
    return render_template('trip_detail.html', user=user, trip=trip, grouped_items=grouped_items, sorted_categories=sorted_categories, contributors=sorted_contributors, active_filter=filter_user, private_note=private_note)

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

@app.route('/trip/<trip_id>/save_note', methods=['POST'])
def save_note_route(trip_id):
    user = session.get('user')
    if not user:
        return redirect(url_for('index'))
        
    content = request.form.get('content')
    
    from firebase_service import save_user_trip_note
    save_user_trip_note(trip_id, user.get('sub'), content)
    
    filter_user = request.form.get('filter_user')
    return redirect(url_for('trip_detail', trip_id=trip_id, filter_user=filter_user, active_tab='notes'))

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

@app.route('/trip/<trip_id>/add_reminder', methods=['POST'])
def add_reminder_route(trip_id):
    user = session.get('user')
    token = session.get('token')
    if not user or not token:
        return redirect(url_for('index'))
        
    summary = request.form.get('summary')
    date_str = request.form.get('date') # datetime-local
    
    # Fetch items to list unchecked ones
    from firebase_service import get_packing_items
    items = get_packing_items(trip_id)
    user_email = user.get('email')
    unchecked_items = [i.get('text') for i in items if not i.get('is_completed') and i.get('added_by_email') == user_email]
    
    description = f"Trip Reminder for {summary}\n\n"
    if unchecked_items:
        description += "Unchecked Items:\n" + "\n".join([f"- {item}" for item in unchecked_items])
    else:
        description += "All items packed!"
        
    description += "\n\nAccess your list here: https://travel-pack-six.vercel.app"
    
    if summary and date_str:
        from calendar_service import create_calendar_event
        link = create_calendar_event(token, summary, description, date_str)
        if link:
            flash(f'Reminder sent to {user.get("email")}', 'success')
        else:
            flash('Failed to add reminder. Please check permissions.', 'danger')
            
    filter_user = request.form.get('filter_user')
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

@app.route('/trip/<trip_id>/chat', methods=['POST'])
def chat_route(trip_id):
    user = session.get('user')
    if not user:
        return {'error': 'Unauthorized'}, 401
        
    data = request.get_json()
    message = data.get('message')
    
    # Chat History Management
    history_key = f'chat_history_{trip_id}'
    history = session.get(history_key, [])
    
    # Add user message to history
    history.append({'role': 'user', 'parts': [message]})
    
    # Keep history manageable (last 10 turns)
    if len(history) > 20:
        history = history[-20:]
    
    from firebase_service import get_packing_items
    items = get_packing_items(trip_id)
    items_text = ", ".join([f"{i.get('text')} ({i.get('category')})" for i in items])
    
    # Construct prompt with context
    system_instruction = f"""
    You are a helpful travel assistant for a packing list app.
    Current Packing List: {items_text}
    
    If the user wants to add items, suggest them.
    If the user wants to remove items, use the 'delete' action.
    
    Return a valid JSON object (no markdown formatting) with these fields:
    - reply: A friendly text response.
    - actions: A list of objects.
      - Add: {{ "type": "add", "item": "Name", "category": "Category", "note": "Optional reason" }}
      - Delete: {{ "type": "delete", "item": "Name" }}
    
    If no items to add/modify, 'actions' should be empty.
    Keep the reply concise.
    """
    
    # For this simple implementation with the new SDK, we can pass history in contents 
    # but strictly structured chat with system instruction is better.
    # The new SDK supports system_instruction argument in models.generate_content? 
    # Yes, typically via config or 'system_instruction' param if using 1.5/pro models.
    # However, 'gemini-2.5-flash' might just take it as part of the prompt.
    # Let's verify if we can pass history simply.
    
    # We will construct a "chat-like" prompt manually for simplicity and robustness with JSON mode
    full_prompt = system_instruction + "\n\nChat History:\n"
    for msg in history:
        role = "User" if msg['role'] == 'user' else "Model"
        content = msg['parts'][0]
        full_prompt += f"{role}: {content}\n"
        
    full_prompt += f"User: {message}\nModel:"
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=full_prompt
        )
        text = response.text.replace('```json', '').replace('```', '').strip()
        import json
        result = json.loads(text)
        
        # Add model response to history
        history.append({'role': 'model', 'parts': [result.get('reply', '')]})
        session[history_key] = history
        
        return result
    except Exception as e:
        print(f"Gemini Error: {e}")
        return {'reply': "Sorry, I'm having trouble thinking right now.", 'actions': []}

@app.route('/trip/<trip_id>/chat/confirm', methods=['POST'])
def chat_confirm_route(trip_id):
    user = session.get('user')
    if not user:
        return {'error': 'Unauthorized'}, 401
        
    data = request.get_json()
    actions = data.get('actions', [])
    
    from firebase_service import add_packing_item, delete_packing_item_by_text
    count = 0
    for action in actions:
        if action.get('type') == 'add':
            add_packing_item(trip_id, action.get('item'), action.get('category', 'General'), 
                           added_by_email=user.get('email'), added_by_name=user.get('name', 'AI Assistant'), 
                           note=action.get('note'))
            count += 1
        elif action.get('type') == 'delete':
            delete_packing_item_by_text(trip_id, action.get('item'))
            count += 1
            
    return {'status': 'success', 'count': count}

@app.route('/trip/<trip_id>/note/<note_id>/update', methods=['POST'])
def update_private_note_route(trip_id, note_id):
    user = session.get('user')
    if not user:
        return {'error': 'Unauthorized'}, 401
    
    data = request.get_json()
    new_content = data.get('note')
    
    if update_user_trip_note(trip_id, user.get('sub'), note_id, new_content):
        return {'status': 'success'}
    return {'error': 'Failed to update'}, 500

@app.route('/trip/<trip_id>/note/<note_id>/delete', methods=['DELETE'])
def delete_private_note_route(trip_id, note_id):
    user = session.get('user')
    if not user:
        return {'error': 'Unauthorized'}, 401
        
    if delete_user_trip_note(trip_id, user.get('sub'), note_id):
        return {'status': 'success'}
    return {'error': 'Failed to delete'}, 500

# Cron Job for Notifications
@app.route('/api/cron/reminders')
def cron_reminders():
    """
    Triggered by Vercel Cron.
    Checks upcoming trips and logic for frequency.
    """
    trips = get_upcoming_trips_for_notifications()
    count = 0
    
    from datetime import datetime
    now = datetime.now()
    
    for trip in trips:
        start_date_str = trip.get('start_date')
        if not start_date_str:
            continue
            
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            delta = start_date - now
            days_diff = delta.days
            
            should_send = False
            last_sent = trip.get('last_notification_sent')
            
            hours_since_last = 9999
            if last_sent:
                last_sent_dt = last_sent.replace(tzinfo=None) # naive comparison
                hours_since_last = (now - last_sent_dt).total_seconds() / 3600
                
            if 3 <= days_diff <= 4:
                if hours_since_last >= 24:
                    should_send = True
            elif days_diff == 2:
                if hours_since_last >= 12:
                    should_send = True
            elif days_diff <= 1 and days_diff >= 0:
                if hours_since_last >= 4:
                    should_send = True
            
            if should_send:
                owner_email = trip.get('owner_email')
                if owner_email:
                    print(f"SENDING NOTIFICATION TO {owner_email} for trip {trip.get('name')}")
                    log_notification(trip['id'], owner_email, 'reminder')
                    update_trip_notification_status(trip['id'], now)
                    count += 1
                    
        except ValueError:
            continue
            
    return {'status': 'success', 'processed': len(trips), 'sent': count}



# Cron Job for Notifications


if __name__ == '__main__':
    app.run(debug=True, port=5000)
