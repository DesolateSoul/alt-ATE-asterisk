### Директория с конфигами asterisk
cd /etc/asterisk
### Директория с agi скриптами
cd /var/lib/asterisk/agi-bin
### Директория со звуками
cd /var/lib/asterisk/sounds
### Директория с бд
cd /home/alt/postgres-asterisk
### Директория с piper-tts
cd /etc/piper
### Директория с моделями piper-tts
cd /etc/piper/models
### Активация среды python для piper-tts
source .venv/bin/activate
### Запуск http сервера piper-tts
python3 -m piper.http_server -m /etc/piper/models/ru_RU-ruslan-medium.onnx
### Запись новых фраз (записываются в /var/lib/asterisk/sounds)
cd /var/lib/asterisk/agi-bin
./create_asterisk_sounds.sh phrases.txt
### Файл с диалпланом
nano /etc/asterisk/extensions.conf
### Файл с настройкой транка
nano /etc/asterisk/pjsip.conf
### Файл с логами asterisk
nano /var/log/asterisk/full
### Запуск docker контейнера vosk
docker run -d -p 2700:2700 alphacep/kaldi-ru:latest
### Запуск docker контейнера postgre
cd /home/alt/postgres-asterisk
docker compose up -d
### Переход в консоль asterisk
asterisk -rvvv
### Перезагрузка диалплана
dialplan reload
### Установка модулей asterisk
module load [название модуля]
