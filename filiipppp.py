import asyncio
import json
import time
import random
from rubpy.bot import BotClient, filters
from rubpy.types import Update

# =========================
# تنظیمات
# =========================
TOKEN = "CGFHBC0DPWAAALEHVFIFVSQMNYACCUVVGWKILVVJLODDUELCEPTTTOADOHOTIGRV"
GAME_FILE = "flip_data.json"
CACHE_FILE = "flip_cache.json"
MEMBERS_FILE = "flip_members.json"
STARTING_COINS = 100
MIN_BET = 10

# ✅ ادمین
ADMINS = ["AmirAli_Sh_Am1"]
ADMIN_GUIDS = ["u0KVFkh022742f8fdd5aa1dcc7689e72"]

def is_admin(username, uid):
    if username and username.lower() in [a.lower() for a in ADMINS]:
        return True
    if str(uid) in ADMIN_GUIDS:
        return True
    return False

bot = BotClient(TOKEN)

# =========================
# داده‌ها
# =========================
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"SAVE ERROR {path}: {e}")

data = load_json(GAME_FILE, {"users": {}})
cache = load_json(CACHE_FILE, {})
members = load_json(MEMBERS_FILE, {"chats": {}})

def save_data(): save_json(GAME_FILE, data)
def save_cache():
    try:
        if len(cache) > 10000:
            items = sorted(cache.items(), key=lambda x: x[1].get("t", 0))
            trimmed = dict(items[-10000:])
            save_json(CACHE_FILE, trimmed)
        else:
            save_json(CACHE_FILE, cache)
    except Exception as e:
        print(f"CACHE ERROR: {e}")
def save_members(): save_json(MEMBERS_FILE, members)


# =========================
# ✅ گرفتن اسم واقعی کاربر (چند روش)
# =========================
async def fetch_real_name(uid, chat_id=None, fallback_name="کاربر"):
    """گرفتن اسم و یوزرنیم واقعی کاربر با چند روش مختلف"""
    uid = str(uid)
    
    # روش ۱: اگه chat_id چت خصوصی هست (b0xxx)، از get_chat استفاده کن
    if chat_id and str(chat_id).startswith("b0"):
        try:
            chat = await bot.get_chat(str(chat_id))
            first = chat.first_name or ""
            last = chat.last_name or ""
            full_name = f"{first} {last}".strip() or chat.title or fallback_name
            username = chat.username or ""
            print(f"✅ روش ۱ (PV chat_id) | uid={uid} | name={full_name} | username={username}")
            return full_name, username
        except Exception as e:
            print(f"❌ روش ۱ (chat_id PV): {e}")
    
    # روش ۲: امتحان با خود uid (شاید بعضی وقتا جواب بده)
    try:
        chat = await bot.get_chat(str(uid))
        first = chat.first_name or ""
        last = chat.last_name or ""
        full_name = f"{first} {last}".strip() or chat.title or fallback_name
        username = chat.username or ""
        print(f"✅ روش ۲ (uid) | uid={uid} | name={full_name} | username={username}")
        return full_name, username
    except Exception as e:
        print(f"❌ روش ۲ (uid): {e}")
    
    # روش ۳: تبدیل u0xxx به b0xxx
    try:
        if uid.startswith("u0"):
            alt_uid = "b" + uid[1:]
            chat = await bot.get_chat(alt_uid)
            first = chat.first_name or ""
            last = chat.last_name or ""
            full_name = f"{first} {last}".strip() or chat.title or fallback_name
            username = chat.username or ""
            print(f"✅ روش ۳ (u→b) | alt={alt_uid} | name={full_name} | username={username}")
            return full_name, username
    except Exception as e:
        print(f"❌ روش ۳ (u→b): {e}")
    
    print(f"⚠️ هیچ روشی کار نکرد برای uid={uid}")
    return fallback_name, ""


def create_user(uid, name, username=""):
    """ساخت کاربر"""
    uid = str(uid)
    if uid not in data["users"]:
        data["users"][uid] = {
            "name": name,
            "username": username,
            "coins": STARTING_COINS,
            "wins": 0,
            "losses": 0,
            "total_wagered": 0,
            "joined": time.time()
        }
        save_data()
        return True
    return False


