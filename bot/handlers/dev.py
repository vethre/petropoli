from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from db.db import execute_query, fetch_one

router = Router()

DEV_IDS = [700929765, 988127866]

def is_dev(uid: int) -> bool:
    return uid in DEV_IDS

@router.message(Command("dev_coins"))
async def dev_coins(message: Message):
    uid = message.from_user.id
    if not is_dev(uid):
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    args = message.text.split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer("❌ Использование: /dev_coins *кол-во*")
        return

    amount = int(args[1])
    await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2", {"coins": amount, "uid": uid})
    await message.answer(f"💰 Начислено {amount} петкойнов.")

@router.message(Command("dev_xp"))
async def dev_xp(message: Message):
    uid = message.from_user.id
    if not is_dev(uid):
        await message.answer("⛔ У тебя нет доступа к этой команде.")
        return

    args = message.text.split()
    if len(args) != 3 or not args[1].isdigit() or not args[2].isdigit():
        await message.answer("❌ Использование: /dev_xp *pet_id* *xp*")
        return

    pet_id = int(args[1])
    xp_add = int(args[2])

    pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "uid": uid,})
    if not pet:
        await message.answer("❌ Питомец не найден.")
        return

    await execute_query("UPDATE pets SET xp = xp + $1 WHERE id = $2", {"xp": xp_add, "id": pet_id})
    await message.answer(f"🌟 Начислено {xp_add} XP питомцу #{pet_id}.")