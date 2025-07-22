# bot/handlers/dungeon.py

import asyncio
import random
import json
from datetime import datetime, timedelta, timezone

from aiogram import Router, F
from aiogram.filters import Command, StateFilter
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest # Импортируем для обработки ошибок

from bot.utils.pet_generator import EGG_TYPES
from db.db import fetch_one, fetch_all, execute_query
from bot.handlers.eggs import create_pet_and_save # Импортируем функцию для создания питомца
from bot.handlers.explore import MAX_ENERGY, recalculate_energy, update_user_energy_db # Импортируем функции для энергии
from bot.utils.battle_system import simulate_battle_dungeon # <--- ИМПОРТ НОВОЙ ФУНКЦИИ

router = Router()

# --- КОНСТАНТЫ ДЛЯ БАЛАНСА ---
BASE_MONSTER_HP_PER_DIFFICULTY = 10 # Базовое HP за единицу сложности
BASE_MONSTER_ATK_PER_DIFFICULTY = 3 # Базовая Атака за единицу сложности
BASE_MONSTER_DEF_PER_DIFFICULTY = 2 # Базовая Защита за единицу сложности
BASE_MONSTER_XP_PER_DIFFICULTY = 5 # Базовый XP за единицу сложности
BASE_MONSTER_COINS_PER_DIFFICULTY = 7 # Базовые Монеты за единицу сложности

BOSS_MULTIPLIER_HP = 2.0 # Босс имеет в X раз больше HP
BOSS_MULTIPLIER_ATK = 1.5 # Босс имеет в X раз больше ATK
BOSS_MULTIPLIER_DEF = 1.5 # Босс имеет в X раз больше DEF
BOSS_MULTIPLIER_REWARD = 2.0 # Босс дает в X раз больше наград

# --- ОПРЕДЕЛЕНИЯ МОНСТРОВ ---
MONSTERS = {
    "лесной_волк": {
        "name_ru": "Лесной Волк",
        "base_hp": 30,
        "base_atk": 10,
        "base_def": 5,
        "abilities": ["Быстрая атака"]
    },
    "древесный_голем": {
        "name_ru": "Древесный Голем",
        "base_hp": 50,
        "base_atk": 8,
        "base_def": 15,
        "abilities": ["Каменная кожа"]
    },
    "огненный_элементаль": {
        "name_ru": "Огненный Элементаль",
        "base_hp": 40,
        "base_atk": 18,
        "base_def": 10,
        "abilities": ["Горящая аура"]
    },
    "лавовый_гоблин": {
        "name_ru": "Лавовый Гоблин",
        "base_hp": 35,
        "base_atk": 15,
        "base_def": 7,
        "abilities": ["Взрывной удар"]
    },
    "древний_зверь": {
        "name_ru": "Древний Зверь",
        "base_hp": 80,
        "base_atk": 25,
        "base_def": 15,
        "abilities": ["Яростный рев"]
    },
    "повелитель_огня": {
        "name_ru": "Повелитель Огня",
        "base_hp": 100,
        "base_atk": 30,
        "base_def": 20,
        "abilities": ["Метеоритный дождь", "Огненный щит"]
    },
    "ледяной_тролль": {
        "name_ru": "Ледяной Тролль",
        "base_hp": 70,
        "base_atk": 20,
        "base_def": 20,
        "abilities": ["Ледяная броня"]
    },
    "снежная_фурия": {
        "name_ru": "Снежная Фурия",
        "base_hp": 60,
        "base_atk": 25,
        "base_def": 12,
        "abilities": ["Заморозка"]
    },
    "призрачный_рыцарь": {
        "name_ru": "Призрачный Рыцарь",
        "base_hp": 90,
        "base_atk": 30,
        "base_def": 25,
        "abilities": ["Неуловимость"]
    },
    "король_скелетов": {
        "name_ru": "Король Скелетов",
        "base_hp": 120,
        "base_atk": 35,
        "base_def": 30,
        "abilities": ["Воскрешение"]
    }
}

