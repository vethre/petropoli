# bot/handlers/start.py

from datetime import datetime
from math import ceil
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json

# Import your DB functions
from db.db import fetch_all, fetch_one, execute_query, get_user_quests, insert_quest, complete_quest, claim_quest_reward

# Import show_pets_paginated from pets.py
# IMPORTANT: Ensure show_pets_paginated in pets.py is updated to match the new signature:
# async def show_pets_paginated(uid: int, source_message: Message | CallbackQuery, page: int = 1):
# It should behave like show_quests and show_zones below: send new message if called as tab, edit if paginating.
from bot.handlers.pets import show_pets_paginated 

router = Router()

@router.message(Command("pstart"))
async def cmd_start(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await execute_query(
            "INSERT INTO users (user_id, coins, eggs, streak, active_zone) VALUES ($1, 500, $2, 0, 'Лужайка')",
            {"uid": uid, "eggs": json.dumps([])}
        )
        await insert_quest(uid, "Первое открытие яйца", "Открой своё первое яйцо", "Лужайка", 1, 250)
        await insert_quest(uid, "Собери 3 яйца", "Попробуй накопить 3 яйца в инвентаре", "Лужайка", 3, 300)
        await insert_quest(uid, "Получение питомца", "Выведи первого питомца", "Лужайка", 1, 0, reward_egg=True)

        # відкриваємо першу зону:
        await execute_query("INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE)", {"user_id": uid, "zone": "Лужайка"})
        
        await message.answer("👋 Добро пожаловать в Petropolis!\nТы получил 500 петкойнов на старт 💰")
    else:
        await message.answer("👋 Ты уже зарегистрирован!\nНапиши /pprofile, чтобы посмотреть свои данные.")

# Helper function for "Back to Profile" button
def back_to_profile_kb():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Назад в Профиль", callback_data="profile_back")
    return kb.as_markup()

# --- Main Profile Command Handler ---
@router.message(Command("pprofile"))
async def profile_cmd(message: Message):
    await show_profile(message.from_user.id, message)

# ——————— Displaying the main profile ———————
async def show_profile(uid: int, source_message: Message | CallbackQuery):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})

    if not user:
        response_text = "Ты ещё не зарегистрирован. Напиши /pstart!"
        if isinstance(source_message, CallbackQuery):
            await source_message.message.answer(response_text, parse_mode="HTML")
            await source_message.answer()
        else:
            await source_message.answer(response_text, parse_mode="HTML")
        return

    eggs = []
    try:
        eggs = json.loads(user["eggs"]) if user["eggs"] else []
    except (json.JSONDecodeError, TypeError):
        print(f"Warning: Failed to decode eggs JSON for user {uid}. Value: {user['eggs']}")
        pass

    kb = InlineKeyboardBuilder()
    kb.button(text="🎒 Инвентарь", callback_data="show_tab_inventory")
    kb.button(text="📜 Квесты", callback_data="show_tab_quests")
    kb.button(text="🧭 Зоны", callback_data="show_tab_zones")
    kb.button(text="🐾 Питомцы", callback_data="show_tab_pets")
    kb.adjust(2, 2)

    zone_display = user.get("active_zone") or "—"
    user_display_name = f"Пользователь {uid}"
    try:
        bot_instance = None
        if isinstance(source_message, Message):
            bot_instance = source_message.bot
        elif isinstance(source_message, CallbackQuery):
            bot_instance = source_message.message.bot

        if bot_instance:
            chat = await bot_instance.get_chat(uid)
            user_display_name = chat.first_name if chat.first_name else chat.full_name
        else:
            user_display_name = source_message.from_user.first_name or f"Пользователь {uid}"
    except Exception as e:
        print(f"Error fetching chat info for user {uid}: {e}")
        user_display_name = source_message.from_user.first_name or f"Пользователь {uid}"

    text = (
        f"✨ <b>Профиль игрока: {user_display_name}</b> ✨\n\n"
        f"━━━━━━━━━━━━━━\n"
        f"🌍 <b>Активная зона:</b> <i>{zone_display}</i>\n"
        f"💰 <b>Петкойны:</b> {user['coins']:,}\n"
        f"🔥 <b>Ежедневный стрик:</b> {user['streak']} дней\n"
        f"🥚 <b>Яиц в инвентаре:</b> {len(eggs)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🐣 <b>Вылуплено питомцев:</b> {user.get('hatched_count', 0)}\n"
        f"🛍️ <b>Куплено яиц:</b> {user.get('bought_eggs', 0)}\n"
        f"━━━━━━━━━━━━━━\n\n"
        f"➡️ <i>Выбери вкладку ниже:</i>"
    )

    if isinstance(source_message, CallbackQuery):
        # If coming from a callback (like "Back to Profile"), delete the old message
        # and send a new one for a fresh profile view.
        try:
            await source_message.message.delete()
        except Exception as e:
            print(f"Could not delete message for user {uid}: {e}")
        await source_message.message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        await source_message.answer() # Acknowledge the callback query
    else:
        # If coming from a /pprofile command, just send a new message
        await source_message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# ——————— Handling "Back to Profile" button ———————
