Для развёртывания интеллектуального модуля для виртуальной АТС, необходимо выполнить следующие шаги:

### 1.

### 2.

### 3. Скопируйте содержимое директории agi-bin из репозитория DesolateSoul/alt-ATE-asterisk в локальную папку сервера /var/lib/asterisk/agi-bin/.

Команда для быстрой установки:

```bash
wget -qO- https://github.com/DesolateSoul/alt-ATE-asterisk/archive/refs/heads/main.tar.gz | tar -xzv --strip-components=2 -C /var/lib/asterisk/agi-bin/ alt-ATE-asterisk-main/agi-bin
```

После копирования файлов задайте правильного владельца и права на исполнение:

```bash
chown -R asterisk:asterisk /var/lib/asterisk/agi-bin/

chmod +x /var/lib/asterisk/agi-bin/*
```

### 4. Запустите Telegram бота в docker контейнере.

Все исходные файлы бота находятся в репозитории в папке telegram-bot-v2. Для сборки и запуска контейнера выполните следующие шаги:

Склонируйте репозиторий (если вы не сделали этого ранее) и перейдите в целевую директорию:

```bash
git clone https://github.com/DesolateSoul/alt-ATE-asterisk.git

cd alt-ATE-asterisk/telegram-bot-v2
```

Перед запуском обязательно настройте переменные окружения (токен бота, параметры подключения к БД и т.д.) путём создания файла .env:

```bash
nano .env
```

Запустите контейнер командой:

```bash
docker-compose up -d --build
```

### 5. Запустите Piper-tts

Установите необходимые зависимости:

``` sh
python3 -m pip install piper-tts[http]
```

Загрузите голос, например:

``` sh
python3 -m piper.download_voices ru_RU-ruslan-medium
```

Запустите веб-сервер:

``` sh
python3 -m piper.http_server -m ru_RU-ruslan-medium
```

Это запустит HTTP-сервер на порту 5000 (для изменения настроек используйте `--host` и `--port`).
Если голоса находятся в другой директории, используйте `--data-dir <DIR>`

### 6. Запустите автоматическую генерацию голосовых файлов для Asterisk

Скрипт create_asterisk_sounds.sh позволяет автоматически генерировать аудиофайлы через TTS-сервер (Text-to-Speech) и сразу конвертировать их в правильный формат для Asterisk (PCM, 16bit, 8000Hz, mono).

Скрипт записывает готовые файлы напрямую в /var/lib/asterisk/sounds. Для этого требуются права администратора (sudo).

Сделайте скрипт исполняемым:

```bash
chmod +x create_asterisk_sounds.sh
```

Вы можете использовать скрипт в трех разных режимах в зависимости от ваших задач:

Вариант А: Интерактивный режим (поштучное создание)

Используется, если нужно быстро сгенерировать один-два файла вручную через консоль.

```bash
sudo ./create_asterisk_sounds.sh -i
```

Скрипт поочередно запросит имя файла и текст для озвучки.

Вариант Б: Пакетный режим из файла (Рекомендуется для массовой генерации)

Сгенерируйте шаблон файла со списком фраз:

```bash
./create_asterisk_sounds.sh -e
```

(Будет создан файл-пример phrases_example.txt)

Заполните созданный файл или создайте свой (например, my_phrases.txt) в формате имя_файла|текст

например:

```text
welcome_ivr|Добро пожаловать в нашу компанию.
operator_busy|К сожалению, все операторы заняты.
```

Запустите пакетную генерацию:

```bash
sudo ./create_asterisk_sounds.sh my_phrases.txt
```

Важные примечания для пользователя

Зависимости: При первом запуске скрипт автоматически проверит наличие утилит curl (для запросов к TTS) и ffmpeg (для конвертации звука). Если их нет, установите их командой:

```bash
sudo apt-get update && sudo apt-get install -y curl ffmpeg
```
