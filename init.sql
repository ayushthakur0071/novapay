-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- USERS Table
CREATE TABLE IF NOT EXISTS users (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  full_name        VARCHAR(100) NOT NULL,
  email            VARCHAR(255) UNIQUE NOT NULL,
  phone            VARCHAR(20) UNIQUE NOT NULL,
  password_hash    VARCHAR(255) NOT NULL,
  date_of_birth    DATE NOT NULL,
  address          TEXT,
  city             VARCHAR(100),
  postcode         VARCHAR(20),
  country          VARCHAR(100) DEFAULT 'United Kingdom',
  is_active        BOOLEAN DEFAULT TRUE,
  is_admin         BOOLEAN DEFAULT FALSE,
  is_verified      BOOLEAN DEFAULT FALSE,
  kyc_status       VARCHAR(20) DEFAULT 'pending',
  failed_attempts  INTEGER DEFAULT 0,
  locked_until     TIMESTAMPTZ,
  last_login       TIMESTAMPTZ,
  mfa_enabled      BOOLEAN DEFAULT FALSE,
  mfa_secret       VARCHAR(32),
  kyc_document_type VARCHAR(50),
  kyc_document_file TEXT,
  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- ACCOUNTS Table
CREATE TABLE IF NOT EXISTS accounts (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  account_number    VARCHAR(20) UNIQUE NOT NULL,
  sort_code         VARCHAR(10) NOT NULL DEFAULT '20-45-91',
  account_type      VARCHAR(30) NOT NULL DEFAULT 'current',
  currency          VARCHAR(3) DEFAULT 'GBP',
  balance           NUMERIC(15,2) NOT NULL DEFAULT 0.00,
  available_balance NUMERIC(15,2) NOT NULL DEFAULT 0.00,
  overdraft_limit   NUMERIC(15,2) DEFAULT 0.00,
  nickname          VARCHAR(100),
  is_active         BOOLEAN DEFAULT TRUE,
  is_frozen         BOOLEAN DEFAULT FALSE,
  created_at        TIMESTAMPTZ DEFAULT NOW(),
  CONSTRAINT balance_ok CHECK (balance >= -overdraft_limit)
);

-- TRANSACTIONS Table
CREATE TABLE IF NOT EXISTS transactions (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_account_id   UUID REFERENCES accounts(id) ON DELETE SET NULL,
  to_account_id     UUID REFERENCES accounts(id) ON DELETE SET NULL,
  transaction_ref   VARCHAR(30) UNIQUE NOT NULL,
  transaction_type  VARCHAR(30) NOT NULL,
  amount            NUMERIC(15,2) NOT NULL CHECK (amount > 0),
  currency          VARCHAR(3) DEFAULT 'GBP',
  description       TEXT,
  reference         VARCHAR(200),
  category          VARCHAR(50) DEFAULT 'other',
  status            VARCHAR(20) DEFAULT 'completed',
  balance_after     NUMERIC(15,2),
  ip_address        VARCHAR(45),
  fee               NUMERIC(15,2) DEFAULT 0.00,
  transfer_method   VARCHAR(30) DEFAULT 'IMPS',
  created_at        TIMESTAMPTZ DEFAULT NOW()
);

-- BENEFICIARIES Table
CREATE TABLE IF NOT EXISTS beneficiaries (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  nickname        VARCHAR(100) NOT NULL,
  full_name       VARCHAR(100) NOT NULL,
  account_number  VARCHAR(20) NOT NULL,
  sort_code       VARCHAR(10) NOT NULL,
  bank_name       VARCHAR(100),
  reference       VARCHAR(200),
  is_trusted      BOOLEAN DEFAULT FALSE,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW(),
  last_used       TIMESTAMPTZ,
  UNIQUE(user_id, account_number, sort_code)
);

-- CARDS Table
CREATE TABLE IF NOT EXISTS cards (
  id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id                UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  masked_number             VARCHAR(19) NOT NULL,
  cardholder_name           VARCHAR(100) NOT NULL,
  expiry_month              INTEGER NOT NULL,
  expiry_year               INTEGER NOT NULL,
  card_type                 VARCHAR(20) DEFAULT 'debit',
  card_network              VARCHAR(20) DEFAULT 'Visa',
  is_active                 BOOLEAN DEFAULT TRUE,
  is_frozen                 BOOLEAN DEFAULT FALSE,
  contactless_enabled       BOOLEAN DEFAULT TRUE,
  online_payments_enabled   BOOLEAN DEFAULT TRUE,
  international_payments    BOOLEAN DEFAULT FALSE,
  daily_limit               NUMERIC(10,2) DEFAULT 1000.00,
  encrypted_card_number     TEXT,
  encrypted_cvv             TEXT,
  created_at                TIMESTAMPTZ DEFAULT NOW()
);

-- STANDING ORDERS Table
CREATE TABLE IF NOT EXISTS standing_orders (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_account_id UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  beneficiary_id  UUID NOT NULL REFERENCES beneficiaries(id) ON DELETE CASCADE,
  amount          NUMERIC(15,2) NOT NULL,
  reference       VARCHAR(200),
  frequency       VARCHAR(20) NOT NULL,
  start_date      DATE NOT NULL,
  end_date        DATE,
  next_payment    DATE NOT NULL,
  is_active       BOOLEAN DEFAULT TRUE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- NOTIFICATIONS Table
CREATE TABLE IF NOT EXISTS notifications (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title       VARCHAR(200) NOT NULL,
  message     TEXT NOT NULL,
  type        VARCHAR(30) DEFAULT 'info',
  is_read     BOOLEAN DEFAULT FALSE,
  action_url  VARCHAR(500),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- SUPPORT TICKETS Table
CREATE TABLE IF NOT EXISTS support_tickets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  ticket_ref  VARCHAR(20) UNIQUE NOT NULL,
  subject     VARCHAR(200) NOT NULL,
  description TEXT NOT NULL,
  category    VARCHAR(50),
  status      VARCHAR(20) DEFAULT 'open',
  priority    VARCHAR(10) DEFAULT 'normal',
  created_at  TIMESTAMPTZ DEFAULT NOW(),
  updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- MONITORING LOGS Table
CREATE TABLE IF NOT EXISTS monitoring_logs (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  server         VARCHAR(50) NOT NULL,
  status         VARCHAR(20) NOT NULL,
  response_time  NUMERIC(10,3),
  cpu_usage      NUMERIC(5,2),
  memory_usage   NUMERIC(5,2),
  active_sessions INTEGER DEFAULT 0,
  region         VARCHAR(50),
  error_message  TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

-- FAILOVER EVENTS Table
CREATE TABLE IF NOT EXISTS failover_events (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_server     VARCHAR(50) NOT NULL,
  to_server       VARCHAR(50) NOT NULL,
  trigger_reason  TEXT,
  rto_seconds     NUMERIC(10,3),
  triggered_at    TIMESTAMPTZ DEFAULT NOW(),
  resolved_at     TIMESTAMPTZ,
  triggered_by    VARCHAR(50) DEFAULT 'decision_engine'
);

-- AUDIT LOGS Table
CREATE TABLE IF NOT EXISTS audit_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  action      VARCHAR(100) NOT NULL,
  resource    VARCHAR(100),
  resource_id UUID,
  old_value   JSONB,
  new_value   JSONB,
  ip_address  VARCHAR(45),
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- SAVINGS GOALS Table (extra feature)
CREATE TABLE IF NOT EXISTS savings_goals (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id      UUID NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  name            VARCHAR(100) NOT NULL,
  target_amount   NUMERIC(15,2) NOT NULL,
  current_amount  NUMERIC(15,2) DEFAULT 0.00,
  target_date     DATE,
  icon            VARCHAR(50) DEFAULT '🎯',
  is_completed    BOOLEAN DEFAULT FALSE,
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- SPENDING BUDGETS Table (extra feature)
CREATE TABLE IF NOT EXISTS spending_budgets (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  category    VARCHAR(50) NOT NULL,
  limit_amount NUMERIC(10,2) NOT NULL,
  month       VARCHAR(7) NOT NULL,  -- YYYY-MM
  UNIQUE(user_id, category, month)
);

-- INDEXES
CREATE INDEX IF NOT EXISTS idx_txn_from     ON transactions(from_account_id);
CREATE INDEX IF NOT EXISTS idx_txn_to       ON transactions(to_account_id);
CREATE INDEX IF NOT EXISTS idx_txn_date     ON transactions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_acc_user     ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_notif_user   ON notifications(user_id, is_read);
CREATE INDEX IF NOT EXISTS idx_ben_user     ON beneficiaries(user_id);
CREATE INDEX IF NOT EXISTS idx_mon_server   ON monitoring_logs(server, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user   ON audit_logs(user_id, created_at DESC);
