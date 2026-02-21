#!/bin/bash

# Скрипт для автоматизации создания голосовых файлов для Asterisk
# Использование: ./create_asterisk_sounds.sh [файл_со_списком_фраз.txt]

# Конфигурация
SOUNDS_DIR="/var/lib/asterisk/sounds"
TTS_SERVER="localhost:5000"
LANGUAGE="ru"  # или "en" для английского

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Функция для логирования
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Функция для проверки зависимостей
check_dependencies() {
    log_info "Проверка зависимостей..."
    
    if ! command -v curl &> /dev/null; then
        log_error "curl не установлен. Установите: apt-get install curl"
        exit 1
    fi
    
    if ! command -v ffmpeg &> /dev/null; then
        log_error "ffmpeg не установлен. Установите: apt-get install ffmpeg"
        exit 1
    fi
    
    # Проверка доступности TTS сервера
    if ! curl -s "http://$TTS_SERVER" &> /dev/null; then
        log_warn "TTS сервер недоступен по адресу http://$TTS_SERVER"
        read -p "Продолжить? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    log_info "Все зависимости найдены"
}

# Функция для создания одного голосового файла
create_sound_file() {
    local text="$1"
    local filename="$2"
    local temp_file="/tmp/${filename}_temp.wav"
    
    log_info "Создание файла: $filename.wav"
    log_info "Текст: $text"
    
    # Создание временного файла через TTS
    if ! curl -X POST \
         -H 'Content-Type: application/json' \
         -d "{ \"text\": \"$text\", \"language\": \"$LANGUAGE\" }" \
         -o "$temp_file" \
         "http://$TTS_SERVER" 2>/dev/null; then
        log_error "Ошибка при создании временного файла для $filename"
        return 1
    fi
    
    # Конвертация в формат Asterisk
    if ! ffmpeg -i "$temp_file" \
                -ar 8000 \
                -ac 1 \
                -c:a pcm_s16le \
                -y \
                "$SOUNDS_DIR/${filename}.wav" 2>/dev/null; then
        log_error "Ошибка при конвертации файла $filename"
        rm -f "$temp_file"
        return 1
    fi
    
    # Очистка временного файла
    rm -f "$temp_file"
    
    log_info "Файл успешно создан: $SOUNDS_DIR/${filename}.wav"
    return 0
}

# Функция для обработки файла со списком фраз
process_phrases_file() {
    local phrases_file="$1"
    local line_num=0
    local success_count=0
    local error_count=0
    
    if [[ ! -f "$phrases_file" ]]; then
        log_error "Файл не найден: $phrases_file"
        return 1
    fi
    
    log_info "Обработка файла: $phrases_file"
    
    while IFS='|' read -r filename text || [[ -n "$filename" ]]; do
        line_num=$((line_num + 1))
        
        # Пропускаем пустые строки и комментарии
        if [[ -z "$filename" || "$filename" == \#* ]]; then
            continue
        fi
        
        # Удаляем пробелы в начале и конце
        filename=$(echo "$filename" | xargs)
        text=$(echo "$text" | xargs)
        
        if [[ -z "$filename" || -z "$text" ]]; then
            log_warn "Строка $line_num: пропущена (некорректный формат)"
            continue
        fi
        
        if create_sound_file "$text" "$filename"; then
            success_count=$((success_count + 1))
        else
            error_count=$((error_count + 1))
        fi
        
        # Небольшая задержка между запросами
        sleep 1
        
    done < "$phrases_file"
    
    log_info "Обработка завершена. Успешно: $success_count, Ошибок: $error_count"
}

# Функция для интерактивного режима
interactive_mode() {
    echo "=== Интерактивный режим создания голосовых файлов ==="
    echo
    
    while true; do
        read -p "Введите имя файла (без .wav): " filename
        if [[ -z "$filename" ]]; then
            break
        fi
        
        read -p "Введите текст для озвучивания: " text
        if [[ -z "$text" ]]; then
            log_warn "Текст не может быть пустым"
            continue
        fi
        
        create_sound_file "$text" "$filename"
        
        echo
        read -p "Создать еще один файл? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            break
        fi
        echo
    done
}

# Функция для создания примера файла с фразами
create_example_file() {
    local example_file="phrases_example.txt"
    
    if [[ -f "$example_file" ]]; then
        log_warn "Файл $example_file уже существует"
        return
    fi
    
    cat > "$example_file" << 'EOF'
# Формат: имя_файла|текст для озвучивания
# Примеры:
welcome|Добро пожаловать в нашу компанию
goodbye|До свидания! Спасибо за звонок
invalid_number|Вы набрали неправильный номер
hold_music|Пожалуйста, оставайтесь на линии
main_menu|Главное меню. Нажмите 1 для продаж, 2 для поддержки
hours|Наш офис работает с 9 до 18 с понедельника по пятницу
email|Наш электронный адрес info@company.com
website|Посетите наш сайт www.company.com
EOF
    
    log_info "Создан пример файла: $example_file"
}

# Главная функция
main() {
    # Проверка прав на запись в директорию звуков
    if [[ ! -w "$SOUNDS_DIR" ]]; then
        log_error "Нет прав на запись в $SOUNDS_DIR"
        log_info "Попробуйте запустить скрипт с sudo"
        exit 1
    fi
    
    # Проверка зависимостей
    check_dependencies
    
    # Создание директории если не существует
    mkdir -p "$SOUNDS_DIR"
    
    # Обработка аргументов командной строки
    case "$1" in
        --example|-e)
            create_example_file
            ;;
        --help|-h)
            echo "Использование: $0 [OPTION] [FILE]"
            echo
            echo "Опции:"
            echo "  -e, --example    Создать пример файла с фразами"
            echo "  -i, --interactive Интерактивный режим"
            echo "  -h, --help       Показать эту справку"
            echo
            echo "Если указан FILE, обрабатывает файл со списком фраз"
            echo "Без аргументов запускает интерактивный режим"
            ;;
        --interactive|-i)
            interactive_mode
            ;;
        "")
            interactive_mode
            ;;
        *)
            if [[ -f "$1" ]]; then
                process_phrases_file "$1"
            else
                log_error "Файл не найден: $1"
                exit 1
            fi
            ;;
    esac
}

# Запуск главной функции
main "$@"
