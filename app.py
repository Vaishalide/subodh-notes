import os
import threading
import asyncio
import io
import requests
import re
import time
import gzip
import shutil
from bs4 import BeautifulSoup
from queue import Queue 

# <--- FORCE FIX FOR PYTHON 3.14 EVENT LOOP --->
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from flask import Flask, jsonify, request, Response, render_template, session, redirect, url_for, send_file, after_this_request
from pyrogram import Client, filters, idle
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pymongo import MongoClient

# Custom Modules
from drive_utils import upload_to_drive, get_storage_info
from pdf_utils import add_watermark_page

# ===========================
# ⚙️ CONFIGURATION
# ===========================
API_ID = int(os.environ.get("API_ID", "26233871"))
API_HASH = os.environ.get("API_HASH", "d1274875c02026a781bbc19d12daa8b6"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8599650881:AAH8ntxRQo6EMoIC0ewl-VsgbeuDFjiDmd0"))
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://vabenix546_db_user:JiBKbhvSUF6RziWO@cluster0.hlq6wml.mongodb.net/?appName=Cluster0"))
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1001819373091"))
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "YOUR_GOOGLE_DRIVE_FOLDER_ID_HERE") # <--- ADD THIS TO ENV
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
SECRET_KEY = "super_secret_key_change_this"
WEBSITE_LINK = "https://your-app-url.herokuapp.com" # Change this to your actual URL

# ===========================
# 🗄️ DATABASE
# ===========================
mongo = MongoClient(MONGO_URL)
db = mongo['college_portal']
files_col = db['files']
options_col = db['options']

# ===========================
# 🚀 PERFORMANCE CACHE
# ===========================
CACHE_STORAGE = {} 
CACHE_TIMEOUT = 600 

def get_cached_data(key):
    if key in CACHE_STORAGE:
        data, timestamp = CACHE_STORAGE[key]
        if time.time() - timestamp < CACHE_TIMEOUT:
            return data
    return None

def set_cached_data(key, data):
    CACHE_STORAGE[key] = (data, time.time())

