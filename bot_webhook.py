import asyncio
import logging
import uuid
import os
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, LabeledPrice
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

# ==================== НАСТРОЙКИ ====================
# Задай эти переменные в настройках хостинга (Environment Variables).
BOT_TOKEN = os.getenv("9286582697:AAFin20uHLeAwN8EG-KIDABZKi5SWOOMmEE", "")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").rstrip("/")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "change_this_secret_123456")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", "8080"))

# Поддержка и менеджер
SUPPORT_USERNAME = "NotCoin"
MANAGER_USERNAME = "qwegyq"

# Имя файла видео (положи видео рядом с bot.py)
VIDEO_FILENAME = "VID_20261124_212025_970.mp4"

# ==================== ХРАНИЛИЩЕ (в памяти) ====================
# deals = {
#   "deal_id": {
#       "creator_id": 123,
#       "buyer_id": None,
#       "seller_id": None,
#       "item": None,
#       "amount": None,
#       "currency": None,
#       "status": "created" | "waiting_payment" | "paid" | "completed"
#   }
# }
deals = {}
user_balances = {}  # {user_id: {"stars": 0, "ton": 0, "rub": 0, "usd": 0, "crypto": 0}}

# ==================== СОСТОЯНИЯ ====================
class DealStates(StatesGroup):
    waiting_item = State()
    waiting_amount = State()
    waiting_currency = State()

# ==================== КЛАВИАТУРЫ ====================
def green_button(text: str, callback_data: str) -> InlineKeyboardButton:
    """Создаёт зелёную кнопку с эмодзи"""
    return InlineKeyboardButton(text=text, callback_data=callback_data)

def role_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [green_button("🛒 Я покупатель", f"role_buyer_{deal_id}")],
        [green_button("💰 Я продавец", f"role_seller_{deal_id}")]
    ])

def currency_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            green_button("⭐ Stars", f"curr_stars_{deal_id}"),
            green_button("💎 TON", f"curr_ton_{deal_id}")
        ],
        [
            green_button("₽ Рубли", f"curr_rub_{deal_id}"),
            green_button("$ Доллары", f"curr_usd_{deal_id}")
        ],
        [
            green_button("🪙 Крипта", f"curr_crypto_{deal_id}")
        ]
    ])

def pay_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [green_button("✅ Оплатить", f"pay_{deal_id}")]
    ])

def confirm_keyboard(deal_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [green_button("✅ Подтвердить получение товара", f"confirm_{deal_id}")]
    ])

def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [green_button("➕ Создать сделку", "create_deal")],
        [green_button("💼 Мой баланс", "my_balance")],
        [green_button("🆘 Поддержка", "support")]
    ])

# ==================== БОТ ====================
logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN or "000000:PLACEHOLDER", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=MemoryStorage())

# ---------- /start ----------
@dp.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    
    # Отправляем видео
    try:
        video = FSInputFile(VIDEO_FILENAME)
        await message.answer_video(
            video=video,
            caption=(
                f"<b>Добро пожаловать!</b>\n\n"
                f"Это бот безопасных сделок.\n"
                f"Создавай сделки, оплачивай и получай товар через менеджера.\n\n"
                f"🆘 Поддержка: @{SUPPORT_USERNAME}"
            )
        )
    except Exception as e:
        # Если видео не найдено — просто текст
        await message.answer(
            f"<b>Добро пожаловать!</b>\n\n"
            f"Это бот безопасных сделок.\n"
            f"Создавай сделки, оплачивай и получай товар через менеджера.\n\n"
            f"🆘 Поддержка: @{SUPPORT_USERNAME}\n\n"
            f"<i>(Видео не найдено: {e})</i>"
        )

    # Проверяем deep-link (сделка)
    args = command.args
    if args and args.startswith("deal_"):
        deal_id = args
        if deal_id not in deals:
            await message.answer("❌ Сделка не найдена или уже завершена.")
            return
        
        deal = deals[deal_id]
        if deal["status"] != "created":
            await message.answer("❌ Эта сделка уже в процессе.")
            return

        await message.answer(
            f"<b>Сделка найдена!</b>\n\n"
            f"Выберите свою роль:",
            reply_markup=role_keyboard(deal_id)
        )
    else:
        await message.answer(
            "Выберите действие:",
            reply_markup=main_menu_keyboard()
        )

# ---------- Главное меню ----------
@dp.callback_query(F.data == "create_deal")
async def create_deal_callback(callback: CallbackQuery):
    deal_id = f"deal_{uuid.uuid4().hex[:8]}"
    deals[deal_id] = {
        "creator_id": callback.from_user.id,
        "buyer_id": None,
        "seller_id": None,
        "item": None,
        "amount": None,
        "currency": None,
        "status": "created"
    }
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={deal_id}"
    
    await callback.message.answer(
        f"✅ <b>Сделка создана!</b>\n\n"
        f"Отправь эту ссылку второму участнику:\n"
        f"<code>{link}</code>\n\n"
        f"Или нажми кнопку ниже, чтобы сам выбрать роль:",
        reply_markup=role_keyboard(deal_id)
    )
    await callback.answer()