# --- ОПРЕДЕЛЕНИЯ ДАНЖЕЙ ---
DUNGEONS = {
    "лесное_подземелье": {
        "name_ru": "Лесное подземелье",
        "description": "Сложное подземелье, кишащее опасными существами. Шанс получить Крутое яйцо.",
        "difficulty_level": 5, # Рекомендуемый уровень питомца/команды
        "reward_egg_type": "крутое",
        "entry_cost_energy": 50,
        "min_pets_required": 1,
        "duration_min": 5,
        "duration_max": 10,
        "monster_pool": ["лесной_волк", "древесный_голем"],
        "num_encounters": 2,
        "boss_monster": None
    },
    "огненная_пещера": {
        "name_ru": "Огненная пещера",
        "description": "Раскаленная пещера с древними духами огня. Шанс получить яйцо всмятку.",
        "difficulty_level": 10,
        "reward_egg_type": "всмятку",
        "entry_cost_energy": 80,
        "min_pets_required": 2,
        "duration_min": 10,
        "duration_max": 20,
        "monster_pool": ["огненный_элементаль", "лавовый_гоблин"],
        "num_encounters": 3,
        "boss_monster": "повелитель_огня"
    },
    "ледяные_глубины": {
        "name_ru": "Ледяные Глубины",
        "description": "Замерзшие пещеры, где обитают древние ледяные существа. Шанс получить Дореволюционное яйцо.",
        "difficulty_level": 15,
        "reward_egg_type": "дореволюционное",
        "entry_cost_energy": 120,
        "min_pets_required": 3,
        "duration_min": 15,
        "duration_max": 25,
        "monster_pool": ["ледяной_тролль", "снежная_фурия", "древний_зверь"],
        "num_encounters": 4,
        "boss_monster": "ледяной_тролль" # Можно использовать существующего монстра как босса, но с усилением
    },
    "забытые_катакомбы": {
        "name_ru": "Забытые Катакомбы",
        "description": "Темные катакомбы, полные призраков и нежити. Шанс получить яйцо Фаберже.",
        "difficulty_level": 20,
        "reward_egg_type": "фаберже",
        "entry_cost_energy": 150,
        "min_pets_required": 4,
        "duration_min": 20,
        "duration_max": 30,
        "monster_pool": ["призрачный_рыцарь", "король_скелетов", "древесный_голем"], # Можно смешивать монстров
        "num_encounters": 5,
        "boss_monster": "король_скелетов"
    }
}

# --- FSM States ---
class DungeonState(StatesGroup):
    choosing_dungeon = State()
    choosing_pets = State()
    in_dungeon_progress = State() # Для отслеживания активного данжа

# --- Dungeon Commands ---

