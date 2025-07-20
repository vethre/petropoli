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

from bot.utils.pet_generator import EGG_TYPES
from db.db import fetch_one, fetch_all, execute_query
from bot.handlers.eggs import create_pet_and_save # Импортируем функцию для создания питомца
from bot.handlers.explore import MAX_ENERGY, recalculate_energy, update_user_energy # Импортируем функции для энергии
from bot.utils.battle_system import simulate_battle_dungeon # <--- ИМПОРТ НОВОЙ ФУНКЦИИ

router = Router()

MONSTERS = {
    "лесной_волк": {
        "name_ru": "Лесной Волк",
        "hp": 50,
        "atk": 15,
        "def": 10,
        "xp_reward": 20,
        "coin_reward": 30,
        "abilities": ["Быстрая атака"] # Пример способностей
    },
    "древесный_голем": {
        "name_ru": "Древесный Голем",
        "hp": 80,
        "atk": 10,
        "def": 25,
        "xp_reward": 35,
        "coin_reward": 45,
        "abilities": ["Каменная кожа"]
    },
    "огненный_элементаль": {
        "name_ru": "Огненный Элементаль",
        "hp": 70,
        "atk": 25,
        "def": 15,
        "xp_reward": 40,
        "coin_reward": 50,
        "abilities": ["Горящая аура"]
    },
    "лавовый_гоблин": {
        "name_ru": "Лавовый Гоблин",
        "hp": 60,
        "atk": 20,
        "def": 10,
        "xp_reward": 30,
        "coin_reward": 35,
        "abilities": ["Взрывной удар"]
    },
    # Добавьте больше монстров
    "древний_зверь": {
        "name_ru": "Древний Зверь",
        "hp": 120,
        "atk": 30,
        "def": 20,
        "xp_reward": 70,
        "coin_reward": 90,
        "abilities": ["Яростный рев"]
    },
    "повелитель_огня": {
        "name_ru": "Повелитель Огня",
        "hp": 150,
        "atk": 40,
        "def": 25,
        "xp_reward": 100,
        "coin_reward": 120,
        "abilities": ["Метеоритный дождь", "Огненный щит"]
    }
}

