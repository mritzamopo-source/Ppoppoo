import asyncio
import json
import os
import time
import random
import re
import hashlib
import aiohttp
import pytz
from datetime import datetime
from rubpy.bot import BotClient, filters
from rubpy.types import Update

# =========================
# تنظیمات
# =========================
TOKEN = "CGEBEF0SFZOZSSLNSIBEYBUERMKKBFLCLMEWMEMBUVNLVWQFMVOGNYBHAKGADXLO"
DATA_FILE = "ducky_data.json"
COIN_DATA_FILE = "coin_data.json"
BANS_FILE = "bans.json"
STATS_FILE = "stats.json"
MEMBERS_FILE = "members.json"
TEHRAN_TZ = pytz.timezone('Asia/Tehran')

OPENROUTER_API_KEY = ""
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_MODEL = "google/gemma-4-26b-a4b-it:free"

FORBIDDEN_AI_TERMS = [
    "http", "tcp", "udp", "request", "python", "java", "ddos",
    "socket", "network", "protocol", "flood", "پایتون", "جاوا",
    "پروتکل", "شبکه", "حمله", "هک", "داس", "پورت", "سوکت"
]

QUACK_WORDS = ["کواک", "quack", "quak", "kwaak", "ghavak", "ghooak", "qwack", "کعاک"]

SHOP_ITEMS = {
    "clothes": {
        "blue": {"name": "لباس آبی 🔵", "price": 1000},
        "red": {"name": "لباس قرمز 🔴", "price": 2000},
        "green": {"name": "لباس سبز 🟢", "price": 3000},
        "gold": {"name": "لباس طلایی ✨", "price": 10000}
    },
    "cages": {
        "wood": {"name": "قفس چوبی 🪵", "price": 1500},
        "iron": {"name": "قفس آهنی ⛓️", "price": 6000},
        "diamond": {"name": "قفس الماسی 💎", "price": 25000}
    }
}

MIN_COIN_PRICE = 100
MAX_COIN_PRICE = 500
QUACK_COOLDOWN = 60
MAX_DISPLAYNAME_LENGTH = 30

ANTI_SELF_CHECK_INTERVAL = 3 * 3600
ANTI_SELF_BAN_DURATION = 3600
ANTI_SELF_MIN_QUACKS = 10

active_ducks = {}

# =========================
# ✅ ادمین‌ها (یوزرنیم + گوید)
# =========================
ADMINS = ["shadowroot", "melika1392ll"]
ADMIN_GUIDS = [
    "u0K3jow0482b09787022637ab20e503f",  # melika1392ll
]
COOLDOWN_EXEMPT_USERS = ["146560355"]
ADMIN_CHAT_IDS = ["146560355"]

def is_admin(username, uid):
    """بررسی ادمین بودن با یوزرنیم یا گوید"""
    if username and username.lower() in [a.lower() for a in ADMINS]:
        return True
    if str(uid) in ADMIN_GUIDS:
        return True
    return False

bot = BotClient(TOKEN)

# =========================
# ✅ سیستم کش و Rate Limit
# =========================
_last_send_time = 0.0
MIN_SEND_INTERVAL = 1.2
_recent_replies = {}
DEDUP_WINDOW = 30

async def safe_reply(update, text, force=False):
    global _last_send_time
    chat_id = str(update.chat_id)

    if not force:
        text_hash = hashlib.md5(text.encode()).hexdigest()
        key = (chat_id, text_hash)
        last_sent = _recent_replies.get(key, 0)
        if time.time() - last_sent < DEDUP_WINDOW:
            return None
        _recent_replies[key] = time.time()
        if len(_recent_replies) > 500:
            cutoff = time.time() - DEDUP_WINDOW * 2
            for k in list(_recent_replies.keys()):
                if _recent_replies[k] < cutoff:
                    del _recent_replies[k]

    now = time.time()
    elapsed = now - _last_send_time
    if elapsed < MIN_SEND_INTERVAL:
        await asyncio.sleep(MIN_SEND_INTERVAL - elapsed)
    _last_send_time = time.time()

    for attempt in range(3):
        try:
            return await update.reply(text)
        except Exception as e:
            if "TOO_REQUESTS" in str(e):
                wait = 5 * (attempt + 1)
                print(f"⚠️ TOO_REQUESTS (attempt {attempt + 1}), wait {wait}s")
                await asyncio.sleep(wait)
                _last_send_time = time.time()
            else:
                print(f"❌ Reply error: {e}")
                return None
    return None

async def safe_send(chat_id, text):
    global _last_send_time
    now = time.time()
    elapsed = now - _last_send_time
    if elapsed < MIN_SEND_INTERVAL:
        await asyncio.sleep(MIN_SEND_INTERVAL - elapsed)
    _last_send_time = time.time()

    for attempt in range(3):
        try:
            return await bot.send_message(chat_id, text)
        except Exception as e:
            if "TOO_REQUESTS" in str(e):
                wait = 5 * (attempt + 1)
                await asyncio.sleep(wait)
                _last_send_time = time.time()
            else:
                return None
    return None

