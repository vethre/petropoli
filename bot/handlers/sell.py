# sell.py
import json
import random
from datetime import datetime, timedelta
from math import ceil

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from db.db import fetch_one, fetch_all, execute_query

# Assume RARITY_ORDER is imported or defined similarly to trade.py
RARITY_ORDER = [
    "Обычная", "Необычная", "Редкая", "Очень Редкая", "Эпическая",
    "Легендарная", "Мифическая", "Древняя", "Божественная", "Абсолютная",
]

router = Router()

# --- NPC Buyers Configuration ---
# Each NPC has a name, description, preferred rarity, and a base price multiplier.
# The actual price will depend on the pet's rarity and this multiplier.
NPC_BUYERS = {
    "Рыжий Боб": {
        "description": "Рыжий Боб — старый ворчливый скупщик, который ценит <b>редких</b> и <b>очень редких</b> питомцев. Он не платит много, но берет почти всех.",
        "preferred_rarities": ["Обычная", "Необычная", "Редкая", "Очень Редкая"],
        "price_multiplier": 0.7, # 70% от базовой цены редкости
        "accepts_all_rarities": False, # If True, will accept any rarity at its multiplier
    },
    "Загадочная Кассандра": {
        "description": "Загадочная Кассандра ищет <b>эпических</b> и <b>легендарных</b> существ для своих таинственных ритуалов. Она платит неплохо!",
        "preferred_rarities": ["Эпическая", "Легендарная", "Мифическая"],
        "price_multiplier": 0.9, # 90% от базовой цены редкости
        "accepts_all_rarities": False,
    },
    "Мастер Ланс": {
        "description": "Мастер Ланс — легендарный зоолог, коллекционирует только <b>древних</b>, <b>божественных</b> и <b>абсолютных</b> питомцев. Готов платить щедро!",
        "preferred_rarities": ["Древняя", "Божественная", "Абсолютная"],
        "price_multiplier": 1.2, # 120% от базовой цены редкости
        "accepts_all_rarities": False,
    },
}

# Base prices for each rarity (can be adjusted)
BASE_RARITY_PRICES = {
    "Обычная": 100,
    "Необычная": 250,
    "Редкая": 500,
    "Очень Редкая": 1000,
    "Эпическая": 2500,
    "Легендарная": 5000,
    "Мифическая": 10000,
    "Древняя": 20000,
    "Божественная": 50000,
    "Абсолютная": 100000,
}

# Helper function to check if a pet is in a user's active arena team
async def is_pet_in_arena_team(user_id: int, pet_id: int) -> bool:
    arena_team_data = await fetch_one("SELECT pet_ids FROM arena_team WHERE user_id = $1", {"user_id": user_id})
    if arena_team_data and arena_team_data["pet_ids"]:
        active_pet_ids = json.loads(arena_team_data["pet_ids"])
        return pet_id in active_pet_ids
    return False

# --- Selling Pets ---
@router.message(Command("sell"))
async def sell_cmd(message: Message):
    uid = message.from_user.id
    args = message.text.split()

    if len(args) == 1:
        # Show list of NPC buyers
        text = "🤝 <b>Рынок скупщиков питомцев</b>\n\n"
        text += "Здесь ты можешь продать своих питомцев NPC.\n"
        text += "Каждый скупщик интересуется определёнными редкостями и предлагает свою цену.\n\n"

        kb = InlineKeyboardBuilder()
        for npc_name, npc_info in NPC_BUYERS.items():
            text += f"👤 <b>{npc_name}:</b> {npc_info['description']}\n\n"
            kb.button(text=f"👉 Поговорить с {npc_name}", callback_data=f"npc_sell:{npc_name}")
        
        kb.adjust(1)
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        return
    
    if len(args) == 3 and args[1].lower() == "pet":
        try:
            pet_id = int(args[2])
        except ValueError:
            await message.answer("🔢 Пожалуйста, укажи числовой ID питомца для продажи.", parse_mode="HTML")
            return

        # Default NPC for direct sell command (e.g., /sell pet <id>)
        # We'll use the first NPC if no specific one is chosen, or prompt to choose.
        await message.answer("Чтобы продать питомца, пожалуйста, выбери скупщика из списка или используй команду `/sell` без аргументов.", parse_mode="HTML")
        return

