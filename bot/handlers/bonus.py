# bot/handlers/bonus.py

import asyncio
import random
import json
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext

from db.db import fetch_one, fetch_all, execute_query
from bot.utils.pet_generator import EGG_TYPES # Для получения инфо о яйцах

router = Router()

# --- Константы для бонусов ---
DAILY_COIN_RANGE = (50, 200)
DAILY_XP_RANGE = (100, 300)
DAILY_EGG_CHANCE = 0.25 # 25% шанс на яйцо
DAILY_EGG_TYPES = ["базовое", "всмятку"] # Типы яиц, которые можно получить
FAV_PET_STAT_BONUS_PERCENT = 0.05 # 5% бонус к HP, ATK, DEF любимца
TOP_PET_COIN_REWARD = 300
TOP_PET_XP_REWARD = 150 # XP для Питомец Дня
TOP_PET_DURATION_HOURS = 24 # Как долго питомец будет "Питомцем дня"

# Список "мемных" названий для Питомца дня
TOP_PET_NICKNAMES = [
    "Герой Дня", "Легенда Арены", "Пушистая Звезда", "Хвостатый Бог",
    "Имба-Питомец", "Король Логова", "Дневной Дозор", "Избранный",
    "Просто Красавчик", "Величайший из Великих"
]

current_top_pet = {
    "pet_id": None,
    "user_id": None,
    "nickname": None,
    "ends_at": None # datetime object
}

def get_xp_for_next_level(level: int) -> int:
    """Возвращает количество XP, необходимое для перехода на следующий уровень."""
    return level * 100 + 50

async def update_pet_stats_and_xp(bot_instance, user_id: int, pet_id: int, xp_gain: int = 0): # Добавили bot_instance и user_id
    pet_record = await fetch_one("SELECT id, name, stats, xp, level FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": user_id})
    if not pet_record:
        return False

    current_xp = pet_record['xp']
    current_level = pet_record['level']
    current_stats = json.loads(pet_record['stats']) if isinstance(pet_record['stats'], str) else pet_record['stats']
    pet_name = pet_record['name']

    new_xp = current_xp + xp_gain
    
    leveled_up = False
    original_hp = current_stats['hp']

    # Проверка и повышение уровня
    while new_xp >= get_xp_for_next_level(current_level):
        xp_needed = get_xp_for_next_level(current_level)
        new_xp -= xp_needed
        current_level += 1
        leveled_up = True
            
        # Применяем увеличение статов при повышении уровня
        current_stats['atk'] += random.randint(1, 3)
        current_stats['def'] += random.randint(1, 3)
        current_stats['hp'] += random.randint(3, 7)

        # Обновляем питомца в БД после каждого повышения уровня
        await execute_query(
            "UPDATE pets SET xp = $1, level = $2, stats = $3 WHERE id = $4 AND user_id = $5",
            {"xp": new_xp, "level": current_level, "stats": json.dumps(current_stats), "id": pet_id, "user_id": user_id}
        )
        
        await execute_query("UPDATE pets SET current_hp = $1 WHERE id = $2", {"current_hp": current_stats['hp'], "id": pet_id})

        if current_level >= 100: 
            new_xp = 0 
            await execute_query(
                "UPDATE pets SET xp = $1, level = $2 WHERE id = $3 AND user_id = $4",
                {"xp": new_xp, "level": current_level, "id": pet_id, "user_id": user_id}
            )
            break
    await execute_query("UPDATE pets SET xp = $1 WHERE id = $2 AND user_id = $3", 
                        {"xp": new_xp, "id": pet_id, "user_id": user_id})

    if leveled_up:
        user_chat_info = await bot_instance.get_chat(user_id)
        user_name = user_chat_info.first_name if user_chat_info.first_name else user_chat_info.full_name
        
        await bot_instance.send_message(
            user_id,
            f"🎉 Поздравляем, {user_name}!\nТвой питомец <b>{pet_name}</b> достиг <b>Уровня {current_level}</b>!\n"
            f"Новые характеристики:\n⚔ Атака: {current_stats['atk']} | 🛡 Защита: {current_stats['def']} | ❤️ Здоровье: {current_stats['hp']}",
            parse_mode="HTML"
        )
    return True


