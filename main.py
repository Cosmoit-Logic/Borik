# bot.py
import asyncio
import json
import logging
import traceback
import os
from contextlib import suppress
from playwright.async_api import async_playwright

from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

import aiohttp
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, ChatMemberUpdated, FSInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import database as db

# --- Настройка и инициализация ---
logging.basicConfig(level=logging.INFO)
bot = Bot(token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

# --- Глобальные переменные и константы ---
current_alerts_state = {}
UKRAINE_REGIONS = [
    "Вінницька область", "Волинська область", "Дніпропетровська область", "Донецька область",
    "Житомирська область", "Закарпатська область", "Запорізька область", "Івано-Франківська область",
    "Київська область", "Кіровоградська область", "Луганська область", "Львівська область",
    "Миколаївська область", "Одеська область", "Полтавська область", "Рівненська область",
    "Сумська область", "Тернопільська область", "Харківська область", "Херсонська область",
    "Хмельницька область", "Черкаська область", "Чернівецька область", "Чернігівська область",
    "м. Київ", "Автономна Республіка Крим"
]

MESSAGE_TYPES = {
    "alert_message": "🚨 Повідомлення про тривогу",
    "end_alert_message": "✅ Повідомлення про відбій",
    "artillery_message": "💥 Повідомлення про артобстріл",
    "end_artillery_message": "🔰 Повідомлення про відбій артобстрілу"
}

# --- Машина состояний (FSM) для редактирования сообщений ---
class MessageSettings(StatesGroup):
    waiting_for_template = State()

# --- Функция создания скриншота ---
async def take_alert_map_screenshot() -> str | None:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.set_viewport_size({"width": 1280, "height": 900})
            await page.goto(config.ALERTS_MAP_URL, timeout=60000, wait_until="networkidle")
            
            screenshot_path = "alerts_map.png"
            await page.locator("#map").screenshot(path=screenshot_path)
            await browser.close()
            logging.info(f"Скріншот карти збережено: {screenshot_path}")
            return screenshot_path
    except Exception as e:
        logging.error(f"Помилка при створенні скріншоту: {e}")
        return None

# --- Вспомогательные функции для создания меню ---

async def _get_main_settings_keyboard(channel_id: int) -> InlineKeyboardBuilder:
    builder = InlineKeyboardBuilder()
    builder.button(text="🏙️ Налаштувати регіони", callback_data=f"cfg_regions_{channel_id}")
    builder.button(text="📝 Налаштувати повідомлення", callback_data=f"cfg_msg_menu_{channel_id}")
    builder.adjust(1)
    return builder

async def show_main_settings_menu(message: Message, channel_id: int):
    try:
        channel = await bot.get_chat(channel_id)
        title = channel.title
    except TelegramAPIError:
        title = f"ID: {channel_id}" # Fallback if bot is not admin in the chat anymore
        
    builder = await _get_main_settings_keyboard(channel_id)
    with suppress(TelegramAPIError):
        await message.edit_text(
            f"⚙️ Головні налаштування для каналу: <b>{title}</b>",
            reply_markup=builder.as_markup()
        )

async def _get_regions_keyboard(channel_id: int) -> InlineKeyboardBuilder:
    settings = db.get_channel_settings(channel_id)
    selected_regions, is_all_ukraine = [], settings and settings['regions'] == 'all'
    if not is_all_ukraine and settings and settings['regions']:
        try: selected_regions = json.loads(settings['regions'])
        except (json.JSONDecodeError, TypeError): selected_regions = []

    builder = InlineKeyboardBuilder()
    builder.button(text=f"{'✅ ' if is_all_ukraine else ''}Вся Україна", callback_data=f"sr_{channel_id}_all")
    
    # ИЗМЕНЕНИЕ: Используем индекс вместо названия для callback_data
    for index, region in enumerate(UKRAINE_REGIONS):
        text = f"{'✅ ' if region in selected_regions else ''}{region}"
        builder.button(text=text, callback_data=f"sr_{channel_id}_{index}")
    
    builder.button(text="⬅️ Назад", callback_data=f"back_to_main_settings_{channel_id}")
    builder.adjust(1, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 1)
    return builder

async def show_message_settings_menu(message: Message, channel_id: int):
    settings = db.get_channel_settings(channel_id)
    text = "📝 <b>Налаштування шаблонів повідомлень.</b>\n\nОберіть, який шаблон ви хочете змінити. Поточні значення:\n\n"
    for key, value in MESSAGE_TYPES.items():
        text += f"{value}:\n<code>{settings[key]}</code>\n\n"
    
    builder = InlineKeyboardBuilder()
    for key, value in MESSAGE_TYPES.items():
        builder.button(text=f"✏️ {value.split(' ')[-1]}", callback_data=f"set_msg_{channel_id}_{key}")
    builder.button(text="⬅️ Назад", callback_data=f"back_to_main_settings_{channel_id}")
    builder.adjust(2, 2)

    with suppress(TelegramAPIError):
        await message.edit_text(text, reply_markup=builder.as_markup())

# --- Основные обработчики команд и событий ---

@dp.my_chat_member()
async def on_bot_join_or_leave(update: ChatMemberUpdated):
    if update.new_chat_member.status in ["member", "administrator"]:
        db.add_known_channel(update.chat.id, update.chat.title)
    elif update.new_chat_member.status in ["left", "kicked"]:
        db.remove_known_channel(update.chat.id)

@dp.message(Command("add_admin"))
async def add_admin_command(message: Message):
    if message.from_user.id != config.BOT_OWNER_ID: return
    try:
        user_id = int(message.text.split()[1])
        db.add_admin(user_id)
        await message.answer(f"✅ Користувача <code>{user_id}</code> додано до списку адміністраторів.")
    except (IndexError, ValueError):
        await message.answer("Будь ласка, вкажіть ID користувача. Приклад: <code>/add_admin 123456</code>")

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer("Привіт! Я бот для моніторингу повітряних тривог.\n\n"
                         "Щоб налаштувати сповіщення для вашого каналу, просто напишіть мені команду /settings.")

@dp.message(Command("settings"))
async def settings_command(message: Message, state: FSMContext):
    await state.clear()
    if message.chat.type != 'private':
        return await message.answer("Будь ласка, налаштовуйте бота в особистих повідомленнях.")
    if not db.is_admin(message.from_user.id):
        return await message.answer("❌ У вас немає прав налаштовувати цього бота. Зверніться до власника.")

    known_channels, admin_channels = db.get_all_known_channels(), []
    for channel_id, channel_title in known_channels:
        with suppress(TelegramAPIError):
            member = await bot.get_chat_member(channel_id, message.from_user.id)
            if member.status in ['creator', 'administrator']:
                admin_channels.append((channel_id, channel_title))

    if not admin_channels:
        return await message.answer("Я не знайшов каналів, де ви є адміністратором і куди я теж доданий.")

    builder = InlineKeyboardBuilder()
    for channel_id, channel_title in admin_channels:
        builder.button(text=f"⚙️ {channel_title}", callback_data=f"select_ch_{channel_id}")
    builder.adjust(1)
    await message.answer("Оберіть канал для налаштування:", reply_markup=builder.as_markup())


# --- Обработчики Callback'ов (нажатий на кнопки) ---

@dp.callback_query(F.data.startswith("select_ch_"))
async def callback_select_channel(callback: CallbackQuery):
    channel_id = int(callback.data.split("_")[2])
    db.add_or_get_channel(channel_id)
    await show_main_settings_menu(callback.message, channel_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("back_to_main_settings_"))
async def callback_back_to_main_settings(callback: CallbackQuery):
    channel_id = int(callback.data.split("_")[4])
    await show_main_settings_menu(callback.message, channel_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("cfg_regions_"))
async def callback_configure_regions(callback: CallbackQuery):
    channel_id = int(callback.data.split("_")[2])
    builder = await _get_regions_keyboard(channel_id)
    await callback.message.edit_text("🏙️ Оберіть регіони для відстежування:", reply_markup=builder.as_markup())
    await callback.answer()

# НОВЫЙ ОБРАБОТЧИК для кнопок с индексом региона
@dp.callback_query(F.data.startswith("sr_"))
async def callback_set_region_by_index(callback: CallbackQuery):
    await callback.answer()
    
    parts = callback.data.split("_"); channel_id = int(parts[1])
    region_identifier = parts[2]
    
    settings = db.get_channel_settings(channel_id); is_all_ukraine = settings and settings['regions'] == 'all'
    selected_regions = []
    if not is_all_ukraine and settings and settings['regions']:
        try: selected_regions = json.loads(settings['regions'])
        except (json.JSONDecodeError, TypeError): selected_regions = []

    if region_identifier == "all":
        db.update_channel_regions(channel_id, 'all')
    else:
        try:
            region_index = int(region_identifier)
            region_name = UKRAINE_REGIONS[region_index]
            
            if is_all_ukraine:
                selected_regions = [region_name]
            else:
                if region_name in selected_regions: selected_regions.remove(region_name)
                else: selected_regions.append(region_name)
            db.update_channel_regions(channel_id, json.dumps(selected_regions))
        except (ValueError, IndexError):
            logging.error(f"Некоректний індекс регіону в callback: {callback.data}")
            return
    
    builder = await _get_regions_keyboard(channel_id)
    with suppress(TelegramAPIError):
        await callback.message.edit_reply_markup(reply_markup=builder.as_markup())


@dp.callback_query(F.data.startswith("cfg_msg_menu_"))
async def callback_msg_menu(callback: CallbackQuery):
    channel_id = int(callback.data.split("_")[3])
    await show_message_settings_menu(callback.message, channel_id)
    await callback.answer()

@dp.callback_query(F.data.startswith("set_msg_"))
async def callback_set_msg_template(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_"); channel_id = int(parts[2]); message_type = parts[3]
    settings = db.get_channel_settings(channel_id)
    
    await state.set_state(MessageSettings.waiting_for_template)
    await state.update_data(channel_id=channel_id, message_type=message_type)
    
    builder = InlineKeyboardBuilder(); builder.button(text="❌ Скасувати", callback_data=f"cancel_fsm_{channel_id}")
    await callback.message.edit_text(
        f"Редагування: <b>{MESSAGE_TYPES[message_type]}</b>\n\n"
        f"Поточний шаблон:\n<code>{settings[message_type]}</code>\n\n"
        "Надішліть новий текст. Він повинен містити <code>{region}</code>.",
        reply_markup=builder.as_markup()
    )
    await callback.answer()

@dp.message(MessageSettings.waiting_for_template)
async def process_new_template(message: Message, state: FSMContext):
    if "{region}" not in message.text:
        return await message.answer("❌ **Помилка:** ваш текст не містить змінну <code>{region}</code>. Спробуйте ще раз.")

    data = await state.get_data(); channel_id = data['channel_id']; message_type = data['message_type']
    db.update_channel_message(channel_id, message_type, message.text)
    await state.clear()
    await message.answer("✅ Налаштування збережено!")
    await show_message_settings_menu(message, channel_id)

@dp.callback_query(F.data.startswith("cancel_fsm_"))
async def cancel_fsm(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Дію скасовано")
    channel_id = int(callback.data.split("_")[2])
    await show_message_settings_menu(callback.message, channel_id)

# --- Фоновая задача мониторинга и отправки уведомлений ---

async def check_alerts():
    global current_alerts_state
    headers = {"Authorization": f"Bearer {config.API_TOKEN}"}
    api_url = "https://api.alerts.in.ua/v1/alerts/active.json"
    
    async with aiohttp.ClientSession(headers=headers) as session:
        while True:
            await asyncio.sleep(30)
            try:
                async with session.get(api_url) as response:
                    if response.status != 200:
                        logging.error(f"Помилка API: {response.status}"); continue
                    data = await response.json()
                    actual_alerts = {a['location_title']: a['alert_type'] for a in data.get("alerts", [])}
                    new_alerts = {r: t for r, t in actual_alerts.items() if r not in current_alerts_state}
                    ended_alerts = {r: t for r, t in current_alerts_state.items() if r not in actual_alerts}

                    if new_alerts or ended_alerts:
                        screenshot_path = await take_alert_map_screenshot()
                        if new_alerts:
                            logging.info(f"Нові тривоги: {list(new_alerts.keys())}")
                            await notify_about_changes(new_alerts, "start", screenshot_path)
                        if ended_alerts:
                            logging.info(f"Відбої тривог: {list(ended_alerts.keys())}")
                            await notify_about_changes(ended_alerts, "end", screenshot_path)
                        if screenshot_path and os.path.exists(screenshot_path):
                            os.remove(screenshot_path)

                    current_alerts_state = actual_alerts
            except Exception as e:
                logging.error(f"Помилка в фоновій задачі: {e}")

async def notify_about_changes(changes: dict, change_type: str, image_path: str | None):
    all_channels = db.get_all_channels()
    for channel in all_channels:
        channel_id, regions_to_track = channel['channel_id'], channel['regions']
        for region, alert_type in changes.items():
            if regions_to_track != 'all':
                try:
                    if region not in json.loads(regions_to_track): continue
                except (json.JSONDecodeError, TypeError): continue
            
            if change_type == "start":
                msg_template = channel['alert_message' if alert_type == "air_raid" else 'artillery_message']
            else:
                original_alert_type = current_alerts_state.get(region, "air_raid")
                msg_template = channel['end_alert_message' if original_alert_type == "air_raid" else 'end_artillery_message']
            
            message_text = msg_template.format(region=region)
            
            with suppress(TelegramAPIError):
                if image_path:
                    await bot.send_photo(channel_id, FSInputFile(path=image_path), caption=message_text)
                else:
                    text_with_link = message_text + f"\n\n<a href='{config.ALERTS_MAP_URL}'>Мапа тривог</a>"
                    await bot.send_message(channel_id, text_with_link, disable_web_page_preview=True)

# --- Основная функция запуска ---

async def main():
    db.init_db()
    db.add_admin(config.BOT_OWNER_ID)
    logging.info(f"Власника бота ({config.BOT_OWNER_ID}) додано до адміністраторів.")
    asyncio.create_task(check_alerts())
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

if __name__ == "__main__":
    asyncio.run(main())