@dp.callback_query(F.data == "my_balance")
async def my_balance(callback: CallbackQuery):
    user_id = callback.from_user.id
    bal = user_balances.get(user_id, {"stars": 0, "ton": 0, "rub": 0, "usd": 0, "crypto": 0})
    
    text = (
        f"<b>💼 Ваш баланс:</b>\n\n"
        f"⭐ Stars: <b>{bal['stars']}</b>\n"
        f"💎 TON: <b>{bal['ton']}</b>\n"
        f"₽ Рубли: <b>{bal['rub']}</b>\n"
        f"$ Доллары: <b>{bal['usd']}</b>\n"
        f"🪙 Крипта: <b>{bal['crypto']}</b>"
    )
    await callback.message.answer(text)
    await callback.answer()

@dp.callback_query(F.data == "support")
async def support_callback(callback: CallbackQuery):
    await callback.message.answer(
        f"🆘 Написать в поддержку:\n@{SUPPORT_USERNAME}"
    )
    await callback.answer()

# ---------- Выбор роли ----------
@dp.callback_query(F.data.startswith("role_buyer_"))
async def role_buyer(callback: CallbackQuery, state: FSMContext):
    deal_id = callback.data.replace("role_buyer_", "")
    if deal_id not in deals:
        await callback.answer("Сделка не найдена", show_alert=True)
        return
    
    deal = deals[deal_id]
    if deal["buyer_id"]:
        await callback.answer("Роль покупателя уже занята", show_alert=True)
        return
    
    deal["buyer_id"] = callback.from_user.id
    await state.set_state(DealStates.waiting_item)
    await state.update_data(deal_id=deal_id)
    
    await callback.message.answer(
        "🛒 Вы — <b>покупатель</b>.\n\n"
        "Отправьте описание товара или ссылку на NFT:"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("role_seller_"))
async def role_seller(callback: CallbackQuery, state: FSMContext):
    deal_id = callback.data.replace("role_seller_", "")
    if deal_id not in deals:
        await callback.answer("Сделка не найдена", show_alert=True)
        return
    
    deal = deals[deal_id]
    if deal["seller_id"]:
        await callback.answer("Роль продавца уже занята", show_alert=True)
        return
    
    deal["seller_id"] = callback.from_user.id
    await state.set_state(DealStates.waiting_amount)
    await state.update_data(deal_id=deal_id)
    
    await callback.message.answer(
        "💰 Вы — <b>продавец</b>.\n\n"
        "Укажите сумму (только число):"
    )
    await callback.answer()

# ---------- Покупатель указывает товар ----------
@dp.message(DealStates.waiting_item)
async def process_item(message: Message, state: FSMContext):
    data = await state.get_data()
    deal_id = data.get("deal_id")
    if not deal_id or deal_id not in deals:
        await message.answer("Ошибка сделки. Начните заново /start")
        await state.clear()
        return
    
    deals[deal_id]["item"] = message.text
    await state.set_state(DealStates.waiting_currency)
    
    await message.answer(
        "Выберите способ оплаты:",
        reply_markup=currency_keyboard(deal_id)
    )

