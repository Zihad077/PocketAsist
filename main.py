import asyncio
import logging
import time
import base64
import io
import httpx
import qrcode
import fitz  # PyMuPDF
from typing import Optional
from urllib.parse import quote
from collections import defaultdict
from datetime import datetime
from duckduckgo_search import DDGS

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ChatAction, ParseMode
from telegram.error import RetryAfter, BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

from groq import AsyncGroq

#                  CONFIG
BOT_NAME           = "Pocket Assist"
CREATOR            = "@Zihad0770"
TELEGRAM_BOT_TOKEN = "8552107107:AAGHJeOr7t6ZbXuS1KTvN73mhJ4T40E5jPI"
GROQ_API_KEY       = "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"
ADMIN_IDS          = [7051391305]

TEXT_MODEL   = "llama-3.3-70b-versatile"
VISION_MODEL = "llama-3.2-11b-vision-preview"
STT_MODEL    = "whisper-large-v3-turbo"

STREAM_EDIT_DELAY = 1.2
MAINTENANCE_MODE  = False

#                  LOGGING
logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

#                  CLIENTS / STATE
client         = AsyncGroq(api_key=GROQ_API_KEY)
user_db        = {}
banned_users   = set()
user_locks     = defaultdict(asyncio.Lock)
bot_start_time = datetime.now()