# =========================
# ماموریت‌های روزانه
# =========================
QUEST_POOL = [
    {"id": "quack_10", "name": "کواک‌کننده تازه‌کار 🦆", "description": "10 بار کواک کن", "target": 10, "reward": 100, "type": "quack"},
    {"id": "level_strong", "name": "اردک قوی 💪", "description": "به سطح 2 برس", "target": 2, "reward": 200, "type": "level"},
    {"id": "buy_3_coins", "name": "سکه‌دار شو 🪙", "description": "3 سکه بخر", "target": 3, "reward": 150, "type": "buy_coin"},
    {"id": "sell_25_coins", "name": "سکه‌فروش 💰", "description": "25 سکه بفروش", "target": 25, "reward": 500, "type": "sell_coin"},
    {"id": "catch_2_ducks", "name": "شکارچی اردک 🎯", "description": "2 اردک بگیر", "target": 2, "reward": 250, "type": "catch_duck"},
    {"id": "level_legendary", "name": "اردک افسانه‌ای 🔥", "description": "به سطح 3 برس", "target": 3, "reward": 350, "type": "level"},
    {"id": "sell_15_coins", "name": "سکه‌فروش حرفه‌ای 💸", "description": "15 سکه بفروش", "target": 15, "reward": 350, "type": "sell_coin"},
    {"id": "quack_90", "name": "کواک‌کننده افسانه‌ای 🦆", "description": "90 بار کواک کن", "target": 90, "reward": 800, "type": "quack"},
    {"id": "pay_120", "name": "بخشنده پوینت 🎁", "description": "120 پوینت بده", "target": 120, "reward": 500, "type": "pay"}
]

def get_tehran_date(): return datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
def get_quest_info(qid): return next((q for q in QUEST_POOL if q["id"] == qid), None)

def init_user_quests(user):
    if "quests" not in user:
        user["quests"] = {"daily_quests": [], "progress": {}, "completed_today": [], "last_reset": "", "total_completed": 0}
    reset_daily_quests(user)

def reset_daily_quests(user):
    today = get_tehran_date()
    quests = user.get("quests", {})
    if quests.get("last_reset") != today:
        selected = random.sample(QUEST_POOL, 3)
        user["quests"] = {
            "daily_quests": [q["id"] for q in selected],
            "progress": {q["id"]: 0 for q in selected},
            "completed_today": [],
            "last_reset": today,
            "total_completed": quests.get("total_completed", 0)
        }
        return True
    return False

def update_quest_progress(user, quest_type, amount=1):
    if "quests" not in user: return []
    completed = []
    for qid in user["quests"].get("daily_quests", []):
        if qid in user["quests"].get("completed_today", []): continue
        qi = get_quest_info(qid)
        if not qi: continue
        if qi["type"] == quest_type:
            current = user["quests"]["progress"].get(qid, 0)
            new_prog = current + amount
            user["quests"]["progress"][qid] = new_prog
            if new_prog >= qi["target"]:
                user["quests"]["completed_today"].append(qid)
                user["quests"]["total_completed"] += 1
                user["points"] = user.get("points", 0) + qi["reward"]
                completed.append(qi)
    return completed

def check_level_quest(user):
    if "quests" not in user: return []
    completed = []
    for qid in user["quests"].get("daily_quests", []):
        if qid in user["quests"].get("completed_today", []): continue
        qi = get_quest_info(qid)
        if qi and qi["type"] == "level":
            if user.get("level", 1) >= qi["target"]:
                user["quests"]["progress"][qid] = user.get("level", 1)
                user["quests"]["completed_today"].append(qid)
                user["quests"]["total_completed"] += 1
                user["points"] = user.get("points", 0) + qi["reward"]
                completed.append(qi)
    return completed

def build_quests_text(user):
    init_user_quests(user)
    today = get_tehran_date()
    quests = user.get("quests", {})
    text = f"🎯 ماموریت‌های روزانه 🎯\n📅 {today}\n🏆 کل: {quests.get('total_completed', 0)}\n\n"
    dq = quests.get("daily_quests", [])
    if not dq: return text + "❌ ماموریتی یافت نشد!"
    for qid in dq:
        qi = get_quest_info(qid)
        if not qi: continue
        prog = quests.get("progress", {}).get(qid, 0)
        target = qi["target"]
        done = qid in quests.get("completed_today", [])
        pct = min(prog, target) / target
        bar = "█" * int(pct * 10) + "░" * (10 - int(pct * 10))
        st = "✅" if done else "⏳"
        rew = f"✨ دریافت شد {qi['reward']}" if done else f"🎁 جایزه: {qi['reward']}"
        text += f"{st} {qi['name']}\n📝 {qi['description']}\n📊 [{bar}] {prog}/{target}\n{rew}\n\n"
    return text + "💡 هر روز ۰۰:۰۰ ریست می‌شن!"

# =========================
# مدیریت داده‌ها
# =========================
def create_user(uid, name, username):
    data["users"][str(uid)] = {
        "name": name, "username": username, "points": 0, "level": 1,
        "quack_per_sec": 1.0, "capacity": 1000,
        "clothes": "معمولی 🦆", "cage": "آزاد 🌿",
        "last_quack": 0, "coins": 0, "ban_until": 0, "spam_start": 0,
        "displayname": "",
        "quests": {"daily_quests": [], "progress": {}, "completed_today": [], "last_reset": "", "total_completed": 0}
    }

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"SAVE ERROR {path}: {e}")

data = load_json(DATA_FILE, {"users": {}, "active_chats": []})
coin_data = load_json(COIN_DATA_FILE, {"base_price": MIN_COIN_PRICE, "last_update": 0})
bans_data = load_json(BANS_FILE, {})
stats_data = load_json(STATS_FILE, {})
members_data = load_json(MEMBERS_FILE, {"chats": {}})