@router.message(Command("dungeon"))
async def dungeon_start_cmd(message: Message, state: FSMContext):
    uid = message.from_user.id
    user = await fetch_one("SELECT * FROM users WHERE user_id = $1", {"uid": uid})

    if not user:
        await message.answer("Ты ещё не зарегистрирован. Напиши /start!")
        return
    
    # Сбрасываем предыдущее состояние, если было
    await state.clear() 
    
    builder = InlineKeyboardBuilder()
    menu_text = "🗺️ Выберите подземелье для прохождения:\n\n"
    for dungeon_key, dungeon_info in DUNGEONS.items():
        menu_text += (
            f"<b>{dungeon_info['name_ru']}</b>:\n"
            f"  <i>{dungeon_info['description']}</i>\n"
            f"  Рекомендуемый уровень: {dungeon_info['difficulty_level']}\n"
            f"  Потребуется энергии: {dungeon_info['entry_cost_energy']}\n"
            f"  Мин. питомцев: {dungeon_info['min_pets_required']}\n\n"
        )
        builder.button(text=dungeon_info['name_ru'], callback_data=f"select_dungeon_{dungeon_key}")
    builder.adjust(1) # Кнопки в столбик

    sent_message = await message.answer(menu_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.update_data(menu_message_id=sent_message.message_id) # Сохраняем ID сообщения для редактирования
    await state.set_state(DungeonState.choosing_dungeon) # Переходим в состояние выбора данжа
    # await asyncio.sleep(random.uniform(0.5, 1.0)) # Задержка после отправки - можно убрать, так как следующее действие - коллбэк

@router.callback_query(F.data.startswith("select_dungeon_"), StateFilter(DungeonState.choosing_dungeon))
async def select_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    dungeon_key = callback.data.split("select_dungeon_")[1]
    dungeon_info = DUNGEONS.get(dungeon_key)
    
    data = await state.get_data()
    menu_message_id = data.get('menu_message_id')

    if not dungeon_info:
        if menu_message_id:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="Подземелье не найдено. Попробуйте еще раз.")
        else:
            await callback.message.answer("Подземелье не найдено. Попробуйте еще раз.")
        await state.clear()
        await callback.answer()
        return

    # Проверка энергии (перенесена на этот этап)
    current_energy = await recalculate_energy(uid)
    if current_energy < dungeon_info['entry_cost_energy']:
        if menu_message_id:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id, message_id=menu_message_id,
                text=f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
                f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(
                f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
                f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
                parse_mode="HTML"
            )
        await state.clear() # Сбрасываем состояние, так как нельзя войти
        await callback.answer()
        return
    
    # Сохраняем выбранный данж в FSM контексте
    await state.update_data(selected_dungeon_key=dungeon_key)

    user_pets_db_records = await fetch_all("SELECT id, name, level, rarity, stats, current_hp FROM pets WHERE user_id = $1 ORDER BY level DESC, rarity DESC", {"uid": uid})
    
    if not user_pets_db_records:
        if menu_message_id:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="У тебя нет питомцев для прохождения подземелий. Используй /buy_egg и /hatch.")
        else:
            await callback.message.answer("У тебя нет питомцев для прохождения подземелий. Используй /buy_egg и /hatch.")
        await state.clear()
        await callback.answer()
        return
    
    user_pets_db = []
    for pet_record in user_pets_db_records:
        pet = dict(pet_record)
        pet['stats'] = json.loads(pet['stats']) # Десериализуем stats
        if pet['current_hp'] is None: 
            pet['current_hp'] = pet['stats']['hp']
        user_pets_db.append(pet)
    
    builder = InlineKeyboardBuilder()
    selected_pets_ids = []
    
    data = await state.get_data()
    if 'selected_pets_ids' in data:
        selected_pets_ids = data['selected_pets_ids']

    for pet in user_pets_db:
        is_selected = pet['id'] in selected_pets_ids
        button_text = f"✅ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" if is_selected else f"☐ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]"
        builder.button(text=button_text, callback_data=f"toggle_pet_{pet['id']}")

    builder.adjust(2)

    builder.row(InlineKeyboardButton(text="Начать поход", callback_data="start_dungeon"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_dungeon"))

    pet_list_text = "\n".join([f"ID {pet['id']} — {pet['name']} ({pet['rarity']}, Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" for pet in user_pets_db])

    if menu_message_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id, message_id=menu_message_id,
                text=f"Ты выбрал подземелье <b>{dungeon_info['name_ru']}</b>.\n"
                f"Рекомендуемый уровень: {dungeon_info['difficulty_level']}, Потребуется энергии: {dungeon_info['entry_cost_energy']}\n\n"
                f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше): \n{pet_list_text}\n\n"
                f"Выбрано питомцев: {len(selected_pets_ids)}",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e): # Избегаем ошибки, если текст не изменился
                await callback.message.answer(
                    f"Ты выбрал подземелье <b>{dungeon_info['name_ru']}</b>.\n"
                    f"Рекомендуемый уровень: {dungeon_info['difficulty_level']}, Потребуется энергии: {dungeon_info['entry_cost_energy']}\n\n"
                    f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше): \n{pet_list_text}\n\n"
                    f"Выбрано питомцев: {len(selected_pets_ids)}",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
    else:
        await callback.message.answer(
            f"Ты выбрал подземелье <b>{dungeon_info['name_ru']}</b>.\n"
            f"Рекомендуемый уровень: {dungeon_info['difficulty_level']}, Потребуется энергии: {dungeon_info['entry_cost_energy']}\n\n"
            f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше): \n{pet_list_text}\n\n"
            f"Выбрано питомцев: {len(selected_pets_ids)}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    
    await state.set_state(DungeonState.choosing_pets)
    await callback.answer()
    # await asyncio.sleep(random.uniform(0.5, 1.0)) # Задержка после редактирования/отправки - можно убрать