# ---------- Выбор валюты ----------
@dp.callback_query(F.data.startswith("curr_"))
async def process_currency(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    currency = parts[1]
    deal_id = "_".join(parts[2:])
    
    if deal_id not in deals:
        await callback.answer("Сделка не найдена", show_alert=True)
        return
    
    deals[deal_id]["currency"] = currency
    await state.clear()
    
    deal = deals[deal_id]
    
    # Если уже есть сумма от продавца — предлагаем оплатить
    if deal["amount"] is not None:
        await send_payment_offer(deal_id)
    else:
        await callback.message.answer(
            f"✅ Товар и способ оплаты сохранены.\n"
            f"Ожидаем, пока продавец укажет сумму..."
        )
    
    await callback.answer()

# ---------- Продавец указывает сумму ----------
@dp.message(DealStates.waiting_amount)
async def process_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    deal_id = data.get("deal_id")
    if not deal_id or deal_id not in deals:
        await message.answer("Ошибка сделки. Начните заново /start")
        await state.clear()
        return
    
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите корректное число (например: 1500)")
        return
    
    deals[deal_id]["amount"] = amount
    await state.clear()
    
    deal = deals[deal_id]
    
    await message.answer(f"✅ Сумма <b>{amount}</b> сохранена.")
    
    # Если уже есть товар и валюта — предлагаем оплату покупателю
    if deal["item"] and deal["currency"]:
        await send_payment_offer(deal_id)
    else:
        await message.answer("Ожидаем данные от покупателя...")

async def send_payment_offer(deal_id: str):
    deal = deals[deal_id]
    if not deal["buyer_id"] or not deal["amount"] or not deal["currency"]:
        return
    
    currency_names = {
        "stars": "⭐ Stars",
        "ton": "💎 TON",
        "rub": "₽ Рубли",
        "usd": "$ Доллары",
        "crypto": "🪙 Крипта"
    }
    
    text = (
        f"<b>Сделка готова к оплате</b>\n\n"
        f"📦 Товар: {deal['item']}\n"
        f"💵 Сумма: <b>{deal['amount']}</b> {currency_names.get(deal['currency'], deal['currency'])}\n\n"
        f"Нажмите кнопку ниже, чтобы оплатить:"
    )
    
    try:
        await bot.send_message(
            deal["buyer_id"],
            text,
            reply_markup=pay_keyboard(deal_id)
        )
    except Exception as e:
        logging.error(f"Не удалось отправить предложение оплаты: {e}")

# ---------- Оплата ----------
@dp.callback_query(F.data.startswith("pay_"))
async def process_pay(callback: CallbackQuery):
    deal_id = callback.data.replace("pay_", "")
    if deal_id not in deals:
        await callback.answer("Сделка не найдена", show_alert=True)
        return

    deal = deals[deal_id]
    if deal["buyer_id"] != callback.from_user.id:
        await callback.answer("Только покупатель может сообщить об оплате", show_alert=True)
        return

    if deal["status"] != "created":
        await callback.answer("По этой сделке уже отправлено сообщение об оплате", show_alert=True)
        return

    # Важно: нажатие кнопки не является подтверждением реального платежа.
    deal["status"] = "payment_reported"

    await callback.message.edit_text(
        "<b>Сообщение об оплате отправлено.</b>\\n\\n"
        "Платёж ещё не проверен. Дождитесь подтверждения менеджера "
        "или продавца после фактической проверки поступления средств."
    )

    if deal["seller_id"]:
        await bot.send_message(
            deal["seller_id"],
            "⚠️ <b>Покупатель сообщил об оплате.</b>\\n\\n"
            f"📦 Товар: {deal['item']}\\n"
            f"💵 Сумма: {deal['amount']}\\n\\n"
            "Это НЕ подтверждение платежа. Проверьте поступление денег "
            "в своём платёжном сервисе и не передавайте товар до проверки."
        )

    await callback.answer("Сообщение отправлено")


# ---------- Подтверждение получения ----------
@dp.callback_query(F.data.startswith("confirm_"))
async def process_confirm(callback: CallbackQuery):
    deal_id = callback.data.replace("confirm_", "")
    if deal_id not in deals:
        await callback.answer("Сделка не найдена", show_alert=True)
        return
    
    deal = deals[deal_id]
    
    if deal["buyer_id"] != callback.from_user.id:
        await callback.answer("Только покупатель может подтвердить", show_alert=True)
        return
    
    if deal["status"] != "paid":
        await callback.answer("Оплата ещё не подтверждена менеджером", show_alert=True)
        return
    
    deal["status"] = "completed"
    
    await callback.message.edit_text(
        "✅ <b>Сделка успешно завершена!</b>\n\n"
        f"Спасибо за использование бота.\n"
        f"Поддержка: @{SUPPORT_USERNAME}"
    )
    
    # Уведомляем продавца
    if deal["seller_id"]:
        try:
            await bot.send_message(
                deal["seller_id"],
                f"✅ Покупатель подтвердил получение товара.\n"
                f"Сделка <code>{deal_id}</code> завершена."
            )
        except:
            pass
    
    await callback.answer("Подтверждено!")

# ---------- Команда /create (альтернатива) ----------
@dp.message(Command("create"))
async def cmd_create(message: Message):
    deal_id = f"deal_{uuid.uuid4().hex[:8]}"
    deals[deal_id] = {
        "creator_id": message.from_user.id,
        "buyer_id": None,
        "seller_id": None,
        "item": None,
        "amount": None,
        "currency": None,
        "status": "created"
    }
    
    bot_info = await bot.get_me()
    link = f"https://t.me/{bot_info.username}?start={deal_id}"
    
    await message.answer(
        f"✅ <b>Сделка создана!</b>\n\n"
        f"Отправь эту ссылку второму участнику:\n"
        f"<code>{link}</code>\n\n"
        f"Или выбери роль сам:",
        reply_markup=role_keyboard(deal_id)
    )

# ---------- Запуск через WEBHOOK ----------
async def on_startup(app: web.Application):
    if not BOT_TOKEN:
        raise RuntimeError("Не задана переменная окружения BOT_TOKEN")
    if not WEBHOOK_URL:
        raise RuntimeError("Не задана переменная окружения WEBHOOK_URL")
    await bot.set_webhook(
        url=f"{WEBHOOK_URL}{WEBHOOK_PATH}",
        secret_token=WEBHOOK_SECRET
    )
    logging.info("Webhook установлен: %s%s", WEBHOOK_URL, WEBHOOK_PATH)


async def on_shutdown(app: web.Application):
    await bot.delete_webhook()
    await bot.session.close()


def create_app() -> web.Application:
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=WEBHOOK_SECRET
    ).register(app, path=WEBHOOK_PATH)

    setup_application(app, dp, bot=bot)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    application = create_app()
    web.run_app(application, host=WEB_SERVER_HOST, port=WEB_SERVER_PORT)
