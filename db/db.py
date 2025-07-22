from datetime import datetime, timezone
import json
import asyncpg
from config import DB_URL

pool: asyncpg.Pool = None

async def init_db():
    global pool
    if pool is None:
        pool = await asyncpg.create_pool(
            dsn=DB_URL, 
            command_timeout=60,
            min_size=1,
            max_size=5
        )

async def fetch_one(query: str, args: dict = None):
    async with pool.acquire() as connection:
        return await connection.fetchrow(query, *args.values() if args else ())
    
async def fetch_all(query: str, args: dict = None):
    async with pool.acquire() as connection:
        return await connection.fetch(query, *args.values() if args else ())
    
async def execute_query(query: str, args: dict = None):
    async with pool.acquire() as connection:
        return await connection.execute(query, *args.values() if args else ())
    
async def get_user_quests(uid: int):
    return await fetch_all("SELECT * FROM quests WHERE user_id = $1", {"uid": uid})

async def insert_quest(user_id: int, quest_id: str, name: str, description: str, zone: str, goal: int, reward_coins: int, reward_egg_type: str = None):
    await execute_query(
        "INSERT INTO quests (user_id, quest_id, name, description, progress, goal, reward_coins, reward_egg_type, completed, claimed, zone) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, FALSE, FALSE, $9)",
        {
            "user_id": user_id,
            "quest_id": quest_id,
            "name": name,
            "description": description,
            "progress": 0, # Начинаем с 0
            "goal": goal,
            "reward_coins": reward_coins,
            "reward_egg_type": reward_egg_type,
            "zone": zone
        }
    )

async def update_quest_progress(uid: int, quest_id: str, increment: int = 1): # Изменено quest_name на quest_id
    await execute_query(
        "UPDATE quests SET progress = progress + $1 WHERE user_id = $2 AND quest_id = $3 AND completed = FALSE", # Использовать quest_id
        {"increment": increment, "uid": uid, "quest_id": quest_id} # Использовать quest_id
    )

async def complete_quest(uid: int, quest_id: str): # Изменено quest_name на quest_id
    await execute_query(
        "UPDATE quests SET completed = TRUE WHERE user_id = $1 AND quest_id = $2", # Использовать quest_id
        {"uid": uid, "quest_id": quest_id} # Использовать quest_id
    )

# ИСПРАВЛЕННАЯ ФУНКЦИЯ claim_quest_reward
async def claim_quest_reward(uid: int, quest_db_id: int): # Изменено user_id на uid для консистентности, и quest_id на quest_db_id для ясности
    quest_record = await fetch_one("SELECT * FROM quests WHERE id = $1 AND user_id = $2", {"id": quest_db_id, "user_id": uid})

    if not quest_record or not quest_record['completed'] or quest_record.get('claimed', False):
        return False, "Квест не завершен или награда уже забрана."

    # Мы больше не используем QUESTS_DEFINITIONS.get(quest_record['quest_id']) здесь
    # Все данные о награде берутся из самой записи квеста в БД
    reward_coins = quest_record.get('reward_coins', 0)
    reward_egg_type = quest_record.get('reward_egg_type') # Теперь это тип яйца

    # Обновляем монеты пользователя и total_coins_collected (если это не делается в другом месте)
    if reward_coins > 0:
        await execute_query("UPDATE users SET coins = coins + $1, total_coins_collected = total_coins_collected + $1 WHERE user_id = $2",
                            {"coins": reward_coins, "uid": uid})

    # Добавляем яйцо в инвентарь пользователя (eggs JSONB)
    if reward_egg_type:
        user_data = await fetch_one("SELECT eggs FROM users WHERE user_id = $1", {"uid": uid})
        eggs_list = json.loads(user_data.get('eggs', '[]') or '[]')
        eggs_list.append({"type": reward_egg_type, "timestamp": datetime.now(timezone.utc).isoformat()}) # Используем datetime.now(timezone.utc)
        await execute_query("UPDATE users SET eggs = $1 WHERE user_id = $2", {"eggs": json.dumps(eggs_list), "uid": uid})
        # Если у вас есть счетчик eggs_collected, увеличьте его здесь:
        await execute_query("UPDATE users SET eggs_collected = eggs_collected + 1 WHERE user_id = $1", {"uid": uid})

    await execute_query("UPDATE quests SET claimed = TRUE WHERE id = $1", {"id": quest_db_id})

    msg = f"🎉 Награда за квест «{quest_record['name']}» получена!" # Используем имя из записи квеста
    if reward_coins > 0:
        msg += f"\n💰 Получено {reward_coins} петкойнов."
    if reward_egg_type:
        msg += f"\n🥚 Получено {reward_egg_type.capitalize()} яйцо."

    return True, msg