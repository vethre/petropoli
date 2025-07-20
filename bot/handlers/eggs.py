import random
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from bot.handlers.start import check_quest_progress, check_zone_unlocks
from db.db import fetch_one, execute_query
from bot.utils.pet_generator import RARITY_STATS_RANGE, RARITY_TOTAL_STAT_MULTIPLIER, roll_pet
import json
from datetime import datetime

router = Router()

EGG_PRICE = 250

@router.message(Command("buy_egg"))
async def buy_egg_cmd(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    if user["coins"] < EGG_PRICE:
        await message.answer("У тебя недостаточно петкойнов для покупки яйца. Нужно 250 петкойнов. 💸")
        return
    
    eggs = json.loads(user['eggs']) if user['eggs'] else []

    new_egg = {
        "type": "basic",
        "bought_at": datetime.utcnow().isoformat(),
    }
    eggs.append(new_egg)

    await execute_query(
        "UPDATE users SET coins = coins - $1, eggs = $2, bought_eggs = bought_eggs + 1 WHERE user_id = $3",
        {"price": EGG_PRICE, "eggs": json.dumps(eggs), "uid": uid}
    )

    if user["bought_eggs"] == 3:
        await check_quest_progress(uid, message)

    await message.answer("🥚 Ты купил обычное яйцо!\nНапиши /hatch, чтобы его вылупить.")

def generate_stats_for_class(pclass: str, rarity: str) -> dict:
    min_base_stat, max_base_stat = RARITY_STATS_RANGE[rarity]
    base_total_points = (min_base_stat + max_base_stat) / 2 * 3 
    total_points = int(base_total_points * RARITY_TOTAL_STAT_MULTIPLIER[rarity])

    total_points = random.randint(max(total_points - 10, min_base_stat * 3), total_points + 10)
    
    min_per_stat = int(min_base_stat * 0.5)
    min_per_stat = max(5, min_per_stat) 

    # Distribution based on class
    if pclass == "Дамаг-диллер":
        atk_weight = random.uniform(0.45, 0.55)
        hp_weight = random.uniform(0.25, 0.35)
        def_weight = 1.0 - atk_weight - hp_weight
        
        atk = int(total_points * atk_weight)
        hp = int(total_points * hp_weight)
        defense = total_points - atk - hp

    elif pclass == "Саппорт":
        def_weight = random.uniform(0.45, 0.55)
        hp_weight = random.uniform(0.25, 0.35)
        atk_weight = 1.0 - def_weight - hp_weight

        defense = int(total_points * def_weight)
        hp = int(total_points * hp_weight)
        atk = total_points - defense - hp

    elif pclass == "Танк":
        # Prioritize HP, then Defense, then Attack
        hp_weight = random.uniform(0.45, 0.55)
        def_weight = random.uniform(0.25, 0.35)
        atk_weight = 1.0 - hp_weight - def_weight

        hp = int(total_points * hp_weight)
        defense = int(total_points * def_weight)
        atk = total_points - hp - defense

    else:
        remaining_points = total_points - (min_per_stat * 3)
        
        remaining_points = max(0, remaining_points) 

        p1 = random.randint(0, remaining_points)
        p2 = random.randint(0, remaining_points - p1)
        p3 = remaining_points - p1 - p2

        parts = [p1, p2, p3]
        random.shuffle(parts)
        
        atk = min_per_stat + parts[0]
        defense = min_per_stat + parts[1]
        hp = min_per_stat + parts[2]

    atk = max(min_per_stat, atk) 
    defense = max(min_per_stat, defense)
    hp = max(min_per_stat, hp)

    return {"atk": atk, "def": defense, "hp": hp}

@router.message(Command("hatch"))
async def hatch_egg_cmd(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    eggs = json.loads(user['eggs']) if user['eggs'] else []
    if not eggs:
        await message.answer("У тебя нет яиц для вылупления. Купи яйцо с помощью /buy_egg.")
        return
    
    eggs.pop(0)

    pet = roll_pet()
    stats = generate_stats_for_class(pet["class"], pet["rarity"])
    coin_rate = random.randint(9, 19)

    await execute_query(
        "INSERT INTO pets (user_id, name, rarity, class, level, xp, xp_needed, stats, coin_rate, last_collected) "
        "VALUES ($1, $2, $3, $4, 1, 0, 100, $5, $6, $7)",
        {
            "uid": uid,
            "name": pet["name"],
            "rarity": pet["rarity"],
            "class": pet["class"],
            "stats": json.dumps(stats),
            "coin_rate": coin_rate,
            "last_collected": datetime.utcnow()
        }
    )

    await execute_query(
        "UPDATE users SET eggs = $1 WHERE user_id = $2",
        {"eggs": json.dumps(eggs), "uid": uid}
    )

    await execute_query("UPDATE users SET hatched_count = hatched_count + 1 WHERE user_id = $1", {"uid": uid})

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if user["hatched_count"] == 1:
        await check_quest_progress(uid, message)

    await message.answer(
        f"🎉 Из яйца вылупился питомец!\n\n"
        f"🔹 <b>{pet['name']}</b> ({pet['rarity']} — {pet['class']})\n"
        f"🏅 Уровень: 1 | XP: 0/100\n"
        f"📊 Статы:\n"
        f"   🗡 Атака: {stats['atk']}\n"
        f"   🛡 Защита: {stats['def']}\n"
        f"   ❤ Здоровье: {stats['hp']}\n"
        f"💰 Доход: {coin_rate} петкойнов/час"
    )