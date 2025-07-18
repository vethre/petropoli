from datetime import datetime
from math import ceil
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from bot.handlers.pets import show_pets_paginated
from db.db import fetch_all, fetch_one, execute_query, get_user_quests, insert_quest
import json

router = Router()

@router.message(Command("pstart"))
async def cmd_start(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await execute_query(
            "INSERT INTO users (user_id, coins, eggs, streak, acitve_zone) VALUES ($1, 500, $2, 0, 'Лужайка')",
            {"uid": uid, "eggs": json.dumps([])}
        )
        await insert_quest(uid, "Первое открытие яйца", "Открой своё первое яйцо", "Лужайка", 1, 250)
        await insert_quest(uid, "Собери 3 яйца", "Попробуй накопить 3 яйца в инвентаре", "Лужайка", 3, 300)
        await insert_quest(uid, "Получение питомца", "Выведи первого питомца", "Лужайка", 1, 0, reward_egg=True)

        # відкриваємо першу зону:
        await execute_query("INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE)", {"user_id": uid, "zone": "Лужайка"})
        
        await message.answer("👋 Добро пожаловать в Petropolis!\nТы получил 500 петкойнов на старт 💰")
    else:
        await message.answer("👋 Ты уже зарегистрирован!\nНапиши /profile, чтобы посмотреть свои данные.")

def back_to_profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад в Профиль", callback_data="profile_back")
    return kb.as_markup()

# --- Main Profile Command ---
@router.message(Command("pprofile"))
async def profile_cmd(message: Message):
    await show_profile(message.from_user.id, message)

# ——————— Displaying the main profile ———————
async def show_profile(uid: int, message: Message | CallbackQuery):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        # If user is not registered, ask them to /start
        if isinstance(message, CallbackQuery):
            await message.message.answer("Ты ещё не зарегистрирован. Напиши /start!", parse_mode="HTML")
            await message.answer() # Acknowledge callback query
        else:
            await message.answer("Ты ещё не зарегистрирован. Напиши /start!", parse_mode="HTML")
        return

    # Eggs for profile summary (even if inventory is not fully built)
    eggs = []
    try:
        eggs = json.loads(user["eggs"]) if user["eggs"] else []
    except Exception:
        # Handle cases where 'eggs' might be malformed or not a JSON string
        pass

    kb = InlineKeyboardBuilder()
    # Updated to reflect status of inventory and separate commands
    kb.button(text="🎒 Инвентарь", callback_data="profile_inventory")
    kb.button(text="📜 Квесты", callback_data="profile_quests")
    kb.button(text="🧭 Зоны", callback_data="profile_zones")
    kb.button(text="🐾 Питомцы", callback_data="profile_pets")
    kb.adjust(2, 2) # Adjusting layout for 4 buttons

    zone_display = user.get("active_zone") or "—"

    # Fetch user's first name for the profile
    user_display_name = f"Пользователь {uid}" # Default fallback
    try:
        chat = await message.bot.get_chat(uid)
        user_display_name = chat.first_name if chat.first_name else chat.full_name
    except Exception:
        # If get_chat fails, use the default display name
        pass

    text = (
        f"✨ <b>Профиль игрока: {user_display_name}</b> ✨\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌍 <b>Активная зона:</b> <i>{zone_display}</i>\n"
        f"💰 <b>Петкойны:</b> {user['coins']:,}\n" # Format with comma for readability
        f"🔥 <b>Ежедневный стрик:</b> {user['streak']} дней\n"
        f"🥚 <b>Яиц в инвентаре:</b> {len(eggs)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🐣 <b>Вылуплено питомцев:</b> {user.get('hatched_count', 0)}\n"
        f"🛍️ <b>Куплено яиц:</b> {user.get('bought_eggs', 0)}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"➡️ <i>Выбери вкладку ниже:</i>"
    )

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await message.answer() # Acknowledge callback query
    else:
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ——————— Handling "Back" button ———————
@router.callback_query(F.data == "profile_back")
async def back_callback(call: CallbackQuery):
    await show_profile(call.from_user.id, call) # Pass the CallbackQuery object directly

# ——————— Profile Tabs Handling ———————
@router.callback_query(F.data.startswith("profile_"))
async def profile_tabs_callback(call: CallbackQuery):
    uid = call.from_user.id
    tab = call.data
    text = ""
    reply_markup = back_to_profile_kb() # Default back button

    if tab == "profile_inventory":
        text = (
            "🎒 <b>Инвентарь</b>\n\n"
            "Твой инвентарь пока пуст... или еще в разработке! 😉 "
            "Скоро здесь появятся твои сокровища и коллекционные предметы!\n\n"
            "<i>Заходи попозже, и мы покажем, что есть в рюкзаке!</i>"
        )
    
    elif tab == "profile_quests":
        quests = await fetch_all("SELECT * FROM quests WHERE user_id = $1", {"uid": uid})
        active_quests = [q for q in quests if not q.get("completed", False)]
        completed_quests = [q for q in quests if q.get("completed", False) and not q.get("claimed", False)]
        claimed_quests = [q for q in quests if q.get("claimed", False)]

        text = (
            f"📜 <b>Твои квесты:</b>\n\n"
            f"🎯 Активных: <b>{len(active_quests)}</b>\n"
            f"✅ Готовых к получению: <b>{len(completed_quests)}</b>\n"
            f"🎁 Завершено и получено: <b>{len(claimed_quests)}</b>\n\n"
            f"<i>Хочешь увидеть все детали?</i>"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="🔍 Показать все квесты", callback_data="show_all_quests") # Link to /quests functionality
        kb.add(InlineKeyboardButton(text="🔙 Назад в Профиль", callback_data="profile_back"))
        kb.adjust(1)
        reply_markup = kb.as_markup()

    elif tab == "profile_zones":
        user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
        user_zones = await fetch_all("SELECT * FROM user_zones WHERE user_id = $1", {"uid": uid})
        unlocked = {z["zone"] for z in user_zones if z["unlocked"]}
        active_zone_name = user.get("active_zone") or "Не выбрана"

        text = (
            f"🧭 <b>Зоны исследования:</b>\n\n"
            f"🌟 Активная зона: <b>{active_zone_name}</b>\n"
            f"🔓 Открыто зон: <b>{len(unlocked)}</b>\n\n"
            f"<i>Готов к новым приключениям?</i>"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="🗺️ Управлять зонами", callback_data="show_all_zones") # Link to /zones functionality
        kb.add(InlineKeyboardButton(text="🔙 Назад в Профиль", callback_data="profile_back"))
        kb.adjust(1)
        reply_markup = kb.as_markup()

    elif tab == "profile_pets":
        pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
        text = (
            f"🐾 <b>Твои питомцы:</b>\n\n"
            f"У тебя <b>{len(pets)}</b> милых и сильных питомцев! ✨\n\n"
            f"<i>Заботься о них, и они принесут тебе много петкойнов!</i>"
        )
        kb = InlineKeyboardBuilder()
        kb.button(text="📊 Посмотреть всех питомцев", callback_data="show_all_pets") # Link to /pets functionality
        kb.add(InlineKeyboardButton(text="🔙 Назад в Профиль", callback_data="profile_back"))
        kb.adjust(1)
        reply_markup = kb.as_markup()

    else:
        text = "⚠️ Неизвестная вкладка. Попробуй ещё раз!"

    await call.message.edit_text(text, reply_markup=reply_markup, parse_mode="HTML")
    await call.answer()

# --- Handlers for navigating to dedicated commands ---
# These will simulate calling the commands, you might need to adjust
# them slightly based on how your /quests, /zones, /pets commands
# are structured to be callable from within other handlers.
# For simplicity, these just call the main functions for those commands.

@router.callback_query(F.data == "show_all_quests")
async def show_all_quests_callback(call: CallbackQuery):
    # Assuming show_quests is defined elsewhere and takes message/call as argument
    # If show_quests expects a Message object, you might need to mock one or
    # refactor show_quests to accept CallbackQuery directly.
    # For now, calling the function directly.
    await show_quests(call) # Assuming show_quests can handle a CallbackQuery
    await call.answer()

@router.callback_query(F.data == "show_all_zones")
async def show_all_zones_callback(call: CallbackQuery):
    await show_zones(call.from_user.id, call) # Assuming show_zones handles CallbackQuery
    await call.answer()

@router.callback_query(F.data == "show_all_pets")
async def show_all_pets_callback(call: CallbackQuery):
    await show_pets_paginated(call.from_user.id, call) # Assuming show_pets_paginated handles CallbackQuery
    await call.answer()

def build_quests_text_and_markup(quests: list[dict], page: int = 1, per_page: int = 3):
    total_pages = max(1, ceil(len(quests) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_quests = quests[start:end]

    text = "🎯 <b>Твои квесты:</b>\n\n"
    inline_buttons = []

    for q in page_quests:
        progress = f"{q['progress']}/{q['goal']}" if q['goal'] > 0 else "Неограниченный"
        status = "✅ Завершён" if q["completed"] else "🔄 В процессе"
        reward = f"💰 {q['reward_coins']} петкойнов" if q['reward_coins'] > 0 else "🎁 Яйцо"

        text += (
            f"🔹 <b>{q['name']}</b>\n"
            f"📖 {q['description']}\n"
            f"🌍 Зона: {q['zone']} | Прогресс: {progress} | Статус: {status}\n"
            f"{reward}\n\n"
        )

        if q["completed"] and not q.get("claimed", False):
            inline_buttons.append([
                InlineKeyboardButton(
                    text=f"🎁 Забрать «{q['name']}»",
                    callback_data=f"claim_quest:{q['name']}"
                )
            ])

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"quests_page:{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 Страница {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"quests_page:{page + 1}"))

    if nav_buttons:
        inline_buttons.append(nav_buttons)

    markup = InlineKeyboardMarkup(inline_keyboard=inline_buttons)
    return text.strip(), markup

@router.message(Command("quests"))
async def show_quests(message: Message):
    uid = message.from_user.id
    quests = await get_user_quests(uid)

    if not quests:
        await message.answer("📜 У тебя пока нет активных квестов.")
        return

    # Заново беремо список вже з оновленнями
    quests = await get_user_quests(uid)
    text, markup = build_quests_text_and_markup(quests, page=1)
    await message.answer(text, reply_markup=markup)

async def check_quest_progress(uid: int, message: Message = None):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    eggs = json.loads(user["eggs"] or "[]")
    pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})

    quests = await fetch_all(
        "SELECT * FROM quests WHERE user_id = $1 AND completed = FALSE", {"uid": uid}
    )

    for q in quests:
        new_progress = q["progress"]

        if q["name"] == "Собери 3 яйца":
            new_progress = len(eggs)

        elif q["name"] == "Получение питомца":
            new_progress = 1 if pets else 0

        elif q["name"] == "Первое открытие яйца":
            new_progress = 1 if len(pets) > 0 else 0

        # Якщо вже виконано або нагорода забрана — скіпаємо
        if q["completed"] or q.get("claimed", False):
            continue

        # Якщо досягнута ціль
        if new_progress >= q["goal"]:
            await execute_query(
                "UPDATE quests SET progress = $1, completed = TRUE WHERE id = $2",
                {"progress": q["goal"], "id": q["id"]}
            )

            # Повідомлення, без нагороди
            if message:
                await message.answer(
                    f"🏆 <b>@{message.from_user.username or 'ты'}</b> завершил квест <b>«{q['name']}»</b>!\n"
                    f"🎁 Награда доступна для получения!"
                )

        # Просто апдейтимо прогрес
        elif new_progress != q["progress"]:
            await execute_query(
                "UPDATE quests SET progress = $1 WHERE id = $2",
                {"progress": new_progress, "id": q["id"]}
            )

@router.callback_query(F.data.startswith("quests_page:"))
async def paginate_quests(call: CallbackQuery):
    uid = call.from_user.id
    page = int(call.data.split(":")[1])
    quests = await get_user_quests(uid)

    text, markup = build_quests_text_and_markup(quests, page)
    await call.message.edit_text(text, reply_markup=markup)
    await call.answer()

@router.message(Command("zones"))
async def zones_cmd(message: Message):
    uid = message.from_user.id
    await show_zones(uid, message)

async def show_zones(uid: int, message: Message | CallbackQuery):
    zones = await fetch_all("SELECT * FROM zones")
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    user_zones = await fetch_all("SELECT * FROM user_zones WHERE user_id = $1", {"uid": uid})
    unlocked = {z["zone"] for z in user_zones if z["unlocked"]}
    active = user.get("active_zone", "Лужайка")  # За замовчуванням

    text = "🧭 <b>Твои зоны:</b>\n\n"
    kb = InlineKeyboardBuilder()

    for zone in zones:
        name = zone["name"]
        is_unlocked = name in unlocked
        is_active = name == active
        status = "🌟 Активна" if is_active else ("✅ Открыта" if is_unlocked else "🔒 Закрыта")

        text += f"🔹 <b>{name}</b>\n📖 {zone['description']}\n💰 Стоимость: {zone['cost']} петкойнов\n{status}\n\n"

        # Кнопки:
        if is_unlocked:
            if not is_active:
                kb.button(text=f"📍 Включить {name}", callback_data=f"zone_set:{name}")
        else:
            kb.button(text=f"🔓 Открыть {name}", callback_data=f"zone_buy:{name}")

    kb.button(text="🔙 Назад", callback_data="profile_back")
    markup = kb.as_markup()

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text, reply_markup=markup)
        await message.answer()
    else:
        await message.answer(text, reply_markup=markup)

