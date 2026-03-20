-- AI City Backend Database Schema
-- PostgreSQL with pgvector for embeddings

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- API Keys table
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    key_hash VARCHAR(255) NOT NULL,
    name VARCHAR(100),
    rate_limit INTEGER DEFAULT 100,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    expires_at TIMESTAMP
);

-- Documents table for RAG
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500),
    content TEXT NOT NULL,
    content_type VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    embedding vector(768),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Create index for vector similarity search
CREATE INDEX IF NOT EXISTS idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Dashboard analytics table
CREATE TABLE IF NOT EXISTS dashboard_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    query_text TEXT,
    result_data JSONB,
    response_time_ms INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

-- API Request logs
CREATE TABLE IF NOT EXISTS api_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    api_key_id UUID REFERENCES api_keys(id) ON DELETE SET NULL,
    endpoint VARCHAR(255) NOT NULL,
    method VARCHAR(10) NOT NULL,
    status_code INTEGER,
    response_time_ms INTEGER,
    request_data JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_logs_created ON api_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_dashboard_analytics_created ON dashboard_analytics(created_at DESC);

-- Lead tracking table
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    source VARCHAR(100) NOT NULL,
    status VARCHAR(50) DEFAULT 'new',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for lead queries
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at DESC);

-- Reports table for automated reporting
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content JSONB NOT NULL,
    generated_at TIMESTAMP DEFAULT NOW(),
    period_start DATE,
    period_end DATE
);

CREATE INDEX IF NOT EXISTS idx_reports_generated ON reports(generated_at DESC);

-- Insert sample users
INSERT INTO users (email, name, role) VALUES
    ('admin@aicity.local', 'AI City Admin', 'admin'),
    ('api@aicity.local', 'API Service', 'service')
ON CONFLICT (email) DO NOTHING;

-- ============== Invoice System Tables ==============

-- Invoice table for Vietnamese e-invoices (Hóa đơn điện tử)
CREATE TABLE IF NOT EXISTS invoices (
    id SERIAL PRIMARY KEY,
    invoice_id VARCHAR(50) UNIQUE NOT NULL,  -- INV-YYYYMM-XXXX format
    invoice_number VARCHAR(50) UNIQUE NOT NULL,
    invoice_serial VARCHAR(20) NOT NULL,  -- For tax authority serialization

    -- Company info (seller)
    company_name VARCHAR(255) NOT NULL DEFAULT 'AI City',
    company_tax_id VARCHAR(20) NOT NULL DEFAULT '0123456789',
    company_address TEXT,
    company_email VARCHAR(255),
    company_phone VARCHAR(50),

    -- Customer info (buyer)
    customer_id UUID REFERENCES users(id),
    customer_name VARCHAR(255) NOT NULL,
    customer_tax_id VARCHAR(20),
    customer_address TEXT,
    customer_email VARCHAR(255),

    -- Invoice details
    subtotal NUMERIC(15, 2) NOT NULL DEFAULT 0,
    vat_rate NUMERIC(5, 2) NOT NULL DEFAULT 10,  -- 10% standard VAT
    vat_amount NUMERIC(15, 2) NOT NULL DEFAULT 0,
    total NUMERIC(15, 2) NOT NULL DEFAULT 0,
    total_in_words VARCHAR(500),  -- Vietnamese number to words

    -- Payment info
    payment_method VARCHAR(50),
    payment_status VARCHAR(20) DEFAULT 'pending',  -- pending, paid, refunded
    payment_transaction_id VARCHAR(100),

    -- Invoice metadata
    line_items JSONB NOT NULL DEFAULT '[]',  -- Array of {description, quantity, unit_price, total}
    notes TEXT,

    -- Tax compliance fields (Circular 78/2021/TT-BTC)
    invoice_pattern VARCHAR(20),  -- 1/2023/XYZ pattern
    invoice_type VARCHAR(20) DEFAULT 'electronic',  -- electronic, paper
    tax_authority_status VARCHAR(20) DEFAULT 'pending',  -- pending, submitted, accepted
    submitted_at TIMESTAMP,
    accepted_at TIMESTAMP,
    submission_deadline TIMESTAMP,  -- 72 hours from issue

    -- Status
    status VARCHAR(20) DEFAULT 'draft',  -- draft, issued, cancelled
    issued_at TIMESTAMP,
    cancelled_at TIMESTAMP,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for invoice queries
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_id ON invoices(invoice_id);
CREATE INDEX IF NOT EXISTS idx_invoices_invoice_number ON invoices(invoice_number);
CREATE INDEX IF NOT EXISTS idx_invoices_customer_id ON invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_payment_status ON invoices(payment_status);
CREATE INDEX IF NOT EXISTS idx_invoices_created ON invoices(created_at DESC);

-- Invoice sequence for serial number generation
CREATE SEQUENCE IF NOT EXISTS invoice_serial_seq START WITH 1;

-- ============== Payment System Tables ==============

-- Payments table
CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    payment_id VARCHAR(50) UNIQUE NOT NULL,  -- PAY-XXXXXXXXXXXX format
    order_id VARCHAR(50) NOT NULL,  -- ORD-YYYYMMDD-XXXXXX format

    amount NUMERIC(15, 0) NOT NULL,  -- Amount in VND
    currency VARCHAR(10) NOT NULL DEFAULT 'VND',
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- pending, completed, failed, refunded

    payment_method VARCHAR(20) NOT NULL,  -- stripe, vietqr, momo, bank_transfer

    -- Customer info
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),

    -- Payment method specific
    checkout_url VARCHAR(500),  -- For Stripe/MoMo redirect
    qr_code VARCHAR(1000),  -- For VietQR QR code
    transaction_id VARCHAR(100),  -- Provider's transaction ID

    -- Expiration
    expires_at TIMESTAMP NOT NULL,

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for payment queries
CREATE INDEX IF NOT EXISTS idx_payments_payment_id ON payments(payment_id);
CREATE INDEX IF NOT EXISTS idx_payments_order_id ON payments(order_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);
CREATE INDEX IF NOT EXISTS idx_payments_customer_email ON payments(customer_email);
CREATE INDEX IF NOT EXISTS idx_payments_expires ON payments(expires_at);

