import os
import threading
import asyncio
import io

# <--- FORCE FIX FOR PYTHON 3.14 EVENT LOOP --->
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

from flask import Flask, jsonify, request, Response, render_template, session, redirect, url_for, send_file
from pyrogram import Client, filters, idle
from pyrogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove
from pymongo import MongoClient

# ===========================
# ⚙️ CONFIGURATION
# ===========================
API_ID = int(os.environ.get("API_ID", "26233871"))
API_HASH = os.environ.get("API_HASH", "d1274875c02026a781bbc19d12daa8b6")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8599650881:AAH8ntxRQo6EMoIC0ewl-VsgbeuDFjiDmd0")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb+srv://vabenix546_db_user:JiBKbhvSUF6RziWO@cluster0.hlq6wml.mongodb.net/?appName=Cluster0")
CHANNEL_ID = int(os.environ.get("CHANNEL_ID", "-1001819373091"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
SECRET_KEY = "super_secret_key_change_this"

# ===========================
# 🗄️ DATABASE
# ===========================
mongo = MongoClient(MONGO_URL)
db = mongo['college_portal']
files_col = db['files']
options_col = db['options']

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

# --- PUBLIC ROUTES ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/public/options', methods=['GET'])
def get_public_options():
    data = {
        "categories": list(options_col.find({"type": "category"}, {'_id': 0})),
        "courses": list(options_col.find({"type": "course"}, {'_id': 0})),
        "semesters": list(options_col.find({"type": "semester"}, {'_id': 0})),
        "subjects": list(options_col.find({"type": "subject"}, {'_id': 0}))
    }
    return jsonify(data)

@app.route('/api/files', methods=['POST'])
def search_files():
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

# --- 🚀 FIXED DOWNLOAD ROUTE ---
@app.route('/download/<file_id>')
def download_file(file_id):
    # 1. Get File Info
    file_doc = files_col.find_one({"file_id": file_id})
    filename = file_doc['name'] if file_doc else "document"
    if not filename.lower().endswith(('.pdf', '.jpg', '.png', '.doc', '.docx')):
        filename += ".pdf"

    # 2. Define Download Helper (Runs on Bot Loop)
    async def download_task():
        # Downloads file to RAM (BytesIO object)
        return await bot.download_media(file_id, in_memory=True)

    try:
        # 3. Check Connection
        if not bot.is_connected:
            return "Bot is starting up... please wait.", 503

        # 4. Run Download
        # This runs the async download in the Bot thread and waits for it here
        future = asyncio.run_coroutine_threadsafe(download_task(), bot.loop)
        memory_file = future.result() # Blocks until download is done
        
        # 5. CRITICAL FIX: Reset pointer to start of file
        memory_file.seek(0)
        
        # 6. Send to User
        return send_file(
            memory_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/octet-stream'
        )
    except Exception as e:
        return f"Download Error: {str(e)}", 500

# --- ADMIN ROUTES ---
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
        query = {"type": data['type'], "name": data['name']}
        if data['type'] == 'subject':
            query['parent'] = data.get('parent')
            query['semester'] = data.get('semester')

        if not options_col.find_one(query):
            options_col.insert_one(data)
        return jsonify({"status": "success"})

    if request.method == 'DELETE':
        data = request.json
        options_col.delete_one({"type": data['type'], "name": data['name']})
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
    user_states[user_id] = {
        "step": "ASK_NAME",
        "file_msg": message,
        "data": {}
    }
    await message.reply("📝 **Enter a Name for this file:**", reply_markup=ReplyKeyboardRemove())

@bot.on_message(filters.text & filters.private)
async def handle_text(client, message):
    user_id = message.from_user.id
    if user_id not in user_states: return
    
    state = user_states[user_id]
    step = state["step"]
    text = message.text

    if step == "ASK_NAME":
        state["data"]["name"] = text
        kb = await get_keyboard("category")
        if not kb: return await message.reply("❌ No Categories found! Add in Admin Panel.")
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

        if not kb: return await message.reply("❌ No Subjects found for this combination!")
        state["step"] = "ASK_SUB"
        await message.reply("📚 **Select Subject:**", reply_markup=kb)

    elif step == "ASK_SUB":
        state["data"]["subject"] = text
        
        status_msg = await message.reply("☁️ Uploading...", reply_markup=ReplyKeyboardRemove())
        
        try:
            original_msg = state["file_msg"]
            saved_msg = await original_msg.copy(CHANNEL_ID)
            
            file_data = {
                "name": state["data"]["name"],
                "category": state["data"]["category"],
                "course": state["data"]["course"],
                "semester": state["data"]["semester"],
                "subject": state["data"]["subject"],
                "file_id": saved_msg.document.file_id,
                "msg_link": saved_msg.link
            }
            files_col.insert_one(file_data)
            
            await status_msg.delete() 
            await message.reply(
                f"✅ **Saved Successfully!**\n\n"
                f"📄 {file_data['name']}\n"
                f"🎓 {file_data['course']} > {file_data['semester']}\n"
                f"📚 {file_data['subject']}"
            )
            
        except Exception as e:
            await message.reply(f"❌ Error: {e}")
        
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
        print("✅ Channel Cached Successfully!")
    except Exception as e:
        print(f"⚠️ Cache Warning (Check if Bot is Admin): {e}")

    print("🚀 System Online! Bot is listening...")
    idle()
    bot.stop()