#                  TEXTS
TEXTS = {
    "bn": {
        "welcome": (
            "👋 আসসালামু আলাইকুম!\n\n"
            f"আমি <b>{BOT_NAME}</b>। আমাকে তৈরি করেছেন {CREATOR}।\n\n"
            "📌 শুরু করতে ভাষা নির্বাচন করুন:"
        ),
        "main_menu": "🏠 প্রধান মেনু\nনিচের অপশনগুলো ব্যবহার করে কাজ শুরু করুন:",
        "tools_menu": (
            "🛠 স্মার্ট টুলবক্স\n"
            "এখানে শুধুমাত্র সেই টুলস আছে যেগুলো চ্যাট দিয়ে পাওয়া সম্ভব না:"
        ),
        "persona_menu": "🎭 এআই ব্যক্তিত্ব\nবট আপনার সাথে কীভাবে কথা বলবে তা বেছে নিন:",
        "thinking":   "🤔 প্রসেসিং",
        "reset_done": "🔄 সব ইতিহাস মুছে ফেলা হয়েছে।",
        "lang_set":   "✅ ভাষা বাংলায় সেট করা হয়েছে!",
        "banned":     "🚫 আপনাকে এই বট থেকে বাদ দেওয়া হয়েছে।",
        "btn_tools":       "🛠 টুলস",
        "btn_profile":     "👤 প্রোফাইল",
        "btn_lang":        "🌐 ভাষা",
        "btn_reset":       "🔄 রিসেট",
        "btn_admin":       "👑 এডমিন প্যানেল",
        "btn_back":        "⬅️ ফিরে যান",
        "btn_image":       "🎨 ছবি তৈরি",
        "btn_weather":     "🌥 আবহাওয়া",
        "btn_search":      "🔍 সার্চ",
        "btn_qr":          "🔗 QR কোড",
        "btn_persona":     "🎭 পারসোনা",
        "ask_city":   "🌍 কোন শহরের আবহাওয়া দেখতে চান? শহরের নাম লিখুন:",
        "ask_qr":     "🔗 আপনি কিসের QR কোড বানাতে চান? লিঙ্ক বা টেক্সট দিন:",
        "ask_img":    "🎨 আপনি কেমন ছবি চান তার বর্ণনা দিন (ইংরেজিতে ভালো হয়):",
        "ask_search": "🔍 কী খুঁজতে চান?",
        "maintenance":       "🚧 বটটি এখন রক্ষণাবেক্ষণে আছে। পরে চেষ্টা করুন।",
        "maintenance_media": "🚧 বট রক্ষণাবেক্ষণে আছে। ছবি/ডকুমেন্ট এখন গ্রহণ করা যাচ্ছে না।",
        "ai_error":          "❌ এআই রেসপন্স জেনারেট করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।",
        "voice_processing":  "🎙️ ভয়েস প্রসেস করা হচ্ছে...",
        "voice_error":       "❌ ভয়েস মেসেজ প্রসেস করতে সমস্যা হয়েছে।",
        "weather_error":     "❌ আবহাওয়ার তথ্য পাওয়া যায়নি। শহরের নাম ঠিকঠাক লিখুন।",
        "img_error":         "❌ ছবি তৈরি করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।",
        "sys_chat":   f"Your name is {BOT_NAME} by {CREATOR}. Reply concisely in Bengali.",
        "sys_pdf":    "You are a document analyzer. Summarize the document accurately in Bengali.",
        "sys_search": "Using the provided search results, give a clear, accurate summary in Bengali. Cite the key points.",
        "help_text": (
            f"ℹ️ <b>{BOT_NAME} — সাহায্য</b>\n\n"
            "🛠 <b>বিশেষ টুলস:</b>\n"
            "• 🎨 ছবি তৈরি — এআই দিয়ে ছবি বানান\n"
            "• 🌥 আবহাওয়া — যেকোনো শহরের আবহাওয়া\n"
            "• 🔍 সার্চ — ইন্টারনেট থেকে তথ্য খোঁজুন\n"
            "• 🔗 QR কোড — যেকোনো লিঙ্ক/টেক্সটের QR\n\n"
            "📷 <b>ছবি পাঠান</b> — এআই বিশ্লেষণ করবে\n"
            "🎙️ <b>ভয়েস পাঠান</b> — এআই উত্তর দেবে\n"
            "📄 <b>PDF/TXT পাঠান</b> — সারাংশ পাবেন\n"
            "💬 <b>যেকোনো প্রশ্ন</b> — সরাসরি টাইপ করুন!\n\n"
            "⚙️ <b>কমান্ড:</b>\n"
            "/start — বট শুরু করুন\n"
            "/help — এই সাহায্য দেখুন"
        ),
    },
    "en": {
        "welcome": (
            "👋 <b>Welcome!</b>\n\n"
            f"I am <b>{BOT_NAME}</b> by {CREATOR}.\n\n"
            "📌 <b>Choose your language to begin:</b>"
        ),
        "main_menu":    "🏠 <b>Main Menu</b>\nSelect an option to proceed:",
        "tools_menu":   "🛠 <b>Smart Toolbox</b>\nOnly tools that can't be done by chatting:",
        "persona_menu": "🎭 <b>AI Persona</b>\nChoose how the bot should behave:",
        "thinking":     "🤔 Processing",
        "reset_done":   "🔄 Memory cleared successfully.",
        "lang_set":     "✅ Language set to English!",
        "banned":       "🚫 You have been banned from this bot.",
        "btn_tools":       "🛠 Tools",
        "btn_profile":     "👤 Profile",
        "btn_lang":        "🌐 Language",
        "btn_reset":       "🔄 Reset",
        "btn_admin":       "👑 Admin Panel",
        "btn_back":        "⬅️ Back",
        "btn_image":       "🎨 Image Gen",
        "btn_weather":     "🌥 Weather",
        "btn_search":      "🔍 Search",
        "btn_qr":          "🔗 QR Code",
        "btn_persona":     "🎭 Persona",
        "ask_city":   "🌍 Which city's weather do you want? Enter city name:",
        "ask_qr":     "🔗 Send the link or text for QR code generation:",
        "ask_img":    "🎨 Describe the image you want to generate:",
        "ask_search": "🔍 What do you want to search for?",
        "maintenance":       "🚧 Bot is currently under maintenance. Please try again later.",
        "maintenance_media": "🚧 Bot is under maintenance. Images/documents not accepted right now.",
        "ai_error":          "❌ Failed to generate AI response. Please try again.",
        "voice_processing":  "🎙️ Processing your voice message...",
        "voice_error":       "❌ Failed to process voice message. Please try again.",
        "weather_error":     "❌ Could not fetch weather. Please check the city name.",
        "img_error":         "❌ Image generation failed. Please try again.",
        "sys_chat":   f"You are {BOT_NAME} by {CREATOR}. Short & helpful. Reply in English.",
        "sys_pdf":    "Summarize the document accurately in English.",
        "sys_search": "Using the provided search results, give a clear, accurate summary in English. Cite the key points.",
        "help_text": (
            f"ℹ️ <b>{BOT_NAME} — Help</b>\n\n"
            "🛠 <b>Special Tools:</b>\n"
            "• 🎨 Image Gen — Create images with AI\n"
            "• 🌥 Weather — Real weather for any city\n"
            "• 🔍 Search — Search the web for info\n"
            "• 🔗 QR Code — Generate QR for any link/text\n\n"
            "📷 <b>Send a photo</b> — AI will analyze it\n"
            "🎙️ <b>Send a voice note</b> — AI will respond\n"
            "📄 <b>Send PDF/TXT</b> — Get a summary\n"
            "💬 <b>Ask anything</b> — Just type it!\n\n"
            "⚙️ <b>Commands:</b>\n"
            "/start — Start the bot\n"
            "/help — Show this help"
        ),
    }
}

