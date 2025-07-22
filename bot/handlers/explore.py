# bot/handlers/explore.py
import asyncio
import random
import json
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest # Import for error handling

from db.db import fetch_one, fetch_all, execute_query
from bot.handlers.start import check_quest_progress, get_zone_buff # Ensure these are correctly imported

router = Router()

EXPLORE_COOLDOWN = timedelta(seconds=60)    # 1 minute for testing, increase for production
EXPLORE_ENERGY_COST = 10                    # Base energy consumed per exploration
MAX_ENERGY = 200                            # Maximum energy a user can have
ENERGY_RECOVERY_RATE_PER_MINUTE = 1         # Energy regenerated per minute

# Exploration Outcomes (these are base ranges, actual values might be buffed by zone data)
EXPLORE_BASE_COIN_RANGE = (50, 150)
EXPLORE_BASE_XP_RANGE = (10, 30)
EXPLORE_BASE_ITEM_CHANCE = 0.05 # Base chance to find an item (e.g., 5%)

EXPLORE_FAIL_MESSAGES = [
    "Тебе не хватает энергии для исследования.",
    "Твои питомцы слишком устали для нового приключения.",
    "Недостаточно сил для полноценного похода.",
    "Отдохни немного, прежде чем отправляться в новое путешествие."
]

# Messages for successful exploration (placeholders for formatting)
EXPLORE_SUCCESS_MESSAGES = [
    "Твой питомец {pet_name} исследовал {zone_name_ru} и нашел {coins} 💰. Он получил {xp} XP!",
    "Прогулка по {zone_name_ru} принесла {pet_name} {xp} XP и {coins} 💰.",
    "На {zone_name_ru} {pet_name} славно потрудился, собрав {coins} 💰, и стал опытнее на {xp} XP!"
]

# --- Energy Management Functions ---

async def get_user_energy_data(user_id: int) -> dict:
    """Fetches raw energy data from the database."""
    user = await fetch_one("SELECT energy, last_energy_update FROM users WHERE user_id = $1", {"uid": user_id})
    if user:
        # Ensure last_energy_update is a datetime object
        if isinstance(user['last_energy_update'], str):
            user['last_energy_update'] = datetime.fromisoformat(user['last_energy_update'])
        # Ensure it's timezone-aware if you are using timezone.utc
        if user['last_energy_update'] and user['last_energy_update'].tzinfo is None:
            user['last_energy_update'] = user['last_energy_update'].replace(tzinfo=timezone.utc)
        return {"energy": user['energy'], "last_energy_update": user['last_energy_update']}
    # If user not found or no update data, initialize with full energy at current time
    return {"energy": MAX_ENERGY, "last_energy_update": datetime.now(timezone.utc)} # Use now(timezone.utc)

async def update_user_energy_db(user_id: int, new_energy: int, update_time: datetime = None):
    """Updates energy and last_energy_update in the database."""
    if update_time is None:
        update_time = datetime.now(timezone.utc) # Use now(timezone.utc) for consistency
    await execute_query("UPDATE users SET energy = $1, last_energy_update = $2 WHERE user_id = $3",
                        {"energy": new_energy, "update_time": update_time, "uid": user_id})

async def recalculate_energy(user_id: int) -> int:
    """
    Recalculates and updates the user's current energy based on elapsed time.
    Returns the current energy after recalculation.
    """
    energy_data = await get_user_energy_data(user_id)
    current_energy = energy_data['energy']
    last_update = energy_data['last_energy_update']

    max_user_energy = MAX_ENERGY # Using global constant for now

    # If last_update is None (e.g., new user), initialize energy to max
    if last_update is None:
        await update_user_energy_db(user_id, max_user_energy, datetime.now(timezone.utc))
        return max_user_energy

    now_utc = datetime.now(timezone.utc)
    time_elapsed_minutes = (now_utc - last_update).total_seconds() / 60

    recovered_energy = int(time_elapsed_minutes * ENERGY_RECOVERY_RATE_PER_MINUTE)
    
    new_energy = min(max_user_energy, current_energy + recovered_energy)

    # Only update if energy has actually changed or if max energy was reached and time passed
    if new_energy != current_energy:
        await update_user_energy_db(user_id, new_energy, now_utc)
    elif new_energy == max_user_energy and recovered_energy > 0:
        # If energy is already full, but time has passed, update last_energy_update
        # to prevent large accumulated time_elapsed_minutes on next check.
        await execute_query("UPDATE users SET last_energy_update = $1 WHERE user_id = $2",
                            {"last_update": now_utc, "uid": user_id})

    return new_energy

