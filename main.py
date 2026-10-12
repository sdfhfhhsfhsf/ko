import os
import asyncio
import logging
import random
import json
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# تنظیمات اصلی ربات
TOKEN = "8507497335:AAGAAyTag5KuSFFGJpUijuOTgDzU6UeCHOg"
ADMIN_ID = 8854073031

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())
logging.basicConfig(level=logging.INFO)

# فایل‌های ذخیره‌سازی برای استفاده از Volume در Railway
DATA_FILE = "database.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # تبدیل تاریخ‌های ذخیره شده به فرمت datetime
                for uid in data.get("users", {}):
                    if data["users"][uid]["last_claim"]:
                        data["users"][uid]["last_claim"] = datetime.fromisoformat(data["users"][uid]["last_claim"])
                    else:
                        data["users"][uid]["last_claim"] = datetime.min
                return data
        except Exception:
            pass
    return {"users": {}, "gift_codes": {}}

def save_data():
    # تبدیل تاریخ‌ها به رشته برای ذخیره در JSON
    serializable_users = {}
    for uid, info in db["users"].items():
        serializable_users[str(uid)] = {
            "sant": info["sant"],
            "last_claim": info["last_claim"].isoformat() if isinstance(info["last_claim"], datetime) else str(datetime.min)
        }
    
    # تبدیل ست‌ها به لیست در کدهای هدیه
    serializable_gifts = {}
    for code, ginfo in db["gift_codes"].items():
        serializable_gifts[code] = {
            "sant": ginfo["sant"],
            "limit": ginfo["limit"],
            "used_by": list(ginfo["used_by"])
        }

    data_to_save = {
        "users": serializable_users,
        "gift_codes": serializable_gifts
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)

# بارگذاری اولیه اطلاعات از فایل (دیتابیس محلی)
raw_db = load_data()
users_db = {int(k): {"sant": v["sant"], "last_claim": v["last_claim"]} for k, v in raw_db.get("users", {}).items()}
gift_codes = {k: {"sant": v["sant"], "limit": v["limit"], "used_by": set(v["used_by"])} for k, v in raw_db.get("gift_codes", {}).items()}

active_games = {}      # ساختار بازی‌های فعال: {game_id: {"creator": id, "amount": int}}

# حالت‌های FSM (مدیریت مراحل پنل ادمین و دریافت کد هدیه)
class AdminPanel(StatesGroup):
    waiting_for_code = State()
    waiting_for_limit = State()
    waiting_for_sant = State()

class UserGift(StatesGroup):
    waiting_for_code_input = State()