@router.callback_query(F.data == "profile_back")
async def back_callback(call: CallbackQuery):
    # This button now triggers a full re-display of the profile, simulating a command
    # It will delete the current message (e.g., quests list) and send a new profile message.
    await show_profile(call.from_user.id, call)


# ——————— Helper Functions for Each Profile Tab (DELETE old, SEND NEW Message) ———————

async def _show_inventory_tab(call: CallbackQuery):
    uid = call.from_user.id
    # Acknowledge the callback immediately
    await call.answer()
    
    # Delete the previous message (main profile)
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Could not delete message for user {uid}: {e}")

    text = (
        "🎒 <b>Инвентарь</b>\n\n"
        "Твой инвентарь пока пуст... или еще в разработке! 😉 "
        "Скоро здесь появятся твои сокровища и коллекционные предметы!\n\n"
        "<i>Заходи попозже, и мы покажем, что есть в рюкзаке!</i>"
    )
    # Send a NEW message for the tab content
    await call.message.answer(text, reply_markup=back_to_profile_kb(), parse_mode="HTML")

async def _show_quests_tab(call: CallbackQuery):
    uid = call.from_user.id
    await call.answer() # Acknowledge

    # Delete the previous message (main profile)
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Could not delete message for user {uid}: {e}")

    # Call the main /quests display logic, which will now send a NEW message
    await show_quests(call, page=1) # Pass the CallbackQuery directly

async def _show_zones_tab(call: CallbackQuery):
    uid = call.from_user.id
    await call.answer() # Acknowledge

    # Delete the previous message (main profile)
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Could not delete message for user {uid}: {e}")

    await show_zones(uid, call, page=1)

async def _show_pets_tab(call: CallbackQuery):
    uid = call.from_user.id
    await call.answer() # Acknowledge

    # Delete the previous message (main profile)
    try:
        await call.message.delete()
    except Exception as e:
        print(f"Could not delete message for user {uid}: {e}")

    await show_pets_paginated(uid, call, page=1)

# ——————— Router for Profile Tabs (Directly calls _show_tab helpers) ———————
@router.callback_query(F.data.startswith("show_tab_"))
async def profile_tabs_router(call: CallbackQuery):
    tab_suffix = call.data.split("show_tab_")[1]
    if tab_suffix == "inventory":
        await _show_inventory_tab(call)
    elif tab_suffix == "quests":
        await _show_quests_tab(call)
    elif tab_suffix == "zones":
        await _show_zones_tab(call)
    elif tab_suffix == "pets":
        await _show_pets_tab(call)
    else:
        await call.answer("⚠️ Неизвестная вкладка.", show_alert=True)

@router.message(Command("quests"))
async def show_quests_command_handler(message: Message):
    # This is for when /quests is typed directly
    await show_quests(message)

# Unified function for displaying quests.
# It handles both initial display (new message) and pagination (edit message).
async def show_quests(source_message: Message | CallbackQuery, page: int = 1):
    uid = source_message.from_user.id
    
    # Determine if this is an initial call (from /quests command or profile tab)
    # or a pagination/action within the quests view.
    is_initial_call = isinstance(source_message, Message) or source_message.data.startswith("show_tab_quests")
    
    # If it's a pagination callback, update the page number
    if isinstance(source_message, CallbackQuery) and source_message.data.startswith("quests_page:"):
        page = int(source_message.data.split(":")[1])

    quests = await get_user_quests(uid)

    if not quests:
        text = "📜 У тебя пока нет активных квестов."
        markup = back_to_profile_kb()
    else:
        text, markup_builder = build_quests_text_and_markup(quests, page)
        # Add back to profile button to pagination markup
        markup_builder.add(InlineKeyboardButton(text="🔙 Назад в Профиль", callback_data="profile_back"))
        markup_builder.adjust(1) # Adjust last row to put back button on its own
        markup = markup_builder.as_markup()

    if is_initial_call:
        await source_message.answer(text, reply_markup=markup, parse_mode="HTML")
    elif isinstance(source_message, CallbackQuery):
        # For pagination callbacks (quests_page:X) or claim_quest, EDIT the current message
        await source_message.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await source_message.answer() # Acknowledge the callback

@router.message(Command("zones"))
async def zones_command_handler(message: Message):
    # For when /zones is typed directly
    await show_zones(message.from_user.id, message)

