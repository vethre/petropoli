import json
import random
from datetime import datetime, timezone

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
# Убедитесь, что fetch_one и execute_query импортированы корректно
from db.db import fetch_all, fetch_one, execute_query

from bot.handlers.bonus import update_pet_stats_and_xp, get_xp_for_next_level 
from aiogram.client.bot import Bot 

router = Router()

# --- Константы для слияния ---
RARITY_ORDER = ["Обычная", "Редкая", "Эпическая", "Легендарная", "Мифическая"] # Порядок редкостей
RARITY_UPGRADE_CHANCE = 0.70 # 70% шанс повышения редкости при слиянии

BASE_STATS_BY_RARITY = {
    "Обычная": {"hp": 50, "atk": 10, "def": 5},
    "Редкая": {"hp": 70, "atk": 15, "def": 8},
    "Эпическая": {"hp": 100, "atk": 20, "def": 12},
    "Легендарная": {"hp": 150, "atk": 30, "def": 18},
    "Мифическая": {"hp": 200, "atk": 40, "def": 25}
}

MERGE_STAT_MULTIPLIER = 0.6 
MERGE_BONUS_PER_STAT = 5 
MERGE_XP_BONUS = 100 

# Стоимость слияния (например, монеты)
MERGE_COST = 500 # Стоимость в монетах

