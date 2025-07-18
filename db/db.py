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
