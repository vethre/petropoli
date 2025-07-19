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

async def insert_quest(uid: int, name: str, description: str, zone: str, goal: int, reward_coins: int = 0, reward_egg: bool = False):
    await execute_query(
        "INSERT INTO quests (user_id, name, description, zone, goal, reward_coins, reward_egg) VALUES ($1, $2, $3, $4, $5, $6, $7)",
        {"uid": uid, "name": name, "description": description, "zone": zone, "goal": goal, "reward_coins": reward_coins, "reward_egg": reward_egg}
    )

async def update_quest_progress(uid: int, quest_name: str, increment: int = 1):
    await execute_query(
        "UPDATE quests SET progress = progress + $1 WHERE user_id = $2 AND name = $3 AND completed = FALSE",
        {"increment": increment, "uid": uid, "quest_name": quest_name}
    )

async def complete_quest(uid: int, quest_name: str):
    await execute_query(
        "UPDATE quests SET completed = TRUE WHERE user_id = $1 AND name = $2",
        {"uid": uid, "quest_name": quest_name}
    )

async def claim_quest_reward(user_id: int, quest_id: int):
    # Теперь мы ищем по ID квеста, а не по имени
    quest = await fetch_one("SELECT * FROM quests WHERE user_id = $1 AND id = $2 AND completed = TRUE AND claimed = FALSE", {"user_id": user_id, "id": quest_id})

    if not quest:
        return False, "Квест не найден, не завершен или награда уже получена."

    # Process rewards
    reward_coins = quest.get("reward_coins", 0)
    reward_egg = quest.get("reward_egg", False)

    # Update user's coins
    if reward_coins > 0:
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2", {"coins_to_add": reward_coins, "user_id": user_id})

    # Add egg if applicable
    if reward_egg:
        user = await fetch_one("SELECT eggs FROM users WHERE user_id = $1", {"user_id": user_id})
        current_eggs = json.loads(user["eggs"] or "[]")
        current_eggs.append({"type": "Лужайка", "rarity": "common"}) # Пример яйца, можешь настроить
        await execute_query("UPDATE users SET eggs = $1 WHERE user_id = $2", {"eggs_json": json.dumps(current_eggs), "user_id": user_id})

    # Mark quest as claimed
    await execute_query("UPDATE quests SET claimed = TRUE WHERE id = $1", {"id": quest_id})

    reward_message = ""
    if reward_coins > 0:
        reward_message += f"💰 {reward_coins} петкойнов"
    if reward_egg:
        if reward_message: reward_message += ", "
        reward_message += "🥚 1 яйцо"

    final_message = f"Награда за квест «{quest['name']}» получена! {reward_message}"
    if not reward_message:
        final_message = f"Квест «{quest['name']}» завершен и отмечен как полученный."

    return True, final_message