#                  KEYBOARDS

def get_main_kb(lang, uid):
    t = TEXTS[lang]
    btns = [
        [KeyboardButton(t["btn_tools"]),   KeyboardButton(t["btn_persona"])],
        [KeyboardButton(t["btn_profile"]), KeyboardButton(t["btn_lang"])],
        [KeyboardButton(t["btn_reset"])],
    ]
    if uid in ADMIN_IDS:
        btns.append([KeyboardButton(t["btn_admin"])])
    return ReplyKeyboardMarkup(btns, resize_keyboard=True, is_persistent=True)

def get_tools_kb(lang):
    t = TEXTS[lang]
    return ReplyKeyboardMarkup([
        [KeyboardButton(t["btn_image"]),  KeyboardButton(t["btn_weather"])],
        [KeyboardButton(t["btn_search"]), KeyboardButton(t["btn_qr"])],
        [KeyboardButton(t["btn_back"])],
    ], resize_keyboard=True, is_persistent=True)

def get_persona_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 Smart Assistant", callback_data="p_smart")],
        [InlineKeyboardButton("👨‍💻 Expert Coder",   callback_data="p_coder")],
        [InlineKeyboardButton("📚 Study Guide",     callback_data="p_teacher")],
    ])

def lang_inline():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇧🇩 বাংলা",  callback_data="l_bn"),
        InlineKeyboardButton("🇬🇧 English", callback_data="l_en"),
    ]])

def get_admin_inline(lang):
    maint_label = "🟢 Maintenance: OFF" if not MAINTENANCE_MODE else "🔴 Maintenance: ON"
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📊 Stats",      callback_data="adm_stats"),
            InlineKeyboardButton("👥 Users",      callback_data="adm_users"),
        ],
        [
            InlineKeyboardButton("📢 Broadcast",  callback_data="adm_bc"),
            InlineKeyboardButton("🚫 Ban User",   callback_data="adm_ban"),
        ],
        [
            InlineKeyboardButton("✅ Unban User", callback_data="adm_unban"),
            InlineKeyboardButton(maint_label,     callback_data="adm_maint"),
        ],
        [InlineKeyboardButton("❌ Close",         callback_data="adm_close")],
    ])

#                  HELPERS

def get_u(uid, name="User"):
    if uid not in user_db:
        user_db[uid] = {
            "lang":    None,
            "hist":    [],
            "name":    name,
            "msgs":    0,
            "persona": "smart",
            "joined":  datetime.now().strftime("%Y-%m-%d"),
        }
    return user_db[uid]

async def safe_edit(msg, text, parse_mode=None, reply_markup=None):
    """Safe message edit with proper emoji handling"""
    kwargs = {}
    if parse_mode:   
        kwargs["parse_mode"] = parse_mode
    if reply_markup: 
        kwargs["reply_markup"] = reply_markup
    
    try:
        await msg.edit_text(text, **kwargs)
    except BadRequest as e:
        if "Message is not modified" in str(e):
            return
        # Try without parse_mode if it fails
        try:
            kwargs.pop("parse_mode", None)
            await msg.edit_text(text, **kwargs)
        except Exception:
            pass
    except RetryAfter as e:
        await asyncio.sleep(e.retry_after + 0.1)
        await safe_edit(msg, text, parse_mode, reply_markup)

async def thinking_anim(msg, lang):
    t = TEXTS[lang]["thinking"]
    try:
        while True:
            for i in range(1, 6):
                await safe_edit(msg, f"{t}{'.' * i}")
                await asyncio.sleep(0.4)
            for i in range(4, 1, -1):
                await safe_edit(msg, f"{t}{'.' * i}")
                await asyncio.sleep(0.4)
    except asyncio.CancelledError:
        pass

