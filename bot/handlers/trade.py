# trade.py
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from db.db import fetch_one, execute_query
import json
import asyncio
from aiogram.exceptions import TelegramBadRequest

router = Router()

# Global dictionary to store pending trade offers
# Format: { proposer_uid: { 'target_uid': target_uid, 'proposer_pet_id': proposed_pet_id,
#                           'proposer_pet_name': pet_name, 'proposer_pet_rarity': rarity_string } }
pending_trades = {}

# Define rarity order for R2R system based on provided RARITY_CHANCES
# This ensures consistency with your game's rarity hierarchy.
RARITY_ORDER = [r[0] for r in [
    ("Обычная", 40),
    ("Необычная", 20),
    ("Редкая", 12),
    ("Очень Редкая", 8),
    ("Эпическая", 6),
    ("Легендарная", 4),
    ("Мифическая", 3),
    ("Древняя", 3),
    ("Божественная", 2),
    ("Абсолютная", 2),
]]

# Helper function to check if a pet is in a user's active arena team
async def is_pet_in_arena_team(user_id: int, pet_id: int) -> bool:
    arena_team_data = await fetch_one("SELECT pet_ids FROM arena_team WHERE user_id = $1", {"user_id": user_id})
    if arena_team_data and arena_team_data["pet_ids"]:
        active_pet_ids = json.loads(arena_team_data["pet_ids"])
        return pet_id in active_pet_ids
    return False

