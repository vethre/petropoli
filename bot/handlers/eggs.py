import random
from aiogram import Router, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot.handlers.start import check_quest_progress, check_zone_unlocks
from db.db import fetch_one, execute_query
from bot.utils.pet_generator import EGG_TYPES, PETS_BY_RARITY, RARITIES, RARITY_STATS_RANGE, RARITY_TOTAL_STAT_MULTIPLIER, generate_stats_for_class, roll_pet_from_egg_type
import json
from datetime import datetime

router = Router()

async def create_pet_and_save(user_id: int, egg_type: str) -> dict:
    """Создает питомца на основе типа яйца и сохраняет в базу данных."""
    
    # 1. Получаем данные для генерации питомца из pet_generator
    pet_data = roll_pet_from_egg_type(egg_type, PETS_BY_RARITY, EGG_TYPES)
    
    if not pet_data:
        return None # Ошибка определения редкости

    rarity = pet_data["rarity"]
    pclass = pet_data["class"]

    # 2. Генерируем статы
    stats = generate_stats_for_class(pclass, rarity, RARITY_STATS_RANGE, RARITY_TOTAL_STAT_MULTIPLIER)
    
    # 3. Определяем coin_rate из RARITIES (из config.py)
    rarity_info_for_coin_rate = RARITIES[rarity]
    coin_rate = random.randint(rarity_info_for_coin_rate["coin_rate_range"][0], rarity_info_for_coin_rate["coin_rate_range"][1])

    initial_xp_needed = 100 # Можете настроить или сделать зависимым от редкости

    new_pet_data = {
        "user_id": user_id,
        "name": pet_data["name"],
        "class": pclass,
        "rarity": rarity,
        "level": 1,
        "xp": 0,
        "xp_needed": initial_xp_needed,
        "stats": json.dumps(stats),
        "coin_rate": coin_rate,
        "last_collected": datetime.utcnow() # Добавлено для совместимости с explore
    }
    
    # Save to database
    query = """
    INSERT INTO pets (user_id, name, class, rarity, level, xp, xp_needed, stats, coin_rate, last_collected)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    RETURNING id, name, class, rarity, level;
    """
    result = await fetch_one(query, new_pet_data)
    
    if result:
        # Assuming result contains the returned columns from RETURNING
        return {
            "id": result['id'],
            "name": result['name'],
            "class": result['class'],
            "rarity": result['rarity'],
            "level": result['level'],
            "stats": stats, # Возвращаем статы для отображения
            "coin_rate": coin_rate
        }
    return None

@router.message(Command("buy_egg"))
async def buy_egg_cmd(message: Message):
    uid = message.from_user.id
    user = await fetch_one("SELECT coins FROM users WHERE user_id = $1", {"uid": uid})
    
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return

    builder = InlineKeyboardBuilder()
    menu_text = "🥚 Выбери яйцо, которое хочешь купить:\n\n"

    for egg_key, egg_info in EGG_TYPES.items():
        if egg_info["cost"] is not None: # Только те яйца, которые можно купить за монеты
            cost_str = f" ({egg_info['cost']} 💰)"
            builder.button(text=f"{egg_info['name_ru']}{cost_str}", callback_data=f"buy_egg_{egg_key}")
            menu_text += f"<b>{egg_info['name_ru']}</b>: {egg_info['description']} - {egg_info['cost']} 💰\n"
    
    builder.adjust(1) # Кнопки в столбик

    await message.answer(
        menu_text,
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("buy_egg_"))
async def process_buy_egg_callback(callback: CallbackQuery):
    uid = callback.from_user.id
    egg_type_key = callback.data.split("buy_egg_")[1]
    
    egg_info = EGG_TYPES.get(egg_type_key)
    if not egg_info or egg_info["cost"] is None:
        await callback.answer("Ошибка: Неверный тип яйца или это яйцо нельзя купить.", show_alert=True)
        return

    cost = egg_info["cost"]
    
    # Используем FOR UPDATE для обеспечения атомарности при списании монет
    user = await fetch_one("SELECT coins, eggs, bought_eggs FROM users WHERE user_id = $1 FOR UPDATE", {"uid": uid})
    if not user:
        await callback.message.answer("Пользователь не найден. Пожалуйста, попробуйте /start.")
        await callback.answer()
        return

    if user['coins'] < cost:
        await callback.message.answer(f"Недостаточно монет! У тебя {user['coins']} 💰, а нужно {cost} 💰.")
        await callback.answer()
        return

    # Вычитаем монеты и добавляем яйцо в инвентарь пользователя
    current_eggs = json.loads(user['eggs']) if user['eggs'] else []
    
    new_egg_record = {
        "type": egg_type_key, # Сохраняем тип яйца, чтобы знать, что вылуплять
        "bought_at": datetime.utcnow().isoformat(),
    }
    current_eggs.append(new_egg_record)

    await execute_query(
        "UPDATE users SET coins = coins - $1, eggs = $2, bought_eggs = bought_eggs + 1 WHERE user_id = $3",
        {"cost": cost, "eggs": json.dumps(current_eggs), "uid": uid}
    )

    await callback.message.answer(
        f"🥚 Ты купил {egg_info['name_ru']} за {cost} 💰!\n"
        f"У тебя осталось {user['coins'] - cost} 💰.\n"
        f"Напиши /hatch, чтобы его вылупить.",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(Command("hatch"))
async def hatch_egg_cmd(message: Message):
    uid = message.from_user.id

    user = await fetch_one("SELECT coins, eggs, hatched_count FROM users WHERE user_id = $1 FOR UPDATE", {"uid": uid})
    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    current_eggs = json.loads(user['eggs']) if user['eggs'] else []
    if not current_eggs:
        await message.answer("У тебя нет яиц для вылупления. Купи яйцо с помощью /buy_egg.")
        return
    
    # Берем первое яйцо из списка (самое старое)
    egg_to_hatch = current_eggs.pop(0) 
    egg_type_key = egg_to_hatch.get("type", "базовое") # По умолчанию 'базовое', если тип не указан

    # Создаем питомца на основе ТИПА ЯЙЦА
    new_pet_data = await create_pet_and_save(uid, egg_type_key)

    if not new_pet_data:
        await message.answer("Что-то пошло не так при вылуплении питомца. Попробуй позже.")
        return

    # Обновляем список яиц у пользователя
    await execute_query(
        "UPDATE users SET eggs = $1, hatched_count = hatched_count + 1 WHERE user_id = $2",
        {"eggs": json.dumps(current_eggs), "uid": uid}
    )

    # Проверка квеста (по вашей логике)
    if user["hatched_count"] == 1: # Это будет 0 + 1 = 1 после вылупления первого яйца
        await check_quest_progress(uid, message)

    await message.answer(
        f"🎉 Из яйца вылупился питомец!\n\n"
        f"🔹 <b>{new_pet_data['name']}</b> ({new_pet_data['rarity']} — {new_pet_data['class']})\n"
        f"🏅 Уровень: {new_pet_data['level']} | XP: 0/{new_pet_data.get('xp_needed', 100)}\n" # XP_needed для нового пета
        f"📊 Статы:\n"
        f"   🗡 Атака: {new_pet_data['stats']['atk']}\n"
        f"   🛡 Защита: {new_pet_data['stats']['def']}\n"
        f"   ❤ Здоровье: {new_pet_data['stats']['hp']}\n"
        f"💰 Доход: {new_pet_data['coin_rate']} петкойнов/час",
        parse_mode="HTML"
    )