async def create_user_with_name(uid, chat_id=None, fallback_name="کاربر"):
    """ساخت کاربر با گرفتن اسم واقعی از سرور"""
    uid = str(uid)
    if uid in data["users"]:
        return False
    
    # ✅ اسم واقعی رو از سرور بگیر
    real_name, real_username = await fetch_real_name(uid, chat_id, fallback_name)
    
    data["users"][uid] = {
        "name": real_name,
        "username": real_username,
        "coins": STARTING_COINS,
        "wins": 0,
        "losses": 0,
        "total_wagered": 0,
        "joined": time.time()
    }
    save_data()
    return True


async def update_user_name_if_missing(uid, chat_id=None):
    """اگه اسم کاربر «کاربر» یا گوید بود، آپدیتش کن"""
    uid = str(uid)
    u = data["users"].get(uid)
    if not u: return
    
    # اگه اسم کاربر «کاربر» یا گوید (u0xxx) بود، آپدیتش کن
    current_name = u.get("name", "")
    if current_name in ["کاربر", "", None] or current_name.startswith("u0"):
        real_name, real_username = await fetch_real_name(uid, chat_id, current_name or "کاربر")
        if real_name and real_name != "کاربر":
            u["name"] = real_name
            if real_username:
                u["username"] = real_username
            save_data()
            print(f"🔄 آپدیت شد | uid={uid} | name={real_name}")


# =========================
# توابع کش و ریپلای
# =========================
def cache_msg(mid, uid, name, chat_id):
    if not mid: return
    cache[str(mid)] = {
        "uid": str(uid),
        "name": name,
        "chat": str(chat_id),
        "t": time.time()
    }

def find_reply_target(msg, chat_id):
    reply_to = getattr(msg, 'reply_to_message', None)
    if reply_to:
        sid = getattr(reply_to, 'sender_id', None)
        sname = getattr(reply_to, 'sender_name', None) or "کاربر"
        if sid:
            return str(sid), sname

    reply_to_id = getattr(msg, 'reply_to_message_id', None)
    if reply_to_id:
        cached = cache.get(str(reply_to_id))
        if cached:
            return cached.get("uid"), cached.get("name", "کاربر")

    reply_to2 = getattr(msg, 'reply_to', None)
    if reply_to2:
        if isinstance(reply_to2, str):
            cached = cache.get(reply_to2)
            if cached:
                return cached.get("uid"), cached.get("name", "کاربر")
        else:
            sid = getattr(reply_to2, 'sender_id', None)
            sname = getattr(reply_to2, 'sender_name', None) or "کاربر"
            if sid:
                return str(sid), sname

    try:
        for key, val in msg.__dict__.items():
            if 'reply' in key.lower():
                if isinstance(val, str):
                    cached = cache.get(val)
                    if cached:
                        return cached.get("uid"), cached.get("name", "کاربر")
                elif hasattr(val, 'sender_id'):
                    return str(val.sender_id), getattr(val, 'sender_name', 'کاربر')
    except: pass

    return None, None

def find_last_user_in_chat(chat_id, exclude_uid):
    last_user = None
    last_time = 0
    for mid, info in cache.items():
        if info.get("chat") == str(chat_id) and info.get("uid") != str(exclude_uid):
            if info.get("t", 0) > last_time:
                last_time = info.get("t", 0)
                last_user = info
    if last_user:
        return last_user.get("uid"), last_user.get("name", "کاربر")
    return None, None

def get_display_name(uid, info=None):
    """نمایش اسم کاربر - اگه اسم نداره، گوید کوتاه‌شده نشون بده"""
    if info is None:
        info = data["users"].get(str(uid), {})
    name = info.get("name", "")
    username = info.get("username", "")
    
    # اگه اسم معتبر نبود، از گوید کوتاه استفاده کن
    if not name or name == "کاربر" or name.startswith("u0"):
        # گوید رو کوتاه کن
        short = str(uid)[:8] + "..." if len(str(uid)) > 8 else str(uid)
        return f"کاربر `{short}`"
    
    if username:
        return f"{name} (@{username})"
    return name


