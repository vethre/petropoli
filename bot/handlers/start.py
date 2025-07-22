# START.PY
from datetime import datetime, timezone
from math import ceil
from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest # Import for error handling
import json

# Import your DB functions
from db.db import (
    fetch_all,
    fetch_one,
    execute_query,
    get_user_quests,      # Assumed to be updated to fetch by quest_id
    insert_quest,         # Assumed to be updated for quest_id, goal, reward_egg_type
    claim_quest_reward,   # Assumed to be updated for quest_id, reward_egg_type, and 'claimed' status
)

# Import show_pets_paginated from pets.py
from bot.handlers.pets import show_pets_paginated
# Import zone and quest data definitions
from bot.data.quests import QUESTS_DEFINITIONS, QUEST_PROGRESS_MAPPING # Make sure QUEST_PROGRESS_MAPPING is defined in bot/data/quests.py

router = Router()

MAX_ENERGY = 200 # Define max energy
ENERGY_REGEN_RATE_MINUTES = 1 # Define how often energy regenerates (e.g., every 1 minute)
ENERGY_REGEN_AMOUNT = 1 # How much energy regenerates per period

# Helper function to assign initial quests (moved here from previous response for clarity)
async def assign_new_quests(uid: int, message_obj: Message = None):
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user: return

    user_quests = await fetch_all("SELECT quest_id, completed, claimed FROM quests WHERE user_id = $1", {"uid": uid})
    user_assigned_quest_ids = {q['quest_id'] for q in user_quests}
    user_completed_claimed_quest_ids = {q['quest_id'] for q in user_quests if q['completed'] and q['claimed']}

    newly_assigned = []
    for quest_key, quest_def in QUESTS_DEFINITIONS.items():
        if quest_key in user_assigned_quest_ids:
            continue # Quest already assigned

        can_assign = True
        # Check prerequisite_quest
        if quest_def['prerequisite_quest']:
            if quest_def['prerequisite_quest'] not in user_completed_claimed_quest_ids:
                can_assign = False
        
        # Add other assignment conditions here if needed (e.g., min_user_level etc.)

        if can_assign:
            # Insert the new quest into the user's quests table
            # NOTE: Your insert_quest function in db.db.py needs to handle quest_id, goal, reward_egg_type
            await insert_quest(
                uid,
                quest_key, # Use quest_id as the primary identifier
                quest_def['name'],
                quest_def['description'],
                quest_def.get('zone'), # Can be None
                quest_def['goal'],
                quest_def['reward_coins'],
                quest_def['reward_egg_type'] # Pass the egg type
            )
            newly_assigned.append(quest_def['name'])
            
            if message_obj:
                try:
                    await message_obj.answer(f"✨ <b>Новый квест: «{quest_def['name']}»!</b>\n"
                                             f"<i>{quest_def['description']}</i>", parse_mode="HTML")
                except TelegramBadRequest as e:
                    print(f"Error sending new quest message: {e}")

    return newly_assigned # Return list of newly assigned quest names

@router.message(Command("pstart"))
async def cmd_start(message: Message):
    uid = message.from_user.id
    user = await fetch_one(
        "SELECT * FROM users WHERE user_id = $1", {"uid": uid}
    )
    if not user:
        # New user setup: Initialize all new columns with default values
        await execute_query(
            "INSERT INTO users (user_id, coins, eggs, streak, active_zone, energy, last_energy_update, "
            "hatched_count, merged_count, eggs_collected, explore_counts, monsters_defeated_counts, "
            "total_coins_collected, highest_pet_level)" # Removed last_quest_assigned here as it's not strictly needed at start
            "VALUES ($1, 500, $2, 0, 'Лужайка', $3, $4, 0, 0, 0, '{}'::jsonb, '{}'::jsonb, 500, 0)",
            {"uid": uid, "eggs": json.dumps([]), "energy": MAX_ENERGY, "last_energy_update": datetime.now(timezone.utc)},
        )
        # Unlock first zone (Лужайка) - no cost
        await execute_query(
            "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
            "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
            {"user_id": uid, "zone": "Лужайка"},
        )
        # Assign initial quests using the new function
        await assign_new_quests(uid, message) # Pass message to send notifications
        
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

