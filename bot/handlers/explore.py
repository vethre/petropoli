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
    pet = await fetch_one("SELECT id, name, level, xp, xp_needed, stats FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
    if pet and pet['xp'] >= pet['xp_needed']:
        level_up_count = 0
        while pet['xp'] >= pet['xp_needed']:
            pet['level'] += 1
            pet['xp'] -= pet['xp_needed']
            pet['xp_needed'] = int(pet['xp_needed'] * 1.5) # Example: XP needed increases by 50%
            
            # Stat increase on level up
            # This is a basic example. You might want a more sophisticated system.
            # For simplicity, we'll increment stats based on their current values.
            if isinstance(pet['stats'], str):
                pet_stats = json.loads(pet['stats'])
            else:
                pet_stats = pet['stats']

            pet_stats['atk'] += random.randint(1, 3)
            pet_stats['def'] += random.randint(1, 3)
            pet_stats['hp'] += random.randint(3, 7)
            
            await execute_query(
                "UPDATE pets SET level = $1, xp = $2, xp_needed = $3, stats = $4 WHERE id = $5", 
                {"level": pet['level'], "xp": pet['xp'], "xp_needed": pet['xp_needed'], 
                 "stats": json.dumps(pet_stats), "id": pet_id}
            )
            level_up_count += 1

        if level_up_count > 0:
            try:
                # Re-fetch pet data to get latest stats for message
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
            except Exception as e:
                print(f"Error sending level up message or fetching chat info: {e}")
        return True
    return False

# --- Command Handlers ---

@router.message(Command("explore"))
async def explore_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    if not command.args:
        # Display unlocked zones and prompt for selection
        unlocked_zones_data = await fetch_all("SELECT z.name, z.description FROM user_zones uz JOIN zones z ON uz.zone = z.name WHERE uz.user_id = $1 AND uz.unlocked = TRUE", {"uid": uid})
        
        if not unlocked_zones_data:
            await message.answer("У тебя пока нет разблокированных зон для исследования. Отправляйся в свою первую зону: /explore Лужайка")
            return
            
        builder = InlineKeyboardBuilder()
        for zone in unlocked_zones_data:
            builder.button(text=zone['name'], callback_data=f"select_explore_zone_{zone['name']}")
        builder.adjust(2) # Two buttons per row

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

    # Fetch zone data from the database
    zone_data = await fetch_one("SELECT * FROM zones WHERE name = $1", {"zone_name": zone_name})
    if not zone_data:
        await message.answer(f"Локация '{zone_name}' не найдена. Проверь название и попробуй снова.")
        return

    # Check if user has unlocked this zone
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
    
    # Use buff_value from zones table for energy cost multiplier
    energy_cost_multiplier = 1 + (zone_data['buff_value'] / 100) # Assuming buff_value is a percentage (e.g., 10 for 10%)
    actual_energy_cost = int(EXPLORE_ENERGY_COST * energy_cost_multiplier)

    if current_energy < actual_energy_cost:
        seconds_for_one_point = 3600 / ENERGY_REGEN_RATE if ENERGY_REGEN_RATE > 0 else float('inf')
        last_update = user.get('last_energy_update', datetime.utcnow())
        seconds_since_last_update = (datetime.utcnow() - last_update).total_seconds()
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

    last_explore_time_str = user.get('last_explore_time')
    last_explore_time = datetime.fromisoformat(last_explore_time_str) if last_explore_time_str else datetime.min
    if last_explore_time.tzinfo is None:
        last_explore_time = last_explore_time.replace(tzinfo=timezone.utc)
    
    if datetime.now(timezone.utc) - last_explore_time < EXPLORE_COOLDOWN:
        remaining_time = EXPLORE_COOLDOWN - (datetime.now(timezone.utc) - last_explore_time)
        await message.answer(
            f"⏳ Ты уже недавно исследовал эти места. Подожди {str(remaining_time).split('.')[0]} перед следующим приключением."
        )
        return

    new_energy_after_explore = current_energy - actual_energy_cost
    await update_user_energy(uid, new_energy_after_explore, datetime.utcnow())

    await execute_query("UPDATE users SET last_explore_time = $1, active_zone = $2 WHERE user_id = $3", 
                        {"time": datetime.utcnow().isoformat(), "active_zone": zone_name, "uid": uid})

    # Rewards based on base ranges and zone buff_value
    buff_multiplier = 1 + (zone_data['buff_value'] / 100) # Buff value also affects rewards

    coins_found = random.randint(EXPLORE_BASE_COIN_RANGE[0], EXPLORE_BASE_COIN_RANGE[1])
    coins_found = int(coins_found * buff_multiplier)
    
    xp_gain = random.randint(EXPLORE_BASE_XP_RANGE[0], EXPLORE_BASE_XP_RANGE[1])
    xp_gain = int(xp_gain * buff_multiplier)
    
    # Optionally, add pet's coin_rate to coins found
    coins_found += pet_to_explore['coin_rate'] # Each pet has its own coin_rate

    await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                        {"xp_gain": xp_gain, "id": pet_id, "user_id": uid})
    await check_and_level_up_pet(message.bot, uid, pet_id)

    await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                        {"coins": coins_found, "uid": uid})

    message_template = random.choice(EXPLORE_SUCCESS_MESSAGES)
    final_message_text = message_template.format(
        pet_name=pet_to_explore['name'], 
        zone_name_ru=zone_data['name'], # Use name from DB
        coins=coins_found, 
        xp=xp_gain
    )
    
    await message.answer(
        f"🌳 Отправляемся исследовать <b>{zone_data['name']}</b> с <b>{pet_to_explore['name']}</b>!\n\n"
        f"{final_message_text}\n\n"
        f"⚡️ Энергия: {new_energy_after_explore}/{MAX_ENERGY}",
        parse_mode="HTML"
    )

    await check_quest_progress(uid, message)

@router.callback_query(F.data.startswith("select_explore_zone_"))
async def select_explore_zone_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    zone_name = callback.data.split("select_explore_zone_")[1]

    # Fetch user's pets to prompt for pet selection
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
        f"Пример: <code>/explore {user_pets_db[0]['id']} {zone_name}</code>", # Suggest first pet for convenience
        parse_mode="HTML"
    )
    await callback.answer()