# --- Ежедневная награда (/daily) ---
@router.message(Command("daily"))
async def daily_reward_cmd(message: Message):
    uid = message.from_user.id
    user = await fetch_one("SELECT last_daily_claim, coins FROM users WHERE user_id = $1", {"uid": uid})

    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return

    last_claim_str = user['last_daily_claim']
    last_claim_dt = None
    if last_claim_str:
        last_claim_dt = last_claim_str.replace(tzinfo=timezone.utc)
    
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

    if last_claim_dt and (now_utc - last_claim_dt) < timedelta(hours=23, minutes=59):
        next_claim_time = last_claim_dt + timedelta(hours=24)
        time_left = next_claim_time - now_utc
        hours, remainder = divmod(time_left.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        await message.answer(f"Ты уже получал ежедневную награду. Следующая будет доступна через {int(hours)} ч. {int(minutes)} мин.")
        return

    coins_reward = random.randint(DAILY_COIN_RANGE[0], DAILY_COIN_RANGE[1])
    user_pets_records = await fetch_all("SELECT id, name FROM pets WHERE user_id = $1", {"uid": uid})
    
    xp_reward_text = ""
    if user_pets_records:
        random_pet = random.choice(user_pets_records)
        xp_reward = random.randint(DAILY_XP_RANGE[0], DAILY_XP_RANGE[1])
        await update_pet_stats_and_xp(message.bot, uid, random_pet['id'], xp_gain=xp_reward)
        xp_reward_text = f", а твой питомец <b>{random_pet['name']}</b> получил <b>{xp_reward} XP</b>"
    else:
        xp_reward_text = ", но у тебя нет питомцев для получения XP"

    egg_reward_text = ""
    egg_obtained = False
    if random.random() < DAILY_EGG_CHANCE:
        egg_type_key = random.choice(DAILY_EGG_TYPES)
        egg_info = EGG_TYPES[egg_type_key]
        
        user_data_for_eggs = await fetch_one("SELECT eggs FROM users WHERE user_id = $1 FOR UPDATE", {"uid": uid})
        current_eggs = json.loads(user_data_for_eggs['eggs']) if user_data_for_eggs['eggs'] else []

        new_egg_record = {
            "type": egg_type_key,
            "obtained_at": datetime.utcnow().isoformat(),
            "source": "Ежедневная награда"
        }
        current_eggs.append(new_egg_record)
        await execute_query("UPDATE users SET eggs = $1 WHERE user_id = $2", {"eggs": json.dumps(current_eggs), "uid": uid})
        egg_reward_text = f" и {egg_info['name_ru']} яйцо! 🥚"
        egg_obtained = True

    # Обновление монет и времени последнего получения
    await execute_query(
        "UPDATE users SET coins = coins + $1, last_daily_claim = $2 WHERE user_id = $3",
        {"coins": coins_reward, "last_daily_claim": now_utc, "uid": uid}
    )

    await message.answer(
        f"🎁 Ты получил ежедневную награду!\n"
        f"Ты заработал <b>{coins_reward} 💰</b>{xp_reward_text}{egg_reward_text}\n\n"
        f"Твои текущие монеты: {user['coins'] + coins_reward} 💰",
        parse_mode="HTML"
    )

# --- Любимый питомец (/fav) ---
@router.message(Command("fav"))
async def fav_pet_cmd(message: Message, command: Command):
    uid = message.from_user.id
    args = command.args.split() if command.args else []

    if not args:
        # Отображение текущего любимца
        user_data = await fetch_one("SELECT fav_pet_id, fav_pet_nickname FROM users WHERE user_id = $1", {"uid": uid})
        fav_pet_id = user_data['fav_pet_id']
        fav_pet_nickname = user_data['fav_pet_nickname']

        if fav_pet_id:
            pet_record = await fetch_one("SELECT name, rarity FROM pets WHERE id = $1 AND user_id = $2", {"id": fav_pet_id, "user_id": uid})
            if pet_record:
                display_name = fav_pet_nickname if fav_pet_nickname else pet_record['name']
                await message.answer(f"❤️ Твой любимчик: <b>{display_name}</b> ({pet_record['name']}, {pet_record['rarity']})\n"
                                     f"Чтобы изменить ник: <code>/fav name &lt;имя&gt;</code>\n"
                                     f"Чтобы убрать: <code>/fav del</code>", parse_mode="HTML")
            else:
                # Питомец не найден, возможно, был удален. Очищаем fav_pet_id
                await execute_query("UPDATE users SET fav_pet_id = NULL, fav_pet_nickname = NULL WHERE user_id = $1", {"uid": uid})
                await message.answer("У тебя нет любимого питомца или он был удален. Используй <code>/fav set &lt;ID питомца&gt;</code>, чтобы выбрать нового.", parse_mode="HTML")
        else:
            await message.answer("У тебя нет любимого питомца. Используй <code>/fav set &lt;ID питомца&gt;</code>, чтобы выбрать его.", parse_mode="HTML")
        return

    subcommand = args[0].lower()

    if subcommand == "set":
        if len(args) < 2:
            await message.answer("Пожалуйста, укажи ID питомца. Пример: <code>/fav set 123</code>", parse_mode="HTML")
            return
        try:
            pet_id = int(args[1])
        except ValueError:
            await message.answer("Неверный формат ID питомца. ID должен быть числом.", parse_mode="HTML")
            return
        
        pet_record = await fetch_one("SELECT id, name FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
        if pet_record:
            await execute_query("UPDATE users SET fav_pet_id = $1, fav_pet_nickname = NULL WHERE user_id = $2", {"fav_pet_id": pet_id, "uid": uid})
            await message.answer(f"❤️ Питомец <b>{pet_record['name']}</b> теперь твой любимчик! Он получит небольшой бонус к статам в бою.", parse_mode="HTML")
        else:
            await message.answer("Питомец с таким ID не найден или не принадлежит тебе.", parse_mode="HTML")

    elif subcommand == "del":
        await execute_query("UPDATE users SET fav_pet_id = NULL, fav_pet_nickname = NULL WHERE user_id = $1", {"uid": uid})
        await message.answer("💔 Любимый питомец удален. Теперь у тебя нет любимчика.", parse_mode="HTML")

    elif subcommand == "name":
        if len(args) < 2:
            await message.answer("Пожалуйста, укажи новое имя для любимого питомца. Пример: <code>/fav name Димитрик</code>", parse_mode="HTML")
            return
        
        new_nickname = " ".join(args[1:])
        if len(new_nickname) > 20: # Ограничение длины имени
            await message.answer("Имя любимчика не может быть длиннее 20 символов.")
            return

        user_data = await fetch_one("SELECT fav_pet_id FROM users WHERE user_id = $1", {"uid": uid})
        if user_data['fav_pet_id']:
            await execute_query("UPDATE users SET fav_pet_nickname = $1 WHERE user_id = $2", {"fav_pet_nickname": new_nickname, "uid": uid})
            await message.answer(f"Имя любимого питомца изменено на <b>{new_nickname}</b>!", parse_mode="HTML")
        else:
            await message.answer("У тебя нет выбранного любимого питомца, чтобы дать ему имя. Сначала используй <code>/fav set &lt;ID питомца&gt;</code>.", parse_mode="HTML")
    else:
        await message.answer("Неизвестная команда. Используй <code>/fav</code>, <code>/fav set &lt;ID&gt;</code>, <code>/fav del</code> или <code>/fav name &lt;имя&gt;</code>.", parse_mode="HTML")


# --- Питомец дня (/top_pet) ---
@router.message(Command("top_pet"))
async def top_pet_cmd(message: Message):
    uid = message.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})

    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    now_utc = datetime.utcnow().replace(tzinfo=timezone.utc)

    if current_top_pet["pet_id"] and current_top_pet["ends_at"] and now_utc < current_top_pet["ends_at"]:
        # Питомец дня уже выбран и срок не истек
        top_pet_owner_name_record = await fetch_one("SELECT username FROM users WHERE user_id = $1", {"uid": current_top_pet['user_id']})
        owner_name = top_pet_owner_name_record['username'] if top_pet_owner_name_record else "Неизвестный"
        
        await message.answer(
            f"🌟 Питомец Дня: <b>{current_top_pet['nickname']}</b>!\n"
            f"Этот почетный титул принадлежит питомцу пользователя @{owner_name}.\n"
            f"Следующий Питомец Дня будет выбран через "
            f"{int((current_top_pet['ends_at'] - now_utc).total_seconds() / 3600)} ч. "
            f"{int(((current_top_pet['ends_at'] - now_utc).total_seconds() % 3600) / 60)} мин."
            , parse_mode="HTML"
        )
        return

    all_pets = await fetch_all("SELECT id, name, user_id, rarity, level FROM pets")
    
    if not all_pets:
        await message.answer("Пока нет питомцев в системе, чтобы выбрать 'Питомца Дня'.")
        return
    
    selected_pet = random.choice(all_pets)
    selected_owner_id = selected_pet['user_id']
    selected_pet_nickname = random.choice(TOP_PET_NICKNAMES)
    
    # Обновляем глобальную переменную (для простоты)
    current_top_pet["pet_id"] = selected_pet['id']
    current_top_pet["user_id"] = selected_owner_id
    current_top_pet["nickname"] = selected_pet_nickname
    current_top_pet["ends_at"] = now_utc + timedelta(hours=TOP_PET_DURATION_HOURS)

    # Выдаем награду владельцу
    await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2", {"coins": TOP_PET_COIN_REWARD, "uid": selected_owner_id})
    await update_pet_stats_and_xp(selected_pet['id'], xp_gain=TOP_PET_XP_REWARD) # Бонус XP для питомца
    
    owner_username_record = await fetch_one("SELECT username FROM users WHERE user_id = $1", {"uid": selected_owner_id})
    owner_username = owner_username_record['username'] if owner_username_record else "Неизвестный"

    announcement_text = (
        f"🌟 ВНИМАНИЕ! Выбран новый <b>Питомец Дня</b>!\n"
        f"Почетный титул \"{selected_pet_nickname}\" получает питомец "
        f"<b>{selected_pet['name']}</b> ({selected_pet['rarity']}, Ур. {selected_pet['level']}) "
        f"принадлежащий пользователю @{owner_username}!\n\n"
        f"Владелец получает {TOP_PET_COIN_REWARD} 💰, а {selected_pet['name']} получает {TOP_PET_XP_REWARD} XP!"
    )
    
    # Отправляем сообщение в чат, где была вызвана команда
    await message.answer(announcement_text, parse_mode="HTML")
