Для развёртывания интеллектуального модуля для виртуальной АТС, необходимо выполнить следующие шаги:

### 1. Установите Asterisk нужной версии из исходного кода 

Для начала обновите систему и установите базовые пакеты: 

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y build-essential git wget subversion \
libjansson-dev libxml2-dev uuid-dev libedit-dev \
libssl-dev curl pkg-config libncurses5-dev
```

Далее загрузите и распакуйте Asterisk: 

```bash
cd /usr/src
sudo wget https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-21-current.tar.gz
sudo tar xvf asterisk-21-current.tar.gz
cd asterisk-21.*/
```

Следующим шагом будет установка зависимостей и выбор модулей: 

```bash
sudo contrib/scripts/install_prereq install
sudo ./configure --with-jansson-bundled
sudo make menuselect
```

Скомпилируйте и установите Asterisk: 

```bash
sudo make -j$(nproc)
sudo make install
sudo make samples
sudo make config
sudo ldconfig
```

Создайте отдельного пользователя и наделите его правами: 

```bash
sudo adduser --system --group --no-create-home asterisk
sudo chown -R asterisk:asterisk /var/{lib,log,spool}/asterisk
sudo chown -R asterisk:asterisk /etc/asterisk
```

Запустите Asterisk и проведите первичную проверку подключившись к консоли: 

```bash
sudo systemctl enable asterisk
sudo systemctl start asterisk
sudo systemctl status asterisk
sudo asterisk -rvvv
```

### 2. Скопируйте содержимое директории config-files из репозитория DesolateSoul/alt-ATE-asterisk в локальную папку сервера /etc/asterisk/.

Команда для быстрой установки: 

```bash
wget -qO- https://github.com/DesolateSoul/alt-ATE-asterisk/archive/refs/heads/main.tar.gz | tar -xzv --strip-components=2 -C /etc/asterisk/ alt-ATE-asterisk-main/config-files
```

После копирования файлов задайте правильного владельца:

```bash
chown -R asterisk:asterisk /etc/asterisk/
```

### 3. Развертывание базы данных в Docker контейнере

Для начала, нужно создать БД на основном сервере посредством скрипта, с помощью команды:

Команда для создания БД:

```
psql -h localhost -p 5433 -U asterisk_user -d asterisk_db_v2 -f init.sql
```
Полный путь где находится скрипт: database/postgres-asterisk/init-scripts/init.sql

Затем необходимо запустить БД с помощью Docker контейнера. Для этого понадобиться docker-compose.yml файл, который расположен в директории: database/postgres-asterisk/docker-compose.yml 
Исполняемый файл запускаем следующей командой:

```
cd /home/alt/postgres-asterisk docker compose up -d
```

### 4. Интеграция Asterisk с сервером распознавания речи Vosk
Это модуль Asterisk для Vosk API сервера:

https://github.com/alphacep/vosk-server

Модуль протестирован с последней версией Asterisk из мастер-ветки git, но должен одинаково работать и с другими ветками (13, 16, 17).

## Установка

Убедитесь, что у вас установлена последняя версия Asterisk

```
git clone https://github.com/asterisk/asterisk
....
```

Сначала соберите модули

```
./bootstrap
./configure --with-asterisk=<path_to_asterisk_source> --prefix=<path_to_install>
make
make install
```
Создайте speech.conf и вставьте содержимое:

```
[general]
url = ws://10.7.35.3:2700
```
Этот файл определяет глобальный URL для движка распознавания речи (Speech Engine).

Создайте res_speech_vosk.conf и вставьте содержимое:

```
[general]
url = ws://10.7.35.3:2700
```
Файл конфигурации модуля res_speech_vosk.so, который отвечает за подключение именно к Vosk-серверу по WebSocket.

После внесения изменений выполнена перезагрузка соответствующих модулей и диалплана:

```bash
asterisk -rx "module reload res_speech_vosk.so"
asterisk -rx "dialplan reload"
```

### 5. Скопируйте содержимое директории agi-bin из репозитория DesolateSoul/alt-ATE-asterisk в локальную папку сервера /var/lib/asterisk/agi-bin/.

Команда для быстрой установки:

```bash
wget -qO- https://github.com/DesolateSoul/alt-ATE-asterisk/archive/refs/heads/main.tar.gz | tar -xzv --strip-components=2 -C /var/lib/asterisk/agi-bin/ alt-ATE-asterisk-main/agi-bin
```

После копирования файлов задайте правильного владельца и права на исполнение:

```bash
chown -R asterisk:asterisk /var/lib/asterisk/agi-bin/

chmod +x /var/lib/asterisk/agi-bin/*
```

### 6. Запустите Telegram бота в docker контейнере.

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

### 7. Запустите Piper-tts

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

### 8. Запустите автоматическую генерацию голосовых файлов для Asterisk

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

### 9. Запустите Asterisk Dashboard в Docker

Панель управления (asterisk-dashboard) реализована на базе веб-фреймворка Django и запускается в изолированном Docker-контейнере.

Перед запуском убедитесь, что в вашей системе:

Создана внешняя сеть Docker с именем asterisk-network (в ней должен работать ваш PostgreSQL-сервер). Если сети еще нет, создайте ее:

```bash
docker network create asterisk-network
```

Запущен и доступен контейнер с базой данных PostgreSQL под именем postgres-asterisk-v3

Перейдите в директорию с файлами панели управления:

```bash
cd alt-ATE-asterisk/asterisk-dashboard
```

Для безопасной передачи пароля от базы данных необходимо создать файл .env.

```bash
nano .env
```

Запустите сборку образа и старт контейнера в фоновом режиме:

```bash
docker compose up -d --build
```

После успешного запуска панель управления будет доступна в браузере по адресу: http://<IP_адрес_вашего_сервера>:8001