@router.message(Command("trade"))
async def trade_cmd(message: Message):
    """
    Handles the /trade command for Rarity to Rarity (R2R) pet exchanges.
    Allows users to propose, accept, and decline trades.
    """
    uid = message.from_user.id
    args = message.text.strip().split()

    if len(args) < 2:
        await message.answer(
            "🤝 <b>Система обмена R2R</b>\n\n"
            "Чтобы предложить обмен: <code>/trade &lt;ID твоего питомца&gt; &lt;ID пользователя&gt;</code>\n"
            "Чтобы принять обмен: <code>/trade accept &lt;ID предложившего&gt; &lt;ID твоего питомца&gt;</code>\n"
            "Чтобы отклонить обмен: <code>/trade decline &lt;ID предложившего&gt;</code>",
            parse_mode="HTML"
        )
        return

    command = args[1].lower()

    if command == "accept":
        if len(args) != 4:
            await message.answer("Неверный формат команды. Используй: <code>/trade accept &lt;ID предложившего&gt; &lt;ID твоего питомца&gt;</code>", parse_mode="HTML")
            return
        
        try:
            proposer_uid = int(args[2])
            acceptor_pet_id = int(args[3])
        except ValueError:
            await message.answer("ID пользователя и питомца должны быть числами.", parse_mode="HTML")
            return

        # Check if there's a pending trade for this user from the proposer
        if proposer_uid not in pending_trades or pending_trades[proposer_uid]['target_uid'] != uid:
            await message.answer("Нет активного предложения обмена от этого пользователя.", parse_mode="HTML")
            return
        
        proposer_trade_info = pending_trades[proposer_uid]
        proposer_pet_id = proposer_trade_info['proposer_pet_id']
        proposer_pet_rarity = proposer_trade_info['proposer_pet_rarity']

        # Fetch acceptor's pet details
        acceptor_pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": acceptor_pet_id, "user_id": uid})
        if not acceptor_pet:
            await message.answer("У тебя нет питомца с таким ID.", parse_mode="HTML")
            return

        # Check if acceptor's pet is in arena team
        if await is_pet_in_arena_team(uid, acceptor_pet_id):
            await message.answer("Ты не можешь обменять питомца, который находится в твоей активной арена-команде.", parse_mode="HTML")
            return

        acceptor_pet_rarity = acceptor_pet['rarity']

        # R2R Logic: Only allow trading pets of the same rarity
        if proposer_pet_rarity != acceptor_pet_rarity:
            await message.answer(
                f"Обмен невозможен. Питомцы должны быть <b>одной редкости</b>.\n"
                f"Твой питомец: <b>{acceptor_pet['name']}</b> ({acceptor_pet_rarity})\n"
                f"Питомец оппонента: <b>{proposer_trade_info['proposer_pet_name']}</b> ({proposer_pet_rarity})",
                parse_mode="HTML"
            )
            return

        # Perform the trade
        # Update user_id for proposer's pet to acceptor's UID
        await execute_query("UPDATE pets SET user_id = $1 WHERE id = $2", {"user_id": uid, "id": proposer_pet_id})
        # Update user_id for acceptor's pet to proposer's UID
        await execute_query("UPDATE pets SET user_id = $1 WHERE id = $2", {"user_id": proposer_uid, "id": acceptor_pet_id})

        # Clean up pending trade
        del pending_trades[proposer_uid]

        # Notify both users
        proposer_chat = await message.bot.get_chat(proposer_uid)
        proposer_name = proposer_chat.first_name if proposer_chat.first_name else proposer_chat.full_name

        acceptor_chat = await message.bot.get_chat(uid)
        acceptor_name = acceptor_chat.first_name if acceptor_chat.first_name else acceptor_chat.full_name

        await message.answer(
            f"✅ Обмен успешно завершен!\n"
            f"Ты получил <b>{proposer_trade_info['proposer_pet_name']}</b> ({proposer_pet_rarity}) от <b>{proposer_name}</b>.",
            parse_mode="HTML"
        )
        try:
            await message.bot.send_message(
                proposer_uid,
                f"✅ Обмен успешно завершен!\n"
                f"Ты получил <b>{acceptor_pet['name']}</b> ({acceptor_pet_rarity}) от <b>{acceptor_name}</b>.",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            # User might have blocked the bot or not started a chat
            pass 

    elif command == "decline":
        if len(args) != 3:
            await message.answer("Неверный формат команды. Используй: <code>/trade decline &lt;ID предложившего&gt;</code>", parse_mode="HTML")
            return
        
        try:
            proposer_uid = int(args[2])
        except ValueError:
            await message.answer("ID предложившего должен быть числом.", parse_mode="HTML")
            return

        if proposer_uid not in pending_trades or pending_trades[proposer_uid]['target_uid'] != uid:
            await message.answer("Нет активного предложения обмена от этого пользователя.", parse_mode="HTML")
            return
        
        proposer_trade_info = pending_trades[proposer_uid]
        proposer_pet_name = proposer_trade_info['proposer_pet_name']
        proposer_pet_rarity = proposer_trade_info['proposer_pet_rarity']

        # Remove the pending trade
        del pending_trades[proposer_uid]

        proposer_chat = await message.bot.get_chat(proposer_uid)
        proposer_name = proposer_chat.first_name if proposer_chat.first_name else proposer_chat.full_name

        acceptor_chat = await message.bot.get_chat(uid)
        acceptor_name = acceptor_chat.first_name if acceptor_chat.first_name else acceptor_chat.full_name

        await message.answer(f"❌ Ты отклонил предложение обмена от <b>{proposer_name}</b>.", parse_mode="HTML")
        try:
            await message.bot.send_message(
                proposer_uid,
                f"❌ <b>{acceptor_name}</b> отклонил твое предложение обменять <b>{proposer_pet_name}</b> ({proposer_pet_rarity}).",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass # User might have blocked the bot

    else: # This is the initial trade offer (e.g., /trade <pet_id> <user_id>)
        try:
            my_pet_id = int(args[1])
            target_uid = int(args[2]) # Assuming target is always by ID for now
        except (ValueError, IndexError):
            await message.answer(
                "Неверный формат команды. Используй: <code>/trade &lt;ID твоего питомца&gt; &lt;ID пользователя&gt;</code>", 
                parse_mode="HTML"
            )
            return
        
        if uid == target_uid:
            await message.answer("Ты не можешь обменяться сам с собой!", parse_mode="HTML")
            return

        my_pet = await fetch_one("SELECT * FROM pets WHERE id = $1 AND user_id = $2", {"id": my_pet_id, "user_id": uid})
        if not my_pet:
            await message.answer("У тебя нет питомца с таким ID.", parse_mode="HTML")
            return
        
        # Check if proposer's pet is in arena team
        if await is_pet_in_arena_team(uid, my_pet_id):
            await message.answer("Ты не можешь обменять питомца, который находится в твоей активной арена-команде.", parse_mode="HTML")
            return

        target_user_exists = await fetch_one("SELECT user_id FROM users WHERE user_id = $1", {"uid": target_uid})
        if not target_user_exists:
            await message.answer("Пользователь с таким ID не найден.", parse_mode="HTML")
            return

        # Store the pending trade
        pending_trades[uid] = {
            'target_uid': target_uid,
            'proposer_pet_id': my_pet_id,
            'proposer_pet_name': my_pet['name'],
            'proposer_pet_rarity': my_pet['rarity']
        }

        # Notify proposer
        try:
            target_chat = await message.bot.get_chat(target_uid)
            target_name = target_chat.first_name if target_chat.first_name else target_chat.full_name
        except Exception:
            target_name = f"Пользователю с ID {target_uid}"
        
        await message.answer(
            f"✅ Ты предложил обменять <b>{my_pet['name']}</b> ({my_pet['rarity']}) "
            f"{target_name}.\n"
            f"Ожидай его ответа.",
            parse_mode="HTML"
        )

        # Notify target
        proposer_chat = await message.bot.get_chat(uid)
        proposer_name = proposer_chat.first_name if proposer_chat.first_name else proposer_chat.full_name

        try:
            await message.bot.send_message(
                target_uid,
                f"🤝 <b>{proposer_name}</b> предлагает тебе обменять своего питомца "
                f"<b>{my_pet['name']}</b> ({my_pet['rarity']}).\n\n"
                f"Чтобы принять, используй: <code>/trade accept {uid} &lt;ID твоего питомца&gt;</code>\n"
                f"Чтобы отклонить, используй: <code>/trade decline {uid}</code>",
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            await message.answer(
                f"Не удалось уведомить пользователя <b>{target_name}</b> (ID: {target_uid}). "
                f"Возможно, он заблокировал бота или не начинал диалог с ним.",
                parse_mode="HTML"
            )