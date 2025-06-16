import logging
import aiohttp
import asyncio
import os
import re
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
GROUP_ID = os.getenv("GROUP_ID")  # তোমার গ্রুপ ID এখানে দিবে

user_states = {}
user_sessions = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 বট এ স্বাগতম!\n\nআপনার ইউজারনেম দিন:")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if user_id not in user_states:
        user_states[user_id] = {"step": "username"}
        user_states[user_id]["username"] = text
        await update.message.reply_text("🔐 এখন আপনার পাসওয়ার্ড দিন:")
        return

    if user_states[user_id]["step"] == "username":
        user_states[user_id]["username"] = text
        user_states[user_id]["step"] = "password"
        await update.message.reply_text("🔐 এখন আপনার পাসওয়ার্ড দিন:")
        return

    elif user_states[user_id]["step"] == "password":
        username = user_states[user_id]["username"]
        password = text

        session = aiohttp.ClientSession()
        login_success = await try_login(session, username, password)

        if login_success:
            user_sessions[user_id] = session
            user_states[user_id]["step"] = "logged_in"
            await update.message.reply_text("✅ লগইন সফল হয়েছে! এখন OTP চেক করা শুরু হবে।")
            asyncio.create_task(otp_checker(user_id, session))
        else:
            await update.message.reply_text("❌ লগইন ব্যর্থ হয়েছে! ইউজারনেম বা পাসওয়ার্ড ভুল।")
            await session.close()
            del user_states[user_id]

async def try_login(session, username, password):
    login_url = "http://94.23.120.156/ints/login.php"
    data = {"username": username, "password": password}

    async with session.post(login_url, data=data) as resp:
        if resp.status == 200:
            cookies = session.cookie_jar.filter_cookies(login_url)
            return 'PHPSESSID' in cookies
        return False

last_seen_ids = {}

async def otp_checker(user_id, session):
    while True:
        try:
            url = "http://94.23.120.156/ints/agent/res/data_smscdr.php?fdate1=2025-06-16%2000:00:00&fdate2=2025-06-16%2023:59:59"
            async with session.get(url, headers={"X-Requested-With": "XMLHttpRequest"}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rows = data.get("aaData", [])

                    for row in rows:
                        sms_id = row[0]
                        number = row[1]
                        service = row[2]
                        country = row[3]
                        time = row[4]
                        message = row[5]

                        otp = extract_otp(message)
                        if otp and (user_id not in last_seen_ids or sms_id != last_seen_ids[user_id]):
                            last_seen_ids[user_id] = sms_id
                            text = f"""🎉 নতুন কোপ 🎉

Number: {number}
OTP Code: {otp}
Service: {service}
Country: {country}
Time: {time}
✉️ Message: {message}
"""
                            buttons = [
                                [InlineKeyboardButton("কোপ Done 🎉 ✅", callback_data="done")],
                                [InlineKeyboardButton("Founded By 𝗠𝗿 𝗘𝘃𝗮𝗻 🍁", url="https://t.me/your_channel_link")]
                            ]
                            await context.bot.send_message(chat_id=GROUP_ID, text=text, reply_markup=InlineKeyboardMarkup(buttons))
        except Exception as e:
            logger.error(f"OTP check error: {e}")
        await asyncio.sleep(5)

def extract_otp(message):
    match = re.search(r"\b\d{4,8}\b", message)
    return match.group() if match else None

async def webhook(request):
    data = await request.json()
    await application.update_queue.put(Update.de_json(data, application.bot))
    return web.Response()

application = Application.builder().token(BOT_TOKEN).build()
application.add_handler(CommandHandler("start", start))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

app = web.Application()
app.router.add_post(f"/{BOT_TOKEN}", webhook)

async def start_webhook():
    await application.bot.set_webhook(f"{WEBHOOK_URL}/{BOT_TOKEN}")
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 8080)
    await site.start()

if __name__ == "__main__":
    asyncio.run(start_webhook())