@router.callback_query(F.data.startswith("toggle_pet_"), StateFilter(DungeonState.choosing_pets))
async def toggle_pet_selection_callback(callback: CallbackQuery, state: FSMContext):
    pet_id = int(callback.data.split("toggle_pet_")[1])
    data = await state.get_data()
    selected_pets_ids = data.get('selected_pets_ids', [])
    menu_message_id = data.get('menu_message_id')
    selected_dungeon_key = data.get('selected_dungeon_key')
    dungeon_info = DUNGEONS.get(selected_dungeon_key)

    user_pets_db_records = await fetch_all("SELECT id, name, level, rarity, stats, current_hp FROM pets WHERE user_id = $1 ORDER BY level DESC, rarity DESC", {"uid": callback.from_user.id})
    
    user_pets_db = []
    for pet_record in user_pets_db_records:
        pet = dict(pet_record)
        pet['stats'] = json.loads(pet['stats']) # Десериализуем stats
        if pet['current_hp'] is None: 
            pet['current_hp'] = pet['stats']['hp']
        user_pets_db.append(pet)

    if pet_id in selected_pets_ids:
        selected_pets_ids.remove(pet_id)
    else:
        if any(pet['id'] == pet_id for pet in user_pets_db):
            selected_pet = next((p for p in user_pets_db if p['id'] == pet_id), None)
            if selected_pet and selected_pet['current_hp'] > 0:
                selected_pets_ids.append(pet_id)
            else:
                await callback.answer("Этот питомец не может быть выбран, так как у него 0 HP. Пожалуйста, вылечите его.", show_alert=True)
                return
        
    await state.update_data(selected_pets_ids=selected_pets_ids)
    
    builder = InlineKeyboardBuilder()
    for pet in user_pets_db:
        is_selected = pet['id'] in selected_pets_ids
        button_text = f"✅ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" if is_selected else f"☐ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]"
        builder.button(text=button_text, callback_data=f"toggle_pet_{pet['id']}")
    builder.adjust(2)

    builder.row(InlineKeyboardButton(text="Начать поход", callback_data="start_dungeon"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_dungeon"))

    pet_list_text = "\n".join([f"ID {pet['id']} — {pet['name']} ({pet['rarity']}, Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" for pet in user_pets_db])

    if menu_message_id:
        try:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id, message_id=menu_message_id,
                text=f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше):\n{pet_list_text}\n\n"
                f"Выбрано питомцев: {len(selected_pets_ids)}",
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                await callback.message.answer(
                    f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше):\n{pet_list_text}\n\n"
                    f"Выбрано питомцев: {len(selected_pets_ids)}",
                    reply_markup=builder.as_markup(),
                    parse_mode="HTML"
                )
    else:
        await callback.message.answer(
            f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше):\n{pet_list_text}\n\n"
            f"Выбрано питомцев: {len(selected_pets_ids)}",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
    await callback.answer()
    # await asyncio.sleep(random.uniform(0.5, 1.0)) # Задержка после редактирования/отправки - можно убрать