# Energy regeneration logic
async def recalculate_energy(uid: int, user_data: dict) -> dict:
    last_update = user_data.get("last_energy_update")
    current_energy = user_data.get("energy", MAX_ENERGY) # Default to MAX_ENERGY if not set

    if not last_update:
        # If no last_update, set it to now and full energy
        await execute_query(
            "UPDATE users SET last_energy_update = $1, energy = $2 WHERE user_id = $3",
            {"last_update": datetime.now(timezone.utc), "energy": MAX_ENERGY, "uid": uid}
        )
        user_data['last_energy_update'] = datetime.now(timezone.utc)
        user_data['energy'] = MAX_ENERGY
        return user_data

    time_diff = datetime.now(timezone.utc) - last_update
    minutes_passed = int(time_diff.total_seconds() / 60)

    if minutes_passed > 0:
        energy_to_add = minutes_passed * ENERGY_REGEN_AMOUNT
        new_energy = min(MAX_ENERGY, current_energy + energy_to_add)
        
        if new_energy > current_energy: # Only update if energy actually increased
            await execute_query(
                "UPDATE users SET energy = $1, last_energy_update = $2 WHERE user_id = $3",
                {"energy": new_energy, "last_update": datetime.now(timezone.utc), "uid": uid}
            )
            user_data['energy'] = new_energy
            user_data['last_energy_update'] = datetime.now(timezone.utc)
    return user_data


async def show_profile(uid: int, message: Message):
    user = await fetch_one(
        "SELECT * FROM users WHERE user_id = $1", {"uid": uid}
    )
    if not user:
        return await message.answer(
            "Ты ещё не зарегистрирован. Напиши /pstart!", parse_mode="HTML"
        )

    # Recalculate energy before displaying profile
    user = await recalculate_energy(uid, user)

    # Parse eggs JSON
    try:
        eggs = json.loads(user.get("eggs") or "[]")
    except (json.JSONDecodeError, TypeError):
        eggs = []

    fav_pet_info_text = ""
    # Check if fav_pet_id exists and is not None (using .get() with default)
    if user.get('fav_pet_id'):
        fav_pet_record = await fetch_one(
            "SELECT name, rarity FROM pets WHERE id = $1 AND user_id = $2",
            {"id": user['fav_pet_id'], "user_id": uid}
        )
        if fav_pet_record:
            display_name = user.get('fav_pet_nickname') or fav_pet_record['name']
            fav_pet_info_text = f"❤️ Любимчик: <b>{display_name}</b> ({fav_pet_record['name']}, {fav_pet_record['rarity']})\n"
        else:
            # If favorite pet not found (e.g., deleted), clear the field in DB
            await execute_query("UPDATE users SET fav_pet_id = NULL, fav_pet_nickname = NULL WHERE user_id = $1", {"uid": uid})
            fav_pet_info_text = "❤️ Любимчик: Нет (предыдущий был удален)\n"
    else:
        fav_pet_info_text = "❤️ Любимчик: Нет\n"

    # Build inline keyboard
    kb = InlineKeyboardBuilder()
    kb.button(text="🎒 Инвентарь", callback_data="inventory_cb")
    kb.button(text="📜 Квесты", callback_data="quests_cb")
    kb.button(text="🧭 Зоны", callback_data="zones_cb")
    kb.button(text="🐾 Питомцы", callback_data="pets_cb")
    kb.adjust(2)  # two columns

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
        f"{fav_pet_info_text}"
        f"💰 <b>Петкойны:</b> {user['coins']:,}\n"
        f"⚡️ <b>Энергия исследований</b>: {user['energy']}/{MAX_ENERGY}\n" # Use MAX_ENERGY
        f"🔥 <b>Ежедневный стрик:</b> {user['streak']} дней\n"
        f"🥚 <b>Яиц в инвентаре:</b> {len(eggs)}\n"
        f"━━━━━━━━━━━━━━\n"
        f"🐣 <b>Вылуплено питомцев:</b> {user.get('hatched_count', 0)}\n"
        f"🤝 <b>Объединено питомцев:</b> {user.get('merged_count', 0)}\n" # New field
        f"🥚 <b>Собрано яиц:</b> {user.get('eggs_collected', 0)}\n" # New field
        f"📈 <b>Макс. уровень питомца:</b> {user.get('highest_pet_level', 0)}\n" # New field
        f"💰 <b>Всего монет собрано:</b> {user.get('total_coins_collected', 0):,}\n" # New field
        f"━━━━━━━━━━━━━━\n\n"
        f"➡️ <i>Выбери действие:</i>"
    )
    await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")

