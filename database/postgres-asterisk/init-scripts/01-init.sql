-- init.sql — структура базы данных версии 2 (февраль 2026)
-- Используется для PostgreSQL 17 в контейнере postgres-asterisk-v2

-- Таблица клиентов (справочник заказчиков)
CREATE TABLE IF NOT EXISTS clients (
    id                BIGSERIAL PRIMARY KEY,
    inn               BIGINT UNIQUE NOT NULL,
    company_name      VARCHAR(255) NOT NULL,
    code_word         VARCHAR(100) NOT NULL,
    phone_number      VARCHAR(30),
    telegram_chat_id  BIGINT,
    active            BOOLEAN DEFAULT true,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Таблица логов верификации и проблем
CREATE TABLE IF NOT EXISTS verification_logs (
    id                  BIGSERIAL PRIMARY KEY,
    call_uniqueid       VARCHAR(150) NOT NULL,
    caller_number       VARCHAR(40),
    spoken_inn          BIGINT,
    matched_client_id   BIGINT REFERENCES clients(id) ON DELETE SET NULL,
    spoken_codeword     VARCHAR(100),
    success             BOOLEAN DEFAULT false,
    problem_text        TEXT,
    problem_recognized_at TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_verif_caller ON verification_logs (caller_number);
CREATE INDEX IF NOT EXISTS idx_verif_client ON verification_logs (matched_client_id);
CREATE INDEX IF NOT EXISTS idx_verif_time ON verification_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_verif_success ON verification_logs (success);

-- Функция для автоматического обновления updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Триггер для автоматического обновления updated_at в clients
DROP TRIGGER IF EXISTS update_clients_updated_at ON clients;
CREATE TRIGGER update_clients_updated_at
    BEFORE UPDATE ON clients
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Пример начальных данных
INSERT INTO clients (inn, company_name, code_word, phone_number)
VALUES 
    (4205128383, 'Альт-Компьютерс', 'альт', '+7 (3842) 57-11-11'),
    (4207017537, 'КемГУ', 'корпус', '+7 (3842) 58-12-39'),
    (4205242442, 'СДЭК-Кемерово', 'синий', '+7 (3842) 77-88-99')
ON CONFLICT (inn) DO NOTHING;

-- Создание пользователя для приложения (опционально)
DO
$do$
BEGIN
   IF NOT EXISTS (
      SELECT FROM pg_catalog.pg_roles
      WHERE  rolname = 'asterisk_app') THEN
      CREATE USER asterisk_app WITH PASSWORD 'secure_password_change_me';
   END IF;
END
$do$;

-- Grant privileges
GRANT CONNECT ON DATABASE asterisk_db TO asterisk_app;
GRANT USAGE ON SCHEMA public TO asterisk_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO asterisk_app;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO asterisk_app;
