import asyncio
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from config import BOT_TOKEN, DB_URL
from db.db import init_db
from bot.handlers import start, eggs, pets, economy, dev, merge, arena, trade, sell, explore, dungeon, bonus

async def main():
    await init_db()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_routers(
        start.router,
        eggs.router,
        pets.router,
        economy.router,
        dev.router,
        merge.router,
        arena.router,
        trade.router,
        sell.router,
        explore.router,
        dungeon.router,
        bonus.router
    )

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())