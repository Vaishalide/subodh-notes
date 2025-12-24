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
try:
    from drive_utils import upload_to_drive, get_storage_info
    from pdf_utils import add_watermark_page
except ImportError:
    print("⚠️ WARNING: drive_utils.py or pdf_utils.py not found! Drive upload will fail.")

# ===========================
# ⚙️ CONFIGURATION
# ===========================
API_ID = int(os.environ.get("API_ID", "26233871"))
API_HASH = os.environ.get("API_HASH", "d1274875c02026a781bbc19d12daa8b6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8411335287:AAFTEW7Ah_A_oDuL-14HraMHWZasS1-Acnw")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://vabenix546_db_user:JiBKbhvSUF6RziWO@cluster0.hlq6wml.mongodb.net/?appName=Cluster0")

CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1001819373091"))
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID", "") 
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
SECRET_KEY = "super_secret_key_change_this"
WEBSITE_LINK = "https://subodhnotes-10fc50a27a91.herokuapp.com" 

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

# --- SCRAPERS ---
@app.route('/api/syllabus', methods=['GET'])
def get_syllabus():
    s_type = request.args.get('type', 'UG')
    cache_key = f'syllabus_{s_type}'
    cached = get_cached_data(cache_key)
    if cached: return jsonify(cached)

    url = "https://www.subodhpgcollege.com/Syllabus_UG_Courses" if s_type == 'UG' else "https://www.subodhpgcollege.com/Syllabus_PG_Courses"
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        syllabus_list = []
        table = soup.find('table', class_='table')
        if not table: return jsonify([])
        rows = table.find_all('tr')
        current_section = "General"
        for row in rows:
            cols = row.find_all('td')
            if not cols: continue
            if len(cols) == 1 or (len(cols) > 0 and cols[0].get('colspan')):
                text = cols[0].get_text(strip=True)
                if text: current_section = text
                continue
            if len(cols) >= 3:
                name = cols[1].get_text(strip=True)
                link_tag = cols[2].find('a')
                if name and link_tag and link_tag.get('href'):
                    link = link_tag['href']
                    if not link.startswith('http'): link = "https://www.subodhpgcollege.com/" + link
                    syllabus_list.append({'section': current_section, 'name': name, 'link': link})
        set_cached_data(cache_key, syllabus_list)
        return jsonify(syllabus_list)
    except Exception as e:
        print(f"Syllabus Error: {e}")
        return jsonify([])

@app.route('/api/assignments', methods=['GET'])
def get_assignments():
    cached = get_cached_data('assignments')
    if cached: return jsonify(cached)
    try:
        url = "https://www.subodhpgcollege.com/assignments"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        assignments = []
        headings = soup.find_all('div', class_='heading_s1')
        for heading_div in headings:
            h4 = heading_div.find('h4')
            section_title = h4.get_text(strip=True) if h4 else "General Assignments"
            sibling = heading_div.find_next_sibling('div', class_='table-responsive')
            if sibling:
                rows = sibling.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        name = cols[0].get_text(strip=True)
                        link_tag = cols[1].find('a')
                        if name and link_tag and link_tag.get('href'):
                            link = link_tag['href']
                            if not link.startswith('http'): link = "https://www.subodhpgcollege.com/" + link
                            assignments.append({'section': section_title, 'name': name, 'link': link})
        set_cached_data('assignments', assignments)
        return jsonify(assignments)
    except Exception as e:
        print(f"Assignment Error: {e}")
        return jsonify([])

@app.route('/api/timetables', methods=['GET'])
def get_timetables():
    cached = get_cached_data('timetables')
    if cached: return jsonify(cached)
    try:
        url = "https://www.subodhpgcollege.com/Time-table"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        timetables = []
        tables = soup.find_all('table', class_='table')
        for table in tables:
            section_title = "Examination Time Table"
            prev_heading = table.find_previous('h3')
            if prev_heading: section_title = prev_heading.get_text(strip=True)
            rows = table.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                if len(cols) >= 3:
                    name = cols[0].get_text(strip=True)
                    sem_or_type = cols[1].get_text(strip=True)
                    link_tag = cols[2].find('a')
                    if link_tag and link_tag.get('href'):
                        link = link_tag['href']
                        if not link.startswith('http'): link = "https://www.subodhpgcollege.com/" + link
                        timetables.append({'section': section_title, 'name': f"{name} ({sem_or_type})", 'link': link})
        set_cached_data('timetables', timetables)
        return jsonify(timetables)
    except Exception as e:
        print(f"Time Table Error: {e}")
        return jsonify([])

