#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для проверки кодового слова
Ожидает уже установленную переменную VERIF_CODEWORD из предыдущего шага
Устанавливает VERIF_STATUS = SUCCESS / WRONG / NO_INN / ERROR
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


class CodeWordVerifier:
    """Класс для проверки кодового слова"""
    
    # Конфигурация базы данных (обновлено для новых таблиц)
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "postgres",  # Изменено с asterisk_user на postgres
        "password": "OP90wq21",  # !!! ИЗМЕНИТЕ НА РЕАЛЬНЫЙ ПАРОЛЬ !!!
        "host": "localhost",
        "port": 5432,
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
    
    # Статусы проверки
    STATUS_SUCCESS = "SUCCESS"
    STATUS_WRONG = "WRONG"
    STATUS_NO_INN = "NO_INN"
    STATUS_ERROR = "ERROR"
    
    def __init__(self):
        """Инициализация AGI и подключения к БД"""
        self.agi = BasicAGI()
        self.conn = None
        self.cursor = None
        
    def cleanup_text(self, text: str) -> str:
        """
        Очищает текст для сравнения
        
        Args:
            text: Исходный текст
            
        Returns:
            Очищенный текст (только буквы и цифры)
        """
        if not text:
            return ""
        # Приводим к нижнему регистру и удаляем всё кроме букв и цифр
        # Поддерживаем русские и английские буквы
        return re.sub(r'[^а-яёa-z0-9]', '', text.lower())
    
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
    
    def get_agi_variables(self) -> Tuple[str, str, str, str]:
        """
        Получает необходимые переменные из AGI
        
        Returns:
            Кортеж (spoken_text, uniqueid, inn_str, caller_number)
        """
        spoken_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        inn_str = self.agi.get_variable("VERIF_INN") or ""
        caller_number = self.agi.get_variable("CALLERID(num)") or ""
        
        return spoken_text.strip().lower(), uniqueid, inn_str, caller_number
    
    def find_log_entry(self, uniqueid: str, inn_value: int) -> Optional[int]:
        """
        Находит запись в логе верификации
        
        Args:
            uniqueid: Уникальный ID вызова
            inn_value: ИНН как число
            
        Returns:
            ID записи если найдена, иначе None
        """
        try:
            self.cursor.execute("""
                SELECT id 
                FROM verification_logs 
                WHERE call_uniqueid = %s 
                  AND spoken_inn = %s
                ORDER BY created_at DESC
                LIMIT 1
            """, (uniqueid, inn_value))
            
            result = self.cursor.fetchone()
            return result[0] if result else None
            
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при поиске записи: {e}", 1)
            return None
    
    def update_verification_log(self, spoken_text: str, uniqueid: str, 
                               inn_str: str, caller_number: str) -> bool:
        """
        Обновляет запись в логе верификации
        
        Args:
            spoken_text: Сказанное кодовое слово
            uniqueid: Уникальный ID вызова
            inn_str: Строка с ИНН
            caller_number: Номер звонящего
            
        Returns:
            True если запись обновлена, иначе False
        """
        try:
            # Проверяем, что ИНН - число
            inn_value = int(inn_str)
            
            # Сначала ищем существующую запись
            log_id = self.find_log_entry(uniqueid, inn_value)
            
            if log_id:
                # Обновляем существующую запись
                self.cursor.execute("""
                    UPDATE verification_logs
                    SET spoken_codeword = %s,
                        success = true,
                        caller_number = COALESCE(caller_number, %s)
                    WHERE id = %s
                    RETURNING id
                """, (spoken_text, caller_number, log_id))
            else:
                # Создаем новую запись
                self.cursor.execute("""
                    INSERT INTO verification_logs 
                        (call_uniqueid, caller_number, spoken_inn, spoken_codeword, success)
                    VALUES (%s, %s, %s, %s, true)
                    RETURNING id
                """, (uniqueid, caller_number, inn_value, spoken_text))
            
            if self.cursor.rowcount > 0:
                self.conn.commit()
                self.agi.verbose(f"✓ Запись в verification_logs обновлена (ID: {log_id if log_id else 'new'})", 1)
                return True
                
        except ValueError as e:
            self.agi.verbose(f"Некорректный ИНН: {inn_str} - {e}", 1)
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при обновлении лога: {e}", 1)
            self.conn.rollback()
            
        return False
    
    def get_expected_codeword(self, inn_str: str) -> Optional[str]:
        """
        Получает ожидаемое кодовое слово из таблицы clients
        
        Args:
            inn_str: Строка с ИНН
            
        Returns:
            Ожидаемое кодовое слово или None
        """
        try:
            inn_value = int(inn_str)
            
            self.cursor.execute("""
                SELECT code_word 
                FROM clients 
                WHERE inn = %s AND active = true
            """, (inn_value,))
            
            result = self.cursor.fetchone()
            return result[0] if result else None
            
        except (ValueError, psycopg2.Error) as e:
            self.agi.verbose(f"Ошибка при получении кодового слова: {e}", 1)
            return None
    
    def verify_code_word(self, spoken: str, expected: str) -> bool:
        """
        Проверяет соответствие кодового слова
        
        Args:
            spoken: Сказанное слово
            expected: Ожидаемое слово
            
        Returns:
            True если слова совпадают, иначе False
        """
        if not spoken or not expected:
            return False
            
        spoken_clean = self.cleanup_text(spoken)
        expected_clean = self.cleanup_text(expected)
        
        # Проверяем точное совпадение или вхождение
        exact_match = spoken_clean == expected_clean
        contains_match = spoken_clean and spoken_clean in expected_clean
        
        # Дополнительная проверка для похожих слов (опционально)
        # Например: "альт" и "олт" - считаем совпадением если разница не более 1 символа
        fuzzy_match = False
        if not exact_match and not contains_match:
            # Простейшая проверка расстояния Левенштейна
            if abs(len(spoken_clean) - len(expected_clean)) <= 1:
                # Если длины почти равны, можно добавить более сложную логику
                pass
        
        return exact_match or contains_match
    
    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            # Получаем переменные из AGI
            spoken_text, uniqueid, inn_str, caller_number = self.get_agi_variables()
            
            self.agi.verbose(f"Проверка кодового слова для звонка {uniqueid}", 1)
            self.agi.verbose(f"Сказано: '{spoken_text}', ИНН: {inn_str}, Номер: {caller_number}", 1)
            
            # Проверяем наличие ИНН
            if not inn_str:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_NO_INN)
                self.agi.verbose("Нет сохранённого ИНН для проверки кодового слова", 1)
                return
            
            # Подключаемся к БД для получения ожидаемого кодового слова
            if not self.connect_to_db():
                self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
                self.agi.verbose("Не удалось подключиться к БД", 1)
                return
            
            # Получаем ожидаемое кодовое слово из БД
            expected_word = self.get_expected_codeword(inn_str)
            
            # Если не нашли в БД, пробуем получить из переменной AGI
            if not expected_word:
                expected_word = self.agi.get_variable("VERIF_CODEWORD") or ""
            
            # Проверяем наличие кодового слова
            if not expected_word:
                self.agi.verbose("ВНИМАНИЕ: Кодовое слово не найдено в БД и VERIF_CODEWORD не установлен", 1)
                self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
                return
            
            # Проверяем кодовое слово
            if self.verify_code_word(spoken_text, expected_word):
                self.agi.set_variable("VERIF_STATUS", self.STATUS_SUCCESS)
                self.agi.verbose(f"✓ Кодовое слово совпало: '{spoken_text}' = '{expected_word}'", 1)
                
                # Обновляем запись в БД
                if self.update_verification_log(spoken_text, uniqueid, inn_str, caller_number):
                    self.agi.verbose("✓ Запись в verification_logs успешно обновлена", 1)
                else:
                    self.agi.verbose("⚠ Не удалось обновить запись в БД", 1)
            else:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_WRONG)
                self.agi.verbose(f"✗ Кодовое слово неверно: ожидалось '{expected_word}', сказано '{spoken_text}'", 1)
                
                # Для отладки показываем очищенные версии
                spoken_clean = self.cleanup_text(spoken_text)
                expected_clean = self.cleanup_text(expected_word)
                self.agi.verbose(f"  Очищенные версии: '{spoken_clean}' vs '{expected_clean}'", 3)
                
        except Exception as e:
            self.handle_error(e)
        finally:
            self.cleanup()
    
    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
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
    verifier = CodeWordVerifier()
    verifier.run()
