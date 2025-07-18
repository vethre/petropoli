import asyncio
import json
from db.db import init_db, execute_query

async def apply_schema():
    await init_db()
    with open("db/models.sql", "r", encoding="utf-8") as f:
        sql = f.read()
    # Розбиваємо по ; щоб виконати кожен запит окремо
    for statement in sql.split(";"):
        statement = statement.strip()
        if statement:
            await execute_query(statement)

STARTER_ZONES = [
    ("Лужайка", "Твоя первая зелёная зона, где петы пасутся и фармят монеты.", 0, {}, "coin_rate", 0),
    ("Ферма", "Плодородные земли и домашние петы. Тут чуть больше дохода.", 500, {"hatched_count": 5}, "coin_rate", 10),
    ("Гора", "Холодные скалы и мощные петы. Выглядит грозно.", 1000, {"hatched_count": 10}, "coin_rate", 20),
]

async def create_zones():
    for name, desc, cost, conditions, buff_type, buff_value in STARTER_ZONES:
        await execute_query(
            """
            INSERT INTO zones (name, description, cost, unlock_conditions, buff_type, buff_value)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (name) DO UPDATE SET
                description = EXCLUDED.description,
                cost = EXCLUDED.cost,
                unlock_conditions = EXCLUDED.unlock_conditions,
                buff_type = EXCLUDED.buff_type,
                buff_value = EXCLUDED.buff_value
            """,
            {
                "name": name,
                "description": desc,
                "cost": cost,
                "unlock_conditions": json.dumps(conditions),
                "buff_type": buff_type,
                "buff_value": buff_value
            }
        )

async def main():
    await apply_schema()
    await init_db()
    await create_zones()

if __name__ == "__main__":
    asyncio.run(main())
    print("Database initialized and starter zones created.")
