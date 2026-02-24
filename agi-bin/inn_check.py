#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для проверки ИНН с использованием BasicAGI
Устанавливает переменные:
VERIF_STATUS = SUCCESS / NOT_FOUND / INVALID / ERROR
VERIF_INN, VERIF_COMPANY, VERIF_CODEWORD — если успех
Работает с таблицами clients и verification_logs
"""

import sys
import re
import os
import traceback
from typing import Optional, Tuple, Dict, Any, List
import psycopg2
from basicagi import BasicAGI


class InnVerifier:
    """Класс для проверки ИНН по распознанному тексту"""

    # Конфигурация базы данных
    DB_CONFIG = {
        "dbname": "asterisk_db",
        "user": "postgres",
        "password": "OP90wq21",
        "host": "localhost",
        "port": 5432,
        "connect_timeout": 5,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "application_name": "inn_verifier_agi"
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

        # Инициализация словарей для распознавания ИНН
        self.init_recognition_dicts()

    def init_recognition_dicts(self):
        """Инициализация словарей для распознавания чисел"""
        # Словарь произношений цифр
        self.digit_map = {
            # Русские
            'ноль': 0, 'нуль': 0,
            'один': 1, 'одна': 1, 'первый': 1, 'раз': 1,
            'два': 2, 'две': 2, 'второй': 2,
            'три': 3, 'третий': 3,
            'четыре': 4, 'четвертый': 4,
            'пять': 5, 'пятый': 5,
            'шесть': 6, 'шестой': 6,
            'семь': 7, 'седьмой': 7,
            'восемь': 8, 'восьмой': 8,
            'девять': 9, 'девятый': 9,
            # Английские
            'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4,
            'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9
        }

        # Словарь двухзначных чисел
        self.tens_map = {
            'десять': 10, 'одиннадцать': 11, 'двенадцать': 12,
            'тринадцать': 13, 'четырнадцать': 14, 'пятнадцать': 15,
            'шестнадцать': 16, 'семнадцать': 17, 'восемнадцать': 18,
            'девятнадцать': 19,
            'двадцать': 20, 'тридцать': 30, 'сорок': 40,
            'пятьдесят': 50, 'шестьдесят': 60, 'семьдесят': 70,
            'восемьдесят': 80, 'девяносто': 90
        }

        # Словарь трёхзначных чисел
        self.hundreds_map = {
            'сто': 100, 'двести': 200, 'триста': 300,
            'четыреста': 400, 'пятьсот': 500, 'шестьсот': 600,
            'семьсот': 700, 'восемьсот': 800, 'девятьсот': 900
        }

    def _normalize_text(self, text: str) -> str:
        """
        Нормализует текст: нижний регистр, замена разделителей

        Args:
            text: Исходный текст

        Returns:
            Нормализованный текст
        """
        if not text:
            return ""

        # Приводим к нижнему регистру и заменяем разделители
        normalized = text.lower()
        normalized = re.sub(r'[-–—.,;:/\\|]', ' ', normalized)
        # Убираем лишние пробелы
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def word_to_number(self, word: str) -> Optional[int]:
        """
        Переводит слово в число

        Args:
            word: Слово для перевода

        Returns:
            Число или None, если не удалось перевести
        """
        word = word.lower().strip()
        clean_word = re.sub(r'[^а-яёa-z]', '', word)

        if not clean_word:
            return None

        if clean_word in self.digit_map:
            return self.digit_map[clean_word]
        elif clean_word in self.tens_map:
            return self.tens_map[clean_word]
        elif clean_word in self.hundreds_map:
            return self.hundreds_map[clean_word]

        return None

    def _extract_digit_sequences(self, text: str) -> List[str]:
        """
        Извлекает все последовательности цифр из текста

        Args:
            text: Текст для поиска

        Returns:
            Список найденных цифровых последовательностей
        """
        return re.findall(r'\d+', text)

    def extract_inn(self, text: str) -> Optional[int]:
        """
        Извлекает наиболее вероятный ИНН из распознанного текста
        ИНН может состоять из 10 или 12 цифр

        Использует два подхода:
        1. Отдельные цифры (10 или 12 слов)
        2. Двухзначные числа с обработкой составных числительных

        Args:
            text: Распознанный текст

        Returns:
            ИНН или None, если не удалось извлечь
        """
        if not text:
            return None

        self.agi.verbose(f"Извлечение ИНН из текста: '{text}'", 3)

        # Нормализуем текст
        normalized = self._normalize_text(text)

        # ШАГ 1: Прямые последовательности цифр (быстрый путь)
        digit_sequences = self._extract_digit_sequences(normalized)
        if digit_sequences:
            digit_sequences.sort(key=len, reverse=True)
            for seq in digit_sequences:
                if self.INN_MIN_LENGTH <= len(seq) <= self.INN_MAX_LENGTH:
                    self.agi.verbose(f"✓ Найдена прямая последовательность цифр: {seq}", 3)
                    return int(seq)

        # Разбиваем на слова для дальнейшего анализа
        words = normalized.split()

        if not words:
            return None

        # ============= ШАГ 2: Отдельные цифры (10 или 12 слов) =============
        if len(words) in [10, 12]:
            result_digits = []
            valid = True

            for word in words:
                num = self.word_to_number(word)
                if num is None or num > 9:  # Для отдельных цифр ожидаем только 0-9
                    valid = False
                    break
                result_digits.append(str(num))

            if valid and len(result_digits) in [10, 12]:
                result = int(''.join(result_digits))
                self.agi.verbose(f"✓ Найден по отдельным цифрам: {result}", 3)
                return result

        # ============= ШАГ 3: Двухзначные числа с обработкой составных числительных =============
        if len(words) <= 12:  # Ограничиваем максимальное количество слов
            result_digits = []
            i = 0
            error = False

            while i < len(words) and not error:
                current_word = words[i]

                # Проверяем, является ли слово двухзначным числом из словаря
                if current_word in self.tens_map:
                    # Проверяем, есть ли следующее слово и является ли оно цифрой (для составных типа "двадцать один")
                    if i + 1 < len(words) and words[i + 1] in self.digit_map:
                        # Составное двухзначное число: двадцать один -> 21
                        tens = self.tens_map[current_word]
                        units = self.digit_map[words[i + 1]]
                        num = tens + units
                        result_digits.append(f"{num:02d}")  # Всегда две цифры
                        i += 2
                    else:
                        # Простое двухзначное число: двадцать -> 20
                        num = self.tens_map[current_word]
                        result_digits.append(str(num))
                        i += 1

                # Проверяем, является ли слово трёхзначным числом (для смешанных случаев)
                elif current_word in self.hundreds_map:
                    # Проверяем, есть ли следующее слово и является ли оно двухзначным или цифрой
                    if i + 1 < len(words):
                        next_word = words[i + 1]
                        if next_word in self.tens_map:
                            # Трёхзначное + двухзначное: сто двадцать -> 120
                            hundreds = self.hundreds_map[current_word]
                            tens = self.tens_map[next_word]

                            # Проверяем, есть ли ещё цифра после двухзначного
                            if i + 2 < len(words) and words[i + 2] in self.digit_map:
                                # Полное трёхзначное: сто двадцать один -> 121
                                units = self.digit_map[words[i + 2]]
                                num = hundreds + tens + units
                                result_digits.append(str(num))
                                i += 3
                            else:
                                # Трёхзначное с десятками: сто двадцать -> 120
                                num = hundreds + tens
                                result_digits.append(str(num))
                                i += 2
                        elif next_word in self.digit_map:
                            # Трёхзначное + цифра: сто один -> 101
                            hundreds = self.hundreds_map[current_word]
                            units = self.digit_map[next_word]
                            num = hundreds + units
                            result_digits.append(str(num))
                            i += 2
                        else:
                            # Только сотни: сто -> 100
                            num = self.hundreds_map[current_word]
                            result_digits.append(str(num))
                            i += 1
                    else:
                        # Только сотни в конце строки
                        num = self.hundreds_map[current_word]
                        result_digits.append(str(num))
                        i += 1

                # Проверяем, является ли слово простой цифрой
                elif current_word in self.digit_map:
                    result_digits.append(str(self.digit_map[current_word]))
                    i += 1

                # Проверяем особый случай: "ноль" может быть частью числа
                elif current_word == "ноль" or current_word == "нуль":
                    result_digits.append("0")
                    i += 1

                else:
                    # Встретилось нечисловое слово - прерываем обработку
                    error = True
                    break

            # Если успешно обработали все слова без ошибок
            if not error and result_digits:
                result_str = ''.join(result_digits)

                # Проверяем, что длина соответствует ИНН (10 или 12 цифр)
                if len(result_str) == 10:
                    result = int(result_str)
                    self.agi.verbose(f"✓ Найден по двухзначным числам (10 цифр): {result}", 3)
                    return result
                elif len(result_str) == 12:
                    result = int(result_str)
                    self.agi.verbose(f"✓ Найден по двухзначным числам (12 цифр): {result}", 3)
                    return result
                elif len(result_str) in [10, 12]:
                    try:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по двухзначным числам: {result}", 3)
                        return result
                    except ValueError:
                        self.agi.verbose(f"✗ Ошибка преобразования: {result_str}", 3)
                else:
                    self.agi.verbose(f"✗ Неподходящая длина: {len(result_str)} цифр", 3)

        # ============= ШАГ 4: Трёхзначные числа с обработкой составных числительных =============
        if len(words) <= 8:  # Для 12-значного ИНН максимум 4 трёхзначных числа, для 10-значного - 3-4 числа
            result_digits = []
            i = 0
            error = False

            while i < len(words) and not error:
                current_word = words[i]

                # Проверяем, является ли слово трёхзначным числом
                if current_word in self.hundreds_map:
                    hundreds = self.hundreds_map[current_word]

                    # Проверяем наличие десятков после сотен
                    if i + 1 < len(words):
                        next_word = words[i + 1]

                        # Случай: сотни + десятки (сто двадцать)
                        if next_word in self.tens_map:
                            tens = self.tens_map[next_word]

                            # Проверяем наличие единиц после десятков (сто двадцать один)
                            if i + 2 < len(words) and words[i + 2] in self.digit_map:
                                units = self.digit_map[words[i + 2]]
                                num = hundreds + tens + units
                                result_digits.append(str(num))
                                i += 3
                            else:
                                # Только сотни + десятки
                                num = hundreds + tens
                                result_digits.append(str(num))
                                i += 2

                        # Случай: сотни + единицы (сто один)
                        elif next_word in self.digit_map:
                            units = self.digit_map[next_word]
                            num = hundreds + units
                            result_digits.append(str(num))
                            i += 2

                        # Случай: только сотни (сто)
                        else:
                            result_digits.append(str(hundreds))
                            i += 1
                    else:
                        # Только сотни в конце строки
                        result_digits.append(str(hundreds))
                        i += 1

                # Проверяем, является ли слово двухзначным числом (может быть частью трёхзначного)
                elif current_word in self.tens_map:
                    tens = self.tens_map[current_word]

                    # Проверяем наличие единиц после десятков
                    if i + 1 < len(words) and words[i + 1] in self.digit_map:
                        units = self.digit_map[words[i + 1]]
                        num = tens + units
                        # Проверяем, не должно ли это быть трёхзначным числом с пропущенными сотнями
                        if i > 0 and words[i - 1] in self.hundreds_map:
                            # Уже обработано в предыдущем шаге с сотнями
                            error = True
                            break
                        result_digits.append(f"{num:02d}" if num < 100 else str(num))
                        i += 2
                    else:
                        # Просто двухзначное число
                        if i > 0 and words[i - 1] in self.hundreds_map:
                            # Уже обработано в предыдущем шаге с сотнями
                            error = True
                            break
                        result_digits.append(str(tens))
                        i += 1

                # Проверяем, является ли слово простой цифрой
                elif current_word in self.digit_map:
                    # Проверяем, не является ли это частью трёхзначного числа
                    if i > 0 and (words[i - 1] in self.hundreds_map or words[i - 1] in self.tens_map):
                        # Уже обработано в составных числах
                        error = True
                        break
                    result_digits.append(str(self.digit_map[current_word]))
                    i += 1

                # Проверяем особый случай: "ноль"
                elif current_word == "ноль" or current_word == "нуль":
                    # Проверяем, не является ли это частью числа (например, "сто ноль" -> 100)
                    if i > 0 and words[i - 1] in self.hundreds_map:
                        # Уже обработано как "сто"
                        error = True
                        break
                    result_digits.append("0")
                    i += 1

                else:
                    # Встретилось нечисловое слово
                    error = True
                    break

            # Если успешно обработали все слова без ошибок
            if not error and result_digits:
                result_str = ''.join(result_digits)

                # Проверяем различные схемы для трёхзначных чисел
                num_count = len(result_digits)

                # Схема 3-3-3-1 (для 10-значного ИНН)
                if num_count == 4 and len(result_digits[0]) == 3 and len(result_digits[1]) == 3 and \
                        len(result_digits[2]) == 3 and len(result_digits[3]) == 1:
                    if len(result_str) == 10:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по схеме 3-3-3-1: {result}", 3)
                        return result

                # Схема 3-3-3-3 (для 12-значного ИНН)
                elif num_count == 4 and all(len(part) == 3 for part in result_digits):
                    if len(result_str) == 12:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по схеме 3-3-3-3: {result}", 3)
                        return result

                # Схема 3-3-2-2 (альтернативная для 10-значного)
                elif num_count == 4 and len(result_digits[0]) == 3 and len(result_digits[1]) == 3 and \
                        len(result_digits[2]) == 2 and len(result_digits[3]) == 2:
                    if len(result_str) == 10:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по схеме 3-3-2-2: {result}", 3)
                        return result

                # Схема 3-2-3-2 (альтернативная)
                elif num_count == 4 and len(result_digits[0]) == 3 and len(result_digits[1]) == 2 and \
                        len(result_digits[2]) == 3 and len(result_digits[3]) == 2:
                    if len(result_str) == 10:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по схеме 3-2-3-2: {result}", 3)
                        return result

                # Схема 2-3-3-2
                elif num_count == 4 and len(result_digits[0]) == 2 and len(result_digits[1]) == 3 and \
                        len(result_digits[2]) == 3 and len(result_digits[3]) == 2:
                    if len(result_str) == 10:
                        result = int(result_str)
                        self.agi.verbose(f"✓ Найден по схеме 2-3-3-2: {result}", 3)
                        return result

                # Если просто подходит по длине
                elif len(result_str) == 10:
                    result = int(result_str)
                    self.agi.verbose(f"✓ Найден по трёхзначным числам (10 цифр): {result}", 3)
                    return result
                elif len(result_str) == 12:
                    result = int(result_str)
                    self.agi.verbose(f"✓ Найден по трёхзначным числам (12 цифр): {result}", 3)
                    return result
                else:
                    self.agi.verbose(f"✗ Неподходящая длина: {len(result_str)} цифр из {num_count} чисел", 3)

        self.agi.verbose("✗ ИНН не найден", 3)
        return None

    def connect_to_db(self) -> bool:
        """Устанавливает соединение с базой данных"""
        try:
            self.conn = psycopg2.connect(**self.DB_CONFIG)
            self.cursor = self.conn.cursor()
            return True
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка подключения к БД: {e}", 1)
            return False

    def get_agi_variables(self) -> Tuple[str, str, str]:
        """Получает необходимые переменные из AGI"""
        spoken_text = self.agi.get_variable("SPEECH_TEXT(0)") or ""
        uniqueid = self.agi.get_variable("UNIQUEID") or ""
        caller_num = self.agi.get_variable("CALLERID(num)") or "unknown"
        channel = self.agi.get_variable("CHANNEL") or ""
        self.agi.verbose(f"Канал: {channel}", 3)
        return spoken_text.strip(), uniqueid, caller_num

    def find_client_by_inn(self, inn: int) -> Optional[Dict[str, Any]]:
        """Ищет клиента по ИНН в таблице clients"""
        try:
            self.cursor.execute("""
                SELECT id, inn, company_name, code_word, phone_number, telegram_chat_id
                FROM clients
                WHERE inn = %s AND active = true
            """, (inn,))
            row = self.cursor.fetchone()
            if row:
                return {
                    'id': row[0],
                    'inn': row[1],
                    'company_name': row[2],
                    'code_word': row[3],
                    'phone_number': row[4],
                    'telegram_chat_id': row[5]
                }
            return None
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка при поиске клиента: {e}", 1)
            return None

    def create_verification_log(self, uniqueid: str, caller_num: str,
                               spoken_inn: int, client_id: Optional[int] = None) -> Optional[int]:
        """Создает запись в таблице verification_logs"""
        try:
            success = client_id is not None
            self.cursor.execute("""
                INSERT INTO verification_logs
                (call_uniqueid, caller_number, spoken_inn, matched_client_id, success)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (uniqueid, caller_num, spoken_inn, client_id, success))
            log_id = self.cursor.fetchone()[0]
            self.conn.commit()
            self.agi.verbose(f"✓ Создана запись в verification_logs (ID: {log_id})", 2)
            return log_id
        except psycopg2.Error as e:
            self.agi.verbose(f"❌ Ошибка при создании записи в логе: {e}", 1)
            self.conn.rollback()
            return None

    def check_existing_log(self, uniqueid: str) -> bool:
        """Проверяет, существует ли уже запись для данного вызова"""
        try:
            self.cursor.execute("""
                SELECT id FROM verification_logs
                WHERE call_uniqueid = %s
            """, (uniqueid,))
            return self.cursor.fetchone() is not None
        except psycopg2.Error as e:
            self.agi.verbose(f"Ошибка при проверке существующей записи: {e}", 2)
            return False

    def set_success_variables(self, client_data: Dict[str, Any]) -> None:
        """Устанавливает переменные AGI для успешной проверки"""
        self.agi.set_variable("VERIF_INN", str(client_data['inn']))
        self.agi.set_variable("VERIF_COMPANY", client_data['company_name'] or "")
        self.agi.set_variable("VERIF_CODEWORD", client_data['code_word'] or "")
        self.agi.set_variable("VERIF_CLIENT_ID", str(client_data['id']))
        self.agi.set_variable("VERIF_STATUS", self.STATUS_SUCCESS)
        if client_data['phone_number']:
            self.agi.set_variable("VERIF_PHONE", client_data['phone_number'])
        self.agi.verbose(f"✓ Установлены переменные для клиента ID {client_data['id']}", 2)

    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            # Получаем переменные из AGI
            spoken_text, uniqueid, caller_num = self.get_agi_variables()

            # Логируем входные данные для отладки
            self.agi.verbose(f"=== НАЧАЛО ПРОВЕРКИ ИНН ===", 1)
            self.agi.verbose(f"Получен текст: '{spoken_text}'", 1)
            self.agi.verbose(f"UniqueID: {uniqueid}, Caller: {caller_num}", 1)

            # Проверяем наличие текста
            if not spoken_text:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_INVALID)
                self.agi.verbose("✗ Пустой текст для распознавания", 1)
                if self.connect_to_db():
                    self.create_verification_log(uniqueid, caller_num, 0, None)
                    self.cleanup()
                return

            # Извлекаем ИНН из текста
            inn = self.extract_inn(spoken_text)

            # Проверяем, удалось ли извлечь ИНН
            if inn is None:
                self.agi.set_variable("VERIF_STATUS", self.STATUS_INVALID)
                self.agi.verbose(f"✗ Не удалось извлечь ИНН из текста: '{spoken_text}'", 1)
                if self.connect_to_db():
                    self.create_verification_log(uniqueid, caller_num, 0, None)
                    self.cleanup()
                return

            self.agi.verbose(f"✓ Извлечён ИНН: {inn} (длина: {len(str(inn))})", 1)

            # Подключаемся к БД
            if not self.connect_to_db():
                self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
                self.agi.verbose("❌ Невозможно подключиться к БД", 1)
                return

            # Проверяем, не было ли уже создано записи для этого звонка
            existing_log = self.check_existing_log(uniqueid)
            if existing_log:
                self.agi.verbose(f"⚠ Запись для звонка {uniqueid} уже существует", 1)

            # Ищем клиента по ИНН
            client = self.find_client_by_inn(inn)

            if client:
                # Клиент найден
                self.set_success_variables(client)
                log_id = self.create_verification_log(uniqueid, caller_num, inn, client['id'])
                self.agi.verbose(f"✓ ИНН {inn} найден: {client['company_name']}", 1)
                if client['code_word']:
                    self.agi.verbose(f"✓ Кодовое слово: '{client['code_word']}'", 1)
                else:
                    self.agi.verbose("⚠ Кодовое слово отсутствует в базе", 1)
            else:
                # Клиент не найден
                self.agi.set_variable("VERIF_STATUS", self.STATUS_NOT_FOUND)
                log_id = self.create_verification_log(uniqueid, caller_num, inn, None)
                self.agi.verbose(f"✗ ИНН {inn} не найден в базе данных", 1)

            self.agi.verbose(f"=== ЗАВЕРШЕНИЕ ПРОВЕРКИ ИНН ===", 1)

        except Exception as e:
            self.handle_error(e)
        finally:
            self.cleanup()

    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("VERIF_STATUS", self.STATUS_ERROR)
        self.agi.verbose(f"❌ Ошибка в скрипте: {str(error)}", 1)
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
    """Основная функция"""
    verifier = InnVerifier()
    verifier.run()


if __name__ == "__main__":
    main()
