import os
import threading
from flask import Flask, jsonify, request, Response, render_template, session, redirect, url_for
from pyrogram import Client, filters
from pyromod import listen
from pymongo import MongoClient
from bson.objectid import ObjectId

# --- CONFIGURATION ---
API_ID = int(os.environ.get("API_ID", "12345"))
API_HASH = os.environ.get("API_HASH", "your_hash")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "your_bot_token")
MONGO_URL = os.environ.get("MONGO_URL", "your_mongo_url")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-100xxxx"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123") # Password for /admin
SECRET_KEY = "supersecretkey" # For session security

# --- DATABASE ---
mongo = MongoClient(MONGO_URL)
db = mongo['college_portal']
files_col = db['files']
# Options Collection Structure: { "type": "course", "name": "B.Tech", "parent": null }
options_col = db['options'] 

# --- FLASK APP ---
app = Flask(__name__)
app.secret_key = SECRET_KEY

# --- PYROGRAM BOT ---
bot = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===========================
# 🔐 ADMIN PANEL ROUTES
# ===========================

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return "Wrong Password!", 403
    return render_template('login.html') # Simple HTML form for password

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('logged_in'):
        return redirect(url_for('admin_login'))
    return render_template('admin.html')

# --- ADMIN API: ADD/DELETE OPTIONS ---

@app.route('/api/admin/options', methods=['GET', 'POST', 'DELETE'])
def manage_options():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'GET':
        # Fetch all options organized by type
        data = {
            "categories": list(options_col.find({"type": "category"}, {'_id': 0})),
            "courses": list(options_col.find({"type": "course"}, {'_id': 0})),
            "semesters": list(options_col.find({"type": "semester"}, {'_id': 0})),
            "subjects": list(options_col.find({"type": "subject"}, {'_id': 0}))
        }
        return jsonify(data)

    if request.method == 'POST':
        # Add new Option
        data = request.json
        # data format: { type: "subject", name: "Java", parent: "B.Tech" }
        options_col.insert_one(data)
        return jsonify({"status": "success"})

    if request.method == 'DELETE':
        # Delete Option
        data = request.json
        options_col.delete_one({"type": data['type'], "name": data['name']})
        return jsonify({"status": "deleted"})

# ===========================
# 🤖 BOT LOGIC (Upload Flow)
# ===========================

async def get_buttons(option_type, parent=None):
    """Helper to get buttons dynamically from DB"""
    query = {"type": option_type}
    if parent:
        query["parent"] = parent 
    
    options = options_col.find(query)
    buttons = []
    for doc in options:
        buttons.append([doc['name']]) # List of lists for Pyrogram Keyboard
    return buttons

@bot.on_message(filters.document & filters.private)
async def upload_handler(client, message):
    chat_id = message.chat.id
    
    # 1. Ask Name
    ans = await client.ask(chat_id, "📝 **Enter File Name:**")
    name = ans.text

    # 2. Select Category (Notes/PYQ)
    btns = await get_buttons("category")
    if not btns: return await message.reply("❌ No Categories found! Add in Admin Panel.")
    ans = await client.ask(chat_id, "📂 **Select Category:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
    category = ans.text

    # 3. Select Course
    btns = await get_buttons("course")
    if not btns: return await message.reply("❌ No Courses found! Add in Admin Panel.")
    ans = await client.ask(chat_id, "🎓 **Select Course:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
    course = ans.text

    # 4. Select Semester
    btns = await get_buttons("semester")
    ans = await client.ask(chat_id, "⏳ **Select Semester:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
    semester = ans.text

    # 5. Select Subject (Filtered by Course if needed, logic can be added here)
    # For now, we show all subjects linked to this course
    btns = await get_buttons("subject", parent=course) 
    # If no specific subjects for this course, fetch all global subjects
    if not btns: btns = await get_buttons("subject") 
    
    ans = await client.ask(chat_id, "📚 **Select Subject:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
    subject = ans.text

    # 6. Save
    sent_msg = await message.copy(CHANNEL_ID)
    file_data = {
        "name": name,
        "category": category,
        "course": course,
        "semester": semester,
        "subject": subject,
        "file_id": sent_msg.document.file_id,
        "msg_link": sent_msg.link
    }
    files_col.insert_one(file_data)
    await message.reply(f"✅ **Saved!**\n{name} added to {course} > {subject}")

# ===========================
# 🌐 PUBLIC API & RUNNER
# ===========================
# (Include the same /api/files and /download routes from previous response here)
# ... [Keeping previous download logic] ...

@app.route('/')
def home():
    return render_template('index.html')

def run_flask():
    app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    bot.start()
    # Keep main thread alive
    import time
    while True: time.sleep(10)
