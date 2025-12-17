import os
import threading
import asyncio # <--- 1. Import asyncio

# <--- 2. FORCE FIX FOR PYTHON 3.10+ / 3.14 --->
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# Now continue with your normal imports
from flask import Flask, jsonify, request, Response, render_template, session, redirect, url_for
from pyrogram import Client, filters, idle
from pyromod import listen
from pymongo import MongoClient

# ===========================
# ⚙️ CONFIGURATION
# ===========================
# Replace these with your actual details or use Environment Variables
API_ID = int(os.environ.get("API_ID", "26233871"))
API_HASH = os.environ.get("API_HASH", "d1274875c02026a781bbc19d12daa8b6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8599650881:AAH8ntxRQo6EMoIC0ewl-VsgbeuDFjiDmd0")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://vabenix546_db_user:JiBKbhvSUF6RziWO@cluster0.hlq6wml.mongodb.net/?appName=Cluster0")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1003601579453")) # Your Private Storage Channel
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123") # Password for Website Admin Panel
SECRET_KEY = "super_secret_key_change_this" # For Flask Session Security

# ===========================
# 🗄️ DATABASE SETUP
# ===========================
mongo = MongoClient(MONGO_URL)
db = mongo['college_portal']
files_col = db['files']
options_col = db['options'] 
# Options Schema: { "type": "course", "name": "B.Tech", "parent": null }

# ===========================
# 🤖 BOT SETUP
# ===========================
bot = Client("server_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ===========================
# 🌐 FLASK APP SETUP
# ===========================
app = Flask(__name__)
app.secret_key = SECRET_KEY

# ---------------------------------------------------------
# 1. PUBLIC ROUTES (Website)
# ---------------------------------------------------------

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/public/options', methods=['GET'])
def get_public_options():
    """API for the Student Website to populate dropdowns"""
    data = {
        "categories": list(options_col.find({"type": "category"}, {'_id': 0})),
        "courses": list(options_col.find({"type": "course"}, {'_id': 0})),
        "semesters": list(options_col.find({"type": "semester"}, {'_id': 0})),
        "subjects": list(options_col.find({"type": "subject"}, {'_id': 0}))
    }
    return jsonify(data)

@app.route('/api/files', methods=['POST'])
def search_files():
    """Search for files based on filters"""
    filters = request.json
    query = {}
    for key, value in filters.items():
        if value and value != "":
            query[key] = value
            
    results = []
    for doc in files_col.find(query):
        doc['_id'] = str(doc['_id'])
        results.append(doc)
    return jsonify(results)

@app.route('/download/<file_id>')
def download_file(file_id):
    """Streams file from Telegram directly to User Browser"""
    async def stream_generator():
        try:
            async for chunk in bot.stream_media(file_id):
                yield chunk
        except Exception as e:
            print(f"Stream Error: {e}")

    file_doc = files_col.find_one({"file_id": file_id})
    filename = file_doc['name'] + ".pdf" if file_doc else "document.pdf"

    return Response(stream_generator(), headers={
        "Content-Disposition": f"attachment; filename={filename}",
        "Content-Type": "application/octet-stream"
    })

# ---------------------------------------------------------
# 2. ADMIN PANEL ROUTES
# ---------------------------------------------------------

@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('login.html', error="Wrong Password")
    return render_template('login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('logged_in'): return redirect(url_for('admin_login'))
    return render_template('admin.html')

@app.route('/api/admin/options', methods=['GET', 'POST', 'DELETE'])
def manage_options():
    """Add or Delete Dropdown Options"""
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401

    if request.method == 'GET':
        data = {
            "categories": list(options_col.find({"type": "category"}, {'_id': 0})),
            "courses": list(options_col.find({"type": "course"}, {'_id': 0})),
            "semesters": list(options_col.find({"type": "semester"}, {'_id': 0})),
            "subjects": list(options_col.find({"type": "subject"}, {'_id': 0}))
        }
        return jsonify(data)

    if request.method == 'POST':
        data = request.json
        # Format: { type: "subject", name: "Maths", parent: "B.Tech" }
        if not options_col.find_one({"type": data['type'], "name": data['name']}):
            options_col.insert_one(data)
        return jsonify({"status": "success"})

    if request.method == 'DELETE':
        data = request.json
        options_col.delete_one({"type": data['type'], "name": data['name']})
        return jsonify({"status": "deleted"})

# ---------------------------------------------------------
# 3. TELEGRAM BOT LOGIC (File Uploader)
# ---------------------------------------------------------

async def get_buttons(option_type, parent=None):
    """Helper to fetch DB options for Bot Buttons"""
    query = {"type": option_type}
    if parent:
        query["parent"] = parent 
    
    # If looking for subject but no parent specific found, get all global subjects
    options = list(options_col.find(query))
    if not options and option_type == 'subject':
        options = list(options_col.find({"type": "subject"}))

    buttons = []
    for doc in options:
        buttons.append([doc['name']])
    return buttons

@bot.on_message(filters.document & filters.private)
async def upload_handler(client, message):
    chat_id = message.chat.id
    
    try:
        # Step 1: Name
        ans = await client.ask(chat_id, "📝 **Enter File Name:**")
        name = ans.text

        # Step 2: Category
        btns = await get_buttons("category")
        if not btns: return await message.reply("❌ No Categories! Add in Admin Panel first.")
        ans = await client.ask(chat_id, "📂 **Select Category:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
        category = ans.text

        # Step 3: Course
        btns = await get_buttons("course")
        ans = await client.ask(chat_id, "🎓 **Select Course:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
        course = ans.text

        # Step 4: Semester
        btns = await get_buttons("semester")
        ans = await client.ask(chat_id, "⏳ **Select Semester:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
        semester = ans.text

        # Step 5: Subject (Filtered by Course)
        btns = await get_buttons("subject", parent=course)
        ans = await client.ask(chat_id, "📚 **Select Subject:**", reply_markup={'keyboard': btns, 'resize_keyboard': True, 'one_time_keyboard': True})
        subject = ans.text

        # Step 6: Save
        status_msg = await message.reply("☁️ Uploading to cloud...")
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
        await status_msg.edit_text(f"✅ **File Live!**\nName: {name}\nPath: {course} > {subject}")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")

# ---------------------------------------------------------
# 4. RUNNER
# ---------------------------------------------------------
def run_flask():
    # Get the PORT from Heroku environment, default to 8080 if not found
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Start Flask in a separate background thread (daemon=True means it closes when bot closes)
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Start the Bot
    bot.start()
    print("🚀 System Online! Bot is listening...")
    
    # idle() keeps the program running AND listening for messages
    # (Unlike time.sleep, which freezes the program)
    idle()
    
    # Stop correctly when Ctrl+C is pressed
    bot.stop()