def save_data(): save_json(DATA_FILE, data)
def save_coin(): save_json(COIN_DATA_FILE, coin_data)
def save_bans(): save_json(BANS_FILE, bans_data)
def save_stats(): save_json(STATS_FILE, stats_data)
def save_members(): save_json(MEMBERS_FILE, members_data)

def add_chat_to_members(chat_id, chat_type, chat_name):
    cid = str(chat_id)
    if cid not in members_data["chats"]:
        members_data["chats"][cid] = {"type": chat_type, "name": chat_name, "added_at": time.time()}
        save_members()

# =========================
# توابع کمکی
# =========================
def normalize_text(text):
    return text.lower().strip().replace("ي", "ی").replace("ك", "ک").replace("آ", "ا")

def get_level(points): return (points // 300) + 1
def get_quack_reward(level): return 5 + (level - 1)
def get_rank(level):
    if level >= 20: return "پادشاه اردک‌ها"
    if level >= 15: return "اردک افسانه‌ای"
    if level >= 10: return "شکارچی حرفه‌ای"
    if level >= 5: return "منقار طلایی"
    return "جوجه اردک"

def get_coin_price(): return coin_data.get("base_price", MIN_COIN_PRICE)

def is_banned(uid, username):
    if is_admin(username, uid): return False, 0
    u = data["users"].get(str(uid))
    if u and u.get("ban_until", 0) > time.time():
        return True, int(u["ban_until"] - time.time())
    b = bans_data.get(str(uid))
    if b and b.get("ban_until", 0) > time.time():
        return True, int(b["ban_until"] - time.time())
    return False, 0

def contains_forbidden(t): return any(w.lower() in t.lower() for w in FORBIDDEN_AI_TERMS)

def record_activity(uid, atype):
    uid = str(uid)
    if uid not in stats_data:
        stats_data[uid] = {"quacks": [], "coin_tx": [], "activities": []}
    if "activities" not in stats_data[uid]:
        stats_data[uid]["activities"] = []
    stats_data[uid]["activities"].append({"t": time.time(), "type": atype})
    cutoff = time.time() - 86400
    stats_data[uid]["activities"] = [a for a in stats_data[uid]["activities"] if a["t"] >= cutoff]

def parse_duration(s):
    m = re.match(r'^(\d+)([dhm])$', s.lower().strip())
    if not m: return None
    v = int(m.group(1)); u = m.group(2)
    if u == 'd': return v * 86400
    if u == 'h': return v * 3600
    if u == 'm': return v * 60
    return None

def format_time_remaining(sec):
    if sec <= 0: return "منقضی"
    d = sec // 86400; h = (sec % 86400) // 3600
    m = (sec % 3600) // 60; s = sec % 60
    parts = []
    if d: parts.append(f"{d} روز")
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s and not d: parts.append(f"{s} ثانیه")
    return " و ".join(parts) if parts else "کمتر از 1 ثانیه"

def format_timestamp(ts):
    try:
        return datetime.fromtimestamp(ts, TEHRAN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except: return "نامشخص"

def validate_displayname(name, exclude_uid=None):
    if not name or not name.strip(): return False, "❌ لقب خالی!"
    name = name.strip()
    if len(name) > MAX_DISPLAYNAME_LENGTH:
        return False, f"❌ حداکثر {MAX_DISPLAYNAME_LENGTH} کاراکتر!"
    invalid = ['@', '#', '$', '%', '^', '&', '*', '(', ')', '+', '=', '{', '}', '[', ']', '|', '\\', '<', '>', '/', '~', '`']
    for c in invalid:
        if c in name: return False, f"❌ کاراکتر '{c}' مجاز نیست!"
    if name.lower() in ["admin", "ادمین", "bot", "ربات", "support", "پشتیبانی"]:
        return False, "❌ این لقب مجاز نیست!"
    for uid, u in data.get("users", {}).items():
        if exclude_uid and uid == exclude_uid: continue
        if u.get("displayname", "").strip() == name:
            return False, "❌ این لقب قبلاً استفاده شده!"
    return True, name

# =========================
# OpenRouter AI
# =========================
async def ask_ai(prompt):
    try:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {OPENROUTER_API_KEY}"}
        payload = {
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": "شما یک دستیار هوشمند فارسی هستید. هرگز به سوالات فنی پاسخ نمی‌دهید."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500, "temperature": 0.7
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(OPENROUTER_URL, headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    r = await resp.json()
                    return r["choices"][0]["message"]["content"]
                return "❌ خطا در AI"
    except: return "❌ خطایی رخ داد"

# =========================
# هندلر اصلی
# =========================
@bot.on_update(filters.text)
async def main_handler(client, update: Update):
    try:
        msg = update.new_message
        text = msg.text.strip() if msg.text else ""
        normalized = normalize_text(text)
        uid = str(msg.sender_id)
        name = getattr(msg, 'sender_name', None) or "کاربر"
        username = getattr(msg, 'sender_username', "") or ""
        chat_id = str(update.chat_id)

        is_group = chat_id.startswith("g") or chat_id.startswith("c")
        add_chat_to_members(chat_id, "group" if is_group else "private", f"Chat {chat_id}")
        if chat_id not in data["active_chats"]:
            data["active_chats"].append(chat_id)

        # ====== ✅ گوید من ======
        if normalized in ["گوید من", "گویدم", "guid من", "my guid", "/myguid", "/guid"]:
            await safe_reply(update,
                f"🆔 گوید شما:\n\n"
                f"`{uid}`\n\n"
                f"👤 نام: {name}\n"
                f"🔖 یوزرنیم: @{username if username else 'نداری'}\n\n"
                f"💡 این شناسه یکتای شماست و هیچ‌وقت تغییر نمی‌کنه!"
            )
            return

        # ====== ✅ دستور گوید ======
        if normalized == "گوید" or normalized.startswith("گوید ") or normalized == "/guidev" or normalized.startswith("/guidev "):
            reply_to = getattr(msg, 'reply_to_message', None)
            target_text = None

            if reply_to:
                target_text = getattr(reply_to, 'text', None)
                if not target_text:
                    target_text = getattr(reply_to, 'caption', None)

            if not target_text:
                if normalized.startswith("/guidev"):
                    parts = text.split(maxsplit=1)
                    if len(parts) >= 2 and parts[1].strip():
                        target_text = parts[1].strip()
                else:
                    parts = text.split(maxsplit=1)
                    if len(parts) >= 2 and parts[1].strip():
                        target_text = parts[1].strip()

            if not target_text:
                await safe_reply(update,
                    "🗣️ روش استفاده از گوید:\n\n"
                    "۱) روی یک پیام ریپلای کن و بنویس:\n"
                    "   گوید\n\n"
                    "۲) یا بنویس:\n"
                    "   گوید [متن دلخواه]\n\n"
                    "🆔 برای دیدن گوید خودت:\n"
                    "   گوید من"
                )
                return

            await safe_reply(update, f"🗣️ گوید:\n\n{target_text}")
            return

        # /start
        if normalized == "/start":
            await safe_reply(update, f"سلام {name} 🌸\nبه دنیای اردک‌ها خوش اومدی 🦆\n\n🪙 سیستم کوین فعال!\n🎯 ۹ ماموریت روزانه!\n🗣️ دستور «گوید» فعال!\n🆔 برای گوید خودت: «گوید من»\n\nبرای ماموریت‌ها: /quests")
            save_data(); return

        # /help
        if normalized in ["/help", "help", "کمک"]:
            help_text = (
                "🦆 راهنمای کامل ربات اردک 🦆\n\n"
                "🎮 گرفتن امتیاز:\n"
                "• گفتن «کواک»\n"
                "• گرفتن اردک‌ها\n\n"
                "🆔 دستور گوید:\n"
                "• گوید من ← گوید خودت\n"
                "• روی پیام ریپلای کن + بنویس «گوید»\n"
                "• یا: گوید [متن]\n\n"
                "🪙 سیستم کوین:\n"
                "/coinbuy /coinsell /coinview /coinstats\n\n"
                "🎯 /quests\n\n"
                "🏷️ /displayname [لقب]\n\n"
                "📊 /leaderboard /me /shop /buy /pay /ai\n\n"
                "🚨 ادمین:\n"
                "/force /coinsetprice /qforce /alert\n"
                "/duckyban /duckyunban /duckylistban\n"
                "/addpoint /removepoint /addlevel /duckystats"
            )
            await safe_reply(update, help_text)
            return

        # /me
        if normalized in ["/me", "me", "من", "اردکام"]:
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]; init_user_quests(u)
            dn = u.get("displayname", "")
            disp = f"{name} ({dn})" if dn else name
            profile = (
                f"🦆 پروفایل\n"
                f"👤 {disp}\n"
                f"🆔 `{uid}`\n"
                f"🌟 {get_rank(u.get('level', 1))} (Lv.{u.get('level', 1)})\n"
                f"💰 {u.get('points', 0):,}\n"
                f"🪙 {u.get('coins', 0)}\n"
                f"👕 {u.get('clothes', 'معمولی 🦆')}\n"
                f"📦 {u.get('cage', 'آزاد 🌿')}\n"
                f"🎯 {len(u.get('quests', {}).get('completed_today', []))}/3\n"
                f"🏆 کل: {u.get('quests', {}).get('total_completed', 0)}"
            )
            await safe_reply(update, profile)
            save_data(); return

        # /quests
        if normalized in ["/quests", "quests", "ماموریت", "کوئست"]:
            if uid not in data["users"]: create_user(uid, name, username)
            qtext = build_quests_text(data["users"][uid])
            await safe_reply(update, qtext)
            save_data(); return

        # /coinview
        if normalized in ["/coinview", "قیمت سکه"]:
            price = get_coin_price()
            await safe_reply(update, f"💵 قیمت سکه: {price:,} پوینت/سکه")
            return

        # /coinstats
        if normalized in ["/coinstats", "سکه من"]:
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]
            coins = u.get("coins", 0)
            points = u.get("points", 0)
            price = get_coin_price()
            value = coins * price
            await safe_reply(update,
                f"🪙 سکه: {coins}\n"
                f"💰 ارزش: {value:,}\n"
                f"💵 نقد: {points:,}\n"
                f"📊 کل: {value + points:,}"
            )
            return

        # /coinbuy
        if normalized.startswith("/coinbuy") or normalized.startswith("خرید سکه"):
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]
            amount = 1
            for p in normalized.split():
                try: amount = int(p); break
                except: pass
            if amount < 1:
                await safe_reply(update, "❌ تعداد ≥ ۱!"); return
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            price = get_coin_price()
            cost = price * amount
            if u.get("points", 0) < cost:
                await safe_reply(update, f"❌ نیاز: {cost:,} | موجودی: {u.get('points', 0):,}"); return
            u["points"] -= cost
            u["coins"] = u.get("coins", 0) + amount
            completed = update_quest_progress(u, "buy_coin", amount)
            if uid not in stats_data: stats_data[uid] = {"quacks": [], "coin_tx": [], "activities": []}
            stats_data[uid]["coin_tx"].append({"t": time.time(), "type": "buy", "amount": amount})
            record_activity(uid, "buy_coin")
            msg_text = f"✅ خرید {amount} سکه!\n💵 هزینه: {cost:,}"
            for q in completed: msg_text += f"\n🎯 {q['name']} (+{q['reward']})"
            await safe_reply(update, msg_text)
            save_data(); return

        # /coinsell
        if normalized.startswith("/coinsell") or normalized.startswith("فروش سکه"):
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]
            amount = 1
            for p in normalized.split():
                try: amount = int(p); break
                except: pass
            if amount < 1:
                await safe_reply(update, "❌ تعداد ≥ ۱!"); return
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            if u.get("coins", 0) < amount:
                await safe_reply(update, f"❌ فقط {u.get('coins', 0)} سکه داری!"); return
            price = get_coin_price()
            income = amount * price
            u["coins"] -= amount
            u["points"] += income
            completed = update_quest_progress(u, "sell_coin", amount)
            if uid not in stats_data: stats_data[uid] = {"quacks": [], "coin_tx": [], "activities": []}
            stats_data[uid]["coin_tx"].append({"t": time.time(), "type": "sell", "amount": amount})
            record_activity(uid, "sell_coin")
            msg_text = f"✅ فروش {amount} سکه!\n💰 درآمد: {income:,}"
            for q in completed: msg_text += f"\n🎯 {q['name']} (+{q['reward']})"
            await safe_reply(update, msg_text)
            save_data(); return

        # /leaderboard
        if normalized in ["/leaderboard", "لیدربورد"]:
            users = data["users"]
            su = sorted(users.items(), key=lambda x: x[1].get("points", 0), reverse=True)
            if not su:
                await safe_reply(update, "هنوز کسی امتیاز نگرفته 🦆"); return
            msg_text = "🏆 جدول برترین‌ها 🏆\n\n"
            for i, (iuid, info) in enumerate(su[:10], 1):
                dn = info.get("displayname", "")
                nm = info.get('name', 'ناشناس')
                disp = f"{nm} ({dn})" if dn else nm
                msg_text += f"{i}. {disp} ➜ {info.get('points', 0):,} 🦆\n"
            await safe_reply(update, msg_text)
            return

        # /shop
        if normalized in ["/shop", "فروشگاه"]:
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            txt = "🏪 فروشگاه\n\n👕 لباس‌ها:\n"
            for k, it in SHOP_ITEMS["clothes"].items():
                txt += f"- {it['name']}: {it['price']:,}\n"
            txt += "\n📦 قفس‌ها:\n"
            for k, it in SHOP_ITEMS["cages"].items():
                txt += f"- {it['name']}: {it['price']:,}\n"
            txt += "\n💡 /buy clothes blue"
            await safe_reply(update, txt)
            return

        # /buy
        if normalized.startswith("/buy"):
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            parts = text.split()
            if len(parts) != 3:
                await safe_reply(update, "❌ /buy [clothes/cages] [key]"); return
            itype, ikey = parts[1].lower(), parts[2].lower()
            if itype not in SHOP_ITEMS or ikey not in SHOP_ITEMS[itype]:
                await safe_reply(update, "❌ آیتم یافت نشد!"); return
            item = SHOP_ITEMS[itype][ikey]
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]
            if u.get("points", 0) < item["price"]:
                await safe_reply(update, f"❌ نیاز: {item['price']:,}"); return
            u["points"] -= item["price"]
            if itype == "clothes": u["clothes"] = item["name"]
            else: u["cage"] = item["name"]
            record_activity(uid, "shop_buy")
            await safe_reply(update, f"✅ {item['name']} خریداری شد!")
            save_data(); return

        # /pay
        if normalized.startswith("/pay"):
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            parts = text.split()
            if len(parts) != 3:
                await safe_reply(update, "❌ /pay [username] [مقدار]"); return
            target_username = parts[1].replace("@", "").lower()
            try: amount = int(parts[2])
            except: await safe_reply(update, "❌ عدد"); return
            if amount <= 0: await safe_reply(update, "❌ > 0"); return
            rid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    rid = iuid; break
            if not rid: await safe_reply(update, "❌ پیدا نشد"); return
            if uid == rid: await safe_reply(update, "❌ به خودت نه"); return
            if uid not in data["users"]: create_user(uid, name, username)
            sender = data["users"][uid]
            if sender.get("points", 0) < amount:
                await safe_reply(update, f"❌ موجودی: {sender.get('points', 0)}"); return
            sender["points"] -= amount
            data["users"][rid]["points"] = data["users"][rid].get("points", 0) + amount
            completed = update_quest_progress(sender, "pay", amount)
            record_activity(uid, "pay")
            rname = data["users"][rid].get("name", "کاربر")
            msg_text = f"✅ {amount} به {rname}"
            for q in completed: msg_text += f"\n🎯 {q['name']} (+{q['reward']})"
            await safe_reply(update, msg_text)
            save_data(); return

        # /ai
        if normalized.startswith("/ai"):
            prompt = text.replace("/ai", "", 1).strip()
            if not prompt:
                await safe_reply(update, "❌ /ai سوال"); return
            if contains_forbidden(prompt):
                await safe_reply(update, "❌ مجاز نیست"); return
            await safe_reply(update, "🤖 فکر می‌کنم...")
            answer = await ask_ai(prompt)
            await safe_reply(update, f"🤖 {answer}", force=True)
            return

        # لقب
        if normalized == "لقب" or normalized.startswith("/لقب") or normalized.startswith("/displayname"):
            b, rt = is_banned(uid, username)
            if b: await safe_reply(update, f"🚫 بن! {rt}s"); return
            if normalized.startswith("/displayname"):
                arg = text.replace("/displayname", "", 1).strip()
            elif normalized.startswith("/لقب"):
                arg = text.replace("/لقب", "", 1).strip()
            else:
                arg = text.replace("لقب", "", 1).strip()

            if arg.lower() in ["clear", "حذف", "پاک", "remove"]:
                if uid not in data["users"]: create_user(uid, name, username)
                data["users"][uid]["displayname"] = ""
                await safe_reply(update, "✅ حذف شد!")
                save_data(); return

            if not arg:
                if uid not in data["users"]: create_user(uid, name, username)
                cur = data["users"][uid].get("displayname", "")
                if cur:
                    await safe_reply(update, f"🏷️ {cur}")
                else:
                    await safe_reply(update, "🏷️ نداری!\n/displayname [لقب]")
                return

            ok, res = validate_displayname(arg, exclude_uid=uid)
            if not ok:
                await safe_reply(update, res); return
            if uid not in data["users"]: create_user(uid, name, username)
            data["users"][uid]["displayname"] = res
            await safe_reply(update, f"✅ لقب: {res}")
            save_data(); return

        # ===== ادمین =====

        # /force
        if normalized == "/force":
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            cur = coin_data.get("base_price", MIN_COIN_PRICE)
            force_down = True if MAX_COIN_PRICE - cur <= 30 else (False if cur - MIN_COIN_PRICE <= 30 else random.choice([True, False]))
            amt = random.randint(1, 10)
            new_p = cur - amt if force_down else cur + amt
            new_p = max(MIN_COIN_PRICE, min(MAX_COIN_PRICE, new_p))
            diff = abs(new_p - cur)
            coin_data["base_price"] = new_p
            coin_data["last_update"] = time.time()
            save_coin()
            sign = "-" if force_down else "+"
            await safe_reply(update,
                f"{'📉' if force_down else '📈'} قیمت فورس شد!\n\n"
                f"👤 {name}\n💵 قبلی: {cur:,}\n💲 جدید: {new_p:,}\n🔄 {sign}{diff:,}"
            )
            return

        # /coinsetprice
        if normalized.startswith("/coinsetprice"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = normalized.split()
            if len(parts) != 2:
                await safe_reply(update, "⚠️ /coinsetprice [عدد]"); return
            try: newp = int(parts[1])
            except: await safe_reply(update, "❌ عدد"); return
            if newp < MIN_COIN_PRICE:
                await safe_reply(update, f"❌ حداقل {MIN_COIN_PRICE}"); return
            old = coin_data.get("base_price", MIN_COIN_PRICE)
            coin_data["base_price"] = newp
            coin_data["last_update"] = time.time()
            save_coin()
            await safe_reply(update, f"✅ {old:,} → {newp:,}")
            return

        # /qforce
        if normalized.startswith("/qforce"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) >= 2 and parts[1].lower() == "all":
                cnt = 0
                for u in data["users"].values():
                    u["quests"] = u.get("quests", {})
                    u["quests"]["last_reset"] = ""
                    init_user_quests(u)
                    cnt += 1
                save_data()
                await safe_reply(update, f"✅ {cnt} کاربر ریست شد 🎯")
            else:
                await safe_reply(update, "🎯 /qforce all")
            return

        # /alert
        if normalized.startswith("/alert"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            alert = text.replace("/alert", "", 1).strip()
            if not alert:
                await safe_reply(update, "⚠️ /alert متن"); return
            total = len(members_data.get("chats", {}))
            await safe_reply(update, f"⏳ ارسال به {total} چت...")
            asyncio.create_task(send_alert_broadcast(alert, chat_id))
            return

        # /addpoint
        if normalized.startswith("/addpoint"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 3:
                await safe_reply(update, "⚠️ /addpoint [username] [مقدار]"); return
            target_username = parts[1].replace("@", "").lower()
            try: amt = int(parts[2])
            except: await safe_reply(update, "❌ عدد"); return
            if amt <= 0: await safe_reply(update, "❌ > 0"); return
            tid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            data["users"][tid]["points"] = data["users"][tid].get("points", 0) + amt
            await safe_reply(update, f"➕ {amt} به {data['users'][tid]['name']}")
            save_data(); return

        # /removepoint
        if normalized.startswith("/removepoint"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 3:
                await safe_reply(update, "⚠️ /removepoint [username] [مقدار]"); return
            target_username = parts[1].replace("@", "").lower()
            try: amt = int(parts[2])
            except: await safe_reply(update, "❌ عدد"); return
            if amt <= 0: await safe_reply(update, "❌ > 0"); return
            tid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            data["users"][tid]["points"] = max(0, data["users"][tid].get("points", 0) - amt)
            await safe_reply(update, f"➖ {amt} از {data['users'][tid]['name']}")
            save_data(); return

        # /addlevel
        if normalized.startswith("/addlevel"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 3:
                await safe_reply(update, "⚠️ /addlevel [username] [تعداد]"); return
            target_username = parts[1].replace("@", "").lower()
            try: lv = int(parts[2])
            except: await safe_reply(update, "❌ عدد"); return
            if lv <= 0: await safe_reply(update, "❌ > 0"); return
            tid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            u = data["users"][tid]
            init_user_quests(u)
            u["level"] = u.get("level", 1) + lv
            u["quack_per_sec"] = u.get("quack_per_sec", 1.0) + 0.25 * lv
            u["capacity"] = u.get("capacity", 1000) + 500 * lv
            completed = check_level_quest(u)
            msg_text = f"✅ {lv} لول به {u['name']}"
            for q in completed: msg_text += f"\n🎯 {q['name']} (+{q['reward']})"
            await safe_reply(update, msg_text)
            save_data(); return

        # /duckyban
        if normalized.startswith("/duckyban"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 3:
                await safe_reply(update, "⚠️ /duckyban [username] [1d/2h/30m]"); return
            target_username = parts[1].replace("@", "").lower()
            secs = parse_duration(parts[2])
            if not secs:
                await safe_reply(update, "❌ فرمت: 1d/2h/30m"); return
            tid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            bans_data[str(tid)] = {"username": target_username, "ban_until": time.time() + secs, "reason": f"by {username}"}
            save_bans()
            await safe_reply(update, f"✅ @{target_username} بن {parts[2]} 🔨")
            return

        # /duckyunban
        if normalized.startswith("/duckyunban"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 2:
                await safe_reply(update, "⚠️ /duckyunban [username]"); return
            target_username = parts[1].replace("@", "").lower()
            tid = None
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            if str(tid) in bans_data:
                del bans_data[str(tid)]
                save_bans()
                await safe_reply(update, f"✅ @{target_username} آنبن شد 🕊️")
            else:
                await safe_reply(update, f"❌ @{target_username} در لیست نیست")
            return

        # /duckylistban
        if normalized.startswith("/duckylistban"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            now = time.time()
            active = []
            expired = []
            for iuid, b in bans_data.items():
                if b["ban_until"] > now:
                    active.append({"uid": iuid, "un": b.get("username", "?"), "r": int(b["ban_until"] - now)})
                else:
                    expired.append({"uid": iuid, "un": b.get("username", "?")})
            if not active and not expired:
                await safe_reply(update, "🕊️ لیست خالیه"); return
            txt = f"🚫 لیست بن‌ها\n🟢 فعال: {len(active)}\n🔴 منقضی: {len(expired)}\n\n"
            for i, b in enumerate(active[:15], 1):
                txt += f"{i}. @{b['un']} | `{b['uid']}` | {format_time_remaining(b['r'])}\n"
            await safe_reply(update, txt)
            return

        # /duckystats
        if normalized.startswith("/duckystats"):
            if not is_admin(username, uid):
                await safe_reply(update, "❌ فقط ادمین"); return
            parts = text.split()
            if len(parts) < 2:
                await safe_reply(update, "⚠️ /duckystats [username]"); return
            target_username = parts[1].replace("@", "").lower()
            tid = None
            tpoints = 0; tcoins = 0; tdn = ""
            for iuid, info in data["users"].items():
                if info.get("username", "").lower() == target_username:
                    tid = iuid; tpoints = info.get("points", 0); tcoins = info.get("coins", 0); tdn = info.get("displayname", "")
                    break
            if not tid:
                await safe_reply(update, "❌ پیدا نشد"); return
            us = stats_data.get(tid, {})
            ql = us.get("quacks", []); cl = us.get("coin_tx", [])
            now = time.time()
            q1h = sum(1 for x in ql if now - x.get("t", 0) <= 3600)
            q1d = sum(1 for x in ql if now - x.get("t", 0) <= 86400)
            q7d = sum(1 for x in ql if now - x.get("t", 0) <= 604800)
            qp1d = sum(x.get("p", 5) for x in ql if now - x.get("t", 0) <= 86400)
            buy1d = sum(x.get("amount", 0) for x in cl if x.get("type") == "buy" and now - x.get("t", 0) <= 86400)
            sell1d = sum(x.get("amount", 0) for x in cl if x.get("type") == "sell" and now - x.get("t", 0) <= 86400)
            txt = f"📊 @{target_username}\n\n"
            if tdn: txt += f"🏷️ {tdn}\n"
            txt += f"💰 {tpoints:,}\n🪙 {tcoins:,}\n\n"
            txt += f"🦆 کواک:\n۱ساعت: {q1h}\n۱روز: {q1d} (+{qp1d:,}p)\n۷روز: {q7d}\n\n"
            txt += f"🛒 خرید ۱روز: {buy1d}\n💸 فروش ۱روز: {sell1d}"
            await safe_reply(update, txt)
            return

        # کواک
        if normalized in QUACK_WORDS:
            b, rt = is_banned(uid, username)
            if uid not in data["users"]: create_user(uid, name, username)
            u = data["users"][uid]; init_user_quests(u)
            now = time.time()
            lq = u.get("last_quack", 0)
            if b:
                await safe_reply(update, f"🚫 بن! {rt}s"); return
            ss = u.get("spam_start", 0)
            if now - lq > 900:
                u["spam_start"] = now
            else:
                if ss == 0: u["spam_start"] = lq if lq > 0 else now
                if now - u["spam_start"] >= 18000:
                    u["ban_until"] = now + 900
                    u["spam_start"] = now
                    save_data()
                    await safe_reply(update, "⛔ ۵ ساعت مداوم! ۱۵ دقیقه استراحت 🦆"); return
            if uid not in COOLDOWN_EXEMPT_USERS and (now - lq) < QUACK_COOLDOWN:
                remain = int(QUACK_COOLDOWN - (now - lq))
                await safe_reply(update, f"⏳ {remain}s دیگه 🦆"); return
            points = u["points"]
            lv = get_level(points)
            rw = get_quack_reward(lv)
            u["points"] += rw
            u["last_quack"] = now
            nl = get_level(u["points"])
            completed = update_quest_progress(u, "quack", 1) + check_level_quest(u)
            if uid not in stats_data: stats_data[uid] = {"quacks": [], "coin_tx": [], "activities": []}
            stats_data[uid]["quacks"].append({"t": now, "p": rw})
            stats_data[uid]["quacks"] = [x for x in stats_data[uid]["quacks"] if now - x["t"] <= 604800]
            record_activity(uid, "quack")
            msg_text = f"🦆 کواک! {rw} امتیاز\n⭐ Lv.{nl} | {u['points']}"
            for q in completed: msg_text += f"\n🎯 {q['name']} (+{q['reward']})"
            await safe_reply(update, msg_text)
            save_data(); return

    except Exception as e:
        print(f"Handler error: {e}")
        import traceback
        traceback.print_exc()

# =========================
# تسک پس‌زمینه: قیمت کوین
# =========================
async def coin_updater():
    while True:
        try:
            now = time.time()
            if now - coin_data.get("last_update", 0) >= 60:
                cur = coin_data.get("base_price", MIN_COIN_PRICE)
                direction = "down" if MAX_COIN_PRICE - cur <= 50 else ("up" if cur - MIN_COIN_PRICE <= 50 else random.choice(["up", "down"]))
                amt = random.randint(5, 20)
                newp = cur - amt if direction == "down" else cur + amt
                newp = max(MIN_COIN_PRICE, min(MAX_COIN_PRICE, newp))
                coin_data["base_price"] = newp
                coin_data["last_update"] = now
                save_coin()
            await asyncio.sleep(60)
        except Exception as e:
            print(f"[Coin] {e}")
            await asyncio.sleep(60)

# =========================
# ارسال اعلان
# =========================
async def send_alert_broadcast(alert_text, admin_chat):
    sent = 0; failed = 0
    chats = list(members_data.get("chats", {}).keys())
    total = len(chats)
    for cid in chats:
        result = await safe_send(cid, f"🚨 اعلان مهم\n\n{alert_text}")
        if result:
            sent += 1
        else:
            failed += 1
        await asyncio.sleep(1.5)
    await safe_send(admin_chat, f"✅ پایان!\n✅ موفق: {sent}\n❌ ناموفق: {failed}\n📈 کل: {total}")

# =========================
# ضد سلف
# =========================
async def anti_self_checker():
    await asyncio.sleep(60)
    print("🛡️ Anti-Self Checker Started")
    while True:
        try:
            await asyncio.sleep(ANTI_SELF_CHECK_INTERVAL)
            now = time.time()
            window = now - ANTI_SELF_CHECK_INTERVAL
            suspicious = []
            for uid, us in stats_data.items():
                if uid in COOLDOWN_EXEMPT_USERS: continue
                ui = data["users"].get(uid)
                if not ui: continue
                if is_admin(ui.get("username", ""), uid): continue
                acts = us.get("activities", [])
                recents = [a for a in acts if a["t"] >= window]
                if not recents: continue
                qc = sum(1 for a in recents if a["type"] == "quack")
                others = [a for a in recents if a["type"] != "quack"]
                if qc >= ANTI_SELF_MIN_QUACKS and not others:
                    suspicious.append({"uid": uid, "un": ui.get("username", ""), "name": ui.get("name", "?"), "qc": qc})
            for s in suspicious:
                bans_data[str(s["uid"])] = {
                    "username": s["un"],
                    "ban_until": now + ANTI_SELF_BAN_DURATION,
                    "reason": f"Self-bot: {s['qc']} quacks"
                }
                save_bans()
                alert = (
                    f"🚨 سلف‌بات!\n\n"
                    f"👤 {s['name']}\n"
                    f"🆔 `{s['uid']}`\n"
                    f"🔖 @{s['un']}\n"
                    f"🦆 کواک: {s['qc']} بار\n"
                    f"🔨 بن {ANTI_SELF_BAN_DURATION // 3600} ساعت"
                )
                for admin_chat in ADMIN_CHAT_IDS:
                    await safe_send(admin_chat, alert)
                    await asyncio.sleep(1.5)
                print(f"✅ {s['un']} بن شد ({s['qc']} quacks)")
        except Exception as e:
            print(f"❌ anti_self: {e}")
            await asyncio.sleep(60)

# =========================
# اجرا
# =========================
async def main():
    print("Connecting... 🦆")
    print("Connected Successfully 🦆")
    asyncio.create_task(coin_updater())
    asyncio.create_task(anti_self_checker())
    print("Bot Started 🦆 (Polling Mode)")
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())