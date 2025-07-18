from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from db.db import fetch_one, fetch_all, execute_query
import json
import random
import asyncio
from aiogram.exceptions import TelegramBadRequest

router = Router()

arena_queue = []

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

# ——— /team — показ або встановлення команди
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
                    f"🐾 <b>#{idx}</b> {pet['name']} ({pet['rarity']} | {pet['class']})\n"
                    f"⚔ Атака: {stats['atk']} | 🛡 Защита: {stats['def']} | ❤️ Здоровье: {stats['hp']}\n"
                    f"🆔 ID: <code>{pet_id}</code>\n\n"
                )
        await message.answer(text)
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

        await message.answer(f"✅ Твоя арена-команда обновлена!\nПитомцы: {', '.join(map(str, new_team))}")


async def fetch_team(uid):
    team_data = await fetch_one("SELECT * FROM arena_team WHERE user_id = $1", {"uid": uid})
    if not team_data:
        return None
    pet_ids = json.loads(team_data["pet_ids"])
    pets = []
    for pid in pet_ids:
        pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pid, "uid": uid})
        if pet:
            pet = dict(pet)
            pet["stats"] = pet["stats"] if isinstance(pet["stats"], dict) else json.loads(pet["stats"])
            pets.append(pet)
    return pets

@router.message(Command("join_arena"))
async def join_arena(message: Message):
    uid = message.from_user.id
    if uid in arena_queue:
        await message.answer("⏳ Ты уже в очереди на арену.")
        return
    arena_queue.append(uid)
    await message.answer("✅ Ты записался в очередь на арену! Ожидай начала битвы...")

    if len(arena_queue) == 1:
        await asyncio.sleep(30)
        if not arena_queue:
            return
        players = arena_queue.copy()
        arena_queue.clear()

        random.shuffle(players)
        pairs = []

        while len(players) >= 2:
            a, b = players.pop(), players.pop()
            pairs.append((a, b))
        if players:
            pairs.append((players[0], None)) # If there's an odd number, the last player fights a bot

        for p1, p2 in pairs:
            await run_battle(message, p1, p2)

async def run_battle(message: Message, uid1, uid2):
    team1 = await fetch_team(uid1)
    if not team1:
        await message.bot.send_message(uid1, "У тебя нет активной команды для арены. Выбери команду с помощью /team.")
        return

    user1 = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid1})
    try:
        chat = await message.bot.get_chat(uid1)
        # Use first_name for a more personal touch
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

    if uid2:
        team2 = await fetch_team(uid2)
        if not team2:
            await message.bot.send_message(uid2, "У тебя нет активной команды для арены. Выбери команду с помощью /team.")
            return
        user2 = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid2})
        try:
            chat = await message.bot.get_chat(uid2)
            # Use first_name for consistency
            name2 = chat.first_name if chat.first_name else chat.full_name
        except Exception:
            name2 = f"Игрок {uid2}"

        power2 = calculate_power(team2)
        is_bot = False
    else:
        # Generate bot team with power relative to player's power
        avg_pet_power = power1 / len(team1)
        num_bot_pets = random.randint(max(1, len(team1) - 1), min(5, len(team1) + 1))
        
        team2 = []
        for _ in range(num_bot_pets):
            # Adjust stats based on average pet power of the player's team
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

        name2 = random.choice(fake_names)
        power2 = calculate_power(team2)
        is_bot = True

    msg = await send_battle_intro(message, name1, power1, name2, power2)

    wins1, wins2 = 0, 0
    
    # Determine the number of rounds based on the smaller team size
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
            current_round_log += "➡️ Оба питомца нанесли урон! Ничья в раунде.\n" # Both hit, considered a draw for this round's win count
        else:
            current_round_log += "➡️ Оба питомца не смогли нанести урон! Ничья в раунде.\n" # Both missed or were defended, considered a draw for this round's win count

        try:
            await msg.edit_text(f"{msg.text}\n\n{current_round_log}", parse_mode="HTML")
        except TelegramBadRequest as e:
            # Handle the case where the message content is identical
            if "message is not modified" not in str(e):
                raise
        await asyncio.sleep(2.3) # Increased sleep for better readability of battle log

    if wins1 > wins2:
        await execute_query("UPDATE arena_team SET wins = wins + 1 WHERE user_id = $1", {"uid": uid1})
        result_text = f"🏆 <b>{name1}</b> одерживает победу!"
        if not is_bot:
            await execute_query("UPDATE arena_team SET losses = losses + 1 WHERE user_id = $1", {"uid": uid2})
    elif wins2 > wins1:
        await execute_query("UPDATE arena_team SET losses = losses + 1 WHERE user_id = $1", {"uid": uid1})
        result_text = f"💀 <b>{name2}</b> одерживает победу!"
        if not is_bot:
            await execute_query("UPDATE arena_team SET wins = wins + 1 WHERE user_id = $1", {"uid": uid2})
    else:
        result_text = "🤝 <b>Ничья!</b> Оба игрока показали себя достойно."
        await execute_query("UPDATE arena_team SET draws = draws + 1 WHERE user_id = $1", {"uid": uid1})
        if not is_bot:
            await execute_query("UPDATE arena_team SET draws = draws + 1 WHERE user_id = $1", {"uid": uid2})


    await asyncio.sleep(2)
    try:
        await msg.edit_text(f"{msg.text}\n\n{result_text}", parse_mode="HTML")
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            raise

async def send_battle_intro(message: Message, name1: str, power1: int, name2: str, power2: int):
    text = (
        f"⚔️ <b>Битва начинается!</b>\n"
        f"👤 {name1} — Сила: {power1}\n"
        f"🆚\n"
        f"👤 {name2} — Сила: {power2}"
    )
    return await message.answer(text, parse_mode="HTML")

@router.message(Command("arena_info"))
async def arena_info(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM arena_team WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не участвуешь в арене. Напиши /team чтобы собрать команду.")
        return

    try:
        chat = await message.bot.get_chat(uid)
        username = chat.username or chat.full_name
    except Exception:
        username = f"user{uid}"
    
    wins = user.get("wins", 0)
    losses = user.get("losses", 0)
    draws = user.get("draws", 0) # Added draws
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
            uname = chat.username or f"user{u['user_id']}"
        except Exception:
            uname = f"user{u['user_id']}"
        leaderboard += f"{idx+1}. {uname} — 🏆 {u['wins']} | 💀 {u['losses']} | 🤝 {u['draws']}\n" # Added draws

    if not leaderboard:
        leaderboard = "Пока никого нет..."

    text = (
        f"🏟️ <b>Арена: статус игрока</b>\n\n"
        f"👤 Игрок: <b>{username}</b>\n"
        f"🔰 Ранг: <b>{rank}</b>\n"
        f"🏆 Победы: <b>{wins}</b>\n"
        f"💀 Поражения: <b>{losses}</b>\n"
        f"🤝 Ничьи: <b>{draws}</b>\n\n" # Added draws
        f"<b>📊 Топ 10 игроков:</b>\n{leaderboard}"
    )

    await message.answer(text, parse_mode="HTML")