@router.callback_query(F.data.startswith("zone_set:"))
async def set_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone_name = call.data.split(":")[1]

    await execute_query("UPDATE users SET active_zone = $1 WHERE user_id = $2", {
        "active_zone": zone_name, "uid": uid
    })

    await call.answer(f"🌍 Зона «{zone_name}» выбрана!")
    await show_zones(uid, call)

@router.callback_query(F.data.startswith("zone_buy:"))
async def buy_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone_name = call.data.split(":")[1]

    zone = await fetch_one("SELECT * FROM zones WHERE name = $1", {"name": zone_name})
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})

    if not zone or not user:
        await call.answer("Ошибка загрузки зоны.", show_alert=True)
        return

    # Вже куплено?
    exists = await fetch_one("SELECT * FROM user_zones WHERE user_id = $1 AND zone = $2", {
        "uid": uid, "zone": zone_name
    })
    if exists and exists["unlocked"]:
        await call.answer("Эта зона уже открыта.", show_alert=True)
        return

    cost = zone["cost"]
    if user["coins"] < cost:
        await call.answer("Недостаточно петкойнов 💸", show_alert=True)
        return

    # Списуємо, додаємо зону
    await execute_query("UPDATE users SET coins = coins - $1 WHERE user_id = $2", {
        "uid": uid, "coins": cost
    })

    await execute_query(
        "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
        "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
        {"uid": uid, "zone": zone_name}
    )

    await call.answer(f"🎉 Зона «{zone_name}» успешно открыта!")
    await show_zones(uid, call)