# Callback for choosing an NPC buyer
@router.callback_query(F.data.startswith("npc_sell:"))
async def choose_npc_sell(call: CallbackQuery):
    npc_name = call.data.split(":")[1]
    uid = call.from_user.id

    if npc_name not in NPC_BUYERS:
        await call.answer("🧐 Этот скупщик не найден.", show_alert=True)
        return

    npc_info = NPC_BUYERS[npc_name]

    pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1", {"uid": uid})
    if not pets:
        await call.message.edit_text(
            f"👤 <b>{npc_name}:</b> У тебя нет питомцев для продажи, юный тренер! Возвращайся, когда обзаведёшься пушистыми друзьями!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад на рынок", callback_data="back_to_sell_market")]
            ]),
            parse_mode="HTML"
        )
        await call.answer()
        return

    # Filter pets that this NPC accepts
    accepted_pets = [
        p for p in pets 
        if p["rarity"] in npc_info["preferred_rarities"] or npc_info["accepts_all_rarities"]
    ]

    if not accepted_pets:
        await call.message.edit_text(
            f"👤 <b>{npc_name}:</b> Увы, но мне не интересны твои питомцы... Приноси тех, что я люблю!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад на рынок", callback_data="back_to_sell_market")]
            ]),
            parse_mode="HTML"
        )
        await call.answer()
        return

    text = f"👤 <b>{npc_name}:</b> Отлично! Покажи, что у тебя есть.\n\n"
    text += "Я готов(а) купить следующих питомцев:\n\n"

    kb = InlineKeyboardBuilder()
    for pet in accepted_pets:
        base_price = BASE_RARITY_PRICES.get(pet["rarity"], 0)
        final_price = int(base_price * npc_info["price_multiplier"])
        
        # Check if pet is in arena team
        is_in_arena = await is_pet_in_arena_team(uid, pet["id"])
        
        if is_in_arena:
            button_text = f"🚫 ID {pet['id']} {pet['name']} ({pet['rarity']}) — В команде"
            kb.button(text=button_text, callback_data="noop") # Disable button
        else:
            button_text = f"💰 Продать ID {pet['id']} {pet['name']} ({pet['rarity']}) за {final_price} Петкойнов"
            kb.button(text=button_text, callback_data=f"confirm_sell:{pet['id']}:{npc_name}")
            
    kb.adjust(1)
    kb.row(InlineKeyboardButton(text="🔙 Назад на рынок", callback_data="back_to_sell_market"))

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("confirm_sell:"))
async def confirm_sell_pet(call: CallbackQuery):
    uid = call.from_user.id
    _, pet_id_str, npc_name = call.data.split(":")
    pet_id = int(pet_id_str)

    pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
    if not pet:
        await call.answer("❌ У тебя нет такого питомца.", show_alert=True)
        await call.message.delete() # Clean up old message
        return

    if await is_pet_in_arena_team(uid, pet_id):
        await call.answer("🚫 Этот питомец сейчас находится в твоей активной арена-команде. Сначала убери его оттуда!", show_alert=True)
        # Re-display the NPC's pet list with updated status if possible, or just inform.
        # For simplicity, we just answer the callback here.
        return

    npc_info = NPC_BUYERS.get(npc_name)
    if not npc_info:
        await call.answer("🧐 Скупщик не найден.", show_alert=True)
        return

    # Re-check if NPC accepts this pet (in case of race condition or old button press)
    if not (pet["rarity"] in npc_info["preferred_rarities"] or npc_info["accepts_all_rarities"]):
        await call.answer(f"🚫 {npc_name} больше не интересуется этим питомцем ({pet['rarity']}).", show_alert=True)
        return

    base_price = BASE_RARITY_PRICES.get(pet["rarity"], 0)
    final_price = int(base_price * npc_info["price_multiplier"])

    # Perform the sale
    await execute_query("DELETE FROM pets WHERE id = $1", {"id": pet_id})
    await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2", {"coins": final_price, "user_id": uid})

    await call.message.edit_text(
        f"🎉 Ты успешно продал(а) <b>{pet['name']}</b> ({pet['rarity']}) <b>{npc_name}</b> за <b>{final_price}</b> Петкойнов! 💰",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад на рынок", callback_data="back_to_sell_market")]
        ]),
        parse_mode="HTML"
    )
    await call.answer("Питомец продан!", show_alert=True)

@router.callback_query(F.data == "back_to_sell_market")
async def back_to_sell_market_callback(call: CallbackQuery):
    await sell_cmd(call.message) # Re-call the initial /sell command logic
    await call.answer()

# --- Renting Pets ---
RENT_COST_PER_DAY_MULTIPLIER = 0.05  # 5% of base rarity price per day
MAX_RENT_DAYS = 7
MIN_RENT_DAYS = 1