@app.route('/api/notices', methods=['GET'])
def get_notices():
    cached = get_cached_data('notices')
    if cached: return jsonify(cached)
    try:
        url = "https://www.subodhpgcollege.com/notice_board"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        soup = BeautifulSoup(response.content, 'html.parser')
        notices = []
        items = soup.find_all('li', class_='comment_info')
        for item in items:
            content_div = item.find('div', class_='comment_content')
            text_p = content_div.find('p')
            title = text_p.get_text(strip=True) if text_p else "No Title"
            meta = content_div.find('div', class_='meta_data')
            date_text = "Unknown Date"
            links = []
            if meta:
                h6 = meta.find('h6')
                if h6:
                    full_meta = h6.get_text(strip=True)
                    if "Posted On :" in full_meta: date_text = full_meta.split("Posted On :")[-1].strip()
                    for a in h6.find_all('a'):
                        link_url = a['href']
                        if not link_url.startswith('http'): link_url = "https://www.subodhpgcollege.com/" + link_url
                        links.append({'text': a.get_text(strip=True), 'url': link_url})
            notices.append({'title': title, 'date': date_text, 'links': links})
        set_cached_data('notices', notices)
        return jsonify(notices)
    except Exception as e:
        print(f"Scraping Error: {e}")
        return jsonify([])

# --- DOWNLOAD ROUTE ---
@app.route('/download/<file_id>')
def download_file(file_id):
    file_doc = files_col.find_one({"file_id": file_id})
    if file_doc and 'drive_link' in file_doc:
        return redirect(file_doc['drive_link'])
    return "File is archived or not on Drive. Contact Admin."

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

@app.route('/api/admin/options', methods=['GET', 'POST', 'DELETE'])
def manage_options():
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
        data['name'] = data['name'].strip()
        query = {"type": data['type'], "name": data['name']}
        if data['type'] == 'subject':
            query['parent'] = data.get('parent')
            query['semester'] = data.get('semester')
        if not options_col.find_one(query): options_col.insert_one(data)
        return jsonify({"status": "success"})
    if request.method == 'DELETE':
        data = request.json
        options_col.delete_one({"type": data['type'], "name": data['name']})
        return jsonify({"status": "deleted"})

@app.route('/api/admin/files', methods=['GET', 'DELETE'])
def manage_files():
    if not session.get('logged_in'): return jsonify({"error": "Unauthorized"}), 401
    if request.method == 'GET':
        files = []
        for doc in files_col.find().sort('_id', -1).limit(50):
            doc['_id'] = str(doc['_id'])
            files.append(doc)
        return jsonify(files)
    if request.method == 'DELETE':
        data = request.json
        files_col.delete_one({"file_id": data.get('file_id')})
        return jsonify({"status": "deleted"})

# ===========================
# 🤖 BOT LOGIC
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
        status_msg = await message.reply("☁️ **Processing File...**", reply_markup=ReplyKeyboardRemove())
        
        try:
            # 1. Download
            await status_msg.edit_text("⬇️ **Downloading...**")
            file_path = await state["file_msg"].download()
            final_path = file_path
            
            # 2. Watermark
            if file_path.lower().endswith(".pdf"):
                try:
                    await status_msg.edit_text("🖼 **Adding Watermark...**")
                    output_path = "watermarked_" + os.path.basename(file_path)
                    await asyncio.to_thread(add_watermark_page, file_path, output_path, "NoteHub", WEBSITE_LINK)
                    final_path = output_path
                except Exception as wm_error:
                    print(f"Watermark Error (Skipping): {wm_error}")
            
            # 3. Drive Upload
            if not DRIVE_FOLDER_ID:
                await status_msg.edit_text("❌ Error: Drive Folder ID not configured!")
                return

            await status_msg.edit_text("🚀 **Uploading to Drive...**")
            file_id, drive_link = await asyncio.to_thread(upload_to_drive, final_path, state["data"]["name"], DRIVE_FOLDER_ID)
            
            # 4. Save DB
            file_data = {
                "name": state["data"]["name"],
                "category": state["data"]["category"],
                "course": state["data"]["course"],
                "semester": state["data"]["semester"],
                "subject": state["data"]["subject"],
                "file_id": file_id,
                "drive_link": drive_link 
            }
            files_col.insert_one(file_data)
            
            # 5. Cleanup
            if os.path.exists(file_path): os.remove(file_path)
            if os.path.exists(final_path) and final_path != file_path: os.remove(final_path)
            
            await status_msg.delete() 
            await message.reply(
                f"✅ **Uploaded Successfully!**\n\n"
                f"📄 {file_data['name']}\n"
                f"🔗 [Open in Drive]({drive_link})"
            )
            
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
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
    try:
        print(f"🔄 Caching Channel ID: {CHANNEL_ID}...")
        bot.loop.run_until_complete(bot.get_chat(CHANNEL_ID))
    except Exception as e: print(f"⚠️ Cache Warning: {e}")
    print("🚀 System Online!")
    idle()
    bot.stop()