async def fetch_weather(city: str, lang: str) -> Optional[str]:
    url = f"https://wttr.in/{quote(city)}?format=j1"
    try:
        async with httpx.AsyncClient(timeout=12) as hc:
            r = await hc.get(url, headers={"User-Agent": "curl/7.88.0"})
            if r.status_code != 200:
                return None
            data = r.json()

        cur       = data["current_condition"][0]
        area      = data["nearest_area"][0]
        city_name = area["areaName"][0]["value"]
        country   = area["country"][0]["value"]
        today     = data["weather"][0]

        temp_c     = cur["temp_C"]
        feels_like = cur["FeelsLikeC"]
        humidity   = cur["humidity"]
        wind_kmph  = cur["windspeedKmph"]
        wind_dir   = cur["winddir16Point"]
        desc       = cur["weatherDesc"][0]["value"]
        visibility = cur["visibility"]
        pressure   = cur["pressure"]
        uv_index   = cur["uvIndex"]
        max_temp   = today["maxtempC"]
        min_temp   = today["mintempC"]

        desc_l = desc.lower()
        emoji  = ("⛈️" if "thunder" in desc_l else
                  "🌧️" if "rain"    in desc_l else
                  "🌦️" if "drizzle" in desc_l else
                  "🌨️" if "snow"    in desc_l else
                  "🌫️" if "fog"     in desc_l or "mist" in desc_l else
                  "⛅"  if "cloud"   in desc_l or "overcast" in desc_l else
                  "☀️")

        if lang == "bn":
            return (
                f"🌍 <b>{city_name}, {country}</b>\n"
                f"{emoji} অবস্থা: {desc}\n"
                f"🌡️ তাপমাত্রা: {temp_c} C (অনুভূতি: {feels_like} C)\n"
                f"📊 সর্বোচ্চ/সর্বনিম্ন: {max_temp} C / {min_temp} C\n"
                f"💧 আর্দ্রতা: {humidity}%\n"
                f"💨 বাতাস: {wind_kmph} km/h ({wind_dir})\n"
                f"👁️ দৃশ্যমানতা: {visibility} km\n"
                f"🔵 বায়ুচাপ: {pressure} hPa\n"
                f"☀️ UV সূচক: {uv_index}\n"
            )
        else:
            return (
                f"🌍 <b>{city_name}, {country}</b>\n"
                f"{emoji} Condition: {desc}\n"
                f"🌡️ Temperature: {temp_c} C (Feels like: {feels_like} C)\n"
                f"📊 High/Low: {max_temp} C / {min_temp} C\n"
                f"💧 Humidity: {humidity}%\n"
                f"💨 Wind: {wind_kmph} km/h ({wind_dir})\n"
                f"👁️ Visibility: {visibility} km\n"
                f"🔵 Pressure: {pressure} hPa\n"
                f"☀️ UV Index: {uv_index}\n"
            )
    except Exception as e:
        logger.error(f"Weather fetch error: {e}")
        return None

#                  AI CORE