# --- Pet & Battle Functions ---

async def check_and_level_up_pet(bot_instance, user_id, pet_id):
    """Checks if a pet has enough XP to level up and updates its stats."""
    pet_record = await fetch_one("SELECT id, name, level, xp, xp_needed, stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})

    if pet_record:
        pet = dict(pet_record) # Create a mutable copy

        level_up_count = 0
        while pet['xp'] >= pet['xp_needed']:
            pet['level'] += 1
            pet['xp'] -= pet['xp_needed']
            pet['xp_needed'] = int(pet['xp_needed'] * 1.5) # XP needed increases

            # Ensure pet['stats'] is a dict
            if isinstance(pet['stats'], str):
                pet_stats = json.loads(pet['stats'])
            else:
                pet_stats = pet['stats']

            # Increase stats on level up
            pet_stats['atk'] += random.randint(1, 3)
            pet_stats['def'] += random.randint(1, 3)
            pet_stats['hp'] += random.randint(3, 7) # Max HP increases

            pet['stats'] = json.dumps(pet_stats) # Store back as JSON string

            await execute_query(
                "UPDATE pets SET level = $1, xp = $2, xp_needed = $3, stats = $4 WHERE id = $5",
                {"level": pet['level'], "xp": pet['xp'], "xp_needed": pet['xp_needed'],
                 "stats": pet['stats'], "id": pet_id}
            )
            level_up_count += 1

        if level_up_count > 0:
            updated_pet = await fetch_one("SELECT name, level, stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
            if updated_pet:
                # Update highest_pet_level in users table
                user = await fetch_one("SELECT highest_pet_level FROM users WHERE user_id = $1", {"uid": user_id})
                if user and updated_pet['level'] > user.get('highest_pet_level', 0):
                    await execute_query("UPDATE users SET highest_pet_level = $1 WHERE user_id = $2",
                                        {"highest_pet_level": updated_pet['level'], "uid": user_id})

                # Fetch user's first name for a personalized message
                user_chat_info = await bot_instance.get_chat(user_id)
                user_name = user_chat_info.first_name if user_chat_info.first_name else user_chat_info.full_name

                if isinstance(updated_pet['stats'], str):
                    updated_pet_stats = json.loads(updated_pet['stats'])
                else:
                    updated_pet_stats = updated_pet['stats']

                await bot_instance.send_message(
                    user_id,
                    f"🎉 Поздравляем, {user_name}!\nТвой питомец <b>{updated_pet['name']}</b> достиг <b>{updated_pet['level']}</b> уровня!\n"
                    f"Новые характеристики:\n🗡 Атака: {updated_pet_stats['atk']} | 🛡 Защита: {updated_pet_stats['def']} | ❤ Здоровье: {updated_pet_stats['hp']}",
                    parse_mode="HTML"
                )
        return True # Indicates if a level up occurred
    return False

# NOTE: get_pet_current_hp and update_pet_current_hp are currently placeholders.
# If you implement persistent HP for pets, you'll need to store current_hp in the DB.
async def get_pet_current_hp(pet_id: int, user_id: int):
    """Retrieves the current HP of a pet. (Currently assumes full HP for battle start)"""
    pet = await fetch_one("SELECT stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
    if pet and pet['stats']:
        stats = json.loads(pet['stats']) if isinstance(pet['stats'], str) else pet['stats']
        return stats.get('hp') # Assuming 'hp' in stats is max HP
    return 0

async def update_pet_current_hp(pet_id: int, user_id: int, new_hp: int):
    """Updates the current HP of a pet. (Placeholder for future persistent HP)"""
    # This function would be used if you had a 'current_hp' column in 'pets' table
    pass

async def simulate_battle(bot_instance: object, user_id: int, pet: dict, monster: dict, message_obj: Message):
    """Simulates a turn-based battle between a pet and a monster."""
    pet_name = pet['name']
    monster_name = monster['name']
    
    # Get pet's stats (current HP will be full for now)
    pet_stats = json.loads(pet['stats']) if isinstance(pet['stats'], str) else pet['stats']
    pet_current_hp = pet_stats['hp'] # Use max HP for simplicity at start of battle
    pet_atk = pet_stats['atk']
    pet_def = pet_stats['def']

    monster_current_hp = monster['hp']
    monster_atk = monster['atk']
    monster_def = monster['def']

    battle_log = [f"⚡️ Началась битва! <b>{pet_name}</b> (Ур. {pet['level']}) против <b>{monster_name}</b> (Ур. {monster['level']})!"]
    
    # Store battle message to update it
    battle_message = await message_obj.answer("\n".join(battle_log), parse_mode="HTML")

    turn = 1
    # Max 20 turns to prevent infinite loops (or until one combatant is defeated)
    while pet_current_hp > 0 and monster_current_hp > 0 and turn < 20: 
        # Pet attacks Monster
        pet_damage = max(1, pet_atk - monster_def)
        monster_current_hp -= pet_damage
        battle_log.append(f"Ход {turn}: <b>{pet_name}</b> атакует <b>{monster_name}</b>, нанося {pet_damage} урона. У <b>{monster_name}</b> осталось {max(0, monster_current_hp)} HP.")

        try:
            await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): # Ignore if text is identical
                await message_obj.answer("\n".join(battle_log), parse_mode="HTML") # Send new message if edit fails
        await asyncio.sleep(1) # Small delay for readability

        if monster_current_hp <= 0:
            battle_log.append(f"✅ <b>{pet_name}</b> победил <b>{monster_name}</b>!")
            try:
                await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
            except TelegramBadRequest:
                await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
            
            # Update monsters_defeated_counts for the user
            user = await fetch_one("SELECT monsters_defeated_counts FROM users WHERE user_id = $1", {"uid": user_id})
            monsters_defeated_counts = json.loads(user.get('monsters_defeated_counts', '{}') or '{}')
            # Assuming monster['name'] is unique enough for tracking defeated counts
            monsters_defeated_counts[monster['name']] = monsters_defeated_counts.get(monster['name'], 0) + 1
            await execute_query("UPDATE users SET monsters_defeated_counts = $1 WHERE user_id = $2",
                                {"monsters_defeated_counts": json.dumps(monsters_defeated_counts), "uid": user_id})

            return "win", monster['xp_reward'], monster['coin_reward'], [] # Dropped items list (empty for now)
            
        # Monster attacks Pet
        monster_damage = max(1, monster_atk - pet_def)
        pet_current_hp -= monster_damage
        battle_log.append(f"Ход {turn}: <b>{monster_name}</b> атакует <b>{pet_name}</b>, нанося {monster_damage} урона. У <b>{pet_name}</b> осталось {max(0, pet_current_hp)} HP.")

        try:
            await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
        await asyncio.sleep(1) # Small delay for readability

        if pet_current_hp <= 0:
            battle_log.append(f"❌ <b>{pet_name}</b> проиграл битву против <b>{monster_name}</b>.")
            try:
                await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
            except TelegramBadRequest:
                await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
            return "loss", 0, 0, [] # No rewards for loss
        
        turn += 1
        
    # If battle ends due to turn limit
    if pet_current_hp > 0:
        battle_log.append(f"✅ Битва окончена! <b>{pet_name}</b> одолел <b>{monster_name}</b>!")
        # If monster HP > 0 but pet HP > 0, it means turn limit was reached and pet survived.
        # Decide if this is a win or a draw. For now, let's treat it as a win if pet survived.
        try:
            await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
        except TelegramBadRequest:
            await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
        
        # If pet survived (even if monster didn't explicitly die within turns) treat as win for progress
        user = await fetch_one("SELECT monsters_defeated_counts FROM users WHERE user_id = $1", {"uid": user_id})
        monsters_defeated_counts = json.loads(user.get('monsters_defeated_counts', '{}') or '{}')
        monsters_defeated_counts[monster['name']] = monsters_defeated_counts.get(monster['name'], 0) + 1
        await execute_query("UPDATE users SET monsters_defeated_counts = $1 WHERE user_id = $2",
                            {"monsters_defeated_counts": json.dumps(monsters_defeated_counts), "uid": user_id})

        return "win", monster['xp_reward'], monster['coin_reward'], []
    else:
        battle_log.append(f"❌ Битва окончена! <b>{pet_name}</b> проиграл битву против <b>{monster_name}</b>.")
        try:
            await battle_message.edit_text("\n".join(battle_log), parse_mode="HTML")
        except TelegramBadRequest:
            await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
        return "loss", 0, 0, []


# --- Command Handlers ---

@router.message(Command("explore"))
async def explore_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        await asyncio.sleep(0.5)
        return
    
    if not command.args:
        unlocked_zones_data = await fetch_all("SELECT z.name, z.description FROM user_zones uz JOIN zones z ON uz.zone = z.name WHERE uz.user_id = $1 AND uz.unlocked = TRUE", {"uid": uid})
        
        if not unlocked_zones_data:
            await message.answer("У тебя пока нет разблокированных зон для исследования. Чтобы разблокировать первую зону, выполни квесты.") # Clarified
            await asyncio.sleep(0.5)
            return
            
        builder = InlineKeyboardBuilder()
        for zone in unlocked_zones_data:
            builder.button(text=zone['name'], callback_data=f"select_explore_zone_{zone['name']}")
        builder.adjust(2)

        zone_list_text = "\n".join([f"- <b>{z['name']}</b>: {z['description']}" for z in unlocked_zones_data])
        
        await message.answer(
            "🌍 Выбери зону для исследования или укажи ее ID питомца и название:\n"
            "<code>/explore &lt;ID питомца&gt; &lt;Название локации&gt;</code>\n\n"
            "Доступные тебе зоны:\n"
            f"{zone_list_text}\n\n"
            "Пример: <code>/explore 1 Лужайка</code>", # Changed example to reflect simpler pet ID
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await asyncio.sleep(0.5)
        return
    
    args = command.args.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Неверный формат команды. Используй: <code>/explore &lt;ID питомца&gt; &lt;Название локации&gt;</code>", parse_mode="HTML")
        await asyncio.sleep(0.5)
        return

    try:
        pet_id = int(args[0])
    except ValueError:
        await message.answer("ID питомца должен быть числом. Используй: <code>/explore &lt;ID питомца&gt; &lt;Название локации&gt;</code>", parse_mode="HTML")
        await asyncio.sleep(0.5)
        return
    
    zone_name = args[1]

    zone_data = await fetch_one("SELECT * FROM zones WHERE name = $1", {"zone_name": zone_name})
    if not zone_data:
        await message.answer(f"Локация '{zone_name}' не найдена. Проверь название и попробуй снова.")
        await asyncio.sleep(0.5)
        return

    user_zone_status = await fetch_one("SELECT unlocked FROM user_zones WHERE user_id = $1 AND zone = $2",
                                        {"uid": uid, "zone_name": zone_name})
    if not user_zone_status or not user_zone_status['unlocked']:
        await message.answer(f"Ты ещё не разблокировал локацию '{zone_name}'.")
        await asyncio.sleep(0.5)
        return

    pet_to_explore = await fetch_one("SELECT id, name, rarity, class, level, xp, stats, coin_rate FROM pets WHERE id = $1 AND user_id = $2",
                                     {"id": pet_id, "user_id": uid})
    if not pet_to_explore:
        await message.answer("У тебя нет питомца с таким ID. Проверь свой список питомцев.")
        await asyncio.sleep(0.5)
        return
    
    current_energy = await recalculate_energy(uid) # Always get the latest energy
    
    # Calculate actual energy cost for this zone
    energy_cost_multiplier = 1 + (zone_data.get('energy_cost_buff', 0) / 100) # Use .get for robustness
    actual_energy_cost = int(EXPLORE_ENERGY_COST * energy_cost_multiplier)

    if current_energy < actual_energy_cost:
        user_energy_data = await get_user_energy_data(uid) # Fetch raw data for last_energy_update
        last_update = user_energy_data['last_energy_update'] or datetime.now(timezone.utc) # Fallback

        if ENERGY_RECOVERY_RATE_PER_MINUTE > 0:
            seconds_for_one_point = 60 / ENERGY_RECOVERY_RATE_PER_MINUTE
        else:
            seconds_for_one_point = float('inf') # No regeneration

        now_utc = datetime.now(timezone.utc)
        seconds_since_last_update = (now_utc - last_update).total_seconds()
        
        seconds_into_current_cycle = seconds_since_last_update % seconds_for_one_point
        
        time_until_next_point = seconds_for_one_point - seconds_into_current_cycle
        points_needed = actual_energy_cost - current_energy
        
        time_to_regen_display = timedelta(seconds=0)

        if points_needed > 0:
            total_wait_seconds = time_until_next_point + (points_needed - 1) * seconds_for_one_point
            time_to_regen_display = timedelta(seconds=int(total_wait_seconds))

        # Format timedelta into a human-readable string
        total_seconds = int(time_to_regen_display.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        time_str_parts = []
        if hours > 0:
            time_str_parts.append(f"{hours}ч")
        if minutes > 0:
            time_str_parts.append(f"{minutes}м")
        if seconds > 0 or not time_str_parts: # Show seconds if non-zero or if no hours/minutes
            time_str_parts.append(f"{seconds}с")
        
        time_to_regen_str = " ".join(time_str_parts) if time_str_parts else "немедленно"

        await message.answer(
            f"🚫 {random.choice(EXPLORE_FAIL_MESSAGES)}\n"
            f"Текущая энергия: {current_energy}/{MAX_ENERGY}\n"
            f"Для исследования <b>{zone_data['name']}</b> нужно {actual_energy_cost} энергии.\n"
            f"⚡️ Энергия восстанавливается на {ENERGY_RECOVERY_RATE_PER_MINUTE} в минуту."
            f"\nПопробуй снова через {time_to_regen_str}.", # Corrected display
            parse_mode="HTML"
        )
        await asyncio.sleep(0.5)
        return

    # Check cooldown before proceeding
    last_explore_time_db = user.get('last_explore_time')
    # Ensure last_explore_time is a datetime object and timezone-aware
    if isinstance(last_explore_time_db, str):
        last_explore_time = datetime.fromisoformat(last_explore_time_db)
    elif last_explore_time_db:
        last_explore_time = last_explore_time_db.replace(tzinfo=timezone.utc) if last_explore_time_db.tzinfo is None else last_explore_time_db
    else:
        last_explore_time = datetime.min.replace(tzinfo=timezone.utc) # Default to a very old time

    if datetime.now(timezone.utc) - last_explore_time < EXPLORE_COOLDOWN: # Use now(timezone.utc)
        remaining_time = EXPLORE_COOLDOWN - (datetime.now(timezone.utc) - last_explore_time) # Use now(timezone.utc)
        # Format timedelta for cooldown
        total_seconds_cooldown = int(remaining_time.total_seconds())
        hours_c, remainder_c = divmod(total_seconds_cooldown, 3600)
        minutes_c, seconds_c = divmod(remainder_c, 60)
        
        cooldown_str_parts = []
        if hours_c > 0:
            cooldown_str_parts.append(f"{hours_c}ч")
        if minutes_c > 0:
            cooldown_str_parts.append(f"{minutes_c}м")
        if seconds_c > 0 or not cooldown_str_parts:
            cooldown_str_parts.append(f"{seconds_c}с")
        
        cooldown_display_str = " ".join(cooldown_str_parts) if cooldown_str_parts else "немедленно"

        await message.answer(
            f"⏳ Ты уже недавно исследовал эти места. Подожди {cooldown_display_str} перед следующим приключением."
        )
        await asyncio.sleep(0.5)
        return

    # Deduct energy and update exploration time
    new_energy_after_explore = current_energy - actual_energy_cost
    await update_user_energy_db(uid, new_energy_after_explore, datetime.now(timezone.utc)) # Use now(timezone.utc)
    await execute_query("UPDATE users SET last_explore_time = $1, active_zone = $2 WHERE user_id = $3",
                        {"time": datetime.now(timezone.utc), "active_zone": zone_name, "uid": uid}) # Use now(timezone.utc)

    # --- Start Simulation ---
    explore_message_text = (
        f"🌳 <b>{pet_to_explore['name']}</b> отправился исследовать <b>{zone_data['name']}</b>...\n"
        f"Это займет некоторое время. Пожалуйста, подожди."
    )
    explore_message = await message.answer(explore_message_text, parse_mode="HTML")

    exploration_duration = random.randint(zone_data['explore_duration_min'], zone_data['explore_duration_max'])
    await asyncio.sleep(exploration_duration)

    # --- Determine Outcome ---
    outcome_message = ""
    xp_gain_final = 0
    coins_found_final = 0

    # Get zone buff
    zone_buff = await get_zone_buff(uid) # get_zone_buff returns a dict
    buff_multiplier_xp = 1.0
    buff_multiplier_coin = 1.0

    if zone_buff and zone_buff['type'] == 'xp_rate':
        buff_multiplier_xp = 1.0 + (zone_buff['value'] / 100)
    elif zone_buff and zone_buff['type'] == 'coin_rate':
        buff_multiplier_coin = 1.0 + (zone_buff['value'] / 100)


    if random.random() < zone_data['pve_chance']: # PvE encounter
        monsters_in_zone = await fetch_all("SELECT * FROM monsters WHERE zone_name = $1 ORDER BY level ASC", {"zone_name": zone_name})
        
        if monsters_in_zone:
            selected_monster = random.choice(monsters_in_zone) # Randomly pick a monster from DB
            
            try: # Try to edit the previous message
                await explore_message.edit_text(f"🌳 <b>{pet_to_explore['name']}</b> в зоне <b>{zone_data['name']}</b> столкнулся с <b>{selected_monster['name']}</b>!", parse_mode="HTML")
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e): # Ignore if text is identical
                    await message.answer(f"🌳 <b>{pet_to_explore['name']}</b> в зоне <b>{zone_data['name']}</b> столкнулся с <b>{selected_monster['name']}</b>!", parse_mode="HTML") # Send new message if edit fails
            await asyncio.sleep(1) # Small pause before battle starts

            battle_result, xp_reward, coin_reward, dropped_items = await simulate_battle(
                message.bot, uid, pet_to_explore, selected_monster, message
            )
            
            if battle_result == "win":
                xp_gain_final = xp_reward
                coins_found_final = coin_reward
                outcome_message = f"<b>{pet_to_explore['name']}</b> победил {selected_monster['name']}!"
                
            else:
                outcome_message = f"<b>{pet_to_explore['name']}</b> проиграл битву с {selected_monster['name']}."
                # Optionally add a penalty for loss (e.g., less energy, temporary debuff)
        else:
            outcome_message = f"<b>{pet_to_explore['name']}</b> не нашел монстров в <b>{zone_data['name']}</b>, но и ничего не нашел."
    else: # Resource find / Normal exploration
        coins_found_final = random.randint(EXPLORE_BASE_COIN_RANGE[0], EXPLORE_BASE_COIN_RANGE[1])
        xp_gain_final = random.randint(EXPLORE_BASE_XP_RANGE[0], EXPLORE_BASE_XP_RANGE[1])

        # Apply zone buff
        coins_found_final = int(coins_found_final * buff_multiplier_coin)
        xp_gain_final = int(xp_gain_final * buff_multiplier_xp)
        
        coins_found_final += pet_to_explore.get('coin_rate', 0) # Add pet's coin_rate, use .get for robustness

        message_template = random.choice(EXPLORE_SUCCESS_MESSAGES)
        outcome_message = message_template.format(
            pet_name=pet_to_explore['name'],
            zone_name_ru=zone_data['name'],
            coins=coins_found_final,
            xp=xp_gain_final
        )

    # --- Apply Final Rewards and Update User Stats ---
    if xp_gain_final > 0:
        await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                            {"xp_gain": xp_gain_final, "id": pet_id, "user_id": uid})
        await check_and_level_up_pet(message.bot, uid, pet_id) # Check level up after XP gain

    if coins_found_final > 0:
        await execute_query("UPDATE users SET coins = coins + $1, total_coins_collected = total_coins_collected + $1 WHERE user_id = $2",
                            {"coins": coins_found_final, "uid": uid}) # Update total_coins_collected

    # Update explore_counts for the zone
    user_data = await fetch_one("SELECT explore_counts FROM users WHERE user_id = $1", {"uid": uid})
    explore_counts = json.loads(user_data.get('explore_counts', '{}') or '{}')
    explore_counts[zone_name] = explore_counts.get(zone_name, 0) + 1
    await execute_query("UPDATE users SET explore_counts = $1 WHERE user_id = $2",
                        {"explore_counts": json.dumps(explore_counts), "uid": uid})

    final_summary_text = f"<b>Результаты исследования:</b>\n"
    if xp_gain_final > 0:
        final_summary_text += f"➕ {xp_gain_final} XP для <b>{pet_to_explore['name']}</b>\n"
    if coins_found_final > 0:
        final_summary_text += f"💰 {coins_found_final} монет\n"
    if not (xp_gain_final > 0 or coins_found_final > 0):
        final_summary_text += "Ничего особого не найдено, но приключение того стоило!\n"

    # Fetch updated energy after all deductions/rewards
    updated_current_energy = await recalculate_energy(uid) # Re-fetch to show precise current state

    try:
        await explore_message.edit_text( # Attempt to edit the initial exploration message
            f"{outcome_message}\n\n"
            f"{final_summary_text}"
            f"\n⚡️ Энергия: {updated_current_energy}/{MAX_ENERGY}",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await message.answer( # Fallback to new message if edit fails (e.g., too old)
                f"{outcome_message}\n\n"
                f"{final_summary_text}"
                f"\n⚡️ Энергия: {updated_current_energy}/{MAX_ENERGY}",
                parse_mode="HTML"
            )
    await asyncio.sleep(0.5)

    await check_quest_progress(uid, message) # Moved this to the end of exploration process


@router.callback_query(F.data.startswith("select_explore_zone_"))
async def select_explore_zone_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    zone_name = callback.data.split("select_explore_zone_")[1]

    user_pets_db = await fetch_all("SELECT id, name, level, rarity FROM pets WHERE user_id = $1 ORDER BY level DESC, rarity DESC", {"uid": uid})
    
    if not user_pets_db:
        await callback.message.answer("У тебя нет питомцев для исследования этой зоны.")
        await callback.answer()
        return

    pet_list_text = "\n".join([f"ID {pet['id']} — {pet['name']} ({pet['rarity']}, Ур. {pet['level']})" for pet in user_pets_db])

    try:
        await callback.message.edit_text(
            f"Ты выбрал зону <b>{zone_name}</b>. Теперь выбери питомца, которого отправишь туда.\n\n"
            f"Твои питомцы:\n{pet_list_text}\n\n"
            f"Используй команду: <code>/explore &lt;ID питомца&gt; {zone_name}</code>\n"
            f"Пример: <code>/explore {user_pets_db[0]['id']} {zone_name}</code>",
            parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e): # Ignore if text is identical
            await callback.message.answer( # Send as new message if edit fails
                f"Ты выбрал зону <b>{zone_name}</b>. Теперь выбери питомца, которого отправишь туда.\n\n"
                f"Твои питомцы:\n{pet_list_text}\n\n"
                f"Используй команду: <code>/explore &lt;ID питомца&gt; {zone_name}</code>\n"
                f"Пример: <code>/explore {user_pets_db[0]['id']} {zone_name}</code>",
                parse_mode="HTML"
            )
    await callback.answer()
    await asyncio.sleep(0.5)