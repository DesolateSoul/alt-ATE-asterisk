#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для сохранения описания проблемы клиента
Сохраняет распознанный текст в поле response_used таблицы inn_verification_log
"""

import sys
import re
import os
import traceback
from typing import Optional, Tuple

import psycopg2
from psycopg2 import sql
from basicagi import BasicAGI


class ProblemSaver:
    """Класс для сохранения описания проблемы"""

    # Конфигурация базы данных
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "asterisk_user",
        "password": "qwerty",  # !!! ИЗМЕНИТЕ НА РЕАЛЬНЫЙ ПАРОЛЬ !!!
        "host": "localhost",
        "port": 5432,  # Измените на 5433 если нужно
        "connect_timeout": 5
    }

    # Статусы выполнения
    STATUS_SUCCESS = "SAVED"
    STATUS_NO_INN = "NO_INN"
    STATUS_NO_TEXT = "NO_TEXT"
    STATUS_ERROR = "ERROR"

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
            return True
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка подключения к БД: {e}", 1)
            return False

    def get_agi_variables(self) -> Tuple[str, str, str]:
        """
        Получает необходимые переменные из AGI

        Returns:
            Кортеж (spoken_text, uniqueid, inn_str, caller_number)
        """
        spoken_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        inn_str = self.agi.get_variable("VERIF_INN") or ""
        caller_number = self.agi.get_variable("CALLERID(num)") or ""

        return spoken_text.strip(), uniqueid, inn_str, caller_number

    def save_problem_description(self, spoken_text: str, uniqueid: str, 
                                 inn_str: str, caller_number: str) -> bool:
        """
        Сохраняет описание проблемы в таблицу inn_verification_log

        Args:
            spoken_text: Распознанный текст проблемы
            uniqueid: Уникальный ID вызова
            inn_str: Строка с ИНН
            caller_number: Номер звонящего

        Returns:
            True если запись сохранена, иначе False
        """
        try:
            # Проверяем наличие всех необходимых данных
            if not all([spoken_text, uniqueid, inn_str, caller_number]):
                missing = []
                if not spoken_text: missing.append("текст проблемы")
                if not uniqueid: missing.append("uniqueid")
                if not inn_str: missing.append("ИНН")
                if not caller_number: missing.append("номер caller")
                
                self.agi.verbose(f"Отсутствуют данные: {', '.join(missing)}", 1)
                return False

            # Проверяем, что ИНН - число
            inn_value = int(inn_str)

            # Проверяем существование записи с таким uniqueid и inn
            self.cursor.execute("""
                SELECT id, response_used 
                FROM inn_verification_log 
                WHERE call_uniqueid = %s AND spoken_inn = %s
                ORDER BY id DESC 
                LIMIT 1
            """, (uniqueid, inn_value))

            result = self.cursor.fetchone()

            if result:
                record_id, existing_response = result
                
                # Если запись существует, обновляем поле response_used
                self.cursor.execute("""
                    UPDATE inn_verification_log
                    SET response_used = %s,
                        caller_number = COALESCE(caller_number, %s),
                        updated_at = NOW()
                    WHERE id = %s
                    RETURNING id
                """, (spoken_text, caller_number, record_id))
                
                action = "обновлена"
            else:
                # Если записи нет, создаем новую
                self.cursor.execute("""
                    INSERT INTO inn_verification_log 
                        (call_uniqueid, spoken_inn, response_used, caller_number, success)
                    VALUES (%s, %s, %s, %s, false)
                    RETURNING id
                """, (uniqueid, inn_value, spoken_text, caller_number))
                
                action = "создана"

            if self.cursor.rowcount > 0:
                self.conn.commit()
                self.agi.verbose(f"✓ Запись {action} в БД (ID: {self.cursor.fetchone()[0] if not result else record_id})", 1)
                return True
            else:
                self.agi.verbose("⚠ Запись не была сохранена", 1)
                return False

        except ValueError:
            self.agi.verbose(f"Некорректный ИНН: {inn_str}", 1)
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при сохранении в БД: {e}", 1)
            if self.conn:
                self.conn.rollback()
        except Exception as e:
            self.agi.verbose(f"Неожиданная ошибка: {e}", 1)

        return False

    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            # Получаем переменные из AGI
            spoken_text, uniqueid, inn_str, caller_number = self.get_agi_variables()

            # Проверяем наличие распознанного текста
            if not spoken_text:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_NO_TEXT)
                self.agi.verbose("Нет распознанного текста для сохранения", 1)
                return

            # Проверяем наличие ИНН
            if not inn_str:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_NO_INN)
                self.agi.verbose("Нет сохранённого ИНН в переменных", 1)
                return

            self.agi.verbose(f"Распознанный текст проблемы: '{spoken_text}'", 1)
            self.agi.verbose(f"Номер звонящего: {caller_number}", 1)
            self.agi.verbose(f"UniqueID: {uniqueid}", 1)

            # Сохраняем проблему в БД
            if self.connect_to_db():
                if self.save_problem_description(spoken_text, uniqueid, inn_str, caller_number):
                    self.agi.set_variable("PROBLEM_STATUS", self.STATUS_SUCCESS)
                    self.agi.verbose("✓ Проблема успешно сохранена в БД", 1)
                else:
                    self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
                    self.agi.verbose("✗ Не удалось сохранить проблему в БД", 1)
            else:
                self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
                self.agi.verbose("✗ Не удалось подключиться к БД", 1)

        except Exception as e:
            self.handle_error(e)
        finally:
            self.cleanup()

    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("PROBLEM_STATUS", self.STATUS_ERROR)
        self.agi.verbose(f"❌ Ошибка в скрипте: {str(error)}", 1)

        # Детальная информация для отладки
        if os.getenv("DEBUG"):
            traceback.print_exc(file=sys.stderr)

    def cleanup(self) -> None:
        """Освобождение ресурсов"""
        if self.cursor:
            try:
                self.cursor.close()
            except:
                pass
        if self.conn:
            try:
                self.conn.close()
            except:
                pass


# ────────────────────────────────────────────────
# Точка входа
# ────────────────────────────────────────────────
if __name__ == "__main__":
    saver = ProblemSaver()
    saver.run()
