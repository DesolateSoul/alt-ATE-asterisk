#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для проверки кодового слова
Ожидает уже установленную переменную VERIF_CODEWORD из предыдущего шага
Устанавливает VERIF_STATUS = SUCCESS / WRONG / NO_INN / ERROR
"""

import sys
import re
import os
import traceback
from typing import Optional, Tuple, Dict, Any

import psycopg2
from psycopg2 import sql
from basicagi import BasicAGI


class CodeWordVerifier:
    """Класс для проверки кодового слова"""
    
    # Конфигурация базы данных
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "asterisk_user",
        "password": "qwerty",  # !!! ИЗМЕНИТЕ НА РЕАЛЬНЫЙ ПАРОЛЬ !!!
        "host": "localhost",
        "port": 5432,  # Измените на 5433 если нужно
        "connect_timeout": 5
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
    
    def get_agi_variables(self) -> Tuple[str, str, str]:
        """
        Получает необходимые переменные из AGI
        
        Returns:
            Кортеж (spoken_text, uniqueid, inn_str)
        """
        spoken_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        inn_str = self.agi.get_variable("VERIF_INN") or ""
        
        return spoken_text.strip().lower(), uniqueid, inn_str
    
    def update_verification_log(self, spoken_text: str, uniqueid: str, inn_str: str) -> bool:
        """
        Обновляет запись в логе верификации
        
        Args:
            spoken_text: Сказанный текст
            uniqueid: Уникальный ID вызова
            inn_str: Строка с ИНН
            
        Returns:
            True если запись обновлена, иначе False
        """
        try:
            # Проверяем, что ИНН - число
            inn_value = int(inn_str)
            
            self.cursor.execute("""
                UPDATE inn_verification_log
                SET success = true,
                    code_word_spoken = %s,
                    updated_at = NOW()
                WHERE call_uniqueid = %s
                  AND spoken_inn = %s
                  AND (success IS NULL OR success IS NOT TRUE)
                RETURNING id
            """, (spoken_text, uniqueid, inn_value))
            
            if self.cursor.rowcount > 0:
                self.conn.commit()
                return True
                
        except ValueError:
            self.agi.verbose(f"Некорректный ИНН: {inn_str}", 1)
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при обновлении лога: {e}", 1)
            self.conn.rollback()
            
        return False
    
    def verify_code_word(self, spoken: str, expected: str) -> bool:
        """
        Проверяет соответствие кодового слова
        
        Args:
            spoken: Сказанное слово
            expected: Ожидаемое слово
            
        Returns:
            True если слова совпадают, иначе False
        """
        spoken_clean = self.cleanup_text(spoken)
        expected_clean = self.cleanup_text(expected)
        
        # Проверяем точное совпадение или вхождение
        return spoken_clean == expected_clean or (spoken_clean and spoken_clean in expected_clean)
    
    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            # Получаем переменные из AGI
            spoken_text, uniqueid, inn_str = self.get_agi_variables()
            
            # Проверяем наличие ИНН
            if not inn_str:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_NO_INN)
                self.agi.verbose("Нет сохранённого ИНН для проверки кодового слова", 1)
                return
            
            # Получаем ожидаемое кодовое слово
            expected_word = self.agi.get_variable("VERIF_CODEWORD") or ""
            
            # Проверяем наличие кодового слова
            if not expected_word:
                self.agi.verbose("ВНИМАНИЕ: VERIF_CODEWORD не установлен", 1)
            
            # Проверяем кодовое слово
            if self.verify_code_word(spoken_text, expected_word):
                self.agi.set_variable("VERIF_STATUS", self.STATUS_SUCCESS)
                self.agi.verbose(f"✓ Кодовое слово совпало: '{spoken_text}'", 1)
                
                # Пытаемся обновить запись в БД
                if self.connect_to_db():
                    if self.update_verification_log(spoken_text, uniqueid, inn_str):
                        self.agi.verbose("✓ Запись в логе обновлена", 1)
                    else:
                        self.agi.verbose("⚠ Лог не обновлён (запись не найдена или уже успешна)", 1)
            else:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_WRONG)
                self.agi.verbose(f"✗ Кодовое слово неверно: ожидалось '{expected_word}', сказано '{spoken_text}'", 1)
                
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
