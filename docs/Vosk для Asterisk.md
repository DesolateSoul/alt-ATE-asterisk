# Модули распознавания речи Vosk для Asterisk
Это модуль Asterisk для Vosk API сервера:

https://github.com/alphacep/vosk-server

Модуль протестирован с последней версией Asterisk из мастер-ветки git, но должен одинаково работать и с другими ветками (13, 16, 17).

## Установка

1) Убедитесь, что у вас установлена последняя версия Asterisk

```
git clone https://github.com/asterisk/asterisk
....
```

2) Сначала соберите модули

```
./bootstrap
./configure --with-asterisk=<path_to_asterisk_source> --prefix=<path_to_install>
make
make install
```

например:

```
./bootstrap
./configure --with-asterisk=/usr --prefix=/usr
make
make install
```

3) Отредактируйте modules.conf для загрузки модулей

```
load = res_speech.so
load = res_http_websocket.so
load = res_speech_vosk.so
```

4) Отредактируйте диалплан в extensions.conf:

```
[internal]
exten = 1,1,Answer
same = n,Wait(1)
same = n,SpeechCreate
same = n,SpeechBackground(hello)
same = n,Verbose(0,Result was ${SPEECH_TEXT(0)})
```

5) Запустите сервер Vosk с помощью Docker

```
docker run -d -p 2700:2700 alphacep/kaldi-en:latest
```

6) Наберите внутренний номер и проверьте результат