@router.message(Command("rent"))
async def rent_cmd(message: Message):
    uid = message.from_user.id
    args = message.text.split()

    if len(args) == 1:
        # Show user's pets available for rent
        pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1 AND rented_until IS NULL", {"uid": uid})
        if not pets:
            await message.answer("🤷‍♀️ У тебя пока нет питомцев, которых можно сдать в аренду, или все твои питомцы уже в аренде!", parse_mode="HTML")
            return
        
        text = "🤝 <b>Сдача питомцев в аренду</b>\n\n"
        text += "Ты можешь сдать питомца в аренду другим игрокам или NPC и получать пассивный доход.\n"
        text += "Выбери питомца и срок аренды (до 7 дней).\n\n"
        text += "<b>Твои доступные питомцы:</b>\n"

        kb = InlineKeyboardBuilder()
        for pet in pets:
            # Check if pet is in arena team
            is_in_arena = await is_pet_in_arena_team(uid, pet["id"])
            
            if is_in_arena:
                button_text = f"🚫 ID {pet['id']} {pet['name']} ({pet['rarity']}) — В команде"
                kb.button(text=button_text, callback_data="noop") # Disable button
            else:
                text += f"🔸 <b>ID {pet['id']}</b> — {pet['name']} ({pet['rarity']}) | Базовая прибыль: {int(BASE_RARITY_PRICES.get(pet['rarity'], 0) * RENT_COST_PER_DAY_MULTIPLIER)}/день\n"
                kb.button(text=f"🏡 Сдать {pet['name']} (ID {pet['id']})", callback_data=f"rent_select_days:{pet['id']}")
        
        kb.adjust(1)
        await message.answer(text, reply_markup=kb.as_markup(), parse_mode="HTML")
        return

    if len(args) == 3 and args[1].lower() == "cancel":
        try:
            pet_id = int(args[2])
        except ValueError:
            await message.answer("🔢 Пожалуйста, укажи числовой ID питомца для отмены аренды.", parse_mode="HTML")
            return
        
        # Logic to cancel rent (if applicable)
        pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
        if not pet:
            await message.answer("❌ У тебя нет такого питомца или он не найден.", parse_mode="HTML")
            return
        
        if not pet.get("rented_until"):
            await message.answer(f"🧐 Питомец <b>{pet['name']}</b> (ID {pet['id']}) не находится в аренде.", parse_mode="HTML")
            return
        
        # For now, cancelling rent means setting rented_until to NULL
        # In a more complex system, this might involve penalties or specific conditions.
        await execute_query("UPDATE pets SET rented_until = NULL WHERE id = $1", {"id": pet_id})
        await message.answer(f"🏡 Аренда питомца <b>{pet['name']}</b> (ID {pet['id']}) успешно отменена! Он вернулся к тебе.", parse_mode="HTML")
        return

    await message.answer("Неверный формат команды. Используй:\n"
                         "<code>/rent</code> — для просмотра доступных питомцев для аренды.\n"
                         "<code>/rent cancel &lt;ID питомца&gt;</code> — для отмены аренды питомца.",
                         parse_mode="HTML")

@router.callback_query(F.data.startswith("rent_select_days:"))
async def rent_select_days(call: CallbackQuery):
    pet_id = int(call.data.split(":")[1])
    uid = call.from_user.id

    pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
    if not pet:
        await call.answer("❌ Питомец не найден.", show_alert=True)
        await call.message.delete()
        return
    
    if await is_pet_in_arena_team(uid, pet_id):
        await call.answer("🚫 Этот питомец сейчас находится в твоей активной арена-команде. Сначала убери его оттуда!", show_alert=True)
        return

    base_price = BASE_RARITY_PRICES.get(pet["rarity"], 0)
    profit_per_day = int(base_price * RENT_COST_PER_DAY_MULTIPLIER)

    text = f"🏡 Ты выбрал(а) <b>{pet['name']}</b> ({pet['rarity']}) для аренды.\n"
    text += f"Прибыль: <b>{profit_per_day}</b> Петкойнов/день.\n"
    text += "На сколько дней хочешь его сдать? (Макс. 7 дней)\n\n"

    kb = InlineKeyboardBuilder()
    for days in range(MIN_RENT_DAYS, MAX_RENT_DAYS + 1):
        total_profit = profit_per_day * days
        kb.button(text=f"{days} дней ({total_profit} Петкойнов)", callback_data=f"rent_confirm:{pet_id}:{days}")
    
    kb.adjust(2) # Two buttons per row
    kb.row(InlineKeyboardButton(text="🔙 Отмена", callback_data="rent_cancel"))

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