-- Revenue Transactions table
CREATE TABLE IF NOT EXISTS revenue_transactions (
    id SERIAL PRIMARY KEY,
    transaction_id VARCHAR(50) UNIQUE NOT NULL,  -- TXN-XXXXXXXXXXXX format

    -- Payment reference
    payment_id VARCHAR(50) REFERENCES payments(payment_id),
    order_id VARCHAR(50),

    -- Revenue amount
    amount NUMERIC(15, 0) NOT NULL,  -- Amount in VND
    currency VARCHAR(10) NOT NULL DEFAULT 'VND',

    -- Customer
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(255),
    customer_location VARCHAR(100),  -- City, Country for globe visualization

    -- Source
    payment_method VARCHAR(20) NOT NULL,  -- stripe, vietqr, momo, bank_transfer
    transaction_ref VARCHAR(100),  -- Provider's transaction ID

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'completed',  -- completed, refunded

    -- Geo location for globe (latitude, longitude)
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    transaction_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for revenue queries
CREATE INDEX IF NOT EXISTS idx_revenue_transaction_id ON revenue_transactions(transaction_id);
CREATE INDEX IF NOT EXISTS idx_revenue_customer_email ON revenue_transactions(customer_email);
CREATE INDEX IF NOT EXISTS idx_revenue_status ON revenue_transactions(status);
CREATE INDEX IF NOT EXISTS idx_revenue_transaction_date ON revenue_transactions(transaction_date);
CREATE INDEX IF NOT EXISTS idx_revenue_payment_method ON revenue_transactions(payment_method);

-- Subscriptions table
CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    subscription_id VARCHAR(50) UNIQUE NOT NULL,  -- SUB-XXXXXXXXXX format

    -- Customer
    customer_id UUID REFERENCES users(id),
    customer_email VARCHAR(255) NOT NULL,

    -- Plan
    plan VARCHAR(20) NOT NULL,  -- starter, pro, business
    plan_name VARCHAR(50),

    -- Status
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, paused, cancelled, expired

    -- Period
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMP NOT NULL,
    paused_at TIMESTAMP,
    cancelled_at TIMESTAMP,

    -- Payment
    payment_id VARCHAR(50) REFERENCES payments(payment_id),

    -- Limits
    ai_runs_used INTEGER DEFAULT 0,
    ai_runs_limit INTEGER,  -- Based on plan
    documents_limit INTEGER,  -- Based on plan

    -- Auto-renewal
    auto_renew BOOLEAN DEFAULT true,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for subscription queries
CREATE INDEX IF NOT EXISTS idx_subscriptions_subscription_id ON subscriptions(subscription_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_customer_email ON subscriptions(customer_email);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_subscriptions_expires ON subscriptions(expires_at);

-- Composite indexes for performance optimization (AIC-405)
CREATE INDEX IF NOT EXISTS idx_leads_status_source ON leads(status, source);
CREATE INDEX IF NOT EXISTS idx_leads_status_created ON leads(status, created_at);
CREATE INDEX IF NOT EXISTS idx_revenue_transactions_status_date ON revenue_transactions(status, transaction_date);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status_expires ON subscriptions(status, expires_at);