# Callbacks for profile actions (unchanged)
@router.callback_query(F.data == "inventory_cb")
async def inventory_cb(call: CallbackQuery):
    uid = call.from_user.id
    user = await fetch_one("SELECT user_items FROM users WHERE user_id = $1", {"uid": uid})

    if not user or not user.get('user_items'):
        items = {}
    else:
        try:
            items = json.loads(user['user_items'])
        except (json.JSONDecodeError, TypeError):
            items = {} # Fallback if JSON is malformed

    if not items:
        text = "🎒 Твой инвентарь пуст."
    else:
        text = "🎒 <b>Твой инвентарь:</b>\n\n"
        for item_name, count in items.items():
            text += f"- {item_name}: {count} шт.\n"

    try:
        await call.message.edit_text(text, parse_mode="HTML") # Или call.message.answer, если не хотите редактировать
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await call.message.answer(text, parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data == "quests_cb")
async def quests_cb(call: CallbackQuery):
    await call.answer()
    await show_quests(call) # Pass the call object directly

@router.callback_query(F.data == "zones_cb")
async def zones_cb(call: CallbackQuery):
    await call.answer()
    await show_zones(call.from_user.id, call) # Pass the call object directly

@router.callback_query(F.data == "pets_cb")
async def pets_cb(call: CallbackQuery):
    await call.answer()
    await show_pets_paginated(call.from_user.id, call) # Pass the call object directly

# Command handlers fallback (unchanged, but now call updated unified functions)
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
    await show_pets_paginated(message.from_user.id, message)


# Unified function for quests
async def show_quests(source: Message | CallbackQuery, page: int = 1):
    uid = source.from_user.id if isinstance(source, CallbackQuery) else source.from_user.id
    
    # Check for new quests before displaying
    await assign_new_quests(uid, source if isinstance(source, Message) else source.message)
    
    # Fetch all user quests, including completed ones, to show history
    quests = await fetch_all("SELECT * FROM quests WHERE user_id = $1 ORDER BY completed ASC, id DESC", {"uid": uid})
    
    if not quests:
        text = "📜 У тебя пока нет активных квестов."
        markup = None
    else:
        text, kb = build_quests_text_and_markup(quests, page)
        markup = kb.as_markup()

    if isinstance(source, Message):
        await source.answer(text, reply_markup=markup, parse_mode="HTML")
    else:
        try:
            await source.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): # Avoid error if text is identical
                await source.message.answer(text, reply_markup=markup, parse_mode="HTML") # Fallback to new message
        await source.answer() # Close callback query


