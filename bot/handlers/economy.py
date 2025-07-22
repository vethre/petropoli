import json
import random
from datetime import datetime, timedelta, timezone
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from bot.handlers.start import get_zone_buff
from db.db import fetch_one, execute_query, fetch_all

router = Router()

COLLECT_COOLDOWN_MINUTES = 60

@router.message(Command("collect"))
async def collect_cmd(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return

    pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
    if not pets:
        await message.answer("У тебя пока нет питомцев 😿\nКупи яйцо через /buy_egg и выведи кого-то!")
        return
    
    # buff_mult теперь будет словарем типа {'type': 'coin_rate', 'value': 5}
    # или None, если баффа нет
    buff_mult_data = await get_zone_buff(uid)
    
    now = datetime.now(timezone.utc)
    total_collected = 0
    updated_pets = []

    for pet in pets:
        last = pet["last_collected"]
        if last:
            # Ваша логика преобразования last в datetime object
            if isinstance(last, str):
                try:
                    # Попытка разобрать с миллисекундами и зоной
                    last = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S.%f%z")
                except ValueError:
                    # Если без миллисекунд или другой формат, попробуйте другой
                    last = datetime.fromisoformat(last)
                last = last.astimezone(timezone.utc)
            elif isinstance(last, datetime):
                last = last.astimezone(timezone.utc) if last.tzinfo is None else last
            else:
                last = None # Если тип не строка и не datetime
        
        # Если last_collected не установлен или прошло достаточно времени
        if not last or (now - last) >= timedelta(minutes=COLLECT_COOLDOWN_MINUTES):
            # --- ИСПРАВЛЕННАЯ ЛОГИКА ПРИМЕНЕНИЯ БАФФА ---
            buff_value = 1 # По умолчанию множитель 1 (нет баффа)
            if buff_mult_data and buff_mult_data.get('type') == 'coin_rate':
                # Проверяем, что buff_mult_data - это словарь, и тип баффа - 'coin_rate'
                # и что значение - число
                if isinstance(buff_mult_data.get('value'), (int, float)):
                    # buff_mult_data['value'] - это процентное значение (например, 5 для +5%)
                    buff_value = 1 + (buff_mult_data['value'] / 100) # Преобразуем процент в множитель (например, 5% -> 1.05)

            income = int(pet["coin_rate"] * buff_value)
            # --- КОНЕЦ ИСПРАВЛЕННОЙ ЛОГИКИ ПРИМЕНЕНИЯ БАФФА ---

            total_collected += income
            updated_pets.append(pet["id"])

    if not updated_pets:
        await message.answer("⏳ Ещё рано. Попробуй позже — питомцы ещё не принесли монет!")
        return
    
    await execute_query(
        "UPDATE users SET coins = coins + $1, total_coins_collected = total_coins_collected + $1 WHERE user_id = $2", # Добавил total_coins_collected
        {"coins": total_collected, "uid": uid}
    )

    for pet_id in updated_pets:
        await execute_query(
            "UPDATE pets SET last_collected = $1 WHERE id = $2",
            {"last_collected": now, "id": pet_id}
        )

    await message.answer(f"💰 Ты собрал <b>{total_collected}</b> петкойнов от своих питомцев!")

TRAIN_COST_BASE = 50
TRAIN_COST_PER_LEVEL = 10
XP_GAIN_RANGE = (10, 25)

@router.message(Command("train"))
async def train_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    args = command.args

    if not args:
        await message.answer("❓ Использование: /train 'id' 'stat'\nНапример: /train 1 atk")
        return
    
    parts = args.strip().split()
    if len(parts) != 2:
        await message.answer("⚠️ Нужно указать ID и характеристику: hp, atk или def.")
        return

    pet_id_raw, stat = parts
    if stat not in ("hp", "atk", "def"):
        await message.answer("⚠️ Неверная характеристика. Используй: hp, atk, def.")
        return
    
    try:
        pet_id = int(pet_id_raw)
    except ValueError:
        await message.answer("⚠️ ID должен быть числом.")
        return
    
    pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "uid": uid})
    if not pet:
        await message.answer("🐾 Питомец не найден.")
        return
    
    cost = TRAIN_COST_BASE + pet["level"] * TRAIN_COST_PER_LEVEL
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})
    if user["coins"] < cost:
        await message.answer(f"💸 Для тренировки нужно {cost} петкойнов. У тебя недостаточно.")
        return
    
    cls = pet["class"]
    boost = 0
    if cls == "Дамаг-диллер":
        boost = random.randint(3, 7) if stat == "atk" else random.randint(1, 3)
    elif cls == "Саппорт":
        boost = random.randint(3, 7) if stat == "def" else random.randint(1, 3)
    elif cls == "Баланс":
        boost = random.randint(2, 5)
    elif cls == "Танк":
        boost = random.randint(3, 7) if stat == "hp" else random.randint(1, 3)
    else:
        boost = random.randint(2, 4)

    xp_gain = random.randint(*XP_GAIN_RANGE)
    new_xp = pet["xp"] + xp_gain
    new_lvl = pet["level"]
    new_xp_needed = pet["xp_needed"]
    leveled_up = False

    if new_xp >= pet["xp_needed"]:
        new_lvl  += 1
        new_xp = 0
        new_xp_needed = int(pet["xp_needed"] * 1.25)
        leveled_up = True

    stats = json.loads(pet["stats"])
    stats[stat] += boost

    coin_rate = pet["coin_rate"]
    if leveled_up and new_lvl % 2 == 0:
        coin_rate += 1

    await execute_query(
        """
        UPDATE pets SET stats = $1, xp = $2, xp_needed = $3, level = $4, coin_rate = $5
        WHERE id = $6
        """,
        {
            "stats": json.dumps(stats),
            "xp": new_xp,
            "xp_needed": new_xp_needed,
            "level": new_lvl,
            "coin_rate": coin_rate,
            "id": pet_id
        }
    )

    await execute_query(
        "UPDATE users SET coins = coins - $1 WHERE user_id = $2",
        {"coins": cost, "uid": uid}
    )

    msg = (
        f"🏋️‍♂️ Ты потренировал <b>{pet['name']}</b>!\n"
        f"📈 {stat.upper()} вырос на <b>{boost}</b>.\n"
        f"💡 Получено {xp_gain} XP.\n"
    )
    if leveled_up:
        msg += f"🎉 Уровень повышен до <b>{new_lvl}</b>!\n💰 Доход: {coin_rate}/час"

    await message.answer(msg)