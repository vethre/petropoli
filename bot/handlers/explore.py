# bot/handlers/explore.py
import asyncio
import random
import json
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.db import fetch_one, fetch_all, execute_query
from bot.handlers.start import check_quest_progress # Ensure this is correctly imported

router = Router()

EXPLORE_COOLDOWN = timedelta(seconds=60) # 1 minute for testing, increase for production
EXPLORE_ENERGY_COST = 10                  # Base energy consumed per exploration
MAX_ENERGY = 100                          # Maximum energy a user can have
ENERGY_REGEN_RATE = 10                    # Energy regenerated per hour (e.g., 10 energy points per hour)

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

async def get_user_energy(user_id: int) -> dict:
    user = await fetch_one("SELECT energy, last_energy_update FROM users WHERE user_id = $1", {"uid": user_id})
    if user:
        return {"energy": user['energy'], "last_energy_update": user['last_energy_update']}
    return {"energy": 0, "last_energy_update": datetime.now(timezone.utc)}

async def update_user_energy(user_id: int, new_energy: int, update_time: datetime = None):
    if update_time is None:
        update_time = datetime.now(timezone.utc)
    await execute_query("UPDATE users SET energy = $1, last_energy_update = $2 WHERE user_id = $3",
                        {"energy": new_energy, "update_time": update_time, "uid": user_id})

async def recalculate_energy(user_id: int):
    energy_data = await get_user_energy(user_id)
    current_energy = energy_data['energy']
    last_update = energy_data['last_energy_update']

    time_since_last_update = datetime.now(timezone.utc) - last_update

    hours_passed = time_since_last_update.total_seconds() / 3600
    energy_gained = int(hours_passed * ENERGY_REGEN_RATE)
    new_energy = min(MAX_ENERGY, current_energy + energy_gained)

    if new_energy != current_energy:
        await update_user_energy(user_id, new_energy)
    return new_energy