# دستور استارت
@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {"sant": 10, "last_claim": datetime.min}
        save_data()

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 وارد کردن کد هدیه", callback_data="enter_gift")],
        [InlineKeyboardButton(text="➕ افزودن ربات به گروه خود", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")]
    ])
    
    await message.answer(
        "سلام! به ربات شرطی و سانتی خوش آمدید.\n\n"
        "📖 **راهنمای دستورات گروه:**\n"
        "• `کی ر` یا `کیر`: دریافت سانت شانسی هر ۵ ساعت\n"
        "• `بازی [تعداد]` (مثل `بازی 20`): ساخت بازی شرطی جدید\n"
        "• `سانت`: مشاهده موجودی سانت خود\n\n"
        "برای زدن کدهای هدیه و مدیریت به پیوی ربات مراجعه کنید:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

# دستور پنل مدیریت (مخصوص آیدی شما)
@dp.message(Command("panel"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return await message.answer("شما دسترسی به این پنل ندارید.")
    
    await state.set_state(AdminPanel.waiting_for_code)
    await message.answer("🔧 **پنل مدیریت مالک**\n\nلطفاً متن یا نام **کد هدیه** را ارسال کنید:")

@dp.message(AdminPanel.waiting_for_code)
async def process_gift_code(message: Message, state: FSMContext):
    await state.update_data(code=message.text.strip())
    await state.set_state(AdminPanel.waiting_for_limit)
    await message.answer("ظرفیت این کد هدیه (تعداد مجاز استفاده‌کنندگان) را به صورت عدد بفرستید:")

@dp.message(AdminPanel.waiting_for_limit)
async def process_gift_limit(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("لطفاً فقط یک عدد صحیح وارد کنید:")
    await state.update_data(limit=int(message.text))
    await state.set_state(AdminPanel.waiting_for_sant)
    await message.answer("مقدار سانتی که این کد هدیه به هر کاربر می‌دهد را وارد کنید:")

@dp.message(AdminPanel.waiting_for_sant)
async def process_gift_sant(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("لطفاً فقط یک عدد صحیح وارد کنید:")
    
    data = await state.get_data()
    code = data["code"]
    limit = data["limit"]
    sant = int(message.text)
    
    gift_codes[code] = {"sant": sant, "limit": limit, "used_by": set()}
    save_data()
    await state.clear()
    
    await message.answer(f"✅ کد هدیه `{code}` ساخته شد!\nظرفیت: {limit} نفر\nمقدار جایزه: {sant} سانت", parse_mode="Markdown")

# دکمه ورود کد هدیه در پیوی
@dp.callback_query(F.data == "enter_gift")
async def ask_for_gift(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserGift.waiting_for_code_input)
    await callback.message.answer("لطفاً کد هدیه خود را ارسال کنید:")
    await callback.answer()

@dp.message(UserGift.waiting_for_code_input)
async def apply_gift_code(message: Message, state: FSMContext):
    user_id = message.from_user.id
    code = message.text.strip()
    await state.clear()

    if code not in gift_codes:
        return await message.answer("❌ این کد هدیه وجود ندارد یا اشتباه است.")
    
    gift = gift_codes[code]
    if user_id in gift["used_by"]:
        return await message.answer("⚠️ شما قبلاً از این کد هدیه استفاده کرده‌اید.")
    
    if len(gift["used_by"]) >= gift["limit"]:
        return await message.answer("❌ کد هدیه تمام شده است (ظرفیت تکمیل شده).")
    
    # اعمال هدیه به کاربر
    gift["used_by"].add(user_id)
    if user_id not in users_db:
        users_db[user_id] = {"sant": 0, "last_claim": datetime.min}
    
    users_db[user_id]["sant"] += gift["sant"]
    save_data()
    
    await message.answer(f"🎉 تبریک! {gift['sant']} سانت به شما داده شد.\nموجودی جدید شما: **{users_db[user_id]['sant']}** سانت", parse_mode="Markdown")

# دستور مشاهده موجودی سانت
@dp.message(F.text.lower() == "سانت")
async def check_sant(message: Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {"sant": 0, "last_claim": datetime.min}
        save_data()
    
    await message.reply(f"📏 موجودی سانت شما: **{users_db[user_id]['sant']}** سانت", parse_mode="Markdown")

# دستور گرفتن سانت شانسی هر ۵ ساعت (کیر / کی ر)
@dp.message(F.text.lower().in_(["کیر", "کی ر"]))
async def claim_sant(message: Message):
    user_id = message.from_user.id
    now = datetime.now()

    if user_id not in users_db:
        users_db[user_id] = {"sant": 0, "last_claim": datetime.min}

    last_time = users_db[user_id]["last_claim"]
    if now - last_time < timedelta(hours=5):
        remaining = timedelta(hours=5) - (now - last_time)
        hours, remainder = divmod(int(remaining.total_seconds()), 3600)
        minutes = remainder // 60
        return await message.reply(f"⏳ شما هر ۵ ساعت یک‌بار می‌توانید سانت بگیرید. لطفاً {hours} ساعت و {minutes} دقیقه دیگر صبر کنید.")

    # احتمال بیشتر برای اعداد ۱ تا ۳۰ نسبت به ۳۱ تا ۷۰
    weights = [3 if i <= 30 else 1 for i in range(1, 71)]
    sant_amount = random.choices(range(1, 71), weights=weights)[0]

    users_db[user_id]["sant"] += sant_amount
    users_db[user_id]["last_claim"] = now
    save_data()

    await message.reply(f"🍆 ربات به شما **{sant_amount}** سانت شانسی هدیه داد!\nموجودی کل: {users_db[user_id]['sant']} سانت", parse_mode="Markdown")

# دستور ساخت بازی (بازی [عدد])
@dp.message(F.text.regexp(r"^بازی\s+(\d+)$"))
async def create_game(message: Message):
    user_id = message.from_user.id
    if user_id not in users_db:
        users_db[user_id] = {"sant": 0, "last_claim": datetime.min}
        save_data()

    parts = message.text.split()
    amount = int(parts[1])

    if users_db[user_id]["sant"] < amount:
        return await message.reply("❌ موجودی ناکافی هست!")

    # کسر سانت از سازنده
    users_db[user_id]["sant"] -= amount
    save_data()
    
    game_id = f"{user_id}_{int(datetime.now().timestamp())}"

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📥 ورود به بازی", callback_data=f"join_{game_id}"),
            InlineKeyboardButton(text="❌ لغو", callback_data=f"cancel_{game_id}")
        ]
    ])

    sent_msg = await message.answer(
        f"🎲 بازی {amount} سانت ساخته شد!\n"
        f"👤 سازنده: {message.from_user.full_name}\n\n"
        f"برای لغو روی لغو و برای پیوستن روی ورود بزنید.",
        reply_markup=keyboard
    )

    active_games[game_id] = {
        "creator": user_id,
        "amount": amount,
        "msg_id": sent_msg.message_id
    }

# مدیریت دکمه‌های شیشه‌ای بازی (لغو و ورود)
@dp.callback_query(F.data.startswith("cancel_") | F.data.startswith("join_"))
async def handle_game_callbacks(callback: CallbackQuery):
    data_parts = callback.data.split("_")
    action = data_parts[0]
    game_id = "_".join(data_parts[1:])

    if game_id not in active_games:
        return await callback.answer("این بازی دیگر وجود ندارد یا پایان یافته است.", show_alert=True)

    game = active_games[game_id]
    user_id = callback.from_user.id

    if action == "cancel":
        if user_id != game["creator"]:
            return await callback.answer("فقط سازنده بازی می‌تواند آن را لغو کند!", show_alert=True)
        
        # بازگشت سانت به سازنده
        users_db[game["creator"]]["sant"] += game["amount"]
        save_data()
        del active_games[game_id]
        
        await callback.message.edit_text("❌ بازی توسط سازنده لغو شد و سانت‌ها عودت داده شد.")
        await callback.answer("بازی لغو شد.")

    elif action == "join":
        if user_id == game["creator"]:
            return await callback.answer("خود سازنده نمی‌تواند ورود بزند!", show_alert=True)

        if user_id not in users_db:
            users_db[user_id] = {"sant": 0, "last_claim": datetime.min}
            save_data()

        if users_db[user_id]["sant"] < game["amount"]:
            return await callback.answer("❌ موجودی شما برای ورود به این بازی کافی نیست!", show_alert=True)

        # کسر موجودی از شرکت‌کننده
        users_db[user_id]["sant"] -= game["amount"]

        # تعیین رندوم برنده و انتقال دوبرابر مبلغ به او
        winner_id = random.choice([game["creator"], user_id])
        prize = game["amount"] * 2
        users_db[winner_id]["sant"] += prize
        save_data()

        winner_name = (await bot.get_chat(winner_id)).full_name

        del active_games[game_id]
        await callback.message.edit_text(
            f"🏆 بازی به اتمام رسید!\n"
            f"💰 مبلغ کل جایزه: {prize} سانت\n"
            f"👑 برنده خوش‌شانس: **{winner_name}**",
            parse_mode="Markdown"
        )
        await callback.answer("بازی با موفقیت انجام شد!")

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