@router.callback_query(F.data == "start_dungeon", StateFilter(DungeonState.choosing_pets))
async def start_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    selected_dungeon_key = data.get('selected_dungeon_key')
    selected_pets_ids = data.get('selected_pets_ids', [])
    menu_message_id = data.get('menu_message_id') # Получаем ID сообщения из FSM

    if not selected_dungeon_key:
        if menu_message_id:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="Произошла ошибка, подземелье не выбрано. Попробуйте /dungeon еще раз.")
        else:
            await callback.message.answer("Произошла ошибка, подземелье не выбрано. Попробуйте /dungeon еще раз.")
        await state.clear()
        await callback.answer()
        return

    dungeon_info = DUNGEONS.get(selected_dungeon_key)
    if not dungeon_info:
        if menu_message_id:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="Произошла ошибка, информация о подземелье не найдена.")
        else:
            await callback.message.answer("Произошла ошибка, информация о подземелье не найдена.")
        await state.clear()
        await callback.answer()
        return

    if len(selected_pets_ids) < dungeon_info['min_pets_required']:
        await callback.answer(f"Для этого подземелья требуется как минимум {dungeon_info['min_pets_required']} питомцев. Выбрано: {len(selected_pets_ids)}.", show_alert=True)
        return

    selected_pets_data = []
    for pet_id in selected_pets_ids:
        pet_record = await fetch_one("SELECT id, name, level, stats, class, rarity, current_hp FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
        
        if pet_record:
            pet = dict(pet_record)
            pet['stats'] = json.loads(pet['stats'])
            if pet['current_hp'] is None:
                pet['current_hp'] = pet['stats']['hp']
            
            if pet['current_hp'] <= 0:
                if menu_message_id:
                    await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text=f"Невозможно начать поход. Питомец <b>{pet['name']}</b> имеет 0 HP. Пожалуйста, вылечите его с помощью /heal.", parse_mode="HTML")
                else:
                    await callback.message.answer(f"Невозможно начать поход. Питомец <b>{pet['name']}</b> имеет 0 HP. Пожалуйста, вылечите его с помощью /heal.", parse_mode="HTML")
                await state.clear()
                await callback.answer()
                return

            selected_pets_data.append(pet)
    
    if len(selected_pets_data) < dungeon_info['min_pets_required']:
        if menu_message_id:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="Не удалось найти всех выбранных питомцев (возможно, они мертвы или были удалены). Попробуйте еще раз.")
        else:
            await callback.message.answer("Не удалось найти всех выбранных питомцев (возможно, они мертвы или были удалены). Попробуйте еще раз.")
        await state.clear()
        await callback.answer()
        return

    current_energy = await recalculate_energy(uid)
    if current_energy < dungeon_info['entry_cost_energy']:
        if menu_message_id:
            await callback.bot.edit_message_text(
                chat_id=callback.message.chat.id, message_id=menu_message_id,
                text=f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
                f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
                parse_mode="HTML"
            )
        else:
            await callback.message.answer(
                f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
                f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
                parse_mode="HTML"
            )
        await state.clear()
        await callback.answer()
        return
    
    await update_user_energy_db(uid, current_energy - dungeon_info['entry_cost_energy'])

    # Сохраняем ID сообщения, которое будем обновлять в процессе данжа
    # Если menu_message_id существует, используем его, иначе отправляем новое
    dungeon_status_message_id = menu_message_id
    if not dungeon_status_message_id:
        # Отправляем новое сообщение, если предыдущего не было (например, при прямом вызове без меню)
        sent_message = await callback.message.answer(f"🗺️ Ваша команда отправляется в <b>{dungeon_info['name_ru']}</b>!\nПриготовьтесь к бою!", parse_mode="HTML")
        dungeon_status_message_id = sent_message.message_id
    else:
        # Редактируем существующее сообщение
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id,
                                                text=f"🗺️ Ваша команда отправляется в <b>{dungeon_info['name_ru']}</b>!\nПриготовьтесь к бою!",
                                                parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                # Если редактирование не удалось по другой причине, отправляем новое
                sent_message = await callback.message.answer(f"🗺️ Ваша команда отправляется в <b>{dungeon_info['name_ru']}</b>!\nПриготовьтесь к бою!", parse_mode="HTML")
                dungeon_status_message_id = sent_message.message_id


    await state.update_data(
        current_dungeon_key=selected_dungeon_key,
        current_pets_data=selected_pets_data,
        current_encounter_index=0,
        dungeon_total_xp = 0,
        dungeon_total_coins = 0,
        dungeon_status_message_id=dungeon_status_message_id # Сохраняем ID сообщения для обновления
    )
    await state.set_state(DungeonState.in_dungeon_progress)

    await callback.answer()
    await asyncio.sleep(random.uniform(1.0, 2.0)) # Задержка перед началом симуляции

    # Передаем message_id в функцию симуляции
    await simulate_dungeon_progress(callback.message, uid, state, dungeon_status_message_id)


@router.callback_query(F.data == "cancel_dungeon", StateFilter(DungeonState.choosing_pets))
async def cancel_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    menu_message_id = data.get('menu_message_id')

    if menu_message_id:
        try:
            await callback.bot.edit_message_text(chat_id=callback.message.chat.id, message_id=menu_message_id, text="Выход из выбора подземелья.")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                await callback.message.answer("Выход из выбора подземелья.")
    else:
        await callback.message.answer("Выход из выбора подземелья.")
    await state.clear()
    await callback.answer()
    # await asyncio.sleep(random.uniform(0.5, 1.0)) # Задержка после отмены - можно убрать

# --- Dungeon Simulation Logic ---

