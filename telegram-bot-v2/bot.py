import asyncio
import logging
import os
from typing import Tuple, List, Optional, Dict
from datetime import datetime

import asyncpg
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import Message
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация БД
DB_CONFIG = {
    "database": os.getenv("DB_NAME", "asterisk_db"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "timeout": int(os.getenv("DB_TIMEOUT", 5)),
    "command_timeout": 60,
    "max_size": 20,
    "min_size": 5
}

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# ID администраторов
ADMIN_IDS = [int(id.strip()) for id in os.getenv("ADMIN_IDS", "").split(",") if id.strip()]

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
        logger.info("✅ Подключение к БД установлено")
        
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS telegram_group_bindings (
                    id BIGSERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    chat_title VARCHAR(255),
                    client_id BIGINT NOT NULL,
                    client_inn BIGINT NOT NULL,
                    company_name VARCHAR(255),
                    bound_by BIGINT,
                    bound_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT true,
                    UNIQUE(chat_id, client_id)
                )
            """)
            
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bindings_chat ON telegram_group_bindings(chat_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bindings_client ON telegram_group_bindings(client_id)")
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_bindings_inn ON telegram_group_bindings(client_inn)")
            
            logger.info("✅ Таблица telegram_group_bindings проверена")
            
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к БД: {e}")
        raise

# Функции для работы с привязками
async def bind_group_to_client(chat_id: int, chat_title: str, inn: int, bound_by: int) -> Tuple[bool, str]:
    async with db_pool.acquire() as conn:
        client = await conn.fetchrow("""
            SELECT id, inn, company_name 
            FROM clients 
            WHERE inn = $1 AND active = true
        """, inn)
        
        if not client:
            return False, f"❌ Клиент с ИНН {inn} не найден или не активен"
        
        existing = await conn.fetchrow("""
            SELECT id FROM telegram_group_bindings 
            WHERE chat_id = $1 AND client_id = $2 AND active = true
        """, chat_id, client['id'])
        
        if existing:
            return False, f"⚠️ Эта группа уже привязана к клиенту {client['company_name']}"
        
        await conn.execute("""
            UPDATE telegram_group_bindings 
            SET active = false 
            WHERE chat_id = $1
        """, chat_id)
        
        await conn.execute("""
            INSERT INTO telegram_group_bindings 
                (chat_id, chat_title, client_id, client_inn, company_name, bound_by)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, chat_id, chat_title, client['id'], inn, client['company_name'], bound_by)
        
        return True, f"✅ Группа привязана к клиенту {client['company_name']}"

async def get_group_bindings(chat_id: int) -> List[Dict]:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM telegram_group_bindings 
            WHERE chat_id = $1 AND active = true
        """, chat_id)
        return [dict(row) for row in rows]

async def unbind_group(chat_id: int) -> Tuple[bool, str]:
    async with db_pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE telegram_group_bindings 
            SET active = false 
            WHERE chat_id = $1
        """, chat_id)
        
        if result.split()[1] == '0':
            return False, "❌ У этой группы не было активных привязок"
        
        return True, "✅ Привязки группы удалены"

# Команды бота
@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "👋 **Привет! Я бот для мониторинга проблем.**\n\n"
        "📌 **Команды:**\n"
        "/problems - список проблем\n"
        "/set <ИНН> - привязать группу\n"
        "/unset - отвязать группу\n"
        "/mybindings - привязки\n"
        "/check - проверка БД\n"
        "/help - помощь",
        parse_mode="Markdown"
    )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    help_text = (
        "📚 **Справка:**\n\n"
        "/problems - последние 50 проблем\n"
        "/set <ИНН> - привязать группу к клиенту\n"
        "/unset - отвязать группу\n"
        "/mybindings - показать привязки\n"
        "/check - диагностика"
    )
    await message.answer(help_text, parse_mode="Markdown")

@dp.message(Command("set"))
async def cmd_set_binding(message: Message):
    logger.info(f"Команда /set в чате {message.chat.id}")
    
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах")
        return
    
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите ИНН. Пример: `/set 4205128383`", parse_mode="Markdown")
        return
    
    try:
        inn = int(args[1].strip())
    except ValueError:
        await message.answer("❌ ИНН должен быть числом")
        return
    
    success, result = await bind_group_to_client(
        message.chat.id,
        message.chat.title or "Без названия",
        inn,
        message.from_user.id
    )
    
    await message.answer(result)

@dp.message(Command("unset"))
async def cmd_unset_binding(message: Message):
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах")
        return
    
    success, result = await unbind_group(message.chat.id)
    await message.answer(result)

@dp.message(Command("mybindings"))
async def cmd_my_bindings(message: Message):
    if message.chat.type not in ['group', 'supergroup']:
        await message.answer("❌ Команда работает только в группах")
        return
    
    bindings = await get_group_bindings(message.chat.id)
    
    if not bindings:
        await message.answer("📭 Нет активных привязок")
        return
    
    response = "📋 **Привязки:**\n\n"
    for b in bindings:
        response += f"🏢 {b['company_name']}\n"
        response += f"🔢 ИНН: {b['client_inn']}\n"
        response += "─" * 20 + "\n"
    
    await message.answer(response, parse_mode="Markdown")

@dp.message(Command("problems"))
async def cmd_problems(message: Message):
    try:
        await message.answer("🔍 Загружаю проблемы...")
        
        async with db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT caller_number, problem_text 
                FROM verification_logs 
                WHERE problem_text IS NOT NULL AND problem_text != ''
                ORDER BY created_at DESC
                LIMIT 50
            """)
        
        if not rows:
            await message.answer("📭 Проблем не найдено")
            return
        
        response = "📋 **Последние проблемы:**\n\n"
        for i, row in enumerate(rows, 1):
            problem = row['problem_text']
            if len(problem) > 100:
                problem = problem[:97] + "..."
            response += f"{i}. 📞 {row['caller_number'] or 'Неизвестно'}\n"
            response += f"   💬 {problem}\n\n"
        
        if len(response) > 4096:
            for i in range(0, len(response), 4096):
                await message.answer(response[i:i+4096], parse_mode="Markdown")
        else:
            await message.answer(response, parse_mode="Markdown")
            
    except Exception as e:
        logger.error(f"Ошибка в problems: {e}")
        await message.answer("❌ Ошибка")

@dp.message(Command("check"))
async def cmd_check(message: Message):
    try:
        async with db_pool.acquire() as conn:
            tables = await conn.fetch("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
            clients = await conn.fetchval("SELECT COUNT(*) FROM clients")
            logs = await conn.fetchval("SELECT COUNT(*) FROM verification_logs")
            bindings = await conn.fetchval("SELECT COUNT(*) FROM telegram_group_bindings WHERE active=true")
            
            response = "✅ **БД работает**\n\n"
            response += f"📊 Таблицы: {len(tables)}\n"
            response += f"👥 Клиенты: {clients}\n"
            response += f"📝 Логи: {logs}\n"
            response += f"🔗 Привязки: {bindings}"
            
            await message.answer(response, parse_mode="Markdown")
            
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")

async def main():
    global db_pool
    await init_db_pool()
    
    try:
        logger.info("🚀 Бот запущен")
        await dp.start_polling(bot)
    finally:
        if db_pool:
            await db_pool.close()
            logger.info("Пул подключений закрыт")

if __name__ == "__main__":
    asyncio.run(main())