# ===========================
# 🤖 BOT STATE MANAGEMENT
# ===========================
bot = Client("server_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_states = {}

# ===========================
# 🌐 FLASK APP
# ===========================
app = Flask(__name__)
app.secret_key = SECRET_KEY

@app.after_request
def compress_response(response):
    if response.status_code != 200 or response.direct_passthrough: return response
    accept_encoding = request.headers.get('Accept-Encoding', '')
    if 'gzip' not in accept_encoding.lower(): return response
    content = response.data
    response.data = gzip.compress(content)
    response.headers['Content-Encoding'] = 'gzip'
    response.headers['Content-Length'] = len(response.data)
    response.headers['Vary'] = 'Accept-Encoding'
    return response

# --- PUBLIC ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/public/options', methods=['GET'])
def get_public_options():
    cached = get_cached_data('db_options')
    if cached: return jsonify(cached)
    data = {
        "categories": list(options_col.find({"type": "category"}, {'_id': 0})),
        "courses": list(options_col.find({"type": "course"}, {'_id': 0})),
        "semesters": list(options_col.find({"type": "semester"}, {'_id': 0})),
        "subjects": list(options_col.find({"type": "subject"}, {'_id': 0}))
    }
    set_cached_data('db_options', data)
    return jsonify(data)

@app.route('/api/files', methods=['POST'])
def search_files():
    filters = request.json
    query = {}
    for key, value in filters.items():
        if value and value != "":
            safe_val = re.escape(value.strip())
            query[key] = {"$regex": f"^{safe_val}$", "$options": "i"}
    results = []
    for doc in files_col.find(query):
        doc['_id'] = str(doc['_id'])
        results.append(doc)
    return jsonify(results)

# --- SCRAPERS (Keep your existing scraper code here) ---
# ... (Paste your syllabus, assignments, timetable, notices scrapers here exactly as before) ...
# I am omitting them to save space, but DO NOT DELETE THEM from your file.
@app.route('/api/syllabus', methods=['GET'])
def get_syllabus():
    # ... (Keep existing code) ...
    return jsonify([]) 

@app.route('/api/assignments', methods=['GET'])
def get_assignments():
    # ... (Keep existing code) ...
    return jsonify([])

@app.route('/api/timetables', methods=['GET'])
def get_timetables():
    # ... (Keep existing code) ...
    return jsonify([])

@app.route('/api/notices', methods=['GET'])
def get_notices():
    # ... (Keep existing code) ...
    return jsonify([])

# --- 🚀 NEW DOWNLOAD ROUTE (Redirect to Drive) ---
@app.route('/download/<file_id>')
def download_file(file_id):
    # Retrieve the Google Drive Link from DB
    file_doc = files_col.find_one({"file_id": file_id})
    
    if file_doc and 'drive_link' in file_doc:
        # Redirect user directly to Google Drive (Zero server load)
        return redirect(file_doc['drive_link'])
    
    # Fallback for old files (Telegram Streaming)
    return "This file is on old storage. Please contact admin to migrate."

# --- ADMIN ROUTES ---
@app.route('/admin', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        return render_template('login.html', error="Wrong Password")
    return render_template('login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('logged_in'): return redirect(url_for('admin_login'))
    return render_template('admin.html')

# ... (Keep manage_options and manage_files routes same as before) ...
@app.route('/api/admin/options', methods=['GET', 'POST', 'DELETE'])
def manage_options():
    # ... (Keep existing code) ...
    return jsonify({})

@app.route('/api/admin/files', methods=['GET', 'DELETE'])
def manage_files():
    # ... (Keep existing code) ...
    return jsonify({})

# ===========================
# 🤖 BOT LOGIC (UPDATED FOR DRIVE)
# ===========================
async def get_keyboard(option_type, parent=None, semester=None):
    query = {"type": option_type}
    if parent: query["parent"] = parent
    if semester: query["semester"] = semester
    options = list(options_col.find(query))
    if not options: return None
    buttons = []
    row = []
    for doc in options:
        row.append(doc['name'])
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row: buttons.append(row)
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

@bot.on_message(filters.document & filters.private)
async def start_upload(client, message):
    user_id = message.from_user.id
    user_states[user_id] = {"step": "ASK_NAME", "file_msg": message, "data": {}}
    await message.reply("📝 **Enter a Name for this file:**", reply_markup=ReplyKeyboardRemove())

@bot.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    if user_id not in user_states: return
    state = user_states[user_id]
    step = state["step"]
    text = message.text.strip()

    if step == "ASK_NAME":
        state["data"]["name"] = text
        kb = await get_keyboard("category")
        if not kb: return await message.reply("❌ No Categories found!")
        state["step"] = "ASK_CAT"
        await message.reply("📂 **Select Category:**", reply_markup=kb)

    elif step == "ASK_CAT":
        state["data"]["category"] = text
        kb = await get_keyboard("course")
        if not kb: return await message.reply("❌ No Courses found!")
        state["step"] = "ASK_COURSE"
        await message.reply("🎓 **Select Course:**", reply_markup=kb)

    elif step == "ASK_COURSE":
        state["data"]["course"] = text
        kb = await get_keyboard("semester")
        if not kb: return await message.reply("❌ No Semesters found!")
        state["step"] = "ASK_SEM"
        await message.reply("⏳ **Select Semester:**", reply_markup=kb)

    elif step == "ASK_SEM":
        state["data"]["semester"] = text
        course = state["data"]["course"]
        kb = await get_keyboard("subject", parent=course, semester=text)
        if not kb: kb = await get_keyboard("subject", parent=course)
        if not kb: kb = await get_keyboard("subject")
        if not kb: return await message.reply("❌ No Subjects found!")
        state["step"] = "ASK_SUB"
        await message.reply("📚 **Select Subject:**", reply_markup=kb)

    elif step == "ASK_SUB":
        state["data"]["subject"] = text
        status_msg = await message.reply("☁️ **Downloading & Processing...**", reply_markup=ReplyKeyboardRemove())
        
        try:
            # 1. Download from Telegram
            file_path = await state["file_msg"].download()
            final_path = file_path
            
            # 2. Add Watermark if PDF
            if file_path.lower().endswith(".pdf"):
                await status_msg.edit_text("🖼 **Adding Watermark...**")
                output_path = "watermarked_" + os.path.basename(file_path)
                # Run PDF processing in a separate thread to not block bot
                await asyncio.to_thread(add_watermark_page, file_path, output_path, "NoteHub", WEBSITE_LINK)
                final_path = output_path
            
            # 3. Upload to Google Drive
            await status_msg.edit_text("🚀 **Uploading to Google Drive...**")
            
            # Run upload in thread
            file_id, drive_link = await asyncio.to_thread(upload_to_drive, final_path, state["data"]["name"], DRIVE_FOLDER_ID)
            
            # 4. Save to Database
            file_data = {
                "name": state["data"]["name"],
                "category": state["data"]["category"],
                "course": state["data"]["course"],
                "semester": state["data"]["semester"],
                "subject": state["data"]["subject"],
                "file_id": file_id,   # Google Drive File ID
                "drive_link": drive_link # Direct Link
            }
            files_col.insert_one(file_data)
            
            # 5. Cleanup & Check Space
            if os.path.exists(file_path): os.remove(file_path)
            if os.path.exists(final_path) and final_path != file_path: os.remove(final_path)
            
            space_info = await asyncio.to_thread(get_storage_info)
            
            await status_msg.delete() 
            await message.reply(
                f"✅ **File Published!**\n\n"
                f"📄 {file_data['name']}\n"
                f"🔗 Drive: [Open Link]({drive_link})\n"
                f"💾 Storage: {space_info}"
            )
            
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
            # Cleanup on error
            if 'file_path' in locals() and os.path.exists(file_path): os.remove(file_path)
        
        del user_states[user_id]

# ===========================
# 4. RUNNER
# ===========================
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask, daemon=True).start()
    print("🤖 Starting Bot...")
    bot.start()
    print("🚀 System Online!")
    idle()
    bot.stop()
