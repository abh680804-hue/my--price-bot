import os
import json
import logging
import threading
import aiohttp
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ==============================================================================
# تنظیمات اولیه و لاگ‌گیری
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# توکن ربات تلگرام شما
BOT_TOKEN = "8572931929:AAGZjKx62owvCe7WioitOIp0RuKDppuMf5I"
USER_DATA_FILE = "users_schedule.json"


# ==============================================================================
# سرور وب ساده برای زنده نگه داشتن ربات در سرورهای ابری رایگان
# ==============================================================================
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>🤖 ربات تلگرام قیمت طلا و ارز فعال است!</h1>".encode("utf-8"))

    def log_message(self, format, *args):
        pass  # جلوگیری از شلوغ شدن لاگ‌ها


def run_web_server():
    port = int(os.environ.get("PORT", 7860))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    server.serve_forever()


# ==============================================================================
# مدیریت ذخیره‌سازی تنظیمات کاربران
# ==============================================================================
def load_user_settings() -> dict:
    if os.path.exists(USER_DATA_FILE):
        try:
            with open(USER_DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"خطا در خواندن فایل تنظیمات: {e}")
    return {}


def save_user_settings(data: dict) -> None:
    try:
        with open(USER_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"خطا در ذخیره فایل تنظیمات: {e}")