# Unified function for displaying zones.
# It handles both initial display (new message) and actions (edit message).
async def show_zones(uid: int, source_message: Message | CallbackQuery):
    zones_data = await fetch_all("SELECT * FROM zones")
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    user_zones = await fetch_all("SELECT * FROM user_zones WHERE user_id = $1", {"uid": uid})
    unlocked = {z["zone"] for z in user_zones if z["unlocked"]}
    active = user.get("active_zone", "Лужайка")

    text = "🧭 <b>Твои зоны:</b>\n\n"
    kb = InlineKeyboardBuilder()

    for zone in zones_data:
        name = zone["name"]
        is_unlocked = name in unlocked
        is_active = name == active
        status = "🌟 Активна" if is_active else ("✅ Открыта" if is_unlocked else "🔒 Закрыта")

        text += f"🔹 <b>{name}</b>\n📖 {zone['description']}\n💰 Стоимость: {zone['cost']} петкойнов\n{status}\n\n"

        if is_unlocked:
            if not is_active:
                kb.button(text=f"📍 Включить {name}", callback_data=f"zone_set:{name}")
        else:
            kb.button(text=f"🔓 Открыть {name}", callback_data=f"zone_buy:{name}")

    kb.add(InlineKeyboardButton(text="🔙 Назад в Профиль", callback_data="profile_back")) # Always add back button
    kb.adjust(1) 
    markup = kb.as_markup()

    is_initial_call = isinstance(source_message, Message) or (isinstance(source_message, CallbackQuery) and source_message.data.startswith("show_tab_zones"))

    if is_initial_call:
        if isinstance(source_message, Message):
            await source_message.answer(text, reply_markup=markup, parse_mode="HTML")
        elif isinstance(source_message, CallbackQuery):
            await source_message.message.answer(text, reply_markup=markup, parse_mode="HTML")
    elif isinstance(source_message, CallbackQuery):
        await source_message.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        await source_message.answer()

def build_quests_text_and_markup(quests: list[dict], page: int = 1, per_page: int = 3):
    total_pages = max(1, ceil(len(quests) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_quests = quests[start:end]

    text = "🎯 <b>Твои квесты:</b>\n\n"
    kb = InlineKeyboardBuilder() # Use InlineKeyboardBuilder here for flexibility

    for q in page_quests:
        progress = f"{q['progress']}/{q['goal']}" if q['goal'] > 0 else "Неограниченный"
        status = "✅ Завершён" if q["completed"] else "🔄 В процессе"
        reward_display = []
        if q['reward_coins'] > 0:
            reward_display.append(f"💰 {q['reward_coins']} петкойнов")
        if q.get('reward_egg', False): # Check for reward_egg explicitly
            reward_display.append("🥚 1 яйцо")
        
        reward_text = "Награда: " + ", ".join(reward_display) if reward_display else "Без награды"


        text += (
            f"🔹 <b>{q['name']}</b>\n"
            f"📖 {q['description']}\n"
            f"🌍 Зона: {q['zone']} | Прогресс: {progress} | Статус: {status}\n"
            f"{reward_text}\n\n"
        )

        if q["completed"] and not q.get("claimed", False):
            kb.button(text=f"🎁 Забрать «{q['name']}»", callback_data=f"claim_quest:{q['id']}")
            
    # Add pagination buttons if necessary
    nav_buttons_row = []
    if page > 1:
        nav_buttons_row.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"quests_page:{page - 1}"))
    nav_buttons_row.append(InlineKeyboardButton(text=f"📄 Страница {page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav_buttons_row.append(InlineKeyboardButton(text="➡️ Вперёд", callback_data=f"quests_page:{page + 1}"))
    
    if nav_buttons_row:
        kb.row(*nav_buttons_row) # Add navigation buttons as a row

    return text.strip(), kb # Return text and the InlineKeyboardBuilder instance


@router.callback_query(F.data.startswith("claim_quest:"))
async def claim_quest_callback(call: CallbackQuery):
    uid = call.from_user.id
    try:
        quest_id = int(call.data.split(":")[1])
    except ValueError:
        await call.answer("Неверный ID квеста.", show_alert=True)
        return

    success, message_text = await claim_quest_reward(uid, quest_id)
    
    await call.answer(message_text, show_alert=True)
    
    await show_quests(call) # Re-display the updated quests


@router.callback_query(F.data.startswith("quests_page:"))
async def paginate_quests_callback(call: CallbackQuery):
    # This pagination handler now just calls show_quests, which will handle the edit.
    await show_quests(call)


@router.callback_query(F.data.startswith("zone_set:"))
async def set_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone_name = call.data.split(":")[1]

    await execute_query("UPDATE users SET active_zone = $1 WHERE user_id = $2", {
        "active_zone": zone_name, "uid": uid
    })

    await call.answer(f"🌍 Зона «{zone_name}» выбрана!")
    # Re-display zones, editing the current message
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

    await execute_query("UPDATE users SET coins = coins - $1 WHERE user_id = $2", {
        "cost": cost, "uid": uid # Changed 'coins' key to 'cost' for clarity with query
    })

    await execute_query(
        "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
        "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
        {"uid": uid, "zone": zone_name}
    )

    await call.answer(f"🎉 Зона «{zone_name}» успешно открыта!")
    # Re-display zones, editing the current message
    await show_zones(uid, call)

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