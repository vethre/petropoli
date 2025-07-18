import json
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from db.db import fetch_all, fetch_one, execute_query
from datetime import datetime

router = Router()

@router.message(Command("merge"))
async def merge_cmd(message: Message, command: CommandObject):
    uid = message.from_user.id
    args = command.args

    if not args:
        await message.answer("❗ Используй команду так: /merge 'id1' 'id2'")
        return
    
    try:
        id1, id2 = map(int, args.strip().split())
    except Exception:
        await message.answer("❗ Укажи корректные ID: /merge 'id1' 'id2'")
        return
    
    if id1 == id2:
        await message.answer("❗ Нужно выбрать двух разных питомцев для слияния.")
        return

    pet1 = await fetch_one("SELECT * FROM pets WHERE user_id = $1 AND id = $2", {"uid": uid, "id": id1})
    pet2 = await fetch_one("SELECT * FROM pets WHERE user_id = $1 AND id = $2", {"uid": uid, "id": id2})

    if not pet1 or not pet2:
        await message.answer("❌ Один из питомцев не найден. Проверь ID.")
        return

    if pet1["rarity"] != pet2["rarity"]:
        await message.answer("⚠️ Слияние возможно только между питомцами одной редкости!")
        return

    stats1, stats2 = json.loads(pet1["stats"]), json.loads(pet2["stats"])
    new_stats = {
        "atk": (stats1["atk"] + stats2["atk"]) // 2 + 1,
        "def": (stats1["def"] + stats2["def"]) // 2 + 1,
        "hp":  (stats1["hp"]  + stats2["hp"])  // 2 + 1
    }
    new_xp = pet1["xp"] + pet2["xp"] + 50
    new_xp_needed = int((pet1["xp_needed"] + pet2["xp_needed"]) * 1.25)

    name = pet1["name"] if pet1["level"] >= pet2["level"] else pet2["name"]
    rarity = pet1["rarity"]
    pclass = pet1["class"] if pet1["level"] >= pet2["level"] else pet2["class"]
    coin_rate = (pet1["coin_rate"] + pet2["coin_rate"]) // 2 + 1

    await execute_query(
        "INSERT INTO pets (user_id, name, rarity, class, level, xp, xp_needed, stats, coin_rate, last_collected) "
        "VALUES ($1, $2, $3, $4, 1, $5, $6, $7, $8, $9)",
        {
            "uid": uid,
            "name": name,
            "rarity": rarity,
            "class": pclass,
            "xp": new_xp,
            "xp_needed": new_xp_needed,
            "stats": json.dumps(new_stats),
            "coin_rate": coin_rate,
            "last_collected": datetime.utcnow()
        }
    )

    await execute_query(
        "DELETE FROM pets WHERE user_id = $1 AND id = ANY($2::int[])",
        {"uid": uid, "ids": [id1, id2]}
    )

    await message.answer(f"✨ <b>{name}</b> был создан слиянием двух питомцев! Статы улучшены, XP сохранена и добавлен +1 ко всем параметрам.")
