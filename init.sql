cat > init.sql << 'EOF'
-- init.sql — структура базы данных версии 2 (февраль 2026)
-- Используется для PostgreSQL 17 в контейнере postgres-asterisk-v2

-- Таблица клиентов (справочник заказчиков)
CREATE TABLE IF NOT EXISTS clients (
    id                BIGSERIAL PRIMARY KEY,
    inn               BIGINT UNIQUE NOT NULL,           -- ИНН компании (10/12 цифр)
    company_name      VARCHAR(255) NOT NULL,             -- Название компании
    code_word         VARCHAR(100) NOT NULL,             -- Кодовое слово для верификации
    phone_number      VARCHAR(30),                       -- Телефон заказчика (опционально)
    telegram_chat_id  BIGINT,                            -- ID чата Telegram для уведомлений
    active            BOOLEAN DEFAULT true,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица логов верификации и проблем
CREATE TABLE IF NOT EXISTS verification_logs (
    id                  BIGSERIAL PRIMARY KEY,
    call_uniqueid       VARCHAR(150),                    -- ID звонка из Asterisk
    caller_number       VARCHAR(40) NOT NULL,            -- Номер звонящего
    spoken_inn          BIGINT,                          -- Что распознал Vosk как ИНН
    matched_client_id   BIGINT REFERENCES clients(id) ON DELETE SET NULL,
    spoken_codeword     VARCHAR(100),                    -- Что сказал как кодовое слово
    success             BOOLEAN DEFAULT false,           -- Успешна ли верификация полностью
    problem_text        TEXT,                            -- Распознанный текст проблемы клиента
    problem_recognized_at TIMESTAMP,                     -- Время распознавания проблемы
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_verif_caller ON verification_logs (caller_number);
CREATE INDEX IF NOT EXISTS idx_verif_client ON verification_logs (matched_client_id);
CREATE INDEX IF NOT EXISTS idx_verif_time   ON verification_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verif_success ON verification_logs (success);

-- Пример начальных данных (можно выполнять только один раз)
-- INSERT INTO clients (inn, company_name, code_word)
-- VALUES
--     (4205128383, 'Альт-Компьютерс', 'альт'),
--     (4207017537, 'КемГУ', 'корпус')
-- ON CONFLICT (inn) DO NOTHING;
EOF
