import asyncio
import logging
import os
from typing import Tuple, List

import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация БД
DB_CONFIG = {
    "database": os.getenv("DB_NAME", "asterisk_db"),
    "user": os.getenv("DB_USER", "asterisk_user"),
    "password": os.getenv("DB_PASSWORD", "qwerty"),
    "host": os.getenv("DB_HOST", "postgres"),  # В Docker используем имя сервиса
    "port": int(os.getenv("DB_PORT", 5432)),
    "timeout": int(os.getenv("DB_TIMEOUT", 5)),
    "command_timeout": 60,
    "max_size": 10,
    "min_size": 2
}

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Пул подключений к БД
db_pool = None

async def init_db_pool():
    """Инициализация пула подключений к БД"""
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(**DB_CONFIG)
        logger.info("Successfully connected to database")
    except Exception as e:
        logger.error(f"Failed to connect to database: {e}")
        raise

async def get_problems() -> List[Tuple[str, str]]:
    """Получение проблем из БД"""
    async with db_pool.acquire() as conn:
        query = """
            SELECT caller_number, response_used 
            FROM inn_verification_log 
            WHERE response_used IS NOT NULL 
            AND response_used != ''
            ORDER BY id DESC
        """
        rows = await conn.fetch(query)
        return [(row['caller_number'], row['response_used']) for row in rows]

def format_problem_message(problems: List[Tuple[str, str]]) -> str:
    """Форматирование сообщения с проблемами"""
    if not problems:
        return "📭 Проблемы не найдены"
    
    message = "📋 Список проблем:\n\n"
    for i, (phone, problem) in enumerate(problems, 1):
        message += f"{i}. 📞 {phone}\n   💬 {problem}\n\n"
    
    return message

@dp.message(Command("start"))
async def cmd_start(message: Message):
    """Обработчик команды /start"""
    await message.answer(
        "👋 Привет! Я бот для просмотра проблем.\n"
        "Используй команду /all_problems чтобы получить список всех проблем."
    )

@dp.message(Command("all_problems"))
async def cmd_all_problems(message: Message):
    """Обработчик команды /all_problems"""
    try:
        # Отправляем уведомление о начале загрузки
        await message.answer("🔍 Загружаю проблемы...")
        
        # Получаем проблемы из БД
        problems = await get_problems()
        
        # Форматируем и отправляем сообщение
        response = format_problem_message(problems)
        
        # Разбиваем длинное сообщение на части (Telegram лимит - 4096 символов)
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await message.answer(response[i:i+4096])
        else:
            await message.answer(response)
            
        logger.info(f"Sent {len(problems)} problems to user {message.from_user.id}")
        
    except Exception as e:
        logger.error(f"Error in all_problems command: {e}")
        await message.answer("❌ Произошла ошибка при получении проблем")

async def main():
    """Главная функция"""
    # Инициализация пула БД
    await init_db_pool()
    
    # Запуск бота
    try:
        await dp.start_polling(bot)
    finally:
        # Закрытие пула при остановке
        if db_pool:
            await db_pool.close()

if __name__ == "__main__":
    asyncio.run(main())