# Добавляем dungeon_status_message_id как аргумент
async def simulate_dungeon_progress(message: Message, user_id: int, state: FSMContext, dungeon_status_message_id: int):
    data = await state.get_data()
    dungeon_key = data['current_dungeon_key']
    dungeon_info = DUNGEONS[dungeon_key]
    pets_data = data['current_pets_data']
    encounter_index = data['current_encounter_index']
    dungeon_total_xp = data['dungeon_total_xp']
    dungeon_total_coins = data['dungeon_total_coins']

    num_encounters_to_do = dungeon_info['num_encounters']
    if dungeon_info['boss_monster']:
        num_encounters_to_do += 1

    current_output_text = "" # Буфер для текущего вывода

    for i in range(encounter_index, num_encounters_to_do):
        if not any(pet['current_hp'] > 0 for pet in pets_data):
            current_output_text += (
                f"\n\n💀 Все ваши питомцы потеряли сознание. Поход окончен!\n"
                f"Вы заработали: {dungeon_total_xp} XP, {dungeon_total_coins} 💰.\n"
                f"<b>Ваши питомцы нуждаются в лечении!</b> Используйте команду <code>/heal</code>."
            )
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id, message_id=dungeon_status_message_id,
                    text=current_output_text, parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    await message.answer(current_output_text, parse_mode="HTML") # Fallback
            
            for pet_with_damage in pets_data:
                await execute_query(
                    "UPDATE pets SET current_hp = $1 WHERE id = $2", 
                    {"current_hp": max(0, pet_with_damage['current_hp']), "pet_id": pet_with_damage['id']}
                )
            await state.clear()
            await asyncio.sleep(random.uniform(1.0, 2.0))
            return

        monster_key = None
        is_boss_encounter = False
        if i < dungeon_info['num_encounters']:
            monster_key = random.choice(dungeon_info['monster_pool'])
            encounter_type = "Монстр"
        else:
            monster_key = dungeon_info['boss_monster']
            encounter_type = "БОСС"
            is_boss_encounter = True

        monster_base_info = MONSTERS[monster_key]
        
        # --- Масштабирование характеристик монстра по сложности данжа ---
        scaled_monster_info = {
            "name_ru": monster_base_info['name_ru'],
            "hp": int(monster_base_info['base_hp'] + (dungeon_info['difficulty_level'] * BASE_MONSTER_HP_PER_DIFFICULTY)),
            "atk": int(monster_base_info['base_atk'] + (dungeon_info['difficulty_level'] * BASE_MONSTER_ATK_PER_DIFFICULTY)),
            "def": int(monster_base_info['base_def'] + (dungeon_info['difficulty_level'] * BASE_MONSTER_DEF_PER_DIFFICULTY)),
            "xp_reward": int(monster_base_info['base_hp'] * 0.5 + (dungeon_info['difficulty_level'] * BASE_MONSTER_XP_PER_DIFFICULTY)), # XP зависит от HP и сложности
            "coin_reward": int(monster_base_info['base_hp'] * 0.3 + (dungeon_info['difficulty_level'] * BASE_MONSTER_COINS_PER_DIFFICULTY)), # Монеты зависят от HP и сложности
            "abilities": monster_base_info.get('abilities', [])
        }

        if is_boss_encounter:
            scaled_monster_info['hp'] = int(scaled_monster_info['hp'] * BOSS_MULTIPLIER_HP)
            scaled_monster_info['atk'] = int(scaled_monster_info['atk'] * BOSS_MULTIPLIER_ATK)
            scaled_monster_info['def'] = int(scaled_monster_info['def'] * BOSS_MULTIPLIER_DEF)
            scaled_monster_info['xp_reward'] = int(scaled_monster_info['xp_reward'] * BOSS_MULTIPLIER_REWARD)
            scaled_monster_info['coin_reward'] = int(scaled_monster_info['coin_reward'] * BOSS_MULTIPLIER_REWARD)
            
        current_monster_name = scaled_monster_info['name_ru']

        # Начинаем формировать вывод для текущей стычки
        current_output_text = f"⚡️ Ваша команда столкнулась с <b>{current_monster_name}</b> ({encounter_type})!\n"
        current_output_text += "Началась битва!\n"

        # Симулируем бой, передавая масштабированные данные монстра
        battle_result = simulate_battle_dungeon(pets_data, scaled_monster_info)
        
        if battle_result.get('battle_log'):
            # Объединяем весь лог боя в одну строку
            current_output_text += "\n".join(battle_result['battle_log']) + "\n"

        if battle_result['victory']:
            dungeon_total_xp += battle_result['xp_gained']
            dungeon_total_coins += battle_result['coins_gained']
            current_output_text += (
                f"\n🏆 Победа над <b>{current_monster_name}</b>!\n"
                f"Получено: {battle_result['xp_gained']} XP, {battle_result['coins_gained']} 💰"
                f"\n\nПрогресс данжа: {i + 1}/{num_encounters_to_do} стычек."
                f"\nОбщий заработок в данже: {dungeon_total_xp} XP, {dungeon_total_coins} 💰"
            )
            
            pets_data = battle_result['updated_pets_data']
            for pet_update in pets_data:
                await execute_query("UPDATE pets SET xp = xp + $1, current_hp = $2 WHERE id = $3", 
                                    {"xp_gained": battle_result['xp_gained'], "current_hp": max(0, pet_update['current_hp']), "pet_id": pet_update['id']})
                # Здесь можно добавить вызов check_and_level_up_pet, если он у вас есть
                # await check_and_level_up_pet(message.bot, user_id, pet_update["id"])
            
            await state.update_data(
                current_encounter_index=i + 1,
                dungeon_total_xp=dungeon_total_xp,
                dungeon_total_coins=dungeon_total_coins,
                current_pets_data=pets_data
            )

        else:
            current_output_text += (
                f"\n💀 Ваша команда потерпела поражение от <b>{current_monster_name}</b>. Поход окончен!\n"
                f"Вы заработали: {dungeon_total_xp} XP, {dungeon_total_coins} 💰 (до поражения).\n"
                f"<b>Ваши питомцы нуждаются в лечении!</b> Используйте команду <code>/heal</code>."
            )
            
            pets_data_after_loss = battle_result['updated_pets_data']
            for pet_with_damage in pets_data_after_loss:
                await execute_query(
                    "UPDATE pets SET current_hp = $1 WHERE id = $2", 
                    {"current_hp": max(0, pet_with_damage['current_hp']), "pet_id": pet_with_damage['id']}
                )
            await state.clear()
            
            try:
                await message.bot.edit_message_text(
                    chat_id=message.chat.id, message_id=dungeon_status_message_id,
                    text=current_output_text, parse_mode="HTML"
                )
            except TelegramBadRequest as e:
                if "message is not modified" not in str(e):
                    await message.answer(current_output_text, parse_mode="HTML") # Fallback
            await asyncio.sleep(random.uniform(1.0, 2.0))
            return

        # Обновляем сообщение с текущим статусом данжа
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id, message_id=dungeon_status_message_id,
                text=current_output_text, parse_mode="HTML"
            )
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e):
                await message.answer(current_output_text, parse_mode="HTML") # Fallback, если редактирование не удалось
        
        await asyncio.sleep(random.uniform(2.0, 4.0)) # Задержка между стычками

    # --- Данж успешно завершен ---
    reward_egg_type_key = dungeon_info['reward_egg_type']
    reward_egg_info = EGG_TYPES.get(reward_egg_type_key)

    user_data_for_eggs = await fetch_one("SELECT eggs FROM users WHERE user_id = $1 FOR UPDATE", {"uid": user_id})
    current_eggs = json.loads(user_data_for_eggs['eggs']) if user_data_for_eggs['eggs'] else []

    new_egg_record = {
        "type": reward_egg_type_key,
        "obtained_at": datetime.utcnow().isoformat(),
        "source": dungeon_info['name_ru']
    }
    current_eggs.append(new_egg_record)

    await execute_query("UPDATE users SET eggs = $1, coins = coins + $2 WHERE user_id = $3", 
                        {"eggs": json.dumps(current_eggs), "coins": dungeon_total_coins, "uid": user_id})
    
    for pet_with_damage in pets_data:
        await execute_query(
            "UPDATE pets SET current_hp = $1 WHERE id = $2", 
            {"current_hp": pet_with_damage['stats']['hp'], "pet_id": pet_with_damage['id']}
        )
    
    final_summary_text = (
        f"🎉 <b>Команда успешно прошла {dungeon_info['name_ru']}</b>!\n"
        f"Общий заработок: <b>{dungeon_total_xp} XP</b> и <b>{dungeon_total_coins} 💰</b>.\n"
        f"В награду ты получил <b>{reward_egg_info['name_ru']}</b>!\n"
        f"Напиши /hatch, чтобы вылупить его!\n"
        f"\nТекущая энергия: {await recalculate_energy(user_id)}/{MAX_ENERGY}"
    )
    
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id, message_id=dungeon_status_message_id,
            text=final_summary_text, parse_mode="HTML"
        )
    except TelegramBadRequest as e:
        if "message is not modified" not in str(e):
            await message.answer(final_summary_text, parse_mode="HTML") # Fallback
            
    await state.clear()
    await asyncio.sleep(random.uniform(1.0, 2.0))