Для развёртывания интеллектуального модуля для виртуальной АТС, необходимо выполнить следующие шаги:

1.

2.

3. Скопируйте содержимое директории agi-bin из репозитория DesolateSoul/alt-ATE-asterisk в локальную папку сервера /var/lib/asterisk/agi-bin/.

Команда для быстрой установки:

``bash
wget -qO- https://github.com/DesolateSoul/alt-ATE-asterisk/archive/refs/heads/main.tar.gz | tar -xzv --strip-components=2 -C /var/lib/asterisk/agi-bin/ alt-ATE-asterisk-main/agi-bin
``
