#START.PY
from datetime import datetime
from math import ceil
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json

# Import your DB functions
from db.db import (
    fetch_all,
    fetch_one,
    execute_query,
    get_user_quests,
    insert_quest,
    claim_quest_reward,
)

# Import show_pets_paginated from pets.py
from bot.handlers.pets import show_pets_paginated

router = Router()

@router.message(Command("pstart"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    user = await fetch_one(
        "SELECT * FROM users WHERE user_id = $1", {"uid": uid}
    )
    if not user:
        # New user setup
        await execute_query(
            "INSERT INTO users (user_id, coins, eggs, streak, active_zone) VALUES ($1, 500, $2, 0, 'Лужайка')",
            {"uid": uid, "eggs": json.dumps([])},
        )
        # Initial quests
        await insert_quest(uid, "Первое открытие яйца", "Открой своё первое яйцо", "Лужайка", 1, 250)
        await insert_quest(uid, "Собери 3 яйца", "Попробуй накопить 3 яйца в инвентаре", "Лужайка", 3, 300)
        await insert_quest(uid, "Получение питомца", "Выведи первого питомца", "Лужайка", 1, 0, reward_egg=True)
        # Unlock first zone
        await execute_query(
            "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE)",
            {"user_id": uid, "zone": "Лужайка"},
        )
        await message.answer(
            "👋 Добро пожаловать в Petropolis!\nТы получил 500 петкойнов на старт 💰"
        )
    else:
        await message.answer(
            "👋 Ты уже зарегистрирован!\nНапиши /pprofile, чтобы посмотреть свои данные."
        )

@router.message(Command("pprofile"))
async def profile_cmd(message: Message):
    await show_profile(message.from_user.id, message)

async def show_profile(uid: int, message: Message):
    user = await fetch_one(
        "SELECT * FROM users WHERE user_id = $1", {"uid": uid}
    )
    if not user:
        return await message.answer(
            "Ты ещё не зарегистрирован. Напиши /pstart!", parse_mode="HTML"
        )

    # Parse eggs JSON
    try:
        eggs = json.loads(user.get("eggs") or "[]")
    except (json.JSONDecodeError, TypeError):
        eggs = []

    # Build inline keyboard
    kb = InlineKeyboardBuilder()
    kb.button(text="🎒 Инвентарь", callback_data="inventory_cb")
    kb.button(text="📜 Квесты",     callback_data="quests_cb")
    kb.button(text="🧭 Зоны",       callback_data="zones_cb")
    kb.button(text="🐾 Питомцы",    callback_data="pets_cb")
    kb.adjust(2)  # два столбца

    # Determine display name
    try:
        chat = await message.bot.get_chat(uid)
        display = chat.first_name or chat.full_name
    except Exception:
        display = message.from_user.first_name or f"Пользователь {uid}"

    zone_display = user.get("active_zone") or "—"
    text = (
        f"✨ <b>Профиль игрока: {display}</b> ✨\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌍 <b>Активная зона:</b> <i>{zone_display}</i>\n"
        f"💰 <b>Петкойны:</b> {user['coins']:,}\n"
        f"🔥 <b>Ежедневный стрик:</b> {user['streak']} дней\n"
        f"🥚 <b>Яиц в инвентаре:</b> {len(eggs)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🐣 <b>Вылуплено питомцев:</b> {user.get('hatched_count', 0)}\n"
        f"🛍️ <b>Куплено яиц:</b> {user.get('bought_eggs', 0)}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"➡️ <i>Выбери действие:</i>"
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# Callbacks for profile actions
@router.callback_query(F.data == "inventory_cb")
async def inventory_cb(call: CallbackQuery):
    await call.answer()
    # Не трогаем профиль, просто отправляем новый ответ
    await call.message.answer("🎒 Инвентарь: в разработке.")

@router.callback_query(F.data == "quests_cb")
async def quests_cb(call: CallbackQuery):
    await call.answer()
    # Показываем квесты новым сообщением, профиль остаётся
    await show_quests(call.message)

@router.callback_query(F.data == "zones_cb")
async def zones_cb(call: CallbackQuery):
    await call.answer()
    await show_zones(call.from_user.id, call.message)

@router.callback_query(F.data == "pets_cb")
async def pets_cb(call: CallbackQuery):
    await call.answer()
    await show_pets_paginated(call.from_user.id, call.message, page=1)

# Command handlers fallback
@router.message(Command("inventory"))
async def inventory_cmd(message: Message):
    await message.answer("🎒 Инвентарь: в разработке.")

@router.message(Command("quests"))
async def show_quests_command(message: Message):
    await show_quests(message)

@router.message(Command("zones"))
async def zones_command(message: Message):
    await show_zones(message.from_user.id, message)

@router.message(Command("pets"))
async def pets_command(message: Message):
    await show_pets_paginated(message.from_user.id, message, page=1)

# Unified function for quests
async def show_quests(source_message: Message | CallbackQuery, page: int = 1):
    uid = source_message.from_user.id
    quests = await get_user_quests(uid)
    if not quests:
        text = "📜 У тебя пока нет активных квестов."
        markup = None
    else:
        text, kb = build_quests_text_and_markup(quests, page)
        markup = kb.as_markup()

    if isinstance(source_message, Message):
        await source_message.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await source_message.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await source_message.answer()

# Unified function for zones
async def show_zones(uid: int, source: Message | CallbackQuery):
    zones_data = await fetch_all("SELECT * FROM zones")
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    user_zones = await fetch_all(
        "SELECT * FROM user_zones WHERE user_id = $1", {"uid": uid}
    )
    unlocked = {z["zone"] for z in user_zones if z["unlocked"]}
    active = user.get("active_zone", "Лужайка")

    text = "🧭 <b>Твои зоны:</b>\n\n"
    kb = InlineKeyboardBuilder()
    for zone in zones_data:
        name = zone["name"]
        status = (
            "🌟 Активна"
            if name == active
            else ("✅ Открыта" if name in unlocked else "🔒 Закрыта")
        )
        text += (
            f"🔹 <b>{name}</b>\n"
            f"📖 {zone['description']}\n"
            f"💰 Стоимость: {zone['cost']} петкойнов\n"
            f"{status}\n\n"
        )
        if name in unlocked and name != active:
            kb.button(text=f"📍 Включить {name}", callback_data=f"zone_set:{name}")
        elif name not in unlocked:
            kb.button(text=f"🔓 Открыть {name}", callback_data=f"zone_buy:{name}")
    kb.adjust(1)
    markup = kb.as_markup()

    if isinstance(source, Message):
        await source.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        await source.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await source.answer()

# Build quests text and pagination
def build_quests_text_and_markup(quests: list[dict], page: int = 1, per_page: int = 3):
    total_pages = max(1, ceil(len(quests) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_quests = quests[start:end]

    text = "🎯 <b>Твои квесты:</b>"
    kb = InlineKeyboardBuilder()
    for q in page_quests:
        progress = f"{q['progress']}/{q['goal']}" if q['goal'] > 0 else "Неограниченный"
        status = "✅ Завершён" if q['completed'] else "🔄 В процессе"
        rewards = []
        if q['reward_coins'] > 0:
            rewards.append(f"💰 {q['reward_coins']} петкойнов")
        if q.get('reward_egg', False):
            rewards.append("🥚 1 яйцо")
        reward_text = "Награда: " + ", ".join(rewards) if rewards else "Без награды"

        text += (
            f"🔹 <b>{q['name']}</b>\n"
            f"📖 {q['description']}\n"
            f"🌍 Зона: {q['zone']} | Прогресс: {progress} | Статус: {status}\n"
            f"{reward_text}"
        )
        if q['completed'] and not q.get('claimed', False):
            kb.button(text=f"🎁 Забрать «{q['name']}»", callback_data=f"claim_quest:{q['id']}")

    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"quests_page:{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"quests_page:{page+1}"))
    if nav_buttons:
        kb.row(*nav_buttons)

    return text, kb

# Claim quest reward
@router.callback_query(F.data.startswith("claim_quest:"))
async def claim_quest_callback(call: CallbackQuery):
    uid = call.from_user.id
    quest_id = int(call.data.split(":")[1])
    success, msg = await claim_quest_reward(uid, quest_id)
    await call.answer(msg, show_alert=True)
    await show_quests(call)

# Pagination callback
@router.callback_query(F.data.startswith("quests_page:"))
async def paginate_quests_callback(call: CallbackQuery):
    page = int(call.data.split(":")[1])
    await show_quests(call, page)

# Set active zone
@router.callback_query(F.data.startswith("zone_set:"))
async def set_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone = call.data.split(":")[1]
    await execute_query(
        "UPDATE users SET active_zone = $1 WHERE user_id = $2",
        {"active_zone": zone, "uid": uid}
    )
    await call.answer(f"🌍 Зона «{zone}» выбрана!")
    await show_zones(uid, call)

# Buy a zone
@router.callback_query(F.data.startswith("zone_buy:"))
async def buy_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone = call.data.split(":")[1]
    zone_data = await fetch_one("SELECT * FROM zones WHERE name = $1", {"name": zone})
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not zone_data or not user:
        return await call.answer("Ошибка загрузки зоны.", show_alert=True)
    cost = zone_data['cost']
    if user['coins'] < cost:
        return await call.answer("Недостаточно петкойнов 💸", show_alert=True)
    # Deduct and unlock
    await execute_query(
        "UPDATE users SET coins = coins - $1 WHERE user_id = $2",
        {"cost": cost, "uid": uid},
    )
    await execute_query(
        "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
        "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
        {"uid": uid, "zone": zone}
    )
    await call.answer(f"🎉 Зона «{zone}» успешно открыта!")
    await show_zones(uid, call)

# Quest progress checker (called periodically)
async def check_quest_progress(uid: int, message: Message = None):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    eggs = json.loads(user.get("eggs") or "[]")
    pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
    quests = await fetch_all(
        "SELECT * FROM quests WHERE user_id = $1 AND completed = FALSE", {"uid": uid}
    )
    for q in quests:
        new_progress = q['progress']
        if q['name'] == "Собери 3 яйца":
            new_progress = len(eggs)
        elif q['name'] == "Получение питомца":
            new_progress = 1 if pets else 0
        elif q['name'] == "Первое открытие яйца":
            new_progress = 1 if pets else 0
        if q['completed'] or q.get('claimed', False):
            continue
        if new_progress >= q['goal']:
            await execute_query(
                "UPDATE quests SET progress = $1, completed = TRUE WHERE id = $2",
                {"progress": q['goal'], "id": q['id']}
            )
            if message:
                await message.answer(
                    f"🏆 <b>@{message.from_user.username or 'ты'} завершил квест «{q['name']}»!</b>\n"
                    f"🎁 Награда доступна для получения!"
                )
        elif new_progress != q['progress']:
            await execute_query(
                "UPDATE quests SET progress = $1 WHERE id = $2",
                {"progress": new_progress, "id": q['id']}
            )

# Zone unlock checker (called periodically)
async def check_zone_unlocks(uid: int, message: Message = None):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        return
    unlocked_zones = await fetch_all(
        "SELECT zone FROM user_zones WHERE user_id = $1 AND unlocked = TRUE", {"uid": uid}
    )
    unlocked = {z['zone'] for z in unlocked_zones}
    all_zones = await fetch_all("SELECT * FROM zones")
    for zone in all_zones:
        name = zone['name']
        if name in unlocked:
            continue
        conds = json.loads(zone.get('unlock_conditions') or "{}")
        can_unlock = True
        if conds.get('hatched_count') and user.get('hatched_count', 0) < conds['hatched_count']:
            can_unlock = False
        if conds.get('coins') and user['coins'] < conds['coins']:
            can_unlock = False
        if conds.get('merge_count') and user.get('merged_count', 0) < conds['merge_count']:
            can_unlock = False
        if can_unlock:
            await execute_query(
                "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
                "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
                {"uid": uid, "zone": name}
            )
            if message:
                await message.answer(f"🌍 Ты открыл новую зону: <b>{name}</b>!\n📖 {zone['description']}")

# Get zone buff multiplier
async def get_zone_buff(user: dict) -> float:
    if not user.get('active_zone'):
        return 1.0
    zone = await fetch_one("SELECT * FROM zones WHERE name = $1", {"name": user['active_zone']})
    if zone and zone.get('buff_type') == 'coin_rate':
        return 1.0 + zone.get('buff_value', 0) / 100
    return 1.0