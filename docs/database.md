mkdir -p docs
cat > docs/database.md << 'EOF'
# Структура базы данных (версия 2)

База используется для верификации клиентов по ИНН + кодовому слову, сохранения текста проблемы и отправки уведомлений в Telegram.

## Таблица clients

| Столбец           | Тип           | Описание                                                                 | Обязательное |
|-------------------|---------------|--------------------------------------------------------------------------|--------------|
| id                | BIGSERIAL     | Автоинкрементный ID клиента                                              | PK           |
| inn               | BIGINT        | ИНН компании (уникальный)                                                | Да           |
| company_name      | VARCHAR(255)  | Название компании                                                        | Да           |
| code_word         | VARCHAR(100)  | Кодовое слово для верификации                                            | Да           |
| phone_number      | VARCHAR(30)   | Телефон заказчика                                                        | Нет          |
| telegram_chat_id  | BIGINT        | ID чата Telegram для отправки уведомлений о проблеме                     | Нет          |
| active            | BOOLEAN       | Активен ли клиент (true/false)                                           | Да (default true) |
| created_at        | TIMESTAMP     | Дата создания записи                                                     | Авто         |
| updated_at        | TIMESTAMP     | Дата последнего изменения                                                | Авто         |

## Таблица verification_logs

| Столбец               | Тип           | Описание                                                                 | Обязательное |
|-----------------------|---------------|--------------------------------------------------------------------------|--------------|
| id                    | BIGSERIAL     | ID записи                                                                | PK           |
| call_uniqueid         | VARCHAR(150)  | Уникальный ID звонка из Asterisk                                         | Нет          |
| caller_number         | VARCHAR(40)   | Номер телефона звонящего                                                 | Да           |
| spoken_inn            | BIGINT        | Распознанный ИНН (может не совпадать с реальным)                         | Нет          |
| matched_client_id     | BIGINT        | ID клиента из таблицы clients (если ИНН нашёлся)                         | Нет (FK)     |
| spoken_codeword       | VARCHAR(100)  | Распознанное кодовое слово                                               | Нет          |
| success               | BOOLEAN       | Успешна ли полная верификация                                            | Да (default false) |
| problem_text          | TEXT          | Текст проблемы, названный клиентом после верификации                     | Нет          |
| problem_recognized_at | TIMESTAMP     | Время распознавания проблемы                                             | Нет          |
| created_at            | TIMESTAMP     | Время создания записи                                                    | Авто         |

## Как применять init.sql

```bash
psql -h localhost -p 5433 -U asterisk_user -d asterisk_db_v2 -f init.sql