@router.callback_query(F.data.startswith("rent_confirm:"))
async def rent_confirm(call: CallbackQuery):
    uid = call.from_user.id
    _, pet_id_str, days_str = call.data.split(":")
    pet_id = int(pet_id_str)
    days = int(days_str)

    pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": pet_id, "user_id": uid})
    if not pet:
        await call.answer("❌ Питомец не найден.", show_alert=True)
        await call.message.delete()
        return

    if await is_pet_in_arena_team(uid, pet_id):
        await call.answer("🚫 Этот питомец сейчас находится в твоей активной арена-команде. Сначала убери его оттуда!", show_alert=True)
        return

    # Check if pet is already rented
    if pet.get("rented_until"):
        await call.answer(f"🧐 {pet['name']} уже в аренде до {pet['rented_until'].strftime('%d.%m.%Y %H:%M')}.", show_alert=True)
        return

    rented_until = datetime.now() + timedelta(days=days)
    base_price = BASE_RARITY_PRICES.get(pet["rarity"], 0)
    total_profit = int(base_price * RENT_COST_PER_DAY_MULTIPLIER * days)

    await execute_query(
        "UPDATE pets SET rented_until = $1, last_rent_payout = $2 WHERE id = $3",
        {"rented_until": rented_until, "last_rent_payout": datetime.now(), "id": pet_id}
    )
    # Store expected profit for later payout (e.g., in a background task)
    await execute_query(
        "UPDATE pets SET expected_rent_profit = $1 WHERE id = $2",
        {"expected_rent_profit": total_profit, "id": pet_id}
    )

    await call.message.edit_text(
        f"🎉 <b>{pet['name']}</b> (ID {pet_id}) успешно сдан(а) в аренду на <b>{days}</b> дней!\n"
        f"Ожидаемая прибыль: <b>{total_profit}</b> Петкойнов.\n"
        f"Вернется: {rented_until.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏡 Посмотреть арендованных", callback_data="show_rented_pets")],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="rent_cancel")]
        ]),
        parse_mode="HTML"
    )
    await call.answer(f"Питомец сдан в аренду на {days} дней!", show_alert=True)


@router.callback_query(F.data == "rent_cancel")
async def rent_cancel(call: CallbackQuery):
    await call.message.edit_text(
        "🏡 Ты отменил(а) сдачу питомца в аренду. Возвращайся, если передумаешь!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Вернуться в меню аренды", callback_data="back_to_rent_menu")]
        ]),
        parse_mode="HTML"
    )
    await call.answer()

@router.callback_query(F.data == "back_to_rent_menu")
async def back_to_rent_menu_callback(call: CallbackQuery):
    await rent_cmd(call.message) # Re-call the initial /rent command logic
    await call.answer()

@router.callback_query(F.data == "show_rented_pets")
async def show_rented_pets_callback(call: CallbackQuery):
    uid = call.from_user.id
    rented_pets = await fetch_all("SELECT * FROM pets WHERE user_id = $1 AND rented_until IS NOT NULL", {"uid": uid})

    if not rented_pets:
        text = "🤷‍♀️ У тебя нет питомцев, находящихся в аренде."
    else:
        text = "🏡 <b>Твои питомцы в аренде:</b>\n\n"
        for pet in rented_pets:
            rent_end_time = pet["rented_until"].strftime('%d.%m.%Y %H:%M') if pet["rented_until"] else "N/A"
            text += (
                f"🔸 <b>ID {pet['id']}</b> — {pet['name']} ({pet['rarity']})\n"
                f"   Прибыль (ожид.): <b>{pet.get('expected_rent_profit', 0)}</b> Петкойнов\n"
                f"   Вернется: <i>{rent_end_time}</i>\n\n"
            )
            
    kb = InlineKeyboardBuilder()
    kb.button(text="🔙 Вернуться в меню аренды", callback_data="back_to_rent_menu")
    kb.adjust(1)

    await call.message.edit_text(text, reply_markup=kb.as_markup(), parse_mode="HTML")
    await call.answer()

# --- Background task for rent payouts (needs to be called periodically from your main bot loop) ---
async def process_rent_payouts():
    # Find pets whose rent period has ended
    overdue_rentals = await fetch_all("SELECT * FROM pets WHERE rented_until IS NOT NULL AND rented_until < $1", {"now": datetime.now()})

    for pet in overdue_rentals:
        user_id = pet["user_id"]
        profit = pet.get("expected_rent_profit", 0)

        # Add coins to user
        await execute_query("UPDATE users SET coins = coins + $1 WHERE user_id = $2", {"coins": profit, "user_id": user_id})
        # Reset pet's rent status
        await execute_query("UPDATE pets SET rented_until = NULL, expected_rent_profit = 0, last_rent_payout = NULL WHERE id = $1", {"id": pet["id"]})

        # Notify user (if bot can reach them)
        try:
            bot = router.bot # Access bot object from router
            await bot.send_message(
                user_id,
                f"🎉 Твой питомец <b>{pet['name']}</b> ({pet['rarity']}) вернулся из аренды! "
                f"Ты получил(а) <b>{profit}</b> Петкойнов прибыли! 💰",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Failed to send rent payout notification to {user_id}: {e}")
            pass # User might have blocked the bot, etc.

    # Find pets whose rent is active but payout might be due (e.g., daily payouts)
    # This example only pays out at the end of the term. If you want daily payouts,
    # you'd need more complex logic here, e.g., checking last_rent_payout and calculating partial profits.
    # For simplicity, current design pays expected_rent_profit at rental end.