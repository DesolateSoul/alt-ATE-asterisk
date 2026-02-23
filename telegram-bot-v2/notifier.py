#!/usr/bin/env python3
"""
Сервис для мониторинга новых записей в verification_logs
и отправки уведомлений в привязанные Telegram группы
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import asyncpg
from aiogram import Bot
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO")),
    format='%(asctime)s - NOTIFIER - %(levelname)s - %(message)s'
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
    "max_size": 10,
    "min_size": 2
}

# Токен бота (тот же, что и у основного бота)
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не установлен в переменных окружения")

# Интервал проверки новых записей (в секундах)
CHECK_INTERVAL = int(os.getenv("NOTIFIER_INTERVAL", "5"))

# Сколько времени считать запись "новой" (в секундах)
NEW_RECORD_THRESHOLD = int(os.getenv("NEW_RECORD_THRESHOLD", "30"))

class ProblemNotifier:
    """Класс для мониторинга и отправки уведомлений о проблемах"""
    
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.db_pool = None
        self.last_check_id = 0
        self.running = True
        
    async def init_db(self):
        """Инициализация подключения к БД"""
        try:
            self.db_pool = await asyncpg.create_pool(**DB_CONFIG)
            logger.info("✅ Подключение к БД установлено")
            
            # Получаем последний ID для старта
            async with self.db_pool.acquire() as conn:
                self.last_check_id = await conn.fetchval(
                    "SELECT COALESCE(MAX(id), 0) FROM verification_logs"
                )
                logger.info(f"🆔 Начальный ID для мониторинга: {self.last_check_id}")
                
        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise
    
    async def get_new_problems(self) -> List[Dict[str, Any]]:
        """
        Получает новые записи с проблемами из verification_logs
        """
        async with self.db_pool.acquire() as conn:
            # Получаем записи с ID больше последнего проверенного
            # И которые содержат текст проблемы
            rows = await conn.fetch("""
                SELECT 
                    v.id,
                    v.call_uniqueid,
                    v.caller_number,
                    v.spoken_inn,
                    v.matched_client_id,
                    v.problem_text,
                    v.problem_recognized_at,
                    v.created_at,
                    v.success,
                    c.id as client_db_id,
                    c.inn as client_inn,
                    c.company_name,
                    c.code_word,
                    c.phone_number
                FROM verification_logs v
                LEFT JOIN clients c ON v.matched_client_id = c.id
                WHERE v.id > $1
                  AND v.problem_text IS NOT NULL 
                  AND v.problem_text != ''
                ORDER BY v.id ASC
            """, self.last_check_id)
            
            new_problems = [dict(row) for row in rows]
            
            if new_problems:
                # Обновляем последний проверенный ID
                self.last_check_id = max(p['id'] for p in new_problems)
                logger.info(f"🔍 Найдено {len(new_problems)} новых проблем. Новый last_id: {self.last_check_id}")
            
            return new_problems
    
    async def get_chats_for_client(self, client_id: int, client_inn: int) -> List[int]:
        """
        Получает список чатов, привязанных к клиенту
        """
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT chat_id FROM telegram_group_bindings 
                WHERE (client_id = $1 OR client_inn = $2) AND active = true
            """, client_id, client_inn)
            return [row['chat_id'] for row in rows]
    
    async def format_problem_message(self, problem: Dict[str, Any]) -> str:
        """
        Форматирует сообщение о проблеме для отправки
        """
        # Определяем компанию
        company = problem.get('company_name') or 'Неизвестная компания'
        
        # Формируем сообщение
        message = f"🚨 **НОВАЯ ПРОБЛЕМА!**\n\n"
        message += f"🏢 **Компания:** {company}\n"
        
        if problem.get('client_inn'):
            message += f"🔢 **ИНН:** {problem['client_inn']}\n"
        elif problem.get('spoken_inn'):
            message += f"🔢 **Указанный ИНН:** {problem['spoken_inn']}\n"
        
        message += f"📞 **Номер caller:** {problem['caller_number'] or 'Неизвестно'}\n"
        message += f"💬 **Проблема:**\n{problem['problem_text']}\n\n"
        
        # Добавляем время
        created_at = problem['created_at']
        if isinstance(created_at, datetime):
            time_str = created_at.strftime('%d.%m.%Y %H:%M:%S')
        else:
            time_str = str(created_at)
        
        message += f"⏰ **Время:** {time_str}\n"
        message += f"🆔 **ID звонка:** {problem['call_uniqueid']}"
        
        return message
    
    async def send_notifications(self, problem: Dict[str, Any]):
        """
        Отправляет уведомление о проблеме во все привязанные чаты
        """
        # Получаем список чатов для этого клиента
        client_id = problem.get('matched_client_id')
        client_inn = problem.get('client_inn') or problem.get('spoken_inn')
        
        if not client_id and not client_inn:
            logger.warning(f"Проблема {problem['id']} не привязана к клиенту, пропускаем")
            return
        
        chat_ids = await self.get_chats_for_client(client_id, client_inn)
        
        if not chat_ids:
            logger.info(f"Нет привязанных чатов для клиента {client_id or client_inn}")
            return
        
        # Форматируем сообщение
        message_text = await self.format_problem_message(problem)
        
        # Отправляем во все чаты
        sent_count = 0
        for chat_id in chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown"
                )
                sent_count += 1
                logger.info(f"✅ Уведомление отправлено в чат {chat_id}")
            except Exception as e:
                logger.error(f"❌ Ошибка отправки в чат {chat_id}: {e}")
                
                # Если бот удален из чата или чат не найден, деактивируем привязку
                if "chat not found" in str(e).lower() or "bot was kicked" in str(e).lower():
                    async with self.db_pool.acquire() as conn:
                        await conn.execute("""
                            UPDATE telegram_group_bindings 
                            SET active = false 
                            WHERE chat_id = $1
                        """, chat_id)
                        logger.info(f"⚠️ Привязка для чата {chat_id} деактивирована")
        
        logger.info(f"📨 Отправлено {sent_count} уведомлений для проблемы {problem['id']}")
    
    async def run(self):
        """Основной цикл мониторинга"""
        logger.info("🚀 Notifier запущен. Интервал проверки: %d сек", CHECK_INTERVAL)
        
        while self.running:
            try:
                # Получаем новые проблемы
                new_problems = await self.get_new_problems()
                
                # Отправляем уведомления по каждой
                for problem in new_problems:
                    await self.send_notifications(problem)
                
                # Ждем перед следующей проверкой
                await asyncio.sleep(CHECK_INTERVAL)
                
            except asyncio.CancelledError:
                logger.info("Получен сигнал остановки")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                await asyncio.sleep(CHECK_INTERVAL)
    
    async def shutdown(self):
        """Корректное завершение работы"""
        logger.info("Завершение работы notifier...")
        self.running = False
        if self.db_pool:
            await self.db_pool.close()
        if self.bot:
            await self.bot.session.close()
        logger.info("Notifier остановлен")

async def main():
    """Главная функция"""
    notifier = ProblemNotifier()
    
    try:
        await notifier.init_db()
        await notifier.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки")
    finally:
        await notifier.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
