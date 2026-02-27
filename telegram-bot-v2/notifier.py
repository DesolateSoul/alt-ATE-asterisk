#!/usr/bin/env python3
"""
Сервис для мониторинга новых записей в verification_logs
и отправки уведомлений в привязанные Telegram группы
Поддерживает множество клиентов в одной группе и отправку аудиофайлов
Версия: конвертация WAV в OGG через внешний скрипт на хосте
"""

import asyncio
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List, Optional, Any

import asyncpg
from aiogram import Bot
from aiogram.types import FSInputFile
from aiogram.client.session.aiohttp import AiohttpSession
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

# Токен бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    logger.error("BOT_TOKEN не установлен!")
    sys.exit(1)

# Интервал проверки
CHECK_INTERVAL = int(os.getenv("NOTIFIER_INTERVAL", "5"))

# Путь к скрипту конвертации на хосте
CONVERT_SCRIPT = os.getenv("CONVERT_SCRIPT", "/usr/local/bin/convert_audio.sh")

# Временная директория для сконвертированных файлов
TEMP_DIR = os.getenv("TEMP_DIR", "/tmp/telegram_bot_audio")
os.makedirs(TEMP_DIR, exist_ok=True)


class ProblemNotifier:
    """Класс для мониторинга и отправки уведомлений о проблемах"""

    def __init__(self):
        logger.info("🚀 Инициализация Notifier...")

        # Создаем сессию с увеличенными таймаутами
        session = AiohttpSession(timeout=120)

        # Инициализируем бота с нашей сессией
        self.bot = Bot(token=BOT_TOKEN, session=session)
        self.db_pool = None
        self.last_check_id = 0
        self.running = True
        self.bindings_cache = {}  # Кэш привязок для оптимизации

        # Проверяем доступность скрипта конвертации
        # self.convert_script_available = os.path.exists(CONVERT_SCRIPT)
        self.convert_script_available = False
        if self.convert_script_available:
            logger.info(f"✅ Скрипт конвертации найден: {CONVERT_SCRIPT}")
        else:
            logger.warning(f"⚠️ Скрипт конвертации не найден: {CONVERT_SCRIPT}")
            logger.warning("⚠️ Аудиофайлы будут отправляться в исходном формате WAV")

    async def init_db(self):
        """Инициализация подключения к БД"""
        try:
            self.db_pool = await asyncpg.create_pool(**DB_CONFIG)
            logger.info("✅ Подключение к БД установлено")

            async with self.db_pool.acquire() as conn:
                self.last_check_id = await conn.fetchval(
                    "SELECT COALESCE(MAX(id), 0) FROM verification_logs"
                )
                logger.info(f"🆔 Начальный ID для мониторинга: {self.last_check_id}")

                # Загружаем кэш привязок
                await self._refresh_bindings_cache(conn)

        except Exception as e:
            logger.error(f"❌ Ошибка подключения к БД: {e}")
            raise

    async def _refresh_bindings_cache(self, conn=None):
        """Обновление кэша привязок"""
        close_conn = False
        if not conn:
            conn = await self.db_pool.acquire()
            close_conn = True

        try:
            rows = await conn.fetch("""
                SELECT chat_id, client_id, client_inn, company_name
                FROM telegram_group_bindings 
                WHERE active = true
            """)

            self.bindings_cache = {}
            for row in rows:
                chat_id = row['chat_id']
                if chat_id not in self.bindings_cache:
                    self.bindings_cache[chat_id] = []

                self.bindings_cache[chat_id].append({
                    'client_id': row['client_id'],
                    'client_inn': row['client_inn'],
                    'company_name': row['company_name']
                })

            logger.info(f"📚 Кэш привязок обновлен: {len(self.bindings_cache)} чатов, "
                        f"{sum(len(v) for v in self.bindings_cache.values())} привязок")

        finally:
            if close_conn:
                await self.db_pool.release(conn)

    async def get_new_problems(self) -> List[Dict[str, Any]]:
        """Получает новые записи с проблемами, включая путь к аудио"""
        try:
            async with self.db_pool.acquire() as conn:
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
                        v.problem_audio_path,
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
                    self.last_check_id = max(p['id'] for p in new_problems)
                    logger.info(f"🔍 Найдено {len(new_problems)} новых проблем. "
                                f"Новый last_id: {self.last_check_id}")

                    # Логируем информацию об аудиофайлах
                    for p in new_problems:
                        if p.get('problem_audio_path'):
                            logger.info(f"🎵 Проблема {p['id']} имеет аудиофайл: {p['problem_audio_path']}")

                return new_problems

        except Exception as e:
            logger.error(f"Ошибка при получении проблем: {e}")
            return []

    async def get_chats_for_client(self, client_id: int, client_inn: int) -> List[int]:
        """
        Получает список всех чатов, привязанных к клиенту
        Использует кэш для оптимизации
        """
        chats = []
        for chat_id, clients in self.bindings_cache.items():
            for client in clients:
                if (client['client_id'] == client_id or
                        client['client_inn'] == client_inn):
                    chats.append(chat_id)
                    break

        return chats

    async def convert_audio_via_host(self, wav_path: str) -> Optional[str]:
        """
        Конвертирует WAV в OGG через скрипт на хост-сервере
        """

        if not self.convert_script_available:
            logger.warning("⚠️ Скрипт конвертации недоступен, отправляем WAV")
            return None
    
        if not wav_path or not os.path.exists(wav_path):
            logger.error(f"❌ Аудиофайл не найден: {wav_path}")
            return None
    
        try:
            # Создаем уникальное имя для выходного файла
            base_name = os.path.basename(wav_path)
            name_without_ext = os.path.splitext(base_name)[0]
            ogg_filename = f"{name_without_ext}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.ogg"
            ogg_path = os.path.join(TEMP_DIR, ogg_filename)
    
            logger.info(f"🔄 Запуск конвертации: {wav_path} -> {ogg_path}")
    
            # Вызываем скрипт конвертации на хосте
            cmd = [
                CONVERT_SCRIPT,
                wav_path,
                ogg_path
            ]
    
            # Запускаем процесс и ждем завершения
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
    
            stdout, stderr = await process.communicate()
    
            # Проверяем результат
            if process.returncode == 0 and os.path.exists(ogg_path):
                file_size = os.path.getsize(ogg_path)
                logger.info(f"✅ Конвертация успешна: {ogg_path} ({file_size} байт)")
                return ogg_path
            else:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                logger.error(f"❌ Ошибка конвертации (код {process.returncode}): {error_msg}")
    
                # Пробуем найти лог-файл скрипта
                try:
                    import glob
                    log_files = glob.glob("/tmp/convert_audio_*.log")
                    if log_files:
                        latest_log = max(log_files, key=os.path.getctime)
                        with open(latest_log, 'r') as f:
                            log_content = f.read()
                        logger.error(f"📋 Содержимое лога конвертации:\n{log_content}")
                except Exception as log_e:
                    logger.error(f"Не удалось прочитать лог: {log_e}")
    
                return None

        except Exception as e:
            logger.error(f"❌ Ошибка при конвертации аудио: {e}")
            return None

    async def format_problem_message(self, problem: Dict[str, Any]) -> str:
        """Форматирует сообщение о проблеме"""
        company = problem.get('company_name') or 'Неизвестная компания'

        message = f"🚨 **НОВАЯ ПРОБЛЕМА!**\n\n"
        message += f"🏢 **Компания:** {company}\n"

        if problem.get('client_inn'):
            message += f"🔢 **ИНН:** {problem['client_inn']}\n"
        elif problem.get('spoken_inn'):
            message += f"🔢 **Указанный ИНН:** {problem['spoken_inn']}\n"

        message += f"📞 **Номер caller:** {problem.get('caller_number') or 'Неизвестно'}\n"
        message += f"💬 **Проблема:**\n{problem.get('problem_text', '')}\n\n"

        # Добавляем информацию об аудио
        if problem.get('problem_audio_path'):
            message += f"🎵 **Аудиозапись разговора (в формате OGG)**\n\n"

        created_at = problem.get('created_at')
        if created_at:
            if isinstance(created_at, datetime):
                time_str = created_at.strftime('%d.%m.%Y %H:%M:%S')
            else:
                time_str = str(created_at)
        else:
            time_str = 'неизвестно'

        message += f"⏰ **Время:** {time_str}\n"
        message += f"🆔 **ID звонка:** {problem.get('call_uniqueid', 'неизвестно')}"

        return message

    async def send_notification_with_audio(self, chat_id: int, message_text: str,
                                           audio_path: Optional[str] = None, retry_count: int = 0) -> bool:
        """
        Отправляет уведомление с возможным аудиофайлом и повторными попытками

        Args:
            chat_id: ID чата
            message_text: Текст сообщения
            audio_path: Путь к аудиофайлу (опционально)
            retry_count: Номер попытки

        Returns:
            True если отправка успешна, False в противном случае
        """
        max_retries = 3
        converted_file = None

        try:
            if audio_path and os.path.exists(audio_path):
                # Пробуем сконвертировать аудио
                if self.convert_script_available:
                    converted_file = await self.convert_audio_via_host(audio_path)

                if converted_file and os.path.exists(converted_file):
                    # Отправляем сконвертированный OGG файл
                    logger.info(f"📤 Отправка OGG файла: {converted_file} (попытка {retry_count + 1}/{max_retries})")
                    audio_file = FSInputFile(converted_file)

                    await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        caption=message_text,
                        parse_mode="Markdown",
                        title=f"Проблема от {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                        performer="Asterisk VOSK",
                        request_timeout=120
                    )
                    logger.info(f"✅ OGG аудио отправлено в чат {chat_id}")

                else:
                    # Отправляем оригинальный WAV файл
                    logger.info(f"📤 Отправка WAV файла: {audio_path} (попытка {retry_count + 1}/{max_retries})")
                    audio_file = FSInputFile(audio_path)

                    await self.bot.send_audio(
                        chat_id=chat_id,
                        audio=audio_file,
                        caption=message_text,
                        parse_mode="Markdown",
                        title=f"Проблема от {datetime.now().strftime('%d.%m.%Y %H:%M')} (WAV)",
                        performer="Asterisk VOSK",
                        request_timeout=120
                    )
                    logger.info(f"✅ WAV аудио отправлено в чат {chat_id}")

                # Удаляем временный сконвертированный файл
                if converted_file and os.path.exists(converted_file):
                    try:
                        os.remove(converted_file)
                        logger.debug(f"🗑️ Временный файл удален: {converted_file}")
                    except Exception as e:
                        logger.warning(f"⚠️ Не удалось удалить временный файл: {e}")

                return True

            else:
                # Отправляем только текст
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message_text,
                    parse_mode="Markdown",
                    request_timeout=60
                )
                logger.info(f"✅ Текстовое уведомление отправлено в чат {chat_id}")
                return True

        except Exception as e:
            logger.error(f"❌ Ошибка отправки в чат {chat_id}: {e}")

            # Повторяем попытку если не превысили лимит
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # Экспоненциальная задержка: 1, 2, 4 секунды
                logger.info(f"⏳ Повторная попытка через {wait_time} сек (попытка {retry_count + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
                return await self.send_notification_with_audio(chat_id, message_text, audio_path, retry_count + 1)
            else:
                logger.error(f"❌ Все попытки отправки в чат {chat_id} исчерпаны")
                return False

    async def send_notifications(self, problem: Dict[str, Any]):
        """Отправляет уведомление о проблеме во все привязанные чаты"""
        client_id = problem.get('matched_client_id')
        client_inn = problem.get('client_inn') or problem.get('spoken_inn')

        if not client_id and not client_inn:
            logger.debug(f"Проблема {problem['id']} не привязана к клиенту")
            return

        # Получаем все чаты для этого клиента
        chat_ids = await self.get_chats_for_client(client_id, client_inn)

        if not chat_ids:
            logger.debug(f"Нет привязанных чатов для клиента {client_id or client_inn}")
            return

        # Форматируем сообщение
        message_text = await self.format_problem_message(problem)

        # Получаем путь к аудио, если есть
        audio_path = problem.get('problem_audio_path')
        if audio_path and not os.path.exists(audio_path):
            logger.warning(f"⚠️ Аудиофайл не найден по пути: {audio_path}")
            audio_path = None
        elif audio_path:
            file_size = os.path.getsize(audio_path)
            logger.info(f"🎵 Найден аудиофайл: {audio_path} (размер: {file_size} байт)")

        # Отправляем во все чаты
        sent_count = 0
        failed_chats = []

        for chat_id in chat_ids:
            success = await self.send_notification_with_audio(chat_id, message_text, audio_path)

            if success:
                sent_count += 1
                # Пауза между отправками в разные чаты
                await asyncio.sleep(1)
            else:
                failed_chats.append(chat_id)

        logger.info(f"📨 Отправлено {sent_count} уведомлений для проблемы {problem['id']}")

        if failed_chats:
            logger.warning(f"Не удалось отправить в чаты: {failed_chats}")

    async def _deactivate_chat_bindings(self, chat_id: int):
        """Деактивирует все привязки для чата"""
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute("""
                    UPDATE telegram_group_bindings 
                    SET active = false 
                    WHERE chat_id = $1 AND active = true
                """, chat_id)

            # Обновляем кэш
            if chat_id in self.bindings_cache:
                del self.bindings_cache[chat_id]

            logger.info(f"⚠️ Деактивированы привязки для чата {chat_id}")

        except Exception as e:
            logger.error(f"Ошибка при деактивации чата {chat_id}: {e}")

    async def run(self):
        """Основной цикл мониторинга"""
        logger.info(f"🔄 Notifier запущен. Интервал проверки: {CHECK_INTERVAL} сек")

        if self.convert_script_available:
            logger.info("✅ Режим: конвертация WAV -> OGG через внешний скрипт")
        else:
            logger.info("⚠️ Режим: отправка WAV файлов без конвертации")

        refresh_counter = 0
        while self.running:
            try:
                # Получаем новые проблемы
                new_problems = await self.get_new_problems()

                # Отправляем уведомления
                for problem in new_problems:
                    await self.send_notifications(problem)

                # Периодически обновляем кэш привязок (каждые 60 циклов)
                refresh_counter += 1
                if refresh_counter >= 60:
                    await self._refresh_bindings_cache()
                    refresh_counter = 0

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

        # Очистка временной директории
        try:
            import shutil
            shutil.rmtree(TEMP_DIR, ignore_errors=True)
            logger.info(f"🗑️ Временная директория очищена: {TEMP_DIR}")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось очистить временную директорию: {e}")

        logger.info("Notifier остановлен")


async def main():
    """Главная функция"""
    logger.info("=" * 60)
    logger.info("ЗАПУСК NOTIFIER (КОНВЕРТАЦИЯ ЧЕРЕЗ ВНЕШНИЙ СКРИПТ)")
    logger.info("=" * 60)

    notifier = ProblemNotifier()

    try:
        await notifier.init_db()
        await notifier.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
    finally:
        await notifier.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