# ==============================================================================
# دریافت قیمت لحظه‌ای و واقعی بازار ایران و جهان
# ==============================================================================
async def fetch_prices() -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    usdt_price = "در دسترس نیست"
    btc_price_usd = "در دسترس نیست"
    eth_price_usd = "در دسترس نیست"
    global_gold_oz = "در دسترس نیست"
    gold_18k_str = "در دسترس نیست"
    coin_emami_str = "در دسترس نیست"
    btc_toman_str = "در دسترس نیست"

    usdt_num = 0
    oz_num = 0.0

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            # ۱. دریافت نرخ لحظه‌ای تتر (دلار آزاد) از نوبیتکس و تترلند
            try:
                async with session.get("https://api.nobitex.ir/v2/orderbook/USDTIRT", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data.get("status") == "ok":
                            usdt_num = int(float(data["lastTradePrice"]) / 10)
                            usdt_price = f"{usdt_num:,} تومان"
            except Exception as e:
                logger.error(f"Nobitex USDT Error: {e}")

            # منبع پشتیبان تترلند در صورت نیاز
            if usdt_num == 0:
                try:
                    async with session.get("https://api.tetherland.com/currencies", timeout=10) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            usdt_num = int(data["data"]["currencies"]["USDT"]["price"])
                            usdt_price = f"{usdt_num:,} تومان"
                except Exception as e:
                    logger.error(f"Tetherland Error: {e}")

            # ۲. دریافت قیمت بیت‌کوین، اتریوم و انس جهانی طلا از Coinbase
            try:
                async with session.get("https://api.coinbase.com/v2/prices/BTC-USD/spot", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        btc_val = float(data["data"]["amount"])
                        btc_price_usd = f"${btc_val:,.0f}"
                        if usdt_num > 0:
                            btc_toman_str = f"{int(btc_val * usdt_num):,} تومان"
            except Exception as e:
                logger.error(f"BTC Error: {e}")

            try:
                async with session.get("https://api.coinbase.com/v2/prices/ETH-USD/spot", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        eth_val = float(data["data"]["amount"])
                        eth_price_usd = f"${eth_val:,.0f}"
            except Exception as e:
                logger.error(f"ETH Error: {e}")

            try:
                async with session.get("https://api.coinbase.com/v2/prices/PAXG-USD/spot", timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        oz_num = float(data["data"]["amount"])
                        global_gold_oz = f"${oz_num:,.1f}"
            except Exception as e:
                logger.error(f"Gold Oz Error: {e}")

            # ۳. محاسبه دقیق طلای ۱۸ عیار و سکه امامی بر اساس نرخ روز دلار و انس
            if usdt_num > 0 and oz_num > 0:
                gram_18k = int(((oz_num / 31.1035) * usdt_num * 0.75) * 1.015)
                gold_18k_str = f"{gram_18k:,} تومان"

                coin_emami = int(((oz_num / 31.1035) * usdt_num * 8.133 * 0.9) * 1.14)
                coin_emami_str = f"{coin_emami:,} تومان"

            now = datetime.now().strftime("%Y/%m/%d - %H:%M")
            message = (
                f"📊 **گزارش لحظه‌ای بازار ارز، طلا و کریپتو**\n"
                f"🕒 زمان: `{now}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 **دلار / تتر (بازار آزاد):** `{usdt_price}`\n"
                f"🌕 **انس جهانی طلا:** `{global_gold_oz}`\n"
                f"✨ **طلای ۱۸ عیار (هر گرم):** `{gold_18k_str}`\n"
                f"🪙 **سکه امامی:** `{coin_emami_str}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"₿ **بیت‌کوین (جهانی):** `{btc_price_usd}`\n"
                f"₿ **بیت‌کوین (تومان):** `{btc_toman_str}`\n"
                f"Ξ **اتریوم (جهانی):** `{eth_price_usd}`\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"⚙️ تنظیم زمان ارسال خودکار: /settings"
            )
            return message

    except Exception as e:
        logger.error(f"خطای کلی: {e}")
        return "❌ خطا در ارتباط با سرورهای قیمت."


# ==============================================================================
# توابع زمان‌بندی (Job Queue)
# ==============================================================================
async def scheduled_price_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    chat_id = job.chat_id
    price_message = await fetch_prices()
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=price_message,
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"خطا در ارسال پیام زمان‌بندی شده به کاربر {chat_id}: {e}")


def schedule_user_job(application: Application, chat_id: int, interval_minutes: int) -> None:
    job_name = f"price_job_{chat_id}"
    current_jobs = application.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()

    if interval_minutes > 0:
        application.job_queue.run_repeating(
            scheduled_price_job,
            interval=interval_minutes * 60,
            first=10,
            chat_id=chat_id,
            name=job_name
        )


# ==============================================================================
# دستورات و دکمه‌های شیشه‌ای ربات
# ==============================================================================
def get_settings_keyboard(current_interval: int) -> InlineKeyboardMarkup:
    options = [
        ("هر ۱۵ دقیقه", 15),
        ("هر ۳۰ دقیقه", 30),
        ("هر ۱ ساعت (پیش‌فرض)", 60),
        ("هر ۳ ساعت", 180),
        ("هر ۶ ساعت", 360),
        ("هر ۱۲ ساعت", 720),
        ("هر ۲۴ ساعت", 1440),
        ("🔕 خاموش کردن ارسال خودکار", 0),
    ]

    keyboard = []
    for label, minutes in options:
        prefix = "✅ " if current_interval == minutes else ""
        keyboard.append([
            InlineKeyboardButton(f"{prefix}{label}", callback_data=f"set_time_{minutes}")
        ])

    keyboard.append([InlineKeyboardButton("🔄 دریافت قیمت همین الان", callback_data="get_now")])
    return InlineKeyboardMarkup(keyboard)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    settings = load_user_settings()

    if str(chat_id) not in settings:
        settings[str(chat_id)] = 60
        save_user_settings(settings)
        schedule_user_job(context.application, chat_id, 60)

    current_interval = settings[str(chat_id)]
    welcome_text = (
        "👋 **سلام! به ربات اعلام لحظه‌ای قیمت طلا، دلار و ارز خوش آمدید.**\n\n"
        "من می‌توانم به صورت خودکار و در بازه‌های زمانی دلخواه شما، آخرین قیمت‌های بازار را برایتان ارسال کنم.\n\n"
        "📌 **دستورات ربات:**\n"
        "• /price - دریافت فوری قیمت‌های لحظه‌ای\n"
        "• /settings - تنظیم زمان‌بندی ارسال خودکار\n\n"
        "👇 از منوی زیر می‌توانید زمان ارسال خودکار را تنظیم کنید:"
    )

    await update.message.reply_text(
        welcome_text,
        reply_markup=get_settings_keyboard(current_interval),
        parse_mode="Markdown"
    )


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    wait_msg = await update.message.reply_text("⏳ در حال دریافت آخرین قیمت‌های بازار...")
    price_message = await fetch_prices()
    await wait_msg.edit_text(price_message, parse_mode="Markdown")


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    settings = load_user_settings()
    current_interval = settings.get(str(chat_id), 0)

    await update.message.reply_text(
        "⚙️ **تنظیمات زمان‌بندی ارسال قیمت:**\n"
        "لطفاً انتخاب کنید ربات هر چند وقت یک‌بار قیمت‌ها را برای شما ارسال کند:",
        reply_markup=get_settings_keyboard(current_interval),
        parse_mode="Markdown"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    chat_id = update.effective_chat.id
    data = query.data

    if data == "get_now":
        await query.message.reply_text("⏳ در حال استعلام قیمت...")
        price_message = await fetch_prices()
        await query.message.reply_text(price_message, parse_mode="Markdown")
        return

    if data.startswith("set_time_"):
        minutes = int(data.split("_")[2])
        settings = load_user_settings()
        settings[str(chat_id)] = minutes
        save_user_settings(settings)
        schedule_user_job(context.application, chat_id, minutes)

        status_text = (
            "🔕 ارسال خودکار غیرفعال شد."
            if minutes == 0
            else f"✅ زمان‌بندی با موفقیت روی **هر {minutes} دقیقه** یک‌بار تنظیم شد."
        )

        await query.edit_message_text(
            text=f"{status_text}\n\nمی‌توانید هر زمان که خواستید از منوی زیر تایم را تغییر دهید:",
            reply_markup=get_settings_keyboard(minutes),
            parse_mode="Markdown"
        )


def main() -> None:
    # اجرای سرور وب در پس‌زمینه برای سازگاری با سرورهای ابری
    threading.Thread(target=run_web_server, daemon=True).start()

    application = Application.builder().token(BOT_TOKEN).build()

    saved_settings = load_user_settings()
    for chat_id_str, interval in saved_settings.items():
        if interval > 0:
            schedule_user_job(application, int(chat_id_str), interval)

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 ربات با موفقیت روشن شد و در حال گوش دادن به پیام‌هاست...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
