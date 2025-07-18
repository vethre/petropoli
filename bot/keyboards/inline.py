from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

profile_back_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🔙 Назад", callback_data="profile_back")]
])