async def check_zone_unlocks(uid: int, message: Message | None = None):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        return

    unlocked_zones = await fetch_all("SELECT zone FROM user_zones WHERE user_id = $1 AND unlocked = TRUE", {"uid": uid})
    unlocked = {z["zone"] for z in unlocked_zones}

    all_zones = await fetch_all("SELECT * FROM zones")

    for zone in all_zones:
        zname = zone["name"]
        if zname in unlocked:
            continue

        conds = json.loads(zone["unlock_conditions"]) or {}

        # 👀 Якщо умов немає — не відкривати
        if not conds:
            continue

        can_unlock = True

        if conds.get("hatched_count"):
            if user["hatched_count"] < conds["hatched_count"]:
                can_unlock = False

        if conds.get("coins"):
            if user["coins"] < conds["coins"]:
                can_unlock = False

        if conds.get("merge_count"):
            if user.get("merged_count", 0) < conds["merge_count"]:
                can_unlock = False

        if can_unlock:
            await execute_query(
                "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
                "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
                {"uid": uid, "zone": zname}
            )
            if message:
                await message.answer(f"🌍 Ты открыл новую зону: <b>{zname}</b>!\n📖 {zone['description']}")

async def get_zone_buff(user: dict) -> float:
    if not user.get("active_zone"):
        return 1.0

    zone = await fetch_one("SELECT * FROM zones WHERE name = $1", {"name": user["active_zone"]})
    if zone and zone.get("buff_type") == "coin_rate":
        return 1.0 + zone.get("buff_value", 0) / 100
    return 1.0