async def check_and_level_up_pet(bot_instance, user_id, pet_id):
    pet_record = await fetch_one("SELECT id, name, level, xp, xp_needed, stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})

    if pet_record:
        pet = dict(pet_record) # Create a mutable copy

        level_up_count = 0
        while pet['xp'] >= pet['xp_needed']:
            pet['level'] += 1
            pet['xp'] -= pet['xp_needed']
            pet['xp_needed'] = int(pet['xp_needed'] * 1.5)

            if isinstance(pet['stats'], str):
                pet_stats = json.loads(pet['stats'])
            else:
                pet_stats = pet['stats']

            pet_stats['atk'] += random.randint(1, 3)
            pet_stats['def'] += random.randint(1, 3)
            pet_stats['hp'] += random.randint(3, 7)

            pet['stats'] = json.dumps(pet_stats)

            await execute_query(
                "UPDATE pets SET level = $1, xp = $2, xp_needed = $3, stats = $4 WHERE id = $5",
                {"level": pet['level'], "xp": pet['xp'], "xp_needed": pet['xp_needed'],
                 "stats": pet['stats'], "id": pet_id}
            )
            level_up_count += 1

        if level_up_count > 0:
            updated_pet = await fetch_one("SELECT name, level, stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
            if updated_pet:
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
        return True
    return False

async def get_pet_current_hp(pet_id: int, user_id: int):
    # Assuming 'current_hp' is stored in the pets table or derived from 'stats'
    # For now, let's assume pets have full HP at the start of battle
    # You might want to add a 'current_hp' column to the 'pets' table if you want persistent damage
    pet = await fetch_one("SELECT stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
    if pet and pet['stats']:
        stats = json.loads(pet['stats']) if isinstance(pet['stats'], str) else pet['stats']
        return stats.get('hp') # Assuming 'hp' in stats is max HP
    return 0

async def update_pet_current_hp(pet_id: int, user_id: int, new_hp: int):
    # This function would be used if you had a 'current_hp' column
    # For now, if pet's HP drops to 0, it means it's defeated.
    pass

async def simulate_battle(bot_instance: object, user_id: int, pet: dict, monster: dict, message_obj: Message):
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

    turn = 1
    while pet_current_hp > 0 and monster_current_hp > 0 and turn < 20: # Max 20 turns to prevent infinite loops
        # Pet attacks Monster
        pet_damage = max(1, pet_atk - monster_def)
        monster_current_hp -= pet_damage
        battle_log.append(f"Ход {turn}: <b>{pet_name}</b> атакует <b>{monster_name}</b>, нанося {pet_damage} урона. У <b>{monster_name}</b> осталось {max(0, monster_current_hp)} HP.")

        if monster_current_hp <= 0:
            battle_log.append(f"✅ <b>{pet_name}</b> победил <b>{monster_name}</b>!")
            await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
            return "win", monster['xp_reward'], monster['coin_reward']

        # Monster attacks Pet
        monster_damage = max(1, monster_atk - pet_def)
        pet_current_hp -= monster_damage
        battle_log.append(f"Ход {turn}: <b>{monster_name}</b> атакует <b>{pet_name}</b>, нанося {monster_damage} урона. У <b>{pet_name}</b> осталось {max(0, pet_current_hp)} HP.")

        if pet_current_hp <= 0:
            battle_log.append(f"❌ <b>{pet_name}</b> проиграл битву против <b>{monster_name}</b>.")
            await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
            return "loss", 0, 0, [] # No rewards for loss

        turn += 1
        await asyncio.sleep(0.5) # Small delay to make battle log appear turn by turn

    if pet_current_hp > 0:
        battle_log.append(f"✅ <b>{pet_name}</b> победил <b>{monster_name}</b>!")
        await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
        return "win", monster['xp_reward'], monster['coin_reward']
    else:
        battle_log.append(f"❌ <b>{pet_name}</b> проиграл битву против <b>{monster_name}</b>.")
        await message_obj.answer("\n".join(battle_log), parse_mode="HTML")
        return "loss", 0, 0, []

# --- Command Handlers ---

@router.message(Command("explore"))
async def explore_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    if not command.args:
        unlocked_zones_data = await fetch_all("SELECT z.name, z.description FROM user_zones uz JOIN zones z ON uz.zone = z.name WHERE uz.user_id = $1 AND uz.unlocked = TRUE", {"uid": uid})
        
        if not unlocked_zones_data:
            await message.answer("У тебя пока нет разблокированных зон для исследования. Отправляйся в свою первую зону: /explore 1 Лужайка (ID питомца 1, если он у тебя есть)") # Adjusted example
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
            "Пример: <code>/explore 1234 Лужайка</code>",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        return
    
    args = command.args.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Неверный формат команды. Используй: <code>/explore &lt;ID питомца&gt; &lt;Название локации&gt;</code>", parse_mode="HTML")
        return

    try:
        pet_id = int(args[0])
    except ValueError:
        await message.answer("ID питомца должен быть числом. Используй: <code>/explore &lt;ID питомца&gt; &lt;Название локации&gt;</code>", parse_mode="HTML")
        return
    
    zone_name = args[1]

    zone_data = await fetch_one("SELECT * FROM zones WHERE name = $1", {"zone_name": zone_name})
    if not zone_data:
        await message.answer(f"Локация '{zone_name}' не найдена. Проверь название и попробуй снова.")
        return

    user_zone_status = await fetch_one("SELECT unlocked FROM user_zones WHERE user_id = $1 AND zone = $2",
                                       {"uid": uid, "zone_name": zone_name})
    if not user_zone_status or not user_zone_status['unlocked']:
        await message.answer(f"Ты ещё не разблокировал локацию '{zone_name}'.")
        return

    pet_to_explore = await fetch_one("SELECT id, name, rarity, class, level, xp, stats, coin_rate FROM pets WHERE id = $1 AND user_id = $2",
                                     {"id": pet_id, "user_id": uid})
    if not pet_to_explore:
        await message.answer("У тебя нет питомца с таким ID. Проверь свой список питомцев.")
        return
    
    current_energy = await recalculate_energy(uid)
    energy_cost_multiplier = 1 + (zone_data['buff_value'] / 100)
    actual_energy_cost = int(EXPLORE_ENERGY_COST * energy_cost_multiplier)

    if current_energy < actual_energy_cost:
        seconds_for_one_point = 3600 / ENERGY_REGEN_RATE if ENERGY_REGEN_RATE > 0 else float('inf')
        last_update = user.get('last_energy_update', datetime.now(timezone.utc))
        seconds_since_last_update = (datetime.now(timezone.utc) - last_update).total_seconds()
        seconds_into_current_cycle = seconds_since_last_update % seconds_for_one_point
        
        time_until_next_point = seconds_for_one_point - seconds_into_current_cycle
        points_needed = actual_energy_cost - current_energy
        
        if points_needed > 0:
            total_wait_seconds = time_until_next_point + (points_needed - 1) * seconds_for_one_point
            time_to_regen_display = timedelta(seconds=int(total_wait_seconds))
        else:
            time_to_regen_display = timedelta(seconds=0)

        await message.answer(
            f"🚫 {random.choice(EXPLORE_FAIL_MESSAGES)}\n"
            f"Текущая энергия: {current_energy}/{MAX_ENERGY}\n"
            f"Для исследования <b>{zone_data['name']}</b> нужно {actual_energy_cost} энергии.\n"
            f"⚡️ Энергия восстанавливается на {ENERGY_REGEN_RATE} в час."
            f"Попробуй снова через {str(time_to_regen_display).split('.')[0]}.",
            parse_mode="HTML"
        )
        return

    last_explore_time_db = user.get('last_explore_time')
    last_explore_time = last_explore_time_db if last_explore_time_db else datetime.min.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) - last_explore_time < EXPLORE_COOLDOWN:
        remaining_time = EXPLORE_COOLDOWN - (datetime.now(timezone.utc) - last_explore_time)
        await message.answer(
            f"⏳ Ты уже недавно исследовал эти места. Подожди {str(remaining_time).split('.')[0]} перед следующим приключением."
        )
        return

    # Deduct energy and update exploration time
    new_energy_after_explore = current_energy - actual_energy_cost
    await update_user_energy(uid, new_energy_after_explore, datetime.now(timezone.utc))
    await execute_query("UPDATE users SET last_explore_time = $1, active_zone = $2 WHERE user_id = $3",
                        {"time": datetime.now(timezone.utc), "active_zone": zone_name, "uid": uid})

    # --- Start Simulation ---
    explore_message = await message.answer(
        f"🌳 <b>{pet_to_explore['name']}</b> отправился исследовать <b>{zone_data['name']}</b>...\n"
        f"Это займет некоторое время. Пожалуйста, подожди."
    )

    exploration_duration = random.randint(zone_data['explore_duration_min'], zone_data['explore_duration_max'])
    await asyncio.sleep(exploration_duration)

    # --- Determine Outcome ---
    outcome_message = ""
    xp_gain_final = 0
    coins_found_final = 0

    if random.random() < zone_data['pve_chance']: # PvE encounter
        monsters_in_zone = await fetch_all("SELECT * FROM monsters WHERE zone_name = $1 ORDER BY level ASC", {"zone_name": zone_name})
        
        # Select a random monster, maybe biased by pet level or just random
        if monsters_in_zone:
            # Simple monster selection for now (e.g., pick one randomly)
            selected_monster = random.choice(monsters_in_zone)
            
            await explore_message.edit_text(f"🌳 <b>{pet_to_explore['name']}</b> в зоне <b>{zone_data['name']}</b> столкнулся с <b>{selected_monster['name']}</b>!")
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
        buff_multiplier = 1 + (zone_data['buff_value'] / 100)

        coins_found_final = random.randint(EXPLORE_BASE_COIN_RANGE[0], EXPLORE_BASE_COIN_RANGE[1])
        coins_found_final = int(coins_found_final * buff_multiplier)
        coins_found_final += pet_to_explore['coin_rate'] # Add pet's coin_rate

        xp_gain_final = random.randint(EXPLORE_BASE_XP_RANGE[0], EXPLORE_BASE_XP_RANGE[1])
        xp_gain_final = int(xp_gain_final * buff_multiplier)
        
        message_template = random.choice(EXPLORE_SUCCESS_MESSAGES)
        outcome_message = message_template.format(
            pet_name=pet_to_explore['name'],
            zone_name_ru=zone_data['name'],
            coins=coins_found_final,
            xp=xp_gain_final
        )

    # --- Apply Final Rewards ---
    if xp_gain_final > 0:
        await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                            {"xp_gain": xp_gain_final, "id": pet_id, "user_id": uid})
        await check_and_level_up_pet(message.bot, uid, pet_id) # Check level up after XP gain

    if coins_found_final > 0:
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                            {"coins": coins_found_final, "uid": uid})

    final_summary_text = f"<b>Результаты исследования:</b>\n"
    if xp_gain_final > 0:
        final_summary_text += f"➕ {xp_gain_final} XP для <b>{pet_to_explore['name']}</b>\n"
    if coins_found_final > 0:
        final_summary_text += f"💰 {coins_found_final} монет\n"
    if not (xp_gain_final > 0 or coins_found_final > 0):
        final_summary_text += "Ничего особого не найдено, но приключение того стоило!\n"

    await message.answer(
        f"{outcome_message}\n\n"
        f"{final_summary_text}"
        f"\n⚡️ Энергия: {new_energy_after_explore}/{MAX_ENERGY}",
        parse_mode="HTML"
    )

    await check_quest_progress(uid, message)


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

    await callback.message.edit_text(
        f"Ты выбрал зону <b>{zone_name}</b>. Теперь выбери питомца, которого отправишь туда.\n\n"
        f"Твои питомцы:\n{pet_list_text}\n\n"
        f"Используй команду: <code>/explore &lt;ID питомца&gt; {zone_name}</code>\n"
        f"Пример: <code>/explore {user_pets_db[0]['id']} {zone_name}</code>",
        parse_mode="HTML"
    )
    await callback.answer()