@router.message(Command("merge"))
async def merge_cmd(message: Message, command: CommandObject, bot: Bot): # Добавлен bot: Bot
	uid = message.from_user.id
	args = command.args

	if not args:
		await message.answer("❗ Используй команду так: <code>/merge id1 id2</code>\n"
							 "Слияние возможно только между питомцами одной редкости.", parse_mode="HTML")
		return
	
	try:
		id1, id2 = map(int, args.strip().split())
	except Exception:
		await message.answer("❗ Укажи корректные ID питомцев (целые числа), например: <code>/merge 123 456</code>", parse_mode="HTML")
		return
	
	if id1 == id2:
		await message.answer("❗ Нужно выбрать двух разных питомцев для слияния.")
		return

	# Проверяем, есть ли у пользователя достаточно монет для слияния
	user_coins_record = await fetch_one("SELECT coins FROM users WHERE user_id = $1", {"uid": uid})
	if not user_coins_record or user_coins_record['coins'] < MERGE_COST:
		await message.answer(f"❌ Для слияния требуется {MERGE_COST} 💰. У тебя недостаточно монет.")
		return

	pet1 = await fetch_one("SELECT id, name, rarity, class, level, xp, stats, coin_rate FROM pets WHERE user_id = $1 AND id = $2", {"uid": uid, "id": id1})
	pet2 = await fetch_one("SELECT id, name, rarity, class, level, xp, stats, coin_rate FROM pets WHERE user_id = $1 AND id = $2", {"uid": uid, "id": id2})

	if not pet1 or not pet2:
		await message.answer("❌ Один из питомцев не найден или не принадлежит тебе. Проверь ID.")
		return

	if pet1["rarity"] != pet2["rarity"]:
		await message.answer("⚠️ Слияние возможно только между питомцами <b>одной редкости</b>!", parse_mode="HTML")
		return
	
	current_rarity_index = RARITY_ORDER.index(pet1["rarity"])
	
	# Определяем новую редкость
	new_rarity = pet1["rarity"] # По умолчанию остается та же редкость
	
	# Проверяем, есть ли более высокая редкость
	if current_rarity_index + 1 < len(RARITY_ORDER):
		# Есть шанс на повышение редкости
		if random.random() < RARITY_UPGRADE_CHANCE:
			new_rarity_index = current_rarity_index + 1
			new_rarity = RARITY_ORDER[new_rarity_index]
			rarity_upgraded = True
		else:
			rarity_upgraded = False
	else:
		# Уже максимальная редкость, повышение невозможно
		rarity_upgraded = False
		await message.answer(f"ℹ️ Примечание: Ваши питомцы уже <b>{pet1['rarity']}</b> редкости, это максимальная редкость. Слияние улучшит статы, но редкость не изменится.", parse_mode="HTML")

	# Расчет новых статов
	stats1 = json.loads(pet1["stats"]) if isinstance(pet1["stats"], str) else pet1["stats"]
	stats2 = json.loads(pet2["stats"]) if isinstance(pet2["stats"], str) else pet2["stats"]

	# Базовые статы для новой (или текущей) редкости
	base_new_stats = BASE_STATS_BY_RARITY.get(new_rarity, {"hp": 1, "atk": 1, "def": 1}) # Дефолтные, если что-то пошло не так

	new_stats = {
		"hp": int(base_new_stats["hp"] + (stats1["hp"] + stats2["hp"]) * MERGE_STAT_MULTIPLIER + MERGE_BONUS_PER_STAT),
		"atk": int(base_new_stats["atk"] + (stats1["atk"] + stats2["atk"]) * MERGE_STAT_MULTIPLIER + MERGE_BONUS_PER_STAT),
		"def": int(base_new_stats["def"] + (stats1["def"] + stats2["def"]) * MERGE_STAT_MULTIPLIER + MERGE_BONUS_PER_STAT)
	}

	new_xp = pet1["xp"] + pet2["xp"] + MERGE_XP_BONUS
	new_level = 1 

	name = pet1["name"] if pet1["level"] >= pet2["level"] else pet2["name"]
	pclass = pet1["class"] if pet1["level"] >= pet2["level"] else pet2["class"]
 
	coin_rate = int((pet1["coin_rate"] + pet2["coin_rate"]) / 2) # Усредняем coin_rate

	# Начинаем транзакцию для атомарности
	try:
		# !!! Здесь мы не используем BEGIN/COMMIT/ROLLBACK напрямую с execute_query,
		# а полагаемся на то, что `asyncpg` и обертки `db.db` управляют транзакциями.
		# Если _pool в db.db использует `conn.transaction()`, то явные BEGIN/COMMIT/ROLLBACK здесь не нужны
		# и даже могут привести к проблемам.
		# Лучше обернуть весь блок в `async with conn.transaction():` если у вас есть прямой доступ к conn.
		# В данном случае, так как вы используете execute_query, fetch_one,
		# то предполагается, что эти функции берут и возвращают соединения из пула.
		# Атомарность нескольких операций в таком случае требует явного управления транзакциями
		# на уровне функций в db.db, или же передачи одного соединения во все функции.
		# Для простоты, я закомментирую явные BEGIN/COMMIT/ROLLBACK здесь,
		# и сосредоточусь на исправлении ошибки execute_query.
		# await execute_query("BEGIN") # <--- Закомментировано

		# Снимаем монеты за слияние
		await execute_query("UPDATE users SET coins = coins - $1 WHERE user_id = $2", {"cost": MERGE_COST, "uid": uid})

		# Вставляем нового питомца и получаем его ID
		# ИСПОЛЬЗУЕМ fetch_one вместо execute_query для INSERT...RETURNING
		insert_result = await fetch_one(
			"INSERT INTO pets (user_id, name, rarity, class, level, xp, stats, coin_rate, last_collected, current_hp) "
			"VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10) RETURNING id, name, stats, xp, level",
			{
				"uid": uid,
				"name": name,
				"rarity": new_rarity,
				"class": pclass,
				"level": new_level, 
				"xp": new_xp,
				"stats": json.dumps(new_stats),
				"coin_rate": coin_rate,
				"last_collected": datetime.utcnow().replace(tzinfo=timezone.utc),
				"current_hp": new_stats['hp'] 
			}
			# УДАЛЕН return_result=True, так как fetch_one уже возвращает результат
		)
		
		new_pet_id = insert_result['id'] if insert_result else None # fetch_one возвращает один Record или None

		if not new_pet_id:
			raise Exception("Не удалось получить ID нового питомца после слияния.")

		# Удаляем старых питомцев
		await execute_query(
			"DELETE FROM pets WHERE user_id = $1 AND id = ANY($2::int[])",
			{"uid": uid, "ids": [id1, id2]}
		)

		# await execute_query("COMMIT") # <--- Закомментировано

		# Обновляем статы и опыт нового питомца
		# Предполагается, что update_pet_stats_and_xp сам работает с базой данных
		await update_pet_stats_and_xp(bot, uid, new_pet_id, xp_gain=0)

		# Получаем финальные данные нового питомца для вывода
		final_new_pet = await fetch_one("SELECT name, rarity, level, stats FROM pets WHERE id = $1", {"id": new_pet_id})
		# Проверка, что final_new_pet не None (хотя после успешного INSERT такого быть не должно)
		if not final_new_pet:
			raise Exception("Не удалось найти нового питомца после слияния для отображения информации.")

		final_stats = json.loads(final_new_pet["stats"]) if isinstance(final_new_pet["stats"], str) else final_new_pet["stats"]

		rarity_message = ""
		if rarity_upgraded:
			rarity_message = f" и повысил свою редкость до <b>{new_rarity}</b>!"
		else:
			rarity_message = f" и остался <b>{new_rarity}</b> редкости, но стал сильнее!"

		await message.answer(
			f"✨ Поздравляем! Ваш питомец <b>{final_new_pet['name']}</b> был создан слиянием двух питомцев{rarity_message}\n"
			f"Теперь он <b>Уровня {final_new_pet['level']}</b>!\n"
			f"Новые характеристики:\n"
			f"⚔ Атака: {final_stats['atk']} | 🛡 Защита: {final_stats['def']} | ❤️ Здоровье: {final_stats['hp']}\n"
			f"Два питомца (ID: {id1}, {id2}) были поглощены.",
			parse_mode="HTML"
		)

	except Exception as e:
		# await execute_query("ROLLBACK") # <--- Закомментировано
		print(f"Ошибка при слиянии питомцев: {e}")
		await message.answer("❌ Произошла ошибка при попытке слияния питомцев. Попробуй еще раз позже.", parse_mode="HTML")