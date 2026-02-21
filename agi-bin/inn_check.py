#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для проверки ИНН с использованием BasicAGI
Устанавливает переменные:
VERIF_STATUS = SUCCESS / NOT_FOUND / INVALID / ERROR
VERIF_INN, VERIF_COMPANY, VERIF_CODEWORD — если успех
"""

import sys
import re
import os
import traceback
from typing import Optional, Tuple, Union

import psycopg2
from psycopg2 import sql
from basicagi import BasicAGI


class InnVerifier:
    """Класс для проверки ИНН по распознанному тексту"""
    
    # Конфигурация базы данных
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "asterisk_user",
        "password": "qwerty",  # !!! ИЗМЕНИТЕ НА РЕАЛЬНЫЙ ПАРОЛЬ !!!
        "host": "localhost",
        "port": 5432,  # Измените на 5433 если нужно
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5
    }
    
    # Статусы проверки
    STATUS_SUCCESS = "SUCCESS"
    STATUS_NOT_FOUND = "NOT_FOUND"
    STATUS_INVALID = "INVALID"
    STATUS_ERROR = "ERROR"
    
    # Допустимая длина ИНН
    INN_MIN_LENGTH = 10
    INN_MAX_LENGTH = 12
    
    def __init__(self):
        """Инициализация BasicAGI и переменных"""
        self.agi = BasicAGI()
        self.conn = None
        self.cursor = None
        
    def extract_inn(self, text: str) -> Optional[int]:
        """
        Извлекает ИНН из распознанного текста, конвертируя слова в цифры

        Args:
            text: Распознанный текст

        Returns:
            ИНН как целое число или None, если не удалось извлечь
        """
        if not text:
            return None
    
        # Словарь для преобразования слов в цифры
        word_to_digit = {
            'ноль': '0', 'один': '1', 'два': '2', 'три': '3', 'четыре': '4',
            'пять': '5', 'шесть': '6', 'семь': '7', 'восемь': '8', 'девять': '9',
            # Варианты с дефисом
            'ноль': '0', 'один': '1', 'два': '2', 'три': '3', 'четыре': '4',
            'пять': '5', 'шесть': '6', 'семь': '7', 'восемь': '8', 'девять': '9',
            # Сокращенные варианты
            'нуль': '0', 'раз': '1', 'два': '2', 'три': '3'
        }
    
    # Нормализуем текст: приводим к нижнему регистру и заменяем дефисы на пробелы
        normalized_text = text.lower().replace('-', ' ')
    
        # Разбиваем на слова и пытаемся преобразовать
        words = normalized_text.split()
        digits_from_words = []
    
        for word in words:
            # Очищаем слово от лишних символов
            clean_word = re.sub(r'[^а-яё]', '', word)
    
            # Проверяем, является ли слово цифрой
            if clean_word in word_to_digit:
                digits_from_words.append(word_to_digit[clean_word])
            else:
                # Если слово не распознано как цифра, ищем цифры в нем
                word_digits = re.findall(r'\d+', word)
                if word_digits:
                    digits_from_words.extend(word_digits)
    
        # Также извлекаем обычные цифры из текста
        regular_digits = re.findall(r'\d+', text)
    
        # Объединяем все найденные цифры
        all_digits = digits_from_words + regular_digits
    
        # Склеиваем все цифры в одну строку
        combined_digits = ''.join(all_digits)
    
        # Если нет цифр, пробуем альтернативный подход:
        # ищем последовательности слов, которые могут быть цифрами
        if not combined_digits:
            # Паттерн для поиска слов-цифр в тексте
            word_pattern = r'\b(?:ноль|один|два|три|четыре|пять|шесть|семь|восемь|девять|нуль|раз)\b'
            found_words = re.findall(word_pattern, normalized_text, re.IGNORECASE)
    
            for word in found_words:
                clean_word = re.sub(r'[^а-яё]', '', word.lower())
                if clean_word in word_to_digit:
                    combined_digits += word_to_digit[clean_word]
    
        # Проверяем длину (ИНН может быть 10 или 12 цифр)
        if self.INN_MIN_LENGTH <= len(combined_digits) <= self.INN_MAX_LENGTH:
            try:
                return int(combined_digits)
            except ValueError:
                return None

    # Если не удалось получить ИНН нужной длины, возвращаем None
        return None
    
    


    
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
            self.agi.verbose(f"❌ Ошибка подключения к БД: {e}", 1)
            return False
    
    def get_agi_variables(self) -> Tuple[str, str, str]:
        """
        Получает необходимые переменные из AGI
        
        Returns:
            Кортеж (spoken_text, uniqueid, caller_num)
        """
        spoken_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        caller_num = self.agi.get_variable("CALLERID(num)") or "unknown"
        
        return spoken_text.strip().lower(), uniqueid, caller_num
    
    def find_client_by_inn(self, inn: int) -> Optional[Tuple]:
        """
        Ищет клиента по ИНН в базе данных
        
        Args:
            inn: ИНН для поиска
            
        Returns:
            Кортеж (inn, company_name, code_word) или None
        """
        try:
            self.cursor.execute("""
                SELECT inn, company_name, code_word 
                FROM clients_inn 
                WHERE inn = %s
            """, (inn,))
            return self.cursor.fetchone()
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка при поиске клиента: {e}", 1)
            return None
    
    def log_verification(self, uniqueid: str, caller_num: str, 
                        spoken_inn: int, matched_inn: Optional[int] = None) -> bool:
        """
        Логирует результат проверки ИНН
        
        Args:
            uniqueid: Уникальный ID вызова
            caller_num: Номер звонящего
            spoken_inn: Распознанный ИНН
            matched_inn: Найденный ИНН (если есть)
            
        Returns:
            True если запись успешно создана, иначе False
        """
        try:
            success = matched_inn is not None
            
            self.cursor.execute("""
                INSERT INTO inn_verification_log
                (call_uniqueid, caller_number, spoken_inn, matched_inn, success, created_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                RETURNING id
            """, (uniqueid, caller_num, spoken_inn, matched_inn, success))
            
            self.conn.commit()
            return True
            
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка при логировании: {e}", 1)
            self.conn.rollback()
            return False
    
    def set_success_variables(self, inn: int, company: str, code_word: str) -> None:
        """
        Устанавливает переменные AGI для успешной проверки
        
        Args:
            inn: ИНН
            company: Название компании
            code_word: Кодовое слово
        """
        self.agi.set_variable("VERIF_INN", str(inn))
        self.agi.set_variable("VERIF_COMPANY", company or "")
        self.agi.set_variable("VERIF_CODEWORD", code_word or "")
        self.agi.set_variable("VERIF_STATUS", self.STATUS_SUCCESS)
    
    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            # Получаем переменные из AGI
            spoken_text, uniqueid, caller_num = self.get_agi_variables()
            
            # Логируем входные данные для отладки
            self.agi.verbose(f"Получен текст: '{spoken_text}'", 3)
            self.agi.verbose(f"UniqueID: {uniqueid}, Caller: {caller_num}", 3)
            
            # Извлекаем ИНН из текста
            inn = self.extract_inn(spoken_text)
            
            # Проверяем, удалось ли извлечь ИНН
            if inn is None:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_INVALID)
                self.agi.verbose(f"✗ Не удалось извлечь ИНН из текста: '{spoken_text}'", 1)
                
                # Логируем неудачную попытку (без matched_inn)
                if self.connect_to_db():
                    self.log_verification(uniqueid, caller_num, 0, None)
                    self.cleanup()
                return
            
            self.agi.verbose(f"✓ Извлечён ИНН: {inn}", 1)
            
            # Подключаемся к БД и ищем клиента
            if not self.connect_to_db():
                self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
                self.agi.verbose("❌ Невозможно подключиться к БД", 1)
                return
            
            # Ищем клиента по ИНН
            client = self.find_client_by_inn(inn)
            
            if client:
                # Клиент найден
                db_inn, company, code_word = client
                self.set_success_variables(db_inn, company, code_word)
                
                # Логируем успех
                self.log_verification(uniqueid, caller_num, inn, db_inn)
                
                self.agi.verbose(f"✓ ИНН найден: {db_inn} → {company or 'Название не указано'}", 1)
                
                if code_word:
                    self.agi.verbose(f"✓ Кодовое слово установлено", 1)
                else:
                    self.agi.verbose("⚠ Кодовое слово отсутствует в базе", 1)
                    
                # Выводим все установленные переменные для отладки
                self.agi.verbose(f"VERIF_INN={db_inn}, VERIF_COMPANY={company}, VERIF_CODEWORD={code_word}", 3)
            else:
                # Клиент не найден
                self.agi.set_variable("VERIF_STATUS", self.STATUS_NOT_FOUND)
                
                # Логируем неудачу
                self.log_verification(uniqueid, caller_num, inn, None)
                
                self.agi.verbose(f"✗ ИНН {inn} не найден в базе", 1)
                
        except Exception as e:
            self.handle_error(e)
        finally:
            self.cleanup()
    
    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
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
def main():
    """Основная функция для совместимости со старым кодом"""
    verifier = InnVerifier()
    verifier.run()


if __name__ == "__main__":
    main()
