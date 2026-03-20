-- Analytics Database Schema
-- Tables for Telesales, Conversion Funnel, and ROI tracking

-- Telesales Calls
CREATE TABLE IF NOT EXISTS telesales_calls (
    call_id VARCHAR(50) PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    agent_name VARCHAR(100) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20) NOT NULL,
    call_duration INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    intent VARCHAR(50),
    revenue DECIMAL(12, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_telesales_calls_agent ON telesales_calls(agent_id);
CREATE INDEX idx_telesales_calls_status ON telesales_calls(status);
CREATE INDEX idx_telesales_calls_created ON telesales_calls(created_at);

-- Funnel Events
CREATE TABLE IF NOT EXISTS funnel_events (
    event_id SERIAL PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    source VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_funnel_events_customer ON funnel_events(customer_id);
CREATE INDEX idx_funnel_events_type ON funnel_events(event_type);
CREATE INDEX idx_funnel_events_created ON funnel_events(created_at);

-- Agent Costs
CREATE TABLE IF NOT EXISTS agent_costs (
    cost_id SERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    cost_type VARCHAR(30) NOT NULL,
    cost DECIMAL(10, 2) NOT NULL,
    cost_date DATE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_agent_costs_agent ON agent_costs(agent_id);
CREATE INDEX idx_agent_costs_date ON agent_costs(cost_date);

-- Agent Usage
CREATE TABLE IF NOT EXISTS agent_usage (
    usage_id SERIAL PRIMARY KEY,
    agent_id VARCHAR(50) NOT NULL,
    user_id VARCHAR(50),
    action VARCHAR(50) NOT NULL,
    tokens_used INTEGER,
    cost DECIMAL(10, 2),
    used_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_agent_usage_agent ON agent_usage(agent_id);
CREATE INDEX idx_agent_usage_user ON agent_usage(user_id);
CREATE INDEX idx_agent_usage_at ON agent_usage(used_at);