# Dungeon Definitions
DUNGEONS = {
    "лесное_подземелье": {
        "name_ru": "Лесное подземелье",
        "description": "Сложное подземелье, кишащее опасными существами. Шанс получить Дореволюционное яйцо.",
        "difficulty_level": 5, # Рекомендуемый уровень питомца/команды
        "reward_egg_type": "дореволюционное",
        "entry_cost_energy": 50,
        "min_pets_required": 1,
        "duration_min": 5, # Для тестирования уменьшаем
        "duration_max": 10, # Для тестирования уменьшаем
        "monster_pool": ["лесной_волк", "древесный_голем"], # Монстры, которые могут встретиться
        "num_encounters": 2, # Количество боев в данже
        "boss_monster": None # Пока нет босса, но можно добавить
    },
    "огненная_пещера": {
        "name_ru": "Огненная пещера",
        "description": "Раскаленная пещера с древними духами огня. Шанс получить Фаберже яйцо.",
        "difficulty_level": 10,
        "reward_egg_type": "фаберже",
        "entry_cost_energy": 80,
        "min_pets_required": 2,
        "duration_min": 10,
        "duration_max": 20,
        "monster_pool": ["огненный_элементаль", "лавовый_гоблин"],
        "num_encounters": 3,
        "boss_monster": "повелитель_огня" # Пример босса
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
            f"  <i>{dungeon_info['description']}</i>\n"
            f"  Рекомендуемый уровень: {dungeon_info['difficulty_level']}\n"
            f"  Потребуется энергии: {dungeon_info['entry_cost_energy']}\n"
            f"  Мин. питомцев: {dungeon_info['min_pets_required']}\n\n"
        )
        builder.button(text=dungeon_info['name_ru'], callback_data=f"select_dungeon_{dungeon_key}")
    builder.adjust(1) # Кнопки в столбик

    await message.answer(menu_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(DungeonState.choosing_dungeon) # Переходим в состояние выбора данжа


@router.callback_query(F.data.startswith("select_dungeon_"), StateFilter(DungeonState.choosing_dungeon))
async def select_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    dungeon_key = callback.data.split("select_dungeon_")[1]
    dungeon_info = DUNGEONS.get(dungeon_key)

    if not dungeon_info:
        await callback.message.edit_text("Подземелье не найдено. Попробуйте еще раз.")
        await state.clear()
        await callback.answer()
        return

    # Проверка энергии (перенесена на этот этап)
    current_energy = await recalculate_energy(uid)
    if current_energy < dungeon_info['entry_cost_energy']:
        await callback.message.edit_text(
            f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
            f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
            parse_mode="HTML"
        )
        await state.clear() # Сбрасываем состояние, так как нельзя войти
        await callback.answer()
        return
    
    # Сохраняем выбранный данж в FSM контексте
    await state.update_data(selected_dungeon_key=dungeon_key)

    # ИЗМЕНЕНИЕ ЗДЕСЬ: Добавляем current_hp в запрос
    user_pets_db_records = await fetch_all("SELECT id, name, level, rarity, stats, current_hp FROM pets WHERE user_id = $1 ORDER BY level DESC, rarity DESC", {"uid": uid})
    
    if not user_pets_db_records:
        await callback.message.edit_text("У тебя нет питомцев для прохождения подземелий. Используй /buy_egg и /hatch.")
        await state.clear()
        await callback.answer()
        return
    
    # ИЗМЕНЕНИЕ ЗДЕСЬ: Преобразуем список asyncpg.Record в список dict и инициализируем current_hp
    user_pets_db = []
    for pet_record in user_pets_db_records:
        pet = dict(pet_record)
        pet['stats'] = json.loads(pet['stats']) # Десериализуем stats
        # Если current_hp не существует или равно None, инициализируем его максимальным HP
        if pet['current_hp'] is None: 
            pet['current_hp'] = pet['stats']['hp']
        user_pets_db.append(pet)
    
    # Формируем кнопки для выбора питомцев
    builder = InlineKeyboardBuilder()
    selected_pets_ids = [] # Будем хранить ID выбранных питомцев
    
    # Получаем уже выбранных питомцев из состояния, если они есть
    data = await state.get_data()
    if 'selected_pets_ids' in data:
        selected_pets_ids = data['selected_pets_ids']

    for pet in user_pets_db:
        is_selected = pet['id'] in selected_pets_ids
        # Отображаем текущее HP в кнопке выбора
        button_text = f"✅ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" if is_selected else f"☐ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]"
        builder.button(text=button_text, callback_data=f"toggle_pet_{pet['id']}")

    builder.adjust(2) # Две кнопки в ряд

    # Добавляем кнопки "Начать поход" и "Отмена"
    builder.row(InlineKeyboardButton(text="Начать поход", callback_data="start_dungeon"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_dungeon"))

    # Обновляем текст списка питомцев, чтобы показать HP
    pet_list_text = "\n".join([f"ID {pet['id']} — {pet['name']} ({pet['rarity']}, Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" for pet in user_pets_db])

    await callback.message.edit_text(
        f"Ты выбрал подземелье <b>{dungeon_info['name_ru']}</b>.\n"
        f"Рекомендуемый уровень: {dungeon_info['difficulty_level']}, Потребуется энергии: {dungeon_info['entry_cost_energy']}\n\n"
        f"Твои питомцы (выбери {dungeon_info['min_pets_required']} или больше): \n{pet_list_text}\n\n"
        f"Выбрано питомцев: {len(selected_pets_ids)}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await state.set_state(DungeonState.choosing_pets) # Переходим в состояние выбора питомцев
    await callback.answer()

@router.callback_query(F.data.startswith("toggle_pet_"), StateFilter(DungeonState.choosing_pets))
async def toggle_pet_selection_callback(callback: CallbackQuery, state: FSMContext):
    pet_id = int(callback.data.split("toggle_pet_")[1])
    data = await state.get_data()
    selected_pets_ids = data.get('selected_pets_ids', [])
    
    # ИЗМЕНЕНИЕ ЗДЕСЬ: Добавляем current_hp в запрос для обновления кнопок
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
        # Проверяем, существует ли питомец у пользователя
        if any(pet['id'] == pet_id for pet in user_pets_db):
            # Проверяем, что питомец не мертв (HP > 0)
            selected_pet = next((p for p in user_pets_db if p['id'] == pet_id), None)
            if selected_pet and selected_pet['current_hp'] > 0:
                selected_pets_ids.append(pet_id)
            else:
                await callback.answer("Этот питомец не может быть выбран, так как у него 0 HP. Пожалуйста, вылечите его.", show_alert=True)
                return
    
    await state.update_data(selected_pets_ids=selected_pets_ids)
    
    # Пересоздаем кнопки для обновления состояния
    builder = InlineKeyboardBuilder()
    for pet in user_pets_db:
        is_selected = pet['id'] in selected_pets_ids
        button_text = f"✅ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" if is_selected else f"☐ {pet['name']} (Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]"
        builder.button(text=button_text, callback_data=f"toggle_pet_{pet['id']}")
    builder.adjust(2)

    builder.row(InlineKeyboardButton(text="Начать поход", callback_data="start_dungeon"))
    builder.row(InlineKeyboardButton(text="Отмена", callback_data="cancel_dungeon"))

    # Обновляем текст списка питомцев, чтобы показать HP
    pet_list_text = "\n".join([f"ID {pet['id']} — {pet['name']} ({pet['rarity']}, Ур. {pet['level']}) [{pet['current_hp']}/{pet['stats']['hp']} HP]" for pet in user_pets_db])

    await callback.message.edit_text(
        f"Твои питомцы (выбери {DUNGEONS[data['selected_dungeon_key']]['min_pets_required']} или больше):\n{pet_list_text}\n\n"
        f"Выбрано питомцев: {len(selected_pets_ids)}",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "start_dungeon", StateFilter(DungeonState.choosing_pets))
async def start_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    uid = callback.from_user.id
    data = await state.get_data()
    selected_dungeon_key = data.get('selected_dungeon_key')
    selected_pets_ids = data.get('selected_pets_ids', [])

    if not selected_dungeon_key:
        await callback.message.edit_text("Произошла ошибка, подземелье не выбрано. Попробуйте /dungeon еще раз.")
        await state.clear()
        await callback.answer()
        return

    dungeon_info = DUNGEONS.get(selected_dungeon_key)
    if not dungeon_info:
        await callback.message.edit_text("Произошла ошибка, информация о подземелье не найдена.")
        await state.clear()
        await callback.answer()
        return

    if len(selected_pets_ids) < dungeon_info['min_pets_required']:
        await callback.message.answer(f"Для этого подземелья требуется как минимум {dungeon_info['min_pets_required']} питомцев. Выбрано: {len(selected_pets_ids)}.")
        await callback.answer()
        return

    # Получаем полную информацию о выбранных питомцах, включая current_hp
    selected_pets_data = []
    for pet_id in selected_pets_ids:
        # ИЗМЕНЕНИЕ ЗДЕСЬ: Добавляем current_hp в запрос
        pet_record = await fetch_one("SELECT id, name, level, stats, class, rarity, current_hp FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
        
        if pet_record:
            pet = dict(pet_record)
            pet['stats'] = json.loads(pet['stats'])
            # Если current_hp не существует или равно None, инициализируем его максимальным HP
            if pet['current_hp'] is None:
                pet['current_hp'] = pet['stats']['hp']
            
            # Проверяем, что питомец не мертв перед началом похода
            if pet['current_hp'] <= 0:
                await callback.message.edit_text(f"Невозможно начать поход. Питомец <b>{pet['name']}</b> имеет 0 HP. Пожалуйста, вылечите его с помощью /heal.", parse_mode="HTML")
                await state.clear()
                await callback.answer()
                return

            selected_pets_data.append(pet)
    
    if len(selected_pets_data) < dungeon_info['min_pets_required']:
        await callback.message.answer("Не удалось найти всех выбранных питомцев (возможно, они мертвы или были удалены). Попробуйте еще раз.")
        await state.clear()
        await callback.answer()
        return

    # Проверка энергии еще раз (на случай, если пользователь долго выбирал)
    current_energy = await recalculate_energy(uid)
    if current_energy < dungeon_info['entry_cost_energy']:
        await callback.message.edit_text(
            f"Недостаточно энергии для входа в <b>{dungeon_info['name_ru']}</b>.\n"
            f"Нужно {dungeon_info['entry_cost_energy']} энергии, у тебя {current_energy}/{MAX_ENERGY}.",
            parse_mode="HTML"
        )
        await state.clear()
        await callback.answer()
        return
    
    # Вычитаем энергию
    await update_user_energy(uid, current_energy - dungeon_info['entry_cost_energy'])

    # Сохраняем информацию о текущем данже и питомцах
    await state.update_data(
        current_dungeon_key=selected_dungeon_key,
        current_pets_data=selected_pets_data,
        current_encounter_index=0, # Для отслеживания прогресса в данже
        dungeon_total_xp = 0,
        dungeon_total_coins = 0
    )
    await state.set_state(DungeonState.in_dungeon_progress)

    await callback.message.edit_text(f"🗺️ Ваша команда отправляется в <b>{dungeon_info['name_ru']}</b>!\n"
                                     f"Приготовьтесь к бою!",
                                     parse_mode="HTML")
    await callback.answer()
    
    # Запускаем симуляцию данжа
    await simulate_dungeon_progress(callback.message, uid, state)


@router.callback_query(F.data == "cancel_dungeon", StateFilter(DungeonState.choosing_pets))
async def cancel_dungeon_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Выход из выбора подземелья.")
    await state.clear() # Сбрасываем FSM состояние
    await callback.answer()

# --- Dungeon Simulation Logic ---

async def simulate_dungeon_progress(message: Message, user_id: int, state: FSMContext):
    data = await state.get_data()
    dungeon_key = data['current_dungeon_key']
    dungeon_info = DUNGEONS[dungeon_key]
    pets_data = data['current_pets_data']
    encounter_index = data['current_encounter_index']
    dungeon_total_xp = data['dungeon_total_xp']
    dungeon_total_coins = data['dungeon_total_coins']

    # Проходим по всем стычкам (монстрам)
    num_encounters_to_do = dungeon_info['num_encounters']
    if dungeon_info['boss_monster']:
        num_encounters_to_do += 1 # Добавляем босса как отдельную стычку

    for i in range(encounter_index, num_encounters_to_do):
        # Проверяем, есть ли еще живые питомцы в команде перед каждым новым боем
        if not any(pet['current_hp'] > 0 for pet in pets_data):
            await message.answer(
                f"💀 Все ваши питомцы потеряли сознание. Поход окончен!\n"
                f"Вы заработали: {dungeon_total_xp} XP, {dungeon_total_coins} 💰.\n"
                f"<b>Ваши питомцы нуждаются в лечении!</b> Используйте команду <code>/heal</code>.",
                parse_mode="HTML"
            )
            # Сохраняем текущее HP питомцев (они все 0)
            for pet_with_damage in pets_data:
                await execute_query(
                    "UPDATE pets SET current_hp = $1 WHERE id = $2", 
                    {"current_hp": max(0, pet_with_damage['current_hp']), "pet_id": pet_with_damage['id']}
                )
            await state.clear()
            return

        if i < dungeon_info['num_encounters']:
            # Обычный монстр
            monster_key = random.choice(dungeon_info['monster_pool'])
            monster_info = MONSTERS[monster_key]
            current_monster_name = monster_info['name_ru']
            encounter_type = "Монстр"
        else:
            # Босс
            monster_key = dungeon_info['boss_monster']
            monster_info = MONSTERS[monster_key]
            current_monster_name = monster_info['name_ru']
            encounter_type = "БОСС"

        await message.answer(f"⚡️ Ваша команда столкнулась с <b>{current_monster_name}</b> ({encounter_type})!", parse_mode="HTML")
        await asyncio.sleep(random.uniform(2, 4)) # Небольшая пауза перед боем

        # Симулируем бой
        battle_result = simulate_battle_dungeon(pets_data, monster_info)
        
        if battle_result.get('battle_log'):
            await message.answer("\n".join(battle_result['battle_log']), parse_mode="HTML")
            await asyncio.sleep(1)

        if battle_result['victory']:
            dungeon_total_xp += battle_result['xp_gained']
            dungeon_total_coins += battle_result['coins_gained']
            await message.answer(
                f"🏆 Победа над <b>{current_monster_name}</b>!\n"
                f"Получено: {battle_result['xp_gained']} XP, {battle_result['coins_gained']} 💰"
                f"\n\nПрогресс данжа: {i + 1}/{num_encounters_to_do} стычек."
                f"\nОбщий заработок в данже: {dungeon_total_xp} XP, {dungeon_total_coins} 💰",
                parse_mode="HTML"
            )
            # Обновляем XP питомцев в БД после каждой победы
            # Обновляем current_hp питомцев, но не восстанавливаем их полностью,
            # они продолжают данж с оставшимся HP
            pets_data = battle_result['updated_pets_data'] # Получаем обновленные данные питомцев из боя
            for pet_update in pets_data:
                await execute_query("UPDATE pets SET xp = xp + $1, current_hp = $2 WHERE id = $3", 
                                    {"xp_gained": battle_result['xp_gained'], "current_hp": max(0, pet_update['current_hp']), "pet_id": pet_update['id']})
                # TODO: Добавить проверку уровня и повышение уровня здесь или в отдельной функции (это отдельная большая задача)
            
            # Обновляем данные в FSM контексте
            await state.update_data(
                current_encounter_index=i + 1,
                dungeon_total_xp=dungeon_total_xp,
                dungeon_total_coins=dungeon_total_coins,
                current_pets_data=pets_data # Сохраняем обновленные данные питомцев
            )

        else:
            # Если поражение
            await message.answer(
                f"💀 Ваша команда потерпела поражение от <b>{current_monster_name}</b>. Поход окончен!\n"
                f"Вы заработали: {dungeon_total_xp} XP, {dungeon_total_coins} 💰 (до поражения).\n"
                f"<b>Ваши питомцы нуждаются в лечении!</b> Используйте команду <code>/heal</code>.",
                parse_mode="HTML"
            )
            
            # Сохраняем текущее HP питомцев в БД при поражении
            pets_data_after_loss = battle_result['updated_pets_data'] # Получаем финальное состояние HP
            for pet_with_damage in pets_data_after_loss:
                await execute_query(
                    "UPDATE pets SET current_hp = $1 WHERE id = $2", 
                    {"current_hp": max(0, pet_with_damage['current_hp']), "pet_id": pet_with_damage['id']}
                )
            await state.clear()
            return

        await asyncio.sleep(random.uniform(2, 5))

    # --- Данж успешно завершен ---
    # Если мы дошли сюда, значит все стычки (и босс, если есть) были побеждены.
    reward_egg_type_key = dungeon_info['reward_egg_type']
    reward_egg_info = EGG_TYPES.get(reward_egg_type_key)

    # Добавляем яйцо в инвентарь пользователя
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
    
    # При успешном завершении, восстанавливаем HP ВСЕХ питомцев (которые участвовали) до полного
    for pet_with_damage in pets_data: # pets_data здесь - это последнее состояние из боя
        await execute_query(
            "UPDATE pets SET current_hp = $1 WHERE id = $2", 
            {"current_hp": pet_with_damage['stats']['hp'], "pet_id": pet_with_damage['id']}
        )
    
    await message.answer(
        f"🎉 <b>Команда успешно прошла {dungeon_info['name_ru']}</b>!\n"
        f"Общий заработок: <b>{dungeon_total_xp} XP</b> и <b>{dungeon_total_coins} 💰</b>.\n"
        f"В награду ты получил <b>{reward_egg_info['name_ru']}</b>!\n"
        f"Напиши /hatch, чтобы вылупить его!\n"
        f"\nТекущая энергия: {await recalculate_energy(user_id)}/{MAX_ENERGY}",
        parse_mode="HTML"
    )
    await state.clear() # Сбрасываем состояние после успешного завершения данжа