# Build quests text and pagination (UPDATED)
def build_quests_text_and_markup(quests: list[dict], page: int = 1, per_page: int = 3):
    total_pages = max(1, ceil(len(quests) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_quests = quests[start:end]

    text = "🎯 <b>Твои квесты:</b>\n\n"
    kb = InlineKeyboardBuilder()

    active_quests_shown = 0
    for q_record in page_quests:
        quest_def = QUESTS_DEFINITIONS.get(q_record['quest_id'])
        if not quest_def: # Skip if definition not found (shouldn't happen if data is consistent)
            continue
        
        active_quests_shown += 1
        
        progress = f"{q_record['progress']}/{quest_def['goal']}" if quest_def['goal'] > 0 else "Неограниченный"
        status = ""
        if q_record['completed'] and q_record.get('claimed', False):
            status = "✅ Забрана"
        elif q_record['completed'] and not q_record.get('claimed', False):
            status = "🎁 Готово!"
        else:
            status = "🔄 В процессе"
            
        rewards = []
        if quest_def['reward_coins'] > 0:
            rewards.append(f"💰 {quest_def['reward_coins']} петкойнов")
        if quest_def['reward_egg_type']: # Check for reward_egg_type
            rewards.append(f"🥚 1 {quest_def['reward_egg_type']} яйцо") # Display egg type
        reward_text = "Награда: " + ", ".join(rewards) if rewards else "Без награды"

        text += (
            f"🔹 <b>{quest_def['name']}</b>\n"
            f"📖 {quest_def['description']}\n"
            f"🌍 Зона: {quest_def.get('zone', 'Не привязана')} | Прогресс: {progress} | Статус: {status}\n"
            f"{reward_text}\n\n"
        )
        if q_record['completed'] and not q_record.get('claimed', False):
            kb.button(text=f"🎁 Забрать «{quest_def['name']}»", callback_data=f"claim_quest:{q_record['id']}")

    if active_quests_shown == 0 and page == 1: # If no active quests, show this
         text += "Пока нет активных квестов. Новые квесты могут появляться по мере твоего прогресса!"
         
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

# Claim quest reward (UPDATED)
@router.callback_query(F.data.startswith("claim_quest:"))
async def claim_quest_callback(call: CallbackQuery):
    uid = call.from_user.id
    quest_db_id = int(call.data.split(":")[1]) # This is the DB ID of the quest record

    quest_record = await fetch_one("SELECT * FROM quests WHERE id = $1 AND user_id = $2", {"id": quest_db_id, "user_id": uid})
    if not quest_record or not quest_record['completed'] or quest_record.get('claimed', False):
        return await call.answer("Этот квест не завершен или награда уже забрана.", show_alert=True)

    quest_def = QUESTS_DEFINITIONS.get(quest_record['quest_id'])
    if not quest_def:
        return await call.answer("Ошибка: Определение квеста не найдено.", show_alert=True)

    # Use the specific claim_quest_reward function that handles different reward types
    success, msg = await claim_quest_reward(uid, quest_db_id)
    
    await call.answer(msg, show_alert=True)
    
    # After claiming a quest, check for new assignable quests
    await assign_new_quests(uid, call.message)
    
    # Refresh quests display
    await show_quests(call)


# Pagination callback (unchanged)
@router.callback_query(F.data.startswith("quests_page:"))
async def paginate_quests_callback(call: CallbackQuery):
    page = int(call.data.split(":")[1])
    await show_quests(call, page)

# Set active zone (unchanged logic, but show_zones is updated)
@router.callback_query(F.data.startswith("zone_set:"))
async def set_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone_name = call.data.split(":")[1] # Renamed variable for clarity
    
    # Check if the zone is actually unlocked before setting
    user_zone_record = await fetch_one("SELECT unlocked FROM user_zones WHERE user_id = $1 AND zone = $2", {"uid": uid, "zone": zone_name})
    if not user_zone_record or not user_zone_record['unlocked']:
        return await call.answer("Эта зона ещё не открыта!", show_alert=True)

    await execute_query(
        "UPDATE users SET active_zone = $1 WHERE user_id = $2",
        {"active_zone": zone_name, "uid": uid}, # Use zone_name
    )
    await call.answer(f"🌍 Зона «{zone_name}» выбрана!") # Use zone_name
    await show_zones(uid, call)

# Buy a zone (UPDATED with full unlock conditions check)
@router.callback_query(F.data.startswith("zone_buy:"))
async def buy_zone_callback(call: CallbackQuery):
    uid = call.from_user.id
    zone_name = call.data.split(":")[1] # Renamed variable for clarity

    zone_data = await fetch_one("SELECT * FROM zones WHERE name = $1", {"name": zone_name})
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    
    if not zone_data or not user:
        return await call.answer("Ошибка загрузки зоны.", show_alert=True)

    # Check if already unlocked
    user_zone_status = await fetch_one("SELECT unlocked FROM user_zones WHERE user_id = $1 AND zone = $2", {"uid": uid, "zone": zone_name})
    if user_zone_status and user_zone_status['unlocked']:
        return await call.answer("Эта зона уже открыта!", show_alert=True)

    cost = zone_data['cost']
    if user['coins'] < cost:
        return await call.answer("Недостаточно петкойнов 💸", show_alert=True)
    
    # --- Check full unlock_conditions from DB ---
    conds = json.loads(zone_data.get('unlock_conditions', '{}') or '{}')
    can_unlock_via_conditions = True

    if conds.get('hatched_count') and user.get('hatched_count', 0) < conds['hatched_count']:
        can_unlock_via_conditions = False
    
    if conds.get('coins') and user['coins'] < conds['coins']: # This checks coins for unlock, not just purchase
        can_unlock_via_conditions = False
    
    if conds.get('merged_count') and user.get('merged_count', 0) < conds['merged_count']:
        can_unlock_via_conditions = False
    
    if conds.get('highest_pet_level') and user.get('highest_pet_level', 0) < conds['highest_pet_level']:
        can_unlock_via_conditions = False

    # Prerequisite zone exploration count
    user_explore_counts = json.loads(user.get('explore_counts', '{}') or '{}')
    if conds.get('prerequisite_zone'):
        req_zone_parts = conds['prerequisite_zone'].split('_explored_')
        if len(req_zone_parts) == 2:
            req_zone_name = req_zone_parts[0]
            req_explore_count = int(req_zone_parts[1])
            if user_explore_counts.get(req_zone_name, 0) < req_explore_count:
                can_unlock_via_conditions = False
        else:
            can_unlock_via_conditions = False 
    
    # Prerequisite quest
    if conds.get('prerequisite_quest'):
        user_completed_claimed_quests = await fetch_all(
            "SELECT quest_id FROM quests WHERE user_id = $1 AND completed = TRUE AND claimed = TRUE", {"uid": uid}
        )
        completed_claimed_quest_ids = {q['quest_id'] for q in user_completed_claimed_quests}
        if conds['prerequisite_quest'] not in completed_claimed_quest_ids:
            can_unlock_via_conditions = False

    if not can_unlock_via_conditions:
        # Construct specific error message if possible
        error_msg = "Ты не соответствуешь условиям разблокировки этой зоны:\n"
        if conds.get('hatched_count') and user.get('hatched_count', 0) < conds['hatched_count']:
            error_msg += f"- Вылупи {conds['hatched_count']} питомцев (у тебя {user.get('hatched_count', 0)}).\n"
        if conds.get('coins') and user['coins'] < conds['coins']:
            error_msg += f"- Набери {conds['coins']} монет (у тебя {user['coins']}).\n"
        if conds.get('merged_count') and user.get('merged_count', 0) < conds['merged_count']:
            error_msg += f"- Объедини {conds['merged_count']} питомцев (у тебя {user.get('merged_count', 0)}).\n"
        if conds.get('highest_pet_level') and user.get('highest_pet_level', 0) < conds['highest_pet_level']:
            error_msg += f"- Достигни {conds['highest_pet_level']} уровня питомца (макс. {user.get('highest_pet_level', 0)}).\n"
        if conds.get('prerequisite_zone'):
            req_zone_parts = conds['prerequisite_zone'].split('_explored_')
            if len(req_zone_parts) == 2:
                req_zone_name = req_zone_parts[0]
                req_explore_count = int(req_zone_parts[1])
                if user_explore_counts.get(req_zone_name, 0) < req_explore_count:
                    error_msg += f"- Исследуй зону '{req_zone_name}' {req_explore_count} раз (у тебя {user_explore_counts.get(req_zone_name, 0)}).\n"
        if conds.get('prerequisite_quest'):
            error_msg += f"- Заверши квест '{QUESTS_DEFINITIONS.get(conds['prerequisite_quest'], {}).get('name', conds['prerequisite_quest'])}' (не завершен/не забран).\n"

        return await call.answer(error_msg, show_alert=True)
    # --- End of unlock conditions check ---

    # Deduct coins and unlock
    await execute_query(
        "UPDATE users SET coins = coins - $1 WHERE user_id = $2",
        {"cost": cost, "uid": uid},
    )
    await execute_query(
        "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
        "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
        {"uid": uid, "zone": zone_name}
    )
    await call.answer(f"🎉 Зона «{zone_name}» успешно открыта!")
    await show_zones(uid, call)


# Quest progress checker (UPDATED)
async def check_quest_progress(uid: int, message_obj: Message = None): # Renamed `message` to `message_obj` to avoid confusion with internal 'message'
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        return
    
    # Get current user progress stats
    user_data_for_quests = {
        "hatched_count": user.get('hatched_count', 0),
        "merged_count": user.get('merged_count', 0),
        "eggs_collected": user.get('eggs_collected', 0), # Assumes this is tracked separately
        "explore_counts": json.loads(user.get('explore_counts', '{}') or '{}'),
        "monsters_defeated_counts": json.loads(user.get('monsters_defeated_counts', '{}') or '{}'),
        "total_coins_collected": user.get('total_coins_collected', 0), # New field
        "highest_pet_level": user.get('highest_pet_level', 0), # New field
    }
    
    # Fetch arena wins
    user_arena_team = await fetch_one("SELECT wins FROM arena_team WHERE user_id = $1", {"uid": uid})
    user_data_for_quests["arena_wins"] = user_arena_team.get('wins', 0) if user_arena_team else 0


    # Fetch quests in progress (not completed and not claimed)
    quests_in_progress = await fetch_all(
        "SELECT * FROM quests WHERE user_id = $1 AND completed = FALSE AND claimed = FALSE", {"uid": uid}
    )

    for q_record in quests_in_progress:
        quest_def = QUESTS_DEFINITIONS.get(q_record['quest_id'])
        if not quest_def:
            continue # Skip if definition not found

        new_progress = q_record['progress'] # Start with current progress

        # Determine new progress based on quest type
        if quest_def['type'] in QUEST_PROGRESS_MAPPING:
            mapper_key = QUEST_PROGRESS_MAPPING[quest_def['type']]
            
            if mapper_key == "explore_counts" or mapper_key == "monsters_defeated_counts":
                zone_target = quest_def.get('zone_target')
                if zone_target:
                    new_progress = user_data_for_quests[mapper_key].get(zone_target, 0)
            elif mapper_key == "eggs_collected":
                # Ensure eggs_collected is tracked by DB update, not just len(user.get("eggs"))
                new_progress = user_data_for_quests[mapper_key]
            else:
                new_progress = user_data_for_quests.get(mapper_key, 0) # Get directly from user_data_for_quests

        # Update quest progress in DB
        if new_progress >= quest_def['goal'] and not q_record['completed']:
            await execute_query(
                "UPDATE quests SET progress = $1, completed = TRUE WHERE id = $2",
                {"progress": quest_def['goal'], "id": q_record['id']}
            )
            if message_obj:
                try:
                    await message_obj.answer(
                        f"🏆 <b>@{message_obj.from_user.username or 'ты'} завершил квест «{quest_def['name']}»!</b>\n"
                        f"🎁 Награда доступна для получения! Используй команду /quests."
                    )
                except TelegramBadRequest as e:
                    print(f"Error sending quest completion message: {e}")
        elif new_progress != q_record['progress']:
            # Only update if progress has actually changed and quest isn't completed yet
            await execute_query(
                "UPDATE quests SET progress = $1 WHERE id = $2",
                {"progress": new_progress, "id": q_record['id']}
            )

# Zone unlock checker (UPDATED)
async def check_zone_unlocks(uid: int, message_obj: Message = None): # Renamed `message` to `message_obj`
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        return
    
    # Get current user progress stats relevant for zone unlocks
    user_hatched_count = user.get('hatched_count', 0)
    user_merged_count = user.get('merged_count', 0)
    user_coins = user['coins']
    user_explore_counts = json.loads(user.get('explore_counts', '{}') or '{}')
    user_highest_pet_level = user.get('highest_pet_level', 0)

    # Fetch already unlocked zones
    unlocked_zones_db = await fetch_all(
        "SELECT zone FROM user_zones WHERE user_id = $1 AND unlocked = TRUE", {"uid": uid}
    )
    unlocked_names_set = {z['zone'] for z in unlocked_zones_db}

    # Fetch all completed and claimed quests for prerequisite_quest check
    user_completed_claimed_quests = await fetch_all(
        "SELECT quest_id FROM quests WHERE user_id = $1 AND completed = TRUE AND claimed = TRUE", {"uid": uid}
    )
    completed_claimed_quest_ids = {q['quest_id'] for q in user_completed_claimed_quests}

    all_zones_from_db = await fetch_all("SELECT * FROM zones") # Fetch all zone definitions

    for zone_info in all_zones_from_db:
        zone_name = zone_info['name']
        if zone_name in unlocked_names_set:
            continue # Already unlocked

        conds = json.loads(zone_info.get('unlock_conditions', '{}') or '{}') # Parse JSONB conditions
        can_unlock = True
        
        # Check hatched_count condition
        if conds.get('hatched_count') and user_hatched_count < conds['hatched_count']:
            can_unlock = False
        
        # Check coins condition
        if conds.get('coins') and user_coins < conds['coins']:
            can_unlock = False
        
        # Check merged_count condition
        if conds.get('merged_count') and user_merged_count < conds['merged_count']: # Use 'merged_count' as key
            can_unlock = False
        
        # Check highest_pet_level condition
        if conds.get('highest_pet_level') and user_highest_pet_level < conds['highest_pet_level']:
            can_unlock = False

        # Check prerequisite_zone exploration count condition
        if conds.get('prerequisite_zone'):
            req_zone_parts = conds['prerequisite_zone'].split('_explored_')
            if len(req_zone_parts) == 2:
                req_zone_name = req_zone_parts[0]
                req_explore_count = int(req_zone_parts[1])
                if user_explore_counts.get(req_zone_name, 0) < req_explore_count:
                    can_unlock = False
            else: # Malformed prerequisite_zone string
                can_unlock = False 
        
        # Check prerequisite_quest condition
        if conds.get('prerequisite_quest'):
            if conds['prerequisite_quest'] not in completed_claimed_quest_ids:
                can_unlock = False

        if can_unlock:
            await execute_query(
                "INSERT INTO user_zones (user_id, zone, unlocked) VALUES ($1, $2, TRUE) "
                "ON CONFLICT (user_id, zone) DO UPDATE SET unlocked = TRUE",
                {"uid": uid, "zone": zone_name}
            )
            if message_obj:
                try:
                    await message_obj.answer(f"🌍 Ты открыл новую зону: <b>{zone_info['name']}</b>!\n📖 {zone_info['description']}", parse_mode="HTML")
                except TelegramBadRequest as e:
                    print(f"Error sending zone unlock message: {e}")

# Get zone buff multiplier (unchanged, but now uses new zone columns)
async def get_zone_buff(user_id: int) -> dict: # Changed to take user_id and return dict with type and value
    user = await fetch_one("SELECT active_zone FROM users WHERE user_id = $1", {"uid": user_id})
    if not user or not user.get('active_zone'):
        return {"type": "none", "value": 0}
    
    zone = await fetch_one("SELECT buff_type, buff_value FROM zones WHERE name = $1", {"name": user['active_zone']})
    
    if zone and zone.get('buff_type') and zone.get('buff_type') != 'none':
        return {"type": zone['buff_type'], "value": zone.get('buff_value', 0)}
    return {"type": "none", "value": 0}

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