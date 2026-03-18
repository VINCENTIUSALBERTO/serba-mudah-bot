-- =============================================================================
-- Serba Mudah Bot — Supabase Schema
-- Run each CREATE TABLE once in the Supabase SQL editor.
-- =============================================================================

-- Users (one row per Telegram user)
CREATE TABLE IF NOT EXISTS users (
    id          BIGINT PRIMARY KEY,         -- Telegram user ID
    username    TEXT,
    balance     NUMERIC NOT NULL DEFAULT 0,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT,
    price       NUMERIC NOT NULL,
    is_active   BOOLEAN NOT NULL DEFAULT true,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Orders
CREATE TABLE IF NOT EXISTS orders (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(id),
    username       TEXT,
    product_id     BIGINT REFERENCES products(id),
    quantity       INTEGER NOT NULL DEFAULT 1,
    total_price    NUMERIC,
    payment_method TEXT,    -- "Saldo" | "QRIS"
    status         TEXT NOT NULL DEFAULT 'pending',
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Top-up requests
CREATE TABLE IF NOT EXISTS topups (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(id),
    amount           NUMERIC NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',  -- pending | approved | rejected
    proof_message_id BIGINT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Product accounts (stock)
CREATE TABLE IF NOT EXISTS product_accounts (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id  BIGINT NOT NULL REFERENCES products(id),
    credential  TEXT NOT NULL,   -- email:password
    is_sold     BOOLEAN NOT NULL DEFAULT false,
    order_id    BIGINT REFERENCES orders(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- =============================================================================
-- Payment methods  (NEW — required for the improved top-up feature)
-- =============================================================================
CREATE TABLE IF NOT EXISTS payment_methods (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider_name   TEXT NOT NULL,          -- e.g. BCA, BRI, GoPay, OVO
    account_number  TEXT NOT NULL,          -- rekening / nomor e-wallet
    account_holder  TEXT NOT NULL,          -- atas nama
    qris_file_id    TEXT,                   -- Telegram file_id of QRIS image (nullable)
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
