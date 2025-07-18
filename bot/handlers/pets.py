import json
from math import ceil
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db.db import fetch_all

router = Router()

PETS_PER_PAGE = 5

@router.message(Command("pets"))
async def pets_cmd(message: Message):
    await show_pets_paginated(message.from_user.id, message)

async def show_pets_paginated(uid: int, message: Message | CallbackQuery, page: int = 1):
    pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
    if not pets:
        await message.answer("У тебя пока нет питомцев 😿\nКупи яйцо через /buy_egg и выведи кого-то!")
        return

    total_pages = max(1, ceil(len(pets) / PETS_PER_PAGE))
    page = max(1, min(page, total_pages))

    start = (page - 1) * PETS_PER_PAGE
    end = start + PETS_PER_PAGE
    page_pets = pets[start:end]

    text = f"🐾 <b>Твои питомцы (стр. {page}/{total_pages}):</b>\n\n"
    for pet in page_pets:
        stats = json.loads(pet["stats"])
        text += (
            f"🔸 <b>ID {pet['id']}</b> — {pet['name']} ({pet['rarity']}, {pet['class']})\n"
            f"🏅 Уровень: {pet['level']} | XP: {pet['xp']}/{pet['xp_needed']}\n"
            f"📊 Статы: 🗡 {stats['atk']} 🛡 {stats['def']} ❤ {stats['hp']}\n"
            f"💸 Приносит: {pet['coin_rate']} петкойнов/час\n\n"
        )

    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="⬅️ Назад", callback_data=f"pets_page:{page-1}")
    kb.button(text=f"📄 Страница {page}/{total_pages}", callback_data="noop")
    if page < total_pages:
        kb.button(text="➡️ Вперёд", callback_data=f"pets_page:{page+1}")
    kb.adjust(3)

    if isinstance(message, CallbackQuery):
        await message.message.edit_text(text.strip(), reply_markup=kb.as_markup())
        await message.answer()
    else:
        await message.answer(text.strip(), reply_markup=kb.as_markup())

@router.callback_query(F.data.startswith("pets_page:"))
async def paginate_pets(call: CallbackQuery):
    uid = call.from_user.id
    page = int(call.data.split(":")[1])
    await show_pets_paginated(uid, call, page)
