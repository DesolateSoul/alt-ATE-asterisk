#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для сохранения описания проблемы клиента
Сохраняет распознанный текст в поле problem_text таблицы verification_logs
Работает с таблицей verification_logs
"""

import sys
import re
import os
import traceback
from typing import Optional, Tuple, Dict, Any
from datetime import datetime

import psycopg2
from psycopg2 import sql
from basicagi import BasicAGI


class ProblemSaver:
    """Класс для сохранения описания проблемы"""

    # Конфигурация базы данных (обновлено для новых таблиц)
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "postgres",  # Изменено с asterisk_user на postgres
        "password": "qwerty",  # !!! ИЗМЕНИТЕ НА РЕАЛЬНЫЙ ПАРОЛЬ !!!
        "host": "localhost",
        "port": 5432,
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "application_name": "problem_saver_agi"
    }

    # Статусы выполнения
    STATUS_SUCCESS = "SAVED"
    STATUS_NO_INN = "NO_INN"
    STATUS_NO_TEXT = "NO_TEXT"
    STATUS_NO_UNIQUEID = "NO_UNIQUEID"
    STATUS_ERROR = "ERROR"
    STATUS_NOT_FOUND = "NOT_FOUND"

    def __init__(self):
        """Инициализация AGI и подключения к БД"""
        self.agi = BasicAGI()
        self.conn = None
        self.cursor = None

    def connect_to_db(self) -> bool:
        """
        Устанавливает соединение с базой данных

        Returns:
            True если соединение успешно, иначе False
        """
        try:
            self.conn = psycopg2.connect(**self.DB_CONFIG)
            self.cursor = self.conn.cursor()
            self.agi.verbose("✓ Подключение к БД установлено", 3)
            return True
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка подключения к БД: {e}", 1)
            return False

    def get_agi_variables(self) -> Tuple[str, str, str, str, str]:
        """
        Получает необходимые переменные из AGI

        Returns:
            Кортеж (problem_text, uniqueid, inn_str, caller_number, client_id)
        """
        problem_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        inn_str = self.agi.get_variable("VERIF_INN") or ""
        caller_number = self.agi.get_variable("CALLERID(num)") or ""
        client_id = self.agi.get_variable("VERIF_CLIENT_ID") or ""

        # Для отладки выводим все полученные переменные
        self.agi.verbose(f"Получены переменные:", 3)
        self.agi.verbose(f"  problem_text: '{problem_text}'", 3)
        self.agi.verbose(f"  uniqueid: '{uniqueid}'", 3)
        self.agi.verbose(f"  inn_str: '{inn_str}'", 3)
        self.agi.verbose(f"  caller_number: '{caller_number}'", 3)
        self.agi.verbose(f"  client_id: '{client_id}'", 3)

        return problem_text, uniqueid, inn_str, caller_number, client_id

    def find_verification_log(self, uniqueid: str, inn_value: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """
        Находит запись в таблице verification_logs

        Args:
            uniqueid: Уникальный ID вызова
            inn_value: ИНН (опционально)

        Returns:
            Словарь с данными записи или None
        """
        try:
            if inn_value:
                # Ищем по uniqueid и ИНН
                self.cursor.execute("""
                    SELECT id, call_uniqueid, caller_number, spoken_inn,
                           matched_client_id, success, problem_text, problem_recognized_at
                    FROM verification_logs
                    WHERE call_uniqueid = %s AND spoken_inn = %s
                    ORDER BY id DESC
                    LIMIT 1
                """, (uniqueid, inn_value))
            else:
                # Ищем только по uniqueid
                self.cursor.execute("""
                    SELECT id, call_uniqueid, caller_number, spoken_inn,
                           matched_client_id, success, problem_text, problem_recognized_at
                    FROM verification_logs
                    WHERE call_uniqueid = %s
                    ORDER BY id DESC
                    LIMIT 1
                """, (uniqueid,))

            row = self.cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'call_uniqueid': row[1],
                    'caller_number': row[2],
                    'spoken_inn': row[3],
                    'matched_client_id': row[4],
                    'success': row[5],
                    'problem_text': row[6],
                    'problem_recognized_at': row[7]
                }
            return None

        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при поиске записи: {e}", 2)
            return None

    def save_problem_description(self, problem_text: str, uniqueid: str,
                                inn_str: str, caller_number: str,
                                client_id: str) -> bool:
        """
        Сохраняет описание проблемы в таблицу verification_logs

        Args:
            problem_text: Распознанный текст проблемы
            uniqueid: Уникальный ID вызова
            inn_str: Строка с ИНН
            caller_number: Номер звонящего
            client_id: ID клиента (если есть)

        Returns:
            True если запись сохранена, иначе False
        """
        try:
            # Проверяем наличие обязательных данных
            if not uniqueid:
                self.agi.verbose("❌ Отсутствует uniqueid", 1)
                return False

            if not problem_text:
                self.agi.verbose("❌ Отсутствует текст проблемы", 1)
                return False

            # Преобразуем ИНН в число, если есть
            inn_value = None
            if inn_str:
                try:
                    inn_value = int(inn_str)
                except ValueError:
                    self.agi.verbose(f"⚠ Некорректный ИНН: {inn_str}, продолжаем без него", 1)

            # Преобразуем client_id в число, если есть
            client_id_value = None
            if client_id:
                try:
                    client_id_value = int(client_id)
                except ValueError:
                    self.agi.verbose(f"⚠ Некорректный client_id: {client_id}", 1)

            # Ищем существующую запись
            existing_log = self.find_verification_log(uniqueid, inn_value)

            if existing_log:
                # Обновляем существующую запись
                self.cursor.execute("""
                    UPDATE verification_logs
                    SET problem_text = %s,
                        problem_recognized_at = NOW(),
                        caller_number = COALESCE(caller_number, %s),
                        matched_client_id = COALESCE(matched_client_id, %s)
                    WHERE id = %s
                    RETURNING id
                """, (problem_text, caller_number, client_id_value, existing_log['id']))

                action = "обновлена"
                record_id = existing_log['id']
                self.agi.verbose(f"Найдена существующая запись ID: {record_id}", 2)

            else:
                # Создаем новую запись
                self.cursor.execute("""
                    INSERT INTO verification_logs
                        (call_uniqueid, caller_number, spoken_inn,
                         matched_client_id, problem_text, problem_recognized_at,
                         success, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), false, NOW())
                    RETURNING id
                """, (uniqueid, caller_number, inn_value, client_id_value, problem_text))

                action = "создана"
                record_id = self.cursor.fetchone()[0]

            if self.cursor.rowcount > 0:
                self.conn.commit()
                self.agi.verbose(f"✓ Запись {action} в verification_logs (ID: {record_id})", 1)

                # Дополнительная информация для отладки
                self.agi.verbose(f"  - Текст проблемы: '{problem_text[:50]}...'", 2)
                self.agi.verbose(f"  - Длина текста: {len(problem_text)} символов", 2)
                if inn_value:
                    self.agi.verbose(f"  - ИНН: {inn_value}", 2)
                if client_id_value:
                    self.agi.verbose(f"  - Client ID: {client_id_value}", 2)

                return True
            else:
                self.agi.verbose("⚠ Запись не была сохранена", 1)
                return False

        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка при сохранении в БД: {e}", 1)
            if self.conn:
                self.conn.rollback()
        except Exception as e:
            self.agi.verbose(f"❌ Неожиданная ошибка: {e}", 1)
            if os.getenv("DEBUG"):
                traceback.print_exc(file=sys.stderr)

        return False

    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            self.agi.verbose("=== НАЧАЛО СОХРАНЕНИЯ ПРОБЛЕМЫ ===", 1)

            # Получаем переменные из AGI
            problem_text, uniqueid, inn_str, caller_number, client_id = self.get_agi_variables()

            # Проверяем наличие uniqueid
            if not uniqueid:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_NO_UNIQUEID)
                self.agi.verbose("❌ Отсутствует UNIQUEID", 1)
                return

            # Проверяем наличие распознанного текста
            if not problem_text:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_NO_TEXT)
                self.agi.verbose("❌ Нет распознанного текста для сохранения", 1)
                return

            # Выводим информацию для отладки
            self.agi.verbose(f"📝 Текст проблемы: '{problem_text}'", 1)
            self.agi.verbose(f"📞 Номер звонящего: {caller_number or 'неизвестен'}", 1)
            self.agi.verbose(f"🆔 UniqueID: {uniqueid}", 1)

            if inn_str:
                self.agi.verbose(f"🔢 ИНН: {inn_str}", 1)
            if client_id:
                self.agi.verbose(f"👤 Client ID: {client_id}", 1)

            # Подключаемся к БД
            if not self.connect_to_db():
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
                self.agi.verbose("❌ Не удалось подключиться к БД", 1)
                return

            # Сохраняем проблему в БД
            if self.save_problem_description(problem_text, uniqueid, inn_str, caller_number, client_id):
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_SUCCESS)
                self.agi.verbose("✅ Проблема успешно сохранена в verification_logs", 1)
            else:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
                self.agi.verbose("❌ Не удалось сохранить проблему в БД", 1)

            self.agi.verbose("=== ЗАВЕРШЕНИЕ СОХРАНЕНИЯ ПРОБЛЕМЫ ===", 1)

        except Exception as e:
            self.handle_error(e)
        finally:
            self.cleanup()

    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
        self.agi.verbose(f"❌ Ошибка в скрипте: {str(error)}", 1)

        # Детальная информация для отладки
        if os.getenv("DEBUG") or os.getenv("ASTERISK_DEBUG"):
            traceback.print_exc(file=sys.stderr)
            self.agi.verbose(f"Traceback: {traceback.format_exc()}", 3)

    def cleanup(self) -> None:
        """Освобождение ресурсов"""
        if self.cursor:
            try:
                self.cursor.close()
                self.agi.verbose("✓ Курсор закрыт", 3)
            except:
                pass
        if self.conn:
            try:
                self.conn.close()
                self.agi.verbose("✓ Соединение с БД закрыто", 3)
            except:
                pass


# ────────────────────────────────────────────────
# Точка входа
# ────────────────────────────────────────────────
if __name__ == "__main__":
    saver = ProblemSaver()
    saver.run()