# =========================
# هندلر اصلی
# =========================
@bot.on_update(filters.text)
async def main_handler(client, update: Update):
    try:
        msg = update.new_message
        text = msg.text.strip() if msg.text else ""
        normalized = text.lower().strip()
        uid = str(msg.sender_id)
        name = getattr(msg, 'sender_name', None) or ""
        username = getattr(msg, 'sender_username', "") or ""
        chat_id = str(update.chat_id)
        msg_id = getattr(msg, 'message_id', None)

        # ✅ اگه اسم خالی بود، یه اسم موقت بذار
        if not name or name.startswith("u0"):
            name = "کاربر"

        # ✅ کش کردن پیام
        if msg_id:
            cache_msg(msg_id, uid, name, chat_id)

        # ثبت چت
        if chat_id not in members["chats"]:
            members["chats"][chat_id] = {"name": f"Chat {chat_id}", "added": time.time()}
            save_members()

        # ✅ ساخت کاربر (اولین بار با get_chat تلاش می‌کنه)
        is_new = await create_user_with_name(uid, chat_id, name)
        
        # ✅ اگه کاربر قدیمی بود و اسمش «کاربر» بود، آپدیت کن
        if not is_new:
            await update_user_name_if_missing(uid, chat_id)
        
        u = data["users"][uid]
        display_name = get_display_name(uid, u)

        # ====== /start ======
        if normalized == "/start":
            welcome = f"سلام {display_name} 🌸\nبه بات شیر یا خط خوش اومدی 🎲\n\n"
            if is_new:
                welcome += f"🎁 {STARTING_COINS} سکه هدیه گرفتی!\n\n"
            welcome += (
                "🎮 **بازی:**\n"
                "«شیر [مقدار]» → شرط روی شیر\n"
                "«خط [مقدار]» → شرط روی خط\n"
                "«زوج [مقدار]» → شرط روی زوج\n"
                "«فرد [مقدار]» → شرط روی فرد\n\n"
                "مثال: `شیر 50`\n"
                "💰 برد = ۲ برابر شرط\n\n"
                "📊 /me — موجودی\n"
                "🏆 /leaderboard — برترین‌ها"
            )
            await update.reply(welcome)
            return

        # ====== /help ======
        if normalized in ["/help", "help", "کمک"]:
            await update.reply(
                "🎲 راهنمای بات شیر یا خط 🎲\n\n"
                "🎮 **بازی:**\n"
                "• شیر [مقدار] — شرط روی شیر\n"
                "• خط [مقدار] — شرط روی خط\n"
                "• زوج [مقدار] — شرط روی زوج\n"
                "• فرد [مقدار] — شرط روی فرد\n\n"
                "مثال: `شیر 50`\n"
                "💰 حداقل شرط: ۱۰ سکه\n"
                "🎁 برد = ۲ برابر شرط\n\n"
                "📊 **دستورات:**\n"
                "• /me — موجودی و آمار\n"
                "• /leaderboard — ۱۰ نفر برتر"
            )
            return

        # ====== /me ======
        if normalized in ["/me", "me", "من", "موجودی"]:
            total_games = u.get("wins", 0) + u.get("losses", 0)
            rate = round((u.get("wins", 0) / total_games * 100), 1) if total_games > 0 else 0
            await update.reply(
                f"👤 **{display_name}**\n\n"
                f"🆔 `{uid}`\n"
                f"🪙 سکه: **{u.get('coins', 0):,}**\n"
                f"🏆 برد: {u.get('wins', 0)}\n"
                f"❌ باخت: {u.get('losses', 0)}\n"
                f"📊 درصد برد: {rate}%\n"
                f"💵 کل شرط: {u.get('total_wagered', 0):,}"
            )
            return

        # ====== /leaderboard ======
        if normalized in ["/leaderboard", "لیدربورد", "top"]:
            users = data["users"]
            if not users:
                await update.reply("هنوز کسی بازی نکرده 🎲")
                return
            sorted_users = sorted(users.items(), key=lambda x: x[1].get("coins", 0), reverse=True)
            msg_text = "🏆 **لیدربورد ۱۰ نفر برتر** 🏆\n\n"
            medals = ["🥇", "🥈", "🥉"]
            for i, (iuid, info) in enumerate(sorted_users[:10], 1):
                medal = medals[i-1] if i <= 3 else f"{i}."
                disp = get_display_name(iuid, info)
                msg_text += f"{medal} {disp} ➜ **{info.get('coins', 0):,}** سکه\n"
            await update.reply(msg_text)
            return

        # ====== ادمین: /reset ======
        if normalized == "/reset":
            if not is_admin(username, uid):
                await update.reply("❌ فقط ادمین!")
                return
            data["users"] = {}
            save_data()
            await update.reply("✅ **کل بات ریست شد!**\nهمه کاربران پاک شدن.")
            return

        # ====== ادمین: /alert ======
        if normalized.startswith("/alert"):
            if not is_admin(username, uid):
                await update.reply("❌ فقط ادمین!")
                return
            alert_text = text.replace("/alert", "", 1).strip()
            if not alert_text:
                await update.reply("⚠️ /alert متن")
                return
            total = len(members.get("chats", {}))
            await update.reply(f"⏳ ارسال به {total} چت...")
            asyncio.create_task(send_alert_broadcast(alert_text, chat_id))
            return

        # ====== ادمین: /addcoin ======
        if normalized.startswith("/addcoin"):
            if not is_admin(username, uid):
                await update.reply("❌ فقط ادمین!")
                return

            parts = text.split()
            tid = None
            amt = None
            rname = "کاربر"

            # حالت ۱: ریپلای
            reply_tid, reply_name = find_reply_target(msg, chat_id)
            if reply_tid:
                tid = reply_tid
                rname = reply_name
                for p in parts[1:]:
                    try:
                        amt = int(p.replace(",", ""))
                        break
                    except:
                        continue
                if amt is None:
                    await update.reply("⚠️ مقدار سکه رو مشخص کن\nمثال: /addcoin 100")
                    return

            # حالت ۲: یوزرنیم + مقدار
            elif len(parts) >= 3:
                target = parts[1].replace("@", "").lower()
                try:
                    amt = int(parts[2].replace(",", ""))
                except:
                    await update.reply("❌ عدد معتبر بده")
                    return
                for iuid, info in data["users"].items():
                    uname_l = info.get("username", "").lower()
                    nname_l = info.get("name", "").lower()
                    if uname_l == target or nname_l == target:
                        tid = iuid
                        rname = info.get("name", "کاربر")
                        break
                if not tid:
                    await update.reply(f"❌ کاربر «{target}» پیدا نشد")
                    return

            # حالت ۳: فقط /addcoin 100 (آخرین کاربر چت)
            elif len(parts) == 2:
                try:
                    amt = int(parts[1].replace(",", ""))
                except:
                    await update.reply(
                        "⚠️ روش استفاده:\n\n"
                        "۱) با یوزرنیم:\n"
                        "   /addcoin @username 100\n\n"
                        "۲) با اسم:\n"
                        "   /addcoin AmirAli 100\n\n"
                        "۳) با ریپلای:\n"
                        "   /addcoin 100"
                    )
                    return
                last_tid, last_name = find_last_user_in_chat(chat_id, uid)
                if last_tid:
                    tid = last_tid
                    rname = last_name
                else:
                    await update.reply(
                        "⚠️ نتونستم کاربر رو تشخیص بدم!\n\n"
                        "روش‌های دیگه:\n"
                        "• /addcoin @username 100\n"
                        "• /addcoin AmirAli 100\n"
                        "• یا ریپلای کن روی پیام کاربر"
                    )
                    return

            else:
                await update.reply(
                    "⚠️ روش استفاده:\n\n"
                    "۱) با یوزرنیم:\n"
                    "   /addcoin @username 100\n\n"
                    "۲) با اسم:\n"
                    "   /addcoin AmirAli 100\n\n"
                    "۳) با ریپلای:\n"
                    "   /addcoin 100"
                )
                return

            if amt is None or amt == 0:
                await update.reply("❌ مقدار نمی‌تونه صفر باشه!")
                return

            if tid not in data["users"]:
                await create_user_with_name(tid, None, rname)

            data["users"][tid]["coins"] = max(0, data["users"][tid].get("coins", 0) + amt)
            save_data()
            uname = get_display_name(tid)

            if amt > 0:
                await update.reply(
                    f"➕ **{amt:,}** سکه به **{uname}** اضافه شد 🪙\n"
                    f"💵 موجودی جدید: **{data['users'][tid]['coins']:,}**"
                )
            else:
                await update.reply(
                    f"➖ **{abs(amt):,}** سکه از **{uname}** کم شد 🪙\n"
                    f"💵 موجودی جدید: **{data['users'][tid]['coins']:,}**"
                )
            return

        # ====== بازی شیر یا خط ======
        parts = text.split()
        if len(parts) == 2:
            bet_type = parts[0].strip().lower()
            try:
                bet_amount = int(parts[1].replace(",", ""))
            except:
                return

            valid_types = {
                "شیر": "شیر", "shir": "شیر", "heads": "شیر",
                "خط": "خط", "khat": "خط", "tails": "خط",
                "زوج": "زوج", "even": "زوج",
                "فرد": "فرد", "odd": "فرد"
            }

            if bet_type not in valid_types:
                return

            user_bet = valid_types[bet_type]

            if bet_amount <= 0:
                await update.reply("❌ تعداد سکه باید > 0 باشه!")
                return
            if bet_amount < MIN_BET:
                await update.reply(f"❌ حداقل شرط {MIN_BET} سکه است!")
                return
            if u.get("coins", 0) < bet_amount:
                await update.reply(
                    f"❌ سکه کافی نداری!\n"
                    f"🪙 موجودی: {u.get('coins', 0):,}\n"
                    f"🎯 شرط: {bet_amount:,}"
                )
                return

            u["coins"] -= bet_amount
            u["total_wagered"] = u.get("total_wagered", 0) + bet_amount

            coin_result = random.choice(["شیر", "خط"])
            coin_number = random.randint(1, 100)
            number_type = "زوج" if coin_number % 2 == 0 else "فرد"

            won = (user_bet == coin_result) or (user_bet == number_type)
            coin_emoji = "🦁" if coin_result == "شیر" else "✂️"

            if won:
                winnings = bet_amount * 2
                u["coins"] = u.get("coins", 0) + winnings
                u["wins"] = u.get("wins", 0) + 1
                save_data()
                await update.reply(
                    f"🎉 **بردی!** 🎉\n\n"
                    f"👤 {display_name}\n"
                    f"🎯 شرط: {user_bet} ({bet_amount:,} سکه)\n"
                    f"{coin_emoji} نتیجه سکه: **{coin_result}**\n"
                    f"🔢 عدد: **{coin_number}** ({number_type})\n\n"
                    f"💰 جایزه: **+{winnings:,}** سکه\n"
                    f"🪙 موجودی جدید: **{u['coins']:,}**"
                )
            else:
                u["losses"] = u.get("losses", 0) + 1
                save_data()
                await update.reply(
                    f"😢 **باختی!**\n\n"
                    f"👤 {display_name}\n"
                    f"🎯 شرط: {user_bet} ({bet_amount:,} سکه)\n"
                    f"{coin_emoji} نتیجه سکه: **{coin_result}**\n"
                    f"🔢 عدد: **{coin_number}** ({number_type})\n\n"
                    f"💸 باخت: **-{bet_amount:,}** سکه\n"
                    f"🪙 موجودی: **{u['coins']:,}**"
                )
            return

    except Exception as e:
        print(f"Handler error: {e}")
        import traceback
        traceback.print_exc()


# =========================
# ارسال اعلان همگانی
# =========================
async def send_alert_broadcast(alert_text, admin_chat):
    sent = 0
    failed = 0
    chats = list(members.get("chats", {}).keys())
    total = len(chats)
    for cid in chats:
        try:
            await bot.send_message(cid, f"🚨 اعلان مهم از طرف مدیریت\n\n{alert_text}")
            sent += 1
        except Exception as e:
            print(f"Alert error to {cid}: {e}")
            failed += 1
        await asyncio.sleep(0.5)
    try:
        await bot.send_message(
            admin_chat,
            f"✅ پایان ارسال!\n✅ موفق: {sent}\n❌ ناموفق: {failed}\n📈 کل: {total}"
        )
    except: pass


# =========================
# تسک ذخیره کش
# =========================
async def cache_saver():
    while True:
        await asyncio.sleep(30)
        save_cache()


# =========================
# اجرا
# =========================
async def main():
    print("🎲 Coin Flip Bot starting...")
    print(f"✅ Loaded {len(data['users'])} users")
    print(f"✅ Loaded {len(cache)} cached messages")
    print(f"✅ Loaded {len(members.get('chats', {}))} chats")
    asyncio.create_task(cache_saver())
    print("🎲 Bot Started!")
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())