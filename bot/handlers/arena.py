from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from db.db import fetch_one, fetch_all, execute_query # Assuming these are async functions
import json
import random
import asyncio
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timedelta # Import for energy system

router = Router()

arena_queue = []

# --- Constants for Arena ---
ARENA_MAX_ENERGY = 9
ENERGY_RECHARGE_TIME_MINUTES = 30 # 1 energy recharges every 30 minutes

BASE_XP_WIN = 100
BASE_XP_LOSS = 30
BASE_XP_DRAW = 60

BASE_COINS_WIN = 50
BASE_COINS_LOSS = 10
BASE_COINS_DRAW = 25

# --- XP to Level Mapping (Example, adjust as needed) ---
# This can be a simple linear progression, or more complex.
# For simplicity, let's say next_level_xp = current_level * 100
def get_xp_for_next_level(current_level: int) -> int:
    return current_level * 100 + 50 # Example: L1 -> 150, L2 -> 250, L3 -> 350

# --- Utility Functions (Keep as is) ---
RANKS = [
    (0, "Новичок"),
    (3, "Ученик"),
    (7, "Боец"),
    (15, "Ветеран"),
    (25, "Гладиатор"),
    (40, "Чемпион"),
    (60, "Звезда Арены"),
    (90, "Легенда"),
]

def get_rank(wins):
    for threshold, title in reversed(RANKS):
        if wins >= threshold:
            return title
    return "Новичок"

def calculate_power(team):
    return sum(p["stats"]["atk"] + p["stats"]["def"] + p["stats"]["hp"] for p in team)

# --- NEW: Energy Recharge Logic ---
async def check_and_recharge_energy(uid: int):
    user = await fetch_one("SELECT arena_energy, last_arena_energy_recharge FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        return # User not found, should be handled before this

    current_energy = user.get("arena_energy", 0)
    last_recharge_time = user.get("last_arena_energy_recharge")

    if current_energy >= ARENA_MAX_ENERGY:
        return current_energy # Already full

    if not last_recharge_time:
        # If no last recharge time, assume they just started or maxed out
        # Set it to now if not full, so next recharge is from now.
        if current_energy < ARENA_MAX_ENERGY:
             await execute_query("UPDATE users SET last_arena_energy_recharge = NOW() WHERE user_id = $1", {"uid": uid})
        return current_energy

    # Ensure last_recharge_time is a datetime object
    if isinstance(last_recharge_time, str):
        # Assuming format from PostgreSQL 'YYYY-MM-DD HH:MM:SS.microseconds'
        try:
            last_recharge_time = datetime.fromisoformat(last_recharge_time)
        except ValueError:
            # Fallback for other potential formats or if parsing fails
            # You might need to adjust this based on how your DB driver returns timestamps
            print(f"Warning: Could not parse last_recharge_time '{last_recharge_time}'. Assuming now.")
            last_recharge_time = datetime.now()


    now = datetime.now()
    time_since_last_recharge = now - last_recharge_time

    recharge_intervals = time_since_last_recharge.total_seconds() // (ENERGY_RECHARGE_TIME_MINUTES * 60)
    
    if recharge_intervals > 0:
        new_energy = min(ARENA_MAX_ENERGY, current_energy + int(recharge_intervals))
        
        # Calculate new last_recharge_time
        new_last_recharge_time = last_recharge_time + timedelta(minutes=ENERGY_RECHARGE_TIME_MINUTES * int(recharge_intervals))
        
        await execute_query(
            "UPDATE users SET arena_energy = $1, last_arena_energy_recharge = $2 WHERE user_id = $3",
            {"arena_energy": new_energy, "last_arena_energy_recharge": new_last_recharge_time, "uid": uid}
        )
        return new_energy
    return current_energy


# ——— /team — показ або встановлення команди (No changes needed here unless you want to show energy info)
@router.message(Command("team"))
async def set_or_show_team(message: Message):
    uid = message.from_user.id
    args = message.text.strip().split()[1:]

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start.")
        return

    all_pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
    pet_ids = [p["id"] for p in all_pets]

    if not args:
        current_team = json.loads(user.get("active_arena_team", "[]"))
        if not current_team:
            await message.answer("⚔ У тебя пока не выбрана команда для арены.\nИспользуй <code>/team id1 id2 ...</code>")
            return

        text = "🏟️ <b>Твоя арена-команда</b>\n\n"
        for idx, pet_id in enumerate(current_team, 1):
            pet = next((p for p in all_pets if p["id"] == pet_id), None)
            if pet:
                stats = pet["stats"] if isinstance(pet["stats"], dict) else json.loads(pet["stats"])
                text += (
                    f"🐾 <b>#{idx}</b> {pet['name']} ({pet['rarity']} | {pet['class']} | Ур. {pet.get('level', 1)})\n" # Added Level
                    f"⚔ Атака: {stats['atk']} | 🛡 Защита: {stats['def']} | ❤️ Здоровье: {stats['hp']}\n"
                    f"🆔 ID: <code>{pet_id}</code>\n\n"
                )
        await message.answer(text, parse_mode="HTML") # Added parse_mode
    else:
        try:
            new_team = list(map(int, args))
        except ValueError:
            await message.answer("⚠ Все ID должны быть числами.")
            return

        if len(new_team) > 5:
            await message.answer("⚠ Максимум 5 питомцев в арене.")
            return

        if any(pet_id not in pet_ids for pet_id in new_team):
            await message.answer("⚠ Один или несколько ID не принадлежат тебе.")
            return
        
        # Check if any pet ID is duplicated in the new team list
        if len(new_team) != len(set(new_team)):
            await message.answer("⚠ В команде не может быть повторяющихся питомцев.")
            return

        await execute_query("UPDATE users SET active_arena_team = $1 WHERE user_id = $2", {
            "active_arena_team": json.dumps(new_team),
            "uid": uid,
        })

        existing_team = await fetch_one("SELECT * FROM arena_team WHERE user_id = $1", {"uid": uid})
        if existing_team:
            await execute_query("UPDATE arena_team SET pet_ids = $1 WHERE user_id = $2", {
                "pet_ids": json.dumps(new_team),
                "uid": uid
            })
        else:
            await execute_query(
                "INSERT INTO arena_team (user_id, pet_ids) VALUES ($1, $2)",
                {"user_id": uid, "pet_ids": json.dumps(new_team)}
            )

        await message.answer(f"✅ Твоя арена-команда обновлена!\nПитомцы: {', '.join(map(str, new_team))}", parse_mode="HTML") # Added parse_mode


async def fetch_team(uid):
    team_data = await fetch_one("SELECT * FROM arena_team WHERE user_id = $1", {"uid": uid})
    if not team_data:
        return None
    pet_ids = json.loads(team_data["pet_ids"])
    pets = []
    for pid in pet_ids:
        # Fetch pet data including level and xp
        pet = await fetch_one("SELECT id, name, rarity, class, stats, xp, level FROM pets WHERE id = $1 AND user_id = $2", {"id": pid, "uid": uid})
        if pet:
            pet = dict(pet)
            pet["stats"] = pet["stats"] if isinstance(pet["stats"], dict) else json.loads(pet["stats"])
            pets.append(pet)
    return pets


@router.message(Command("join_arena"))
async def join_arena(message: Message):
    uid = message.from_user.id

    # Check and recharge energy first
    current_energy = await check_and_recharge_energy(uid)
    
    if current_energy < 1:
        user_data = await fetch_one("SELECT last_arena_energy_recharge FROM users WHERE user_id = $1", {"uid": uid})
        # Calculate time until next energy point
        last_recharge = user_data["last_arena_energy_recharge"]
        if isinstance(last_recharge, str):
            try:
                last_recharge = datetime.fromisoformat(last_recharge)
            except ValueError:
                 print(f"Warning: Could not parse last_recharge_time '{last_recharge}'. Assuming now for display.")
                 last_recharge = datetime.now()

        next_recharge_at = last_recharge + timedelta(minutes=ENERGY_RECHARGE_TIME_MINUTES * (ARENA_MAX_ENERGY - current_energy))
        time_left = next_recharge_at - datetime.now()
        
        minutes_left = int(time_left.total_seconds() // 60)
        seconds_left = int(time_left.total_seconds() % 60)

        await message.answer(f"⚡ У тебя недостаточно энергии для арены ({current_energy}/{ARENA_MAX_ENERGY}).\n"
                             f"Следующая энергия восстановится через {minutes_left} мин {seconds_left} сек.")
        return

    if uid in arena_queue:
        await message.answer("⏳ Ты уже в очереди на арену.")
        return
    
    # Deduct energy
    new_energy = current_energy - 1
    await execute_query("UPDATE users SET arena_energy = $1, last_arena_energy_recharge = NOW() WHERE user_id = $2",
                        {"arena_energy": new_energy, "uid": uid})

    arena_queue.append(uid)
    await message.answer(f"✅ Ты записался в очередь на арену! Ожидай начала битвы...\n⚡ Энергия: {new_energy}/{ARENA_MAX_ENERGY}")

    # Start the matching process only if this is the first player to join the queue
    # This prevents multiple `asyncio.sleep` calls and battle loops
    if len(arena_queue) == 1:
        await asyncio.sleep(30) # Wait for 30 seconds for more players
        
        # After waiting, check if there are still players in the queue
        if not arena_queue:
            return # Queue became empty, no battles to run

        # Take all current players from the queue
        players_in_session = arena_queue.copy()
        arena_queue.clear() # Clear the queue for the next batch

        random.shuffle(players_in_session)
        pairs = []

        while len(players_in_session) >= 2:
            a, b = players_in_session.pop(), players_in_session.pop()
            pairs.append((a, b))
        
        if players_in_session:
            # If there's an odd number, the last player fights a bot
            pairs.append((players_in_session[0], None))

        for p1, p2 in pairs:
            # Check if player has enough team selected before starting battle
            team1 = await fetch_team(p1)
            if not team1:
                await message.bot.send_message(p1, "У тебя нет активной команды для арены. Выбери команду с помощью /team.")
                continue # Skip this player if they don't have a team

            if p2: # If opponent is another player
                team2 = await fetch_team(p2)
                if not team2:
                    await message.bot.send_message(p2, "У тебя нет активной команды для арены. Выбери команду с помощью /team.")
                    # If opponent doesn't have a team, the first player (p1) fights a bot
                    await run_battle(message, p1, None)
                    continue
            
            # Run the battle
            await run_battle(message, p1, p2)
            await asyncio.sleep(1) # Small delay between battles


# --- NEW: Pet Level Up Logic ---
async def check_and_level_up_pet(bot_instance, uid: int, pet_id: int): # Add bot_instance here
    pet = await fetch_one("SELECT xp, level, stats, name FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "uid": uid})
    if not pet:
        return False

    current_xp = pet["xp"]
    current_level = pet["level"]
    pet_stats = pet["stats"] if isinstance(pet["stats"], dict) else json.loads(pet["stats"])

    leveled_up = False
    # Assuming get_xp_for_next_level is defined elsewhere in this file
    while current_xp >= get_xp_for_next_level(current_level):
        current_xp -= get_xp_for_next_level(current_level)
        current_level += 1
        leveled_up = True
        
        # Apply stat increases upon level up
        pet_stats['atk'] += random.randint(1, 3)
        pet_stats['def'] += random.randint(1, 3)
        pet_stats['hp'] += random.randint(3, 7)

        await execute_query(
            "UPDATE pets SET xp = $1, level = $2, stats = $3 WHERE id = $4 AND user_id = $5",
            {"xp": current_xp, "level": current_level, "stats": json.dumps(pet_stats), "id": pet_id, "user_id": uid}
        )
        if current_level >= 100:
            current_xp = 0
            break

    if leveled_up:
        # Use bot_instance to get chat info and send message
        user_chat_info = await bot_instance.get_chat(uid) 
        user_name = user_chat_info.first_name if user_chat_info.first_name else user_chat_info.full_name
        
        await bot_instance.send_message( # Use bot_instance here
            uid,
            f"🎉 Поздравляем, {user_name}!\nТвой питомец <b>{pet['name']}</b> достиг <b>Уровня {current_level}</b>!\n"
            f"Новые характеристики:\n⚔ Атака: {pet_stats['atk']} | 🛡 Защита: {pet_stats['def']} | ❤️ Здоровье: {pet_stats['hp']}",
            parse_mode="HTML"
        )
    return leveled_up

async def run_battle(message: Message, uid1, uid2):
    team1 = await fetch_team(uid1)
    if not team1:
        # This case should ideally be handled before calling run_battle in join_arena
        # But as a fallback:
        await message.bot.send_message(uid1, "У тебя нет активной команды для арены. Выбери команду с помощью /team.")
        return

    user1 = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid1})
    try:
        chat = await message.bot.get_chat(uid1)
        name1 = chat.first_name if chat.first_name else chat.full_name
    except Exception:
        name1 = f"Игрок {uid1}"

    power1 = calculate_power(team1)

    fake_names = [
        "Макан", "Lisa228", "Вася_Нагибатор", "ЧоткийПацан", "Бублик_Топ",
        "Котя_Мур", "Беброчка", "Смешарик_2007", "Хрущев_Босс", "Грустный_Еж",
        "Плюшевый_Мишка", "Купи_Джинсы", "БатяВЗдании", "АУФ", "Легенда_Района",
        "КиберКотлета", "Шашлычок_ТВ", "МемныйЛорд", "Тигр_Дэн", "Димон_Лимон",
        "Сочный_Персик", "Огурчик", "КеПаПа", "Гопник_PRO",
        "НеТвойБро", "ХагиВаги", "Шрек_Нагибатор", "Эщкере", "ЗаБазуОтвечаю",
        "Холодный_Чай", "Кринж_Босс", "ЧикиБрики", "СИМПЛ_ДИМПЛ", "ПоПоПить",
        "Груша_Разрушитель", "БибаИБоба", "Жиза_Бро", "Ешка_Кошка", "Абобус",
        "MoonLight", "Dreamer", "ShadowHunter", "Astra", "Zenith",
        "Echo", "MysticFlow", "Vesper", "Aurora", "Phantom",
        "Кристина", "Артем", "София", "Даниил", "Алина",
        "SkyWalker", "PixelGuru", "ByteMe", "CodeBreaker", "DataMiner",
        "CosmicRay", "StarGazer", "Nova", "GalacticCore", "QuantumLeap",
        "Глеб", "Вероника", "Платон", "Милана", "Ярослав",
        "SilentKiller", "GhostBlade", "NightRaven", "IronHeart", "StormRider"
    ]

    is_bot = False
    if uid2:
        team2 = await fetch_team(uid2)
        if not team2:
            # Fallback to bot if opponent player has no team
            is_bot = True 
            name2 = random.choice(fake_names)
            avg_pet_power = power1 / len(team1)
            num_bot_pets = random.randint(max(1, len(team1) - 1), min(5, len(team1) + 1))
            team2 = []
            for _ in range(num_bot_pets):
                base_atk = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
                base_def = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
                base_hp = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
                team2.append({
                    "name": random.choice(["Кот", "Пёс", "Лиса", "Бобр", "Дракон", "Волк", "Медведь", "Пантера", "Орел", "Змея"]),
                    "stats": {
                        "atk": max(5, base_atk + random.randint(-2, 2)),
                        "def": max(5, base_def + random.randint(-2, 2)),
                        "hp": max(15, base_hp + random.randint(-5, 5))
                    }
                })
            await message.bot.send_message(uid2, "Твой противник не имеет активной команды. Ты сразишься с ботом.")

        else: # Opponent is another player and has a team
            user2 = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid2})
            try:
                chat = await message.bot.get_chat(uid2)
                name2 = chat.first_name if chat.first_name else chat.full_name
            except Exception:
                name2 = f"Игрок {uid2}"
            power2 = calculate_power(team2)
    else: # uid2 is None, directly assigned to bot
        is_bot = True
        name2 = random.choice(fake_names)
        avg_pet_power = power1 / len(team1)
        num_bot_pets = random.randint(max(1, len(team1) - 1), min(5, len(team1) + 1))
        
        team2 = []
        for _ in range(num_bot_pets):
            base_atk = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
            base_def = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
            base_hp = max(1, int(avg_pet_power * random.uniform(0.7, 1.3) / 3))
            
            team2.append({
                "name": random.choice(["Кот", "Пёс", "Лиса", "Бобр", "Дракон", "Волк", "Медведь", "Пантера", "Орел", "Змея"]),
                "stats": {
                    "atk": max(5, base_atk + random.randint(-2, 2)),
                    "def": max(5, base_def + random.randint(-2, 2)),
                    "hp": max(15, base_hp + random.randint(-5, 5))
                }
            })
    power2 = calculate_power(team2) # Recalculate power for bot team if it was generated

    msg = await send_battle_intro(message, name1, power1, name2, power2)

    wins1, wins2 = 0, 0
    
    num_rounds = min(len(team1), len(team2))

    for i in range(num_rounds):
        p1_pet = team1[i]
        p2_pet = team2[i]
        
        current_round_log = f"<b>Раунд {i+1}:</b>\n🐾 {name1}'s {p1_pet['name']} (ATK: {p1_pet['stats']['atk']}) VS {name2}'s {p2_pet['name']} (DEF: {p2_pet['stats']['def']})\n"

        # Player 1's pet attacks Player 2's pet
        crit_p1 = random.random() < 0.15
        miss_p1 = random.random() < 0.1

        if miss_p1:
            current_round_log += f"❌ {name1}'s {p1_pet['name']} промахнулся по {p2_pet['name']}!\n"
            winner_round_p1 = False
        elif p1_pet["stats"]["atk"] > p2_pet["stats"]["def"] or crit_p1:
            if crit_p1:
                current_round_log += f"💥 {name1}'s {p1_pet['name']} наносит критический удар по {p2_pet['name']}!\n"
            else:
                current_round_log += f"✅ {name1}'s {p1_pet['name']} пробивает защиту {p2_pet['name']}!\n"
            winner_round_p1 = True
        else:
            current_round_log += f"🛡 {name2}'s {p2_pet['name']} отбивает атаку {p1_pet['name']}!\n"
            winner_round_p1 = False

        # Player 2's pet attacks Player 1's pet (if player 1 didn't miss)
        crit_p2 = random.random() < 0.15
        miss_p2 = random.random() < 0.1
        
        if miss_p2:
            current_round_log += f"❌ {name2}'s {p2_pet['name']} промахнулся по {p1_pet['name']}!\n"
            winner_round_p2 = False
        elif p2_pet["stats"]["atk"] > p1_pet["stats"]["def"] or crit_p2:
            if crit_p2:
                current_round_log += f"💥 {name2}'s {p2_pet['name']} наносит критический удар по {p1_pet['name']}!\n"
            else:
                current_round_log += f"✅ {name2}'s {p2_pet['name']} пробивает защиту {p1_pet['name']}!\n"
            winner_round_p2 = True
        else:
            current_round_log += f"🛡 {name1}'s {p1_pet['name']} отбивает атаку {p2_pet['name']}!\n"
            winner_round_p2 = False

        # Determine round winner based on combined outcomes
        if winner_round_p1 and not winner_round_p2:
            wins1 += 1
            current_round_log += f"➡️ {name1}'s {p1_pet['name']} выигрывает раунд!\n"
        elif winner_round_p2 and not winner_round_p1:
            wins2 += 1
            current_round_log += f"➡️ {name2}'s {p2_pet['name']} выигрывает раунд!\n"
        elif winner_round_p1 and winner_round_p2:
            current_round_log += "➡️ Оба питомца нанесли урон! Ничья в раунде.\n"
        else:
            current_round_log += "➡️ Оба питомца не смогли нанести урон! Ничья в раунде.\n"

        try:
            await msg.edit_text(f"{msg.text}\n\n{current_round_log}", parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): # Avoid raising if content is identical
                # Fallback: if message not found for editing, send a new one
                if "message to edit not found" in str(e).lower(): # Using .lower() for robustness
                    print(f"DEBUG: Message to edit not found in battle log update for {uid1}. Sending new message.")
                    msg = await message.bot.send_message(uid1, f"{msg.text}\n\n{current_round_log}", parse_mode="HTML") # Update msg reference
                else:
                    raise
        await asyncio.sleep(2.3)

    final_result_text = ""
    # --- XP and Coin Distribution ---
    if wins1 > wins2:
        await execute_query("UPDATE arena_team SET wins = wins + 1 WHERE user_id = $1", {"uid": uid1})
        final_result_text = f"🏆 <b>{name1}</b> одерживает победу!"
        
        # Player 1 (Winner) rewards
        coins_gain1 = BASE_COINS_WIN
        xp_gain1 = BASE_XP_WIN
        for pet in team1:
            await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                {"xp_gain": xp_gain1, "id": pet["id"], "user_id": uid1})
            await check_and_level_up_pet(message.bot, uid1, pet["id"]) # Check for level up after XP
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                            {"coins_gain": coins_gain1, "uid": uid1})
        final_result_text += f"\n+{xp_gain1} XP каждому питомцу | +{coins_gain1} 💰"

        if not is_bot:
            # Player 2 (Loser) rewards
            await execute_query("UPDATE arena_team SET losses = losses + 1 WHERE user_id = $1", {"uid": uid2})
            coins_gain2 = BASE_COINS_LOSS
            xp_gain2 = BASE_XP_LOSS
            for pet in team2:
                await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                    {"xp_gain": xp_gain2, "id": pet["id"], "user_id": uid2})
                await check_and_level_up_pet(message.bot, uid2, pet["id"]) # Check for level up after XP
            await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                                {"coins_gain": coins_gain2, "uid": uid2})
            # Send message to losing player as well
            await message.bot.send_message(
                uid2,
                f"💀 Ты проиграл битву против {name1}!\n"
                f"+{xp_gain2} XP каждому питомцу | +{coins_gain2} 💰",
                parse_mode="HTML"
            )

    elif wins2 > wins1:
        await execute_query("UPDATE arena_team SET losses = losses + 1 WHERE user_id = $1", {"uid": uid1})
        final_result_text = f"💀 <b>{name2}</b> одерживает победу!"

        # Player 1 (Loser) rewards
        coins_gain1 = BASE_COINS_LOSS
        xp_gain1 = BASE_XP_LOSS
        for pet in team1:
            await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                {"xp_gain": xp_gain1, "id": pet["id"], "user_id": uid1})
            await check_and_level_up_pet(message.bot, uid1, pet["id"]) # Check for level up after XP
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                            {"coins_gain": coins_gain1, "uid": uid1})
        final_result_text += f"\n+{xp_gain1} XP каждому питомцу | +{coins_gain1} 💰"

        if not is_bot:
            # Player 2 (Winner) rewards
            await execute_query("UPDATE arena_team SET wins = wins + 1 WHERE user_id = $1", {"uid": uid2})
            coins_gain2 = BASE_COINS_WIN
            xp_gain2 = BASE_XP_WIN
            for pet in team2:
                await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                    {"xp_gain": xp_gain2, "id": pet["id"], "user_id": uid2})
                await check_and_level_up_pet(message.bot, uid2, pet["id"]) # Check for level up after XP
            await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                                {"coins_gain": coins_gain2, "uid": uid2})
            # Send message to winning player as well
            await message.bot.send_message(
                uid2,
                f"🏆 Ты выиграл битву против {name1}!\n"
                f"+{xp_gain2} XP каждому питомцу | +{coins_gain2} 💰",
                parse_mode="HTML"
            )
        else: # Bot wins against player, "bot gains" for flavor
            final_result_text += f"\nБот {name2} получает +{BASE_XP_WIN} XP и +{BASE_COINS_WIN} 💰 (виртуально)"

    else: # Draw
        final_result_text = "🤝 <b>Ничья!</b> Оба игрока показали себя достойно."
        await execute_query("UPDATE arena_team SET draws = draws + 1 WHERE user_id = $1", {"uid": uid1})
        
        # Player 1 (Draw) rewards
        coins_gain1 = BASE_COINS_DRAW
        xp_gain1 = BASE_XP_DRAW
        for pet in team1:
            await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                {"xp_gain": xp_gain1, "id": pet["id"], "user_id": uid1})
            await check_and_level_up_pet(message.bot, uid1, pet["id"]) # Check for level up after XP
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                            {"coins_gain": coins_gain1, "uid": uid1})
        final_result_text += f"\n+{xp_gain1} XP каждому питомцу | +{coins_gain1} 💰"

        if not is_bot:
            # Player 2 (Draw) rewards
            await execute_query("UPDATE arena_team SET draws = draws + 1 WHERE user_id = $1", {"uid": uid2})
            coins_gain2 = BASE_COINS_DRAW
            xp_gain2 = BASE_XP_DRAW
            for pet in team2:
                await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2 AND user_id = $3",
                                    {"xp_gain": xp_gain2, "id": pet["id"], "user_id": uid2})
                await check_and_level_up_pet(message.bot, uid2, pet["id"]) # Check for level up after XP
            await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2",
                                {"coins_gain": coins_gain2, "uid": uid2})
            # Send message to other player as well
            await message.bot.send_message(
                uid2,
                f"🤝 Ничья в битве против {name1}!\n"
                f"+{xp_gain2} XP каждому питомцу | +{coins_gain2} 💰",
                parse_mode="HTML"
            )
        else: # Bot draws against player, "bot gains" for flavor
            final_result_text += f"\nБот {name2} получает +{BASE_XP_DRAW} XP и +{BASE_COINS_DRAW} 💰 (виртуально)"


    await asyncio.sleep(2)
    try:
        await msg.edit_text(f"{msg.text}\n\n{final_result_text}", parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            # Fallback for "message to edit not found" for final result
            if "message to edit not found" in str(e).lower():
                print(f"DEBUG: Message to edit not found for final result for {uid1}. Sending new message.")
                await message.bot.send_message(uid1, f"{msg.text}\n\n{final_result_text}", parse_mode="HTML")
            else:
                raise

async def send_battle_intro(message: Message, name1: str, power1: int, name2: str, power2: int):
    text = (
        f"⚔️ <b>Битва начинается!</b>\n"
        f"👤 {name1} — Сила: {power1}\n"
        f"🆚\n"
        f"👤 {name2} — Сила: {power2}"
    )
    # The message should be sent to *both* players if it's a PvP battle,
    # or just the player if it's PvE.
    # For simplicity, we use the message.answer() which replies in the same chat where /join_arena was called.
    # If you want to send private messages for battle logs, you would need to use message.bot.send_message(uid, text).
    # For now, let's keep it simple as it was, replying in the chat where join_arena was initiated.
    return await message.answer(text, parse_mode="HTML")

@router.message(Command("arena_info"))
async def arena_info(message: Message):
    uid = message.from_user.id

    # Check and recharge energy before displaying info
    current_energy = await check_and_recharge_energy(uid)

    user_arena_stats = await fetch_one("SELECT * FROM arena_team WHERE user_id = $1", {"uid": uid})
    if not user_arena_stats:
        await message.answer("Ты ещё не участвуешь в арене. Напиши /team чтобы собрать команду.")
        return

    try:
        chat = await message.bot.get_chat(uid)
        username = chat.username if chat.username else chat.full_name # Prefer username if available
    except Exception:
        username = f"user{uid}"
    
    wins = user_arena_stats.get("wins", 0)
    losses = user_arena_stats.get("losses", 0)
    draws = user_arena_stats.get("draws", 0)
    rank = get_rank(wins)

    top_users = await fetch_all("""
        SELECT u.user_id, a.wins, a.losses, a.draws FROM arena_team a
        JOIN users u ON u.user_id = a.user_id
        WHERE u.user_id != 0
        ORDER BY a.wins DESC, a.draws DESC, a.losses ASC
        LIMIT 10
    """)

    leaderboard = ""
    for idx, u in enumerate(top_users):
        try:
            chat = await message.bot.get_chat(u["user_id"])
            # Use first_name if username not available, then fallback to user{id}
            uname = chat.username or chat.first_name or f"user{u['user_id']}"
        except Exception:
            uname = f"user{u['user_id']}"
        leaderboard += f"{idx+1}. {uname} — 🏆 {u['wins']} | 💀 {u['losses']} | 🤝 {u['draws']}\n"

    if not leaderboard:
        leaderboard = "Пока никого нет..."

    text = (
        f"🏟️ <b>Арена: статус игрока</b>\n\n"
        f"⚡ Энергия: <b>{current_energy}/{ARENA_MAX_ENERGY}</b>\n" # Display energy
        f"👤 Игрок: <b>{username}</b>\n"
        f"🔰 Ранг: <b>{rank}</b>\n"
        f"🏆 Победы: <b>{wins}</b>\n"
        f"💀 Поражения: <b>{losses}</b>\n"
        f"🤝 Ничьи: <b>{draws}</b>\n\n"
        f"<b>📊 Топ 10 игроков:</b>\n{leaderboard}"
    )

    await message.answer(text, parse_mode="HTML")