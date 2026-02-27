#!/var/lib/asterisk/agi-bin/.venv/bin/python3
# -*- coding: utf-8 -*-

"""
AGI-скрипт для конвертации WAV в OGG с использованием ffmpeg
Использование в диалплане: AGI(convert_recording.py,${RECORDING_WAV},${RECORDING_OGG})
"""

import sys
import os
import subprocess
import traceback
from typing import Optional, Tuple
import time
import json

# Добавляем путь для импорта basicagi
sys.path.append('/var/lib/asterisk/agi-bin')
from basicagi import BasicAGI


class RecordingConverter:
    """Класс для конвертации аудиозаписей из WAV в OGG"""

    # Статусы выполнения
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_NO_PATHS = "NO_PATHS"
    STATUS_FFMPEG_MISSING = "FFMPEG_MISSING"
    STATUS_WAV_NOT_FOUND = "WAV_NOT_FOUND"
    STATUS_ERROR = "ERROR"

    def __init__(self):
        """Инициализация AGI"""
        self.agi = BasicAGI()
        self.log_file = '/var/log/asterisk/convert_recording.log'

    def log_to_file(self, message: str, level: str = "INFO") -> None:
        """
        Дополнительное логирование в файл

        Args:
            message: Сообщение для логирования
            level: Уровень логирования (INFO, ERROR, WARNING)
        """
        try:
            timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
            with open(self.log_file, 'a') as f:
                f.write(f"{timestamp} - CONVERT - {level} - {message}\n")
        except:
            pass  # Игнорируем ошибки записи в лог-файл

    def get_arguments(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Получает аргументы командной строки (пути к файлам)

        Returns:
            Кортеж (wav_path, ogg_path) или (None, None) если аргументов нет
        """
        if len(sys.argv) >= 3:
            wav_path = sys.argv[1]
            ogg_path = sys.argv[2]
            self.agi.verbose(f"📁 Получены аргументы: wav={os.path.basename(wav_path)}", 3)
            self.agi.verbose(f"📁 ogg={os.path.basename(ogg_path)}", 3)
            self.log_to_file(f"Получены аргументы: wav={wav_path}, ogg={ogg_path}")
            return wav_path, ogg_path
        else:
            self.agi.verbose("❌ Недостаточно аргументов", 1)
            self.log_to_file("Недостаточно аргументов", "ERROR")
            return None, None

    def check_ffmpeg(self) -> bool:
        """
        Проверяет доступность ffmpeg в системе

        Returns:
            True если ffmpeg доступен, иначе False
        """
        try:
            result = subprocess.run(
                ['ffmpeg', '-version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version_line = result.stdout.split('\n')[0]
                self.agi.verbose(f"✓ ffmpeg: {version_line[:50]}...", 1)
                self.log_to_file(f"ffmpeg найден: {version_line}")
                return True
            else:
                self.agi.verbose("❌ ffmpeg не отвечает корректно", 1)
                self.log_to_file("ffmpeg не отвечает корректно", "ERROR")
                return False
        except FileNotFoundError:
            self.agi.verbose("❌ ffmpeg не установлен в системе", 1)
            self.log_to_file("ffmpeg не найден в системе", "ERROR")
            return False
        except subprocess.TimeoutExpired:
            self.agi.verbose("❌ Таймаут при проверке ffmpeg", 1)
            self.log_to_file("Таймаут при проверке ffmpeg", "ERROR")
            return False
        except Exception as e:
            self.agi.verbose(f"❌ Ошибка при проверке ffmpeg: {e}", 1)
            self.log_to_file(f"Ошибка при проверке ffmpeg: {e}", "ERROR")
            return False

    def ensure_directory_exists(self, file_path: str) -> bool:
        """
        Проверяет и создает директорию для файла если нужно

        Args:
            file_path: Полный путь к файлу

        Returns:
            True если директория существует или создана
        """
        directory = os.path.dirname(file_path)
        if not directory:  # Если путь без директории
            return True

        try:
            if not os.path.exists(directory):
                os.makedirs(directory, mode=0o755, exist_ok=True)
                self.agi.verbose(f"📁 Создана директория: {directory}", 2)
                self.log_to_file(f"Создана директория: {directory}")
            return True
        except PermissionError:
            self.agi.verbose(f"❌ Нет прав на создание директории: {directory}", 1)
            self.log_to_file(f"Нет прав на создание директории: {directory}", "ERROR")
            return False
        except Exception as e:
            self.agi.verbose(f"❌ Ошибка при создании директории: {e}", 1)
            self.log_to_file(f"Ошибка при создании директории: {e}", "ERROR")
            return False

    def convert_wav_to_ogg(self, wav_path: str, ogg_path: str, quality: int = 5) -> bool:
        """
        Конвертирует WAV файл в OGG с помощью ffmpeg

        Args:
            wav_path: Путь к исходному WAV файлу
            ogg_path: Путь для сохранения OGG файла
            quality: Качество кодирования (0-10, где 5 - стандартное)

        Returns:
            True если конвертация успешна, иначе False
        """
        try:
            # Проверяем существование исходного файла
            if not os.path.exists(wav_path):
                self.agi.verbose(f"❌ WAV файл не найден: {wav_path}", 1)
                self.log_to_file(f"WAV файл не найден: {wav_path}", "ERROR")
                return False

            # Получаем информацию о файле
            wav_size = os.path.getsize(wav_path)
            wav_size_mb = wav_size / (1024 * 1024)
            self.agi.verbose(f"📊 Размер WAV: {wav_size_mb:.2f} MB", 1)
            self.log_to_file(f"Начало конвертации: {wav_path} ({wav_size_mb:.2f} MB)")

            # Проверяем и создаем директорию для выходного файла
            if not self.ensure_directory_exists(ogg_path):
                return False

            # Формируем команду ffmpeg
            cmd = [
                'ffmpeg',
                '-i', wav_path,              # Входной файл
                '-c:a', 'libvorbis',          # Кодек Vorbis для OGG
                '-q:a', str(quality),         # Качество звука (0-10)
                '-y',                          # Перезаписывать существующий
                '-loglevel', 'error',          # Только ошибки в вывод
                ogg_path                        # Выходной файл
            ]

            self.agi.verbose(f"🔄 Запуск конвертации...", 1)
            self.log_to_file(f"Команда: {' '.join(cmd)}")

            # Запускаем процесс
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60  # Максимум 60 секунд на конвертацию
            )

            # Проверяем результат
            if process.returncode == 0 and os.path.exists(ogg_path):
                ogg_size = os.path.getsize(ogg_path)
                ogg_size_mb = ogg_size / (1024 * 1024)
                compression_ratio = (ogg_size / wav_size * 100) if wav_size > 0 else 0

                self.agi.verbose(f"✅ Конвертация успешна!", 1)
                self.agi.verbose(f"📊 Размер OGG: {ogg_size_mb:.2f} MB ({compression_ratio:.1f}% от исходного)", 1)
                self.log_to_file(f"Успешно: {ogg_path} ({ogg_size_mb:.2f} MB, сжатие {compression_ratio:.1f}%)")

                # Удаляем исходный WAV файл
                try:
                    os.remove(wav_path)
                    self.agi.verbose(f"🗑️ Исходный WAV файл удален", 1)
                    self.log_to_file(f"WAV файл удален: {wav_path}")
                except Exception as e:
                    self.agi.verbose(f"⚠️ Не удалось удалить WAV: {e}", 2)
                    self.log_to_file(f"Ошибка удаления WAV: {e}", "WARNING")

                return True
            else:
                error_msg = process.stderr if process.stderr else "Неизвестная ошибка"
                self.agi.verbose(f"❌ Ошибка конвертации: {error_msg[:200]}", 1)
                self.log_to_file(f"Ошибка ffmpeg: {error_msg}", "ERROR")

                # Удаляем частично созданный файл если есть
                if os.path.exists(ogg_path):
                    try:
                        os.remove(ogg_path)
                        self.log_to_file(f"Удален поврежденный OGG файл")
                    except:
                        pass
                return False

        except subprocess.TimeoutExpired:
            self.agi.verbose("❌ Таймаут при конвертации (превышено 60 секунд)", 1)
            self.log_to_file("Таймаут при конвертации", "ERROR")
            return False
        except Exception as e:
            self.agi.verbose(f"❌ Неожиданная ошибка: {e}", 1)
            self.log_to_file(f"Неожиданная ошибка: {e}", "ERROR")
            return False

    def run(self) -> None:
        """Основной метод выполнения скрипта"""
        try:
            self.agi.verbose("=== НАЧАЛО КОНВЕРТАЦИИ АУДИО ===", 1)
            self.log_to_file("=== ЗАПУСК КОНВЕРТАЦИИ ===")

            # Получаем аргументы (пути к файлам)
            wav_path, ogg_path = self.get_arguments()
            if not wav_path or not ogg_path:
                self.agi.set_variable("CONVERT_STATUS", self.STATUS_NO_PATHS)
                self.agi.verbose("❌ Не переданы пути к файлам", 1)
                self.agi.verbose("❌ Используйте: AGI(convert_recording.py,${RECORDING_WAV},${RECORDING_OGG})", 1)
                self.log_to_file("Не переданы пути к файлам", "ERROR")
                return

            # Выводим информацию для отладки
            self.agi.verbose(f"📂 WAV файл: {wav_path}", 1)
            self.agi.verbose(f"📂 OGG файл: {ogg_path}", 1)

            # Проверяем наличие ffmpeg
            if not self.check_ffmpeg():
                self.agi.set_variable("CONVERT_STATUS", self.STATUS_FFMPEG_MISSING)
                self.agi.verbose("❌ ffmpeg не установлен. Установите: apt-get install ffmpeg", 1)
                self.log_to_file("ffmpeg не установлен", "ERROR")
                return

            # Проверяем существование WAV файла
            if not os.path.exists(wav_path):
                self.agi.set_variable("CONVERT_STATUS", self.STATUS_WAV_NOT_FOUND)
                self.agi.verbose(f"❌ WAV файл не существует: {wav_path}", 1)
                self.log_to_file(f"WAV файл не существует: {wav_path}", "ERROR")
                return

            # Получаем качество из переменной Asterisk (опционально)
            quality_str = self.agi.get_variable("OGG_QUALITY") or "5"
            try:
                quality = int(quality_str)
                quality = max(0, min(10, quality))  # Ограничиваем 0-10
            except ValueError:
                quality = 5
            self.agi.verbose(f"🎚️ Качество OGG: {quality} (0-10)", 1)

            # Выполняем конвертацию
            success = self.convert_wav_to_ogg(wav_path, ogg_path, quality)

            # Устанавливаем статус для диалплана
            if success:
                self.agi.set_variable("CONVERT_STATUS", self.STATUS_SUCCESS)
                self.agi.set_variable("AUDIO_FILE", ogg_path)
                self.agi.set_variable("AUDIO_FORMAT", "ogg")
                self.agi.verbose("✅ Статус: SUCCESS", 1)
                self.log_to_file("✅ Конвертация завершена успешно")
            else:
                self.agi.set_variable("CONVERT_STATUS", self.STATUS_FAILED)
                self.agi.set_variable("AUDIO_FILE", wav_path)  # В случае ошибки используем WAV
                self.agi.set_variable("AUDIO_FORMAT", "wav")
                self.agi.verbose("❌ Статус: FAILED", 1)
                self.log_to_file("❌ Конвертация завершилась с ошибкой")

            self.agi.verbose("=== ЗАВЕРШЕНИЕ КОНВЕРТАЦИИ АУДИО ===", 1)
            self.log_to_file("=== ЗАВЕРШЕНИЕ КОНВЕРТАЦИИ ===")

        except Exception as e:
            self.handle_error(e)

    def handle_error(self, error: Exception) -> None:
        """Обработка ошибок"""
        self.agi.set_variable("CONVERT_STATUS", self.STATUS_ERROR)
        self.agi.verbose(f"❌ Критическая ошибка в скрипте: {str(error)}", 1)
        self.log_to_file(f"Критическая ошибка: {error}", "ERROR")

        # Детальная информация для отладки
        if os.getenv("DEBUG") or os.getenv("ASTERISK_DEBUG"):
            traceback.print_exc(file=sys.stderr)
            self.agi.verbose(f"Traceback: {traceback.format_exc()}", 3)
            self.log_to_file(f"Traceback: {traceback.format_exc()}", "DEBUG")


# ────────────────────────────────────────────────
# Точка входа
# ────────────────────────────────────────────────
if __name__ == "__main__":
    converter = RecordingConverter()
    converter.run()