async def stream_groq(prompt, hist, user_msg, thinking_msg, anim_task,
                      model=TEXT_MODEL, img_b64=None):
    messages = [{"role": "system", "content": prompt}]
    if hist:
        messages.extend(hist)

    if img_b64:
        messages.append({
            "role": "user",
            "content": [
                {"type": "text", "text": user_msg},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
            ],
        })
        if anim_task:
            anim_task.cancel()
        try:
            resp = await client.chat.completions.create(model=VISION_MODEL, messages=messages)
            res  = resp.choices[0].message.content
            await safe_edit(thinking_msg, res, parse_mode=ParseMode.HTML)
            return res
        except Exception as e:
            logger.error(f"Vision API error: {e}")
            return None

    messages.append({"role": "user", "content": user_msg})
    full_text, last_edit = "", 0
    try:
        stream = await client.chat.completions.create(
            model=model, messages=messages, stream=True
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content or ""
            if content:
                if anim_task and not anim_task.done():
                    anim_task.cancel()
                full_text += content
                if (time.monotonic() - last_edit) > STREAM_EDIT_DELAY:
                    await safe_edit(thinking_msg, full_text + " ▊")
                    last_edit = time.monotonic()
        await safe_edit(thinking_msg, full_text, parse_mode=ParseMode.HTML)
        return full_text
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        return None

#                  COMMANDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        TEXTS["en"]["welcome"], 
        reply_markup=lang_inline(), 
        parse_mode=ParseMode.HTML
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_u(uid, update.effective_user.first_name)
    lang = u.get("lang", "en")
    await update.message.reply_text(
        TEXTS[lang]["help_text"], 
        parse_mode=ParseMode.HTML
    )

#               CALLBACK HANDLER

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    q = update.callback_query
    try:
        await q.answer()
    except BadRequest:
        return

    data = q.data
    uid  = q.from_user.id
    u    = get_u(uid, q.from_user.first_name)
    lang = u.get("lang", "en")

    if data.startswith("l_"):
        chosen = data.split("_")[1]
        u["lang"] = chosen
        try:
            await q.edit_message_text(
                TEXTS[chosen]["lang_set"], 
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            await context.bot.send_message(uid, TEXTS[chosen]["lang_set"])
        await context.bot.send_message(
            uid, 
            TEXTS[chosen]["main_menu"],
            reply_markup=get_main_kb(chosen, uid), 
            parse_mode=ParseMode.HTML
        )
        return

    if data.startswith("p_"):
        persona = data.split("_")[1]
        u["persona"] = persona
        labels = {"smart": "🧠 Smart Assistant", "coder": "👨‍💻 Expert Coder", "teacher": "📚 Study Guide"}
        try:
            await q.edit_message_text(
                f"✅ <b>Persona set:</b> {labels.get(persona, persona)}",
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            pass
        return

    if uid not in ADMIN_IDS:
        return

    if data == "adm_stats":
        uptime    = str(datetime.now() - bot_start_time).split(".")[0]
        total_msg = sum(v["msgs"] for v in user_db.values())
        text = (
            "📊 <b>Bot Statistics</b>\n\n"
            f"👥 Total Users: {len(user_db)}\n"
            f"💬 Total Messages: {total_msg}\n"
            f"🚫 Banned Users: {len(banned_users)}\n"
            f"🚧 Maintenance: {'ON' if MAINTENANCE_MODE else 'OFF'}\n"
            f"⏱️ Uptime: {uptime}\n"
            f"🤖 Model: {TEXT_MODEL}"
        )
        try:
            await q.edit_message_text(
                text, 
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_inline(lang)
            )
        except BadRequest:
            pass
        return

    if data == "adm_users":
        if not user_db:
            text = "👥 <b>No users yet.</b>"
        else:
            lines = ["👥 <b>Recent Users</b>\n"]
            for i, (user_id, info) in enumerate(list(user_db.items())[-15:], 1):
                ban_tag = " 🚫" if user_id in banned_users else ""
                lines.append(
                    f"{i}. {info['name']}{ban_tag}\n"
                    f"   ID: {user_id} | Msgs: {info['msgs']} | Lang: {info.get('lang', '?')}"
                )
            text = "\n".join(lines)
        try:
            await q.edit_message_text(
                text, 
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_inline(lang)
            )
        except BadRequest:
            pass
        return

    if data == "adm_bc":
        context.user_data["adm_action"] = "broadcast"
        try:
            await q.edit_message_text(
                "📢 <b>Broadcast Mode</b>\nWrite the message you want to send to all users:",
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            pass
        return

    if data == "adm_ban":
        context.user_data["adm_action"] = "ban"
        try:
            await q.edit_message_text(
                "🚫 <b>Ban User</b>\nSend the <b>User ID</b> to ban:",
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            pass
        return

    if data == "adm_unban":
        context.user_data["adm_action"] = "unban"
        try:
            await q.edit_message_text(
                "✅ <b>Unban User</b>\nSend the <b>User ID</b> to unban:",
                parse_mode=ParseMode.HTML
            )
        except BadRequest:
            pass
        return

    if data == "adm_maint":
        MAINTENANCE_MODE = not MAINTENANCE_MODE
        state = "🔴 ON" if MAINTENANCE_MODE else "🟢 OFF"
        try:
            await q.edit_message_text(
                f"🚧 <b>Maintenance toggled</b>\nCurrent status: {state}",
                parse_mode=ParseMode.HTML,
                reply_markup=get_admin_inline(lang)
            )
        except BadRequest:
            pass
        return

    if data == "adm_close":
        try:
            await q.delete_message()
        except BadRequest:
            pass
        return

#               MESSAGE HANDLER

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    uid = update.effective_user.id
    u   = get_u(uid, update.effective_user.first_name)

    if not u["lang"]:
        return await start(update, context)

    txt  = update.message.text
    lang = u["lang"]
    t    = TEXTS[lang]

    if uid in banned_users:
        return await update.message.reply_text(t["banned"])

    if MAINTENANCE_MODE and uid not in ADMIN_IDS:
        return await update.message.reply_text(t["maintenance"])

    # Admin action inputs
    adm_action = context.user_data.get("adm_action")
    if adm_action and uid in ADMIN_IDS:
        context.user_data.pop("adm_action", None)

        if adm_action == "broadcast":
            success = 0
            for user_id in list(user_db.keys()):
                try:
                    await context.bot.send_message(
                        user_id, 
                        f"📢 <b>Notice from Admin</b>\n\n{txt}", 
                        parse_mode=ParseMode.HTML
                    )
                    success += 1
                    await asyncio.sleep(0.05)
                except Exception as e:
                    logger.error(f"Broadcast failed for {user_id}: {e}")
            return await update.message.reply_text(
                f"✅ Broadcast sent to {success} / {len(user_db)} users.",
                parse_mode=ParseMode.HTML
            )

        if adm_action == "ban":
            try:
                target = int(txt.strip())
                banned_users.add(target)
                name = user_db[target]["name"] if target in user_db else "Unknown"
                return await update.message.reply_text(
                    f"🚫 User {target} ({name}) has been banned.",
                    parse_mode=ParseMode.HTML
                )
            except ValueError:
                return await update.message.reply_text("❌ Invalid user ID.")

        if adm_action == "unban":
            try:
                target = int(txt.strip())
                if target in banned_users:
                    banned_users.discard(target)
                    return await update.message.reply_text(
                        f"✅ User {target} has been unbanned.", 
                        parse_mode=ParseMode.HTML
                    )
                else:
                    return await update.message.reply_text("ℹ️ That user is not banned.")
            except ValueError:
                return await update.message.reply_text("❌ Invalid user ID.")

    # Navigation
    if txt == t["btn_back"]:
        context.user_data.clear()
        return await update.message.reply_text(
            t["main_menu"], 
            reply_markup=get_main_kb(lang, uid), 
            parse_mode=ParseMode.HTML
        )
    if txt == t["btn_tools"]:
        return await update.message.reply_text(
            t["tools_menu"], 
            reply_markup=get_tools_kb(lang), 
            parse_mode=ParseMode.HTML
        )
    if txt == t["btn_persona"]:
        return await update.message.reply_text(
            t["persona_menu"], 
            reply_markup=get_persona_kb(), 
            parse_mode=ParseMode.HTML
        )
    if txt == t["btn_admin"] and uid in ADMIN_IDS:
        return await update.message.reply_text(
            f"👑 <b>Admin Panel</b>\n<i>Welcome, {u['name']}!</i>",
            reply_markup=get_admin_inline(lang),
            parse_mode=ParseMode.HTML
        )
    if txt == t["btn_profile"]:
        persona_labels = {"smart": "🧠 Smart", "coder": "👨‍💻 Coder", "teacher": "📚 Teacher"}
        return await update.message.reply_text(
            f"👤 <b>Profile</b>\n\n"
            f"🏷️ Name: {u['name']}\n"
            f"💬 Messages: {u['msgs']}\n"
            f"🎭 Persona: {persona_labels.get(u['persona'], u['persona'])}\n"
            f"🌐 Language: {lang.upper()}\n"
            f"📅 Joined: {u.get('joined', 'N/A')}",
            parse_mode=ParseMode.HTML
        )
    if txt == t["btn_reset"]:
        u["hist"] = []
        return await update.message.reply_text(t["reset_done"])
    if txt == t["btn_lang"]:
        return await start(update, context)

    # Tool triggers
    tool_map = {
        t["btn_image"]:   "image",
        t["btn_weather"]: "weather",
        t["btn_search"]:  "search",
        t["btn_qr"]:      "qr",
    }
    if txt in tool_map:
        mode = tool_map[txt]
        context.user_data["mode"] = mode
        prompt_key = {"image": "ask_img", "weather": "ask_city",
                      "search": "ask_search", "qr": "ask_qr"}[mode]
        return await update.message.reply_text(t[prompt_key])

    # Tool execution
    mode = context.user_data.get("mode")

    if mode == "qr":
        context.user_data.clear()
        try:
            img = qrcode.make(txt)
            bio = io.BytesIO()
            bio.name = "qr.png"
            img.save(bio, "PNG")
            bio.seek(0)
            await context.bot.send_photo(
                chat_id=uid, photo=bio,
                caption=f"✅ <b>QR Code Generated!</b>\n{txt[:60]}",
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.error(f"QR error: {e}")
            await update.message.reply_text("❌ QR generation failed.")
        return

    if mode == "image":
        context.user_data.clear()
        msg = await update.message.reply_text(t["thinking"] + " 🎨...")
        img_url = (
            f"https://pollinations.ai/p/{quote(txt)}"
            f"?width=1024&height=1024&seed={int(time.time())}&model=flux&nologo=true"
        )
        try:
            async with httpx.AsyncClient(timeout=60) as hc:
                r = await hc.get(img_url)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                bio = io.BytesIO(r.content)
                bio.name = "image.jpg"
                await context.bot.send_photo(
                    chat_id=uid, photo=bio,
                    caption=f"🎨 <b>{txt[:100]}</b>",
                    parse_mode=ParseMode.HTML
                )
                await msg.delete()
            else:
                await safe_edit(msg, t["img_error"])
        except Exception as e:
            logger.error(f"Image gen error: {e}")
            await safe_edit(msg, t["img_error"])
        return

    if mode == "weather":
        context.user_data.clear()
        msg = await update.message.reply_text(t["thinking"] + " 🌥...")
        weather_text = await fetch_weather(txt, lang)
        if weather_text:
            await safe_edit(msg, weather_text, parse_mode=ParseMode.HTML)
        else:
            await safe_edit(msg, t["weather_error"])
        return

    if mode == "search":
        context.user_data.clear()
        msg = await update.message.reply_text(t["thinking"] + " 🔍...")
        try:
            results = []
            with DDGS() as ddgs:
                for r in ddgs.text(txt, max_results=5):
                    results.append(f"• {r['title']}: {r['body']}")
            search_ctx = "\n".join(results) if results else "No results found."
            combined   = f"User query: {txt}\n\nSearch results:\n{search_ctx}"
            anim = asyncio.create_task(thinking_anim(msg, lang))
            resp = await stream_groq(t["sys_search"], [], combined, msg, anim)
            if not anim.done():
                anim.cancel()
            if not resp:
                await safe_edit(msg, t["ai_error"])
        except Exception as e:
            logger.error(f"Search error: {e}")
            await safe_edit(msg, t["ai_error"])
        return

    # Regular AI Chat
    sys_prompt = t["sys_chat"]
    if u["persona"] == "coder":
        sys_prompt += " You are an expert programmer. Prioritize code solutions."
    elif u["persona"] == "teacher":
        sys_prompt += " You are a patient, simple teacher. Use examples."

    async with user_locks[uid]:
        await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
        thinking_msg = await update.message.reply_text(t["thinking"] + "...")
        anim = asyncio.create_task(thinking_anim(thinking_msg, lang))
        resp = await stream_groq(sys_prompt, u["hist"], txt, thinking_msg, anim)

        if not anim.done():
            anim.cancel()

        if resp:
            u["hist"].append({"role": "user",      "content": txt})
            u["hist"].append({"role": "assistant",  "content": resp})
            if len(u["hist"]) > 8:
                u["hist"] = u["hist"][-8:]
            u["msgs"] += 1
        else:
            await safe_edit(thinking_msg, t["ai_error"])

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_u(uid, update.effective_user.first_name)
    lang = u.get("lang")
    if not lang: return
    if uid in banned_users: return
    if MAINTENANCE_MODE and uid not in ADMIN_IDS:
        return await update.message.reply_text(TEXTS[lang]["maintenance_media"])
    try:
        file    = await update.message.photo[-1].get_file()
        img_b64 = base64.b64encode(await file.download_as_bytearray()).decode("utf-8")
        caption = update.message.caption or "Analyze this image in detail."
        async with user_locks[uid]:
            thinking_msg = await update.message.reply_text(TEXTS[lang]["thinking"] + "...")
            anim = asyncio.create_task(thinking_anim(thinking_msg, lang))
            resp = await stream_groq(TEXTS[lang]["sys_chat"], [], caption, thinking_msg, anim, img_b64=img_b64)
            if not anim.done(): anim.cancel()
            if not resp:
                await safe_edit(thinking_msg, TEXTS[lang]["ai_error"])
    except Exception as e:
        logger.error(f"Photo error: {e}")
        await update.message.reply_text(TEXTS[lang]["ai_error"])

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_u(uid, update.effective_user.first_name)
    lang = u.get("lang")
    if not lang: return
    if uid in banned_users: return
    if MAINTENANCE_MODE and uid not in ADMIN_IDS:
        return await update.message.reply_text(TEXTS[lang]["maintenance_media"])

    msg = await update.message.reply_text(TEXTS[lang]["voice_processing"])
    try:
        voice_file  = await update.message.voice.get_file()
        voice_bytes = await voice_file.download_as_bytearray()
        transcription = await client.audio.transcriptions.create(
            model=STT_MODEL,
            file=("voice.ogg", bytes(voice_bytes), "audio/ogg"),
        )
        transcribed = transcription.text.strip()
        if not transcribed:
            return await safe_edit(msg, TEXTS[lang]["voice_error"])

        await safe_edit(
            msg,
            f"🎙️ <b>Heard:</b> <i>{transcribed}</i>\n\n{TEXTS[lang]['thinking']}...",
            parse_mode=ParseMode.HTML
        )

        sys_prompt = TEXTS[lang]["sys_chat"]
        if u["persona"] == "coder":
            sys_prompt += " You are an expert programmer."
        elif u["persona"] == "teacher":
            sys_prompt += " You are a patient teacher."

        async with user_locks[uid]:
            anim = asyncio.create_task(thinking_anim(msg, lang))
            resp = await stream_groq(sys_prompt, u["hist"], transcribed, msg, anim)
            if not anim.done(): anim.cancel()
            if resp:
                u["hist"].append({"role": "user",      "content": transcribed})
                u["hist"].append({"role": "assistant",  "content": resp})
                if len(u["hist"]) > 8:
                    u["hist"] = u["hist"][-8:]
                u["msgs"] += 1
            else:
                await safe_edit(msg, TEXTS[lang]["voice_error"])
    except Exception as e:
        logger.error(f"Voice error: {e}")
        await safe_edit(msg, TEXTS[lang]["voice_error"])

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    u    = get_u(uid, update.effective_user.first_name)
    lang = u.get("lang")
    if not lang: return
    if uid in banned_users: return
    if MAINTENANCE_MODE and uid not in ADMIN_IDS:
        return await update.message.reply_text(TEXTS[lang]["maintenance_media"])

    doc = update.message.document
    if not doc.file_name.endswith((".pdf", ".txt")):
        return await update.message.reply_text("❌ Only PDF and TXT files are supported.")

    msg = await update.message.reply_text("📄 Reading document...")
    try:
        file    = await doc.get_file()
        content = await file.download_as_bytearray()
        text    = ""
        if doc.file_name.endswith(".pdf"):
            with fitz.open(stream=content, filetype="pdf") as d:
                for page in d:
                    text += page.get_text()
        else:
            text = content.decode("utf-8")

        anim = asyncio.create_task(thinking_anim(msg, lang))
        resp = await stream_groq(TEXTS[lang]["sys_pdf"], [], f"Document:\n{text[:4000]}", msg, anim)
        if not anim.done(): anim.cancel()
        if not resp:
            await safe_edit(msg, TEXTS[lang]["ai_error"])
    except Exception as e:
        logger.error(f"Doc error: {e}")
        await safe_edit(msg, TEXTS[lang]["ai_error"])

#               POST INIT / MAIN

async def post_init(application: Application):
    await application.bot.delete_my_commands()
    logger.info("☰ Menu commands deleted.")
    logger.info(f"🤖 {BOT_NAME} started successfully!")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.add_handler(MessageHandler(filters.PHOTO,        handle_photo))
    app.add_handler(MessageHandler(filters.VOICE,        handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    logger.info("🚀 Bot is Running 🦍")
    app.run_polling()

if __name__ == "__main__":
    main()
