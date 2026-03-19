-- Customer Success Database Schema
-- AI City - Customer Success Management

-- Customer Health Scores
CREATE TABLE IF NOT EXISTS customer_health_scores (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    health_score INTEGER CHECK (health_score >= 0 AND health_score <= 100),
    nps_score INTEGER CHECK (nps_score >= 0 AND nps_score <= 10),
    engagement_level VARCHAR(20) CHECK (engagement_level IN ('low', 'medium', 'high')),
    last_activity_at TIMESTAMP WITH TIME ZONE,
    calculated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_health_customer ON customer_health_scores(customer_id);
CREATE INDEX idx_health_calculated ON customer_health_scores(calculated_at);

-- Onboarding Milestones
CREATE TABLE IF NOT customer_onboarding_milestones (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    milestone_name VARCHAR(100) NOT NULL,
    milestone_order INTEGER NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'in_progress', 'completed', 'skipped')),
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_onboarding_customer ON customer_onboarding_milestones(customer_id);

-- Customer Check-ins
CREATE TABLE IF NOT EXISTS customer_checkins (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    checkin_type VARCHAR(50) NOT NULL CHECK (checkin_type IN ('weekly', 'monthly', 'quarterly', 'ad_hoc')),
    scheduled_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    status VARCHAR(20) DEFAULT 'scheduled' CHECK (status IN ('scheduled', 'completed', 'missed', 'cancelled')),
    notes TEXT,
    outcome VARCHAR(20) CHECK (outcome IN ('positive', 'neutral', 'negative', 'escalated')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_checkin_customer ON customer_checkins(customer_id);
CREATE INDEX idx_checkin_scheduled ON customer_checkins(scheduled_at);

-- Success Metrics
CREATE TABLE IF NOT EXISTS customer_success_metrics (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    metric_name VARCHAR(100) NOT NULL,
    metric_value DECIMAL(10, 2),
    target_value DECIMAL(10, 2),
    unit VARCHAR(20),
    recorded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    period_start DATE,
    period_end DATE
);

CREATE INDEX idx_metrics_customer ON customer_success_metrics(customer_id);
CREATE INDEX idx_metrics_recorded ON customer_success_metrics(recorded_at);

-- Churn Risk Alerts
CREATE TABLE IF NOT EXISTS churn_risk_alerts (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    risk_level VARCHAR(20) CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    trigger_events JSONB,
    risk_score INTEGER,
    status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'acknowledged', 'resolved', 'false_positive')),
    acknowledged_by INTEGER REFERENCES users(id),
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    resolution_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_churn_customer ON churn_risk_alerts(customer_id);
CREATE INDEX idx_churn_risk ON churn_risk_alerts(risk_level);

-- Customer Health Score Calculation Function
CREATE OR REPLACE FUNCTION calculate_customer_health_score(p_customer_id INTEGER)
RETURNS INTEGER AS $$
DECLARE
    v_score INTEGER := 50;
    v_nps INTEGER;
    v_engagement VARCHAR(20);
    v_days_inactive INTEGER;
    v_total_logins INTEGER;
    v_feature_usage INTEGER;
BEGIN
    -- NPS contribution (0-30 points)
    SELECT COALESCE(nps_score, 5) INTO v_nps
    FROM nps_surveys
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC
    LIMIT 1;

    v_score := v_score + (v_nps - 5) * 3;

    -- Engagement level (0-20 points)
    SELECT engagement_level INTO v_engagement
    FROM customer_health_scores
    WHERE customer_id = p_customer_id
    ORDER BY calculated_at DESC
    LIMIT 1;

    CASE v_engagement
        WHEN 'high' THEN v_score := v_score + 20;
        WHEN 'medium' THEN v_score := v_score + 10;
        WHEN 'low' THEN v_score := v_score + 0;
    END CASE;

    -- Activity recency (0-30 points)
    SELECT EXTRACT(DAY FROM NOW() - last_activity_at)::INTEGER INTO v_days_inactive
    FROM customers
    WHERE id = p_customer_id;

    CASE
        WHEN v_days_inactive <= 7 THEN v_score := v_score + 30;
        WHEN v_days_inactive <= 14 THEN v_score := v_score + 20;
        WHEN v_days_inactive <= 30 THEN v_score := v_score + 10;
        ELSE v_score := v_score + 0;
    END CASE;

    -- Feature usage (0-20 points)
    SELECT COUNT(*) INTO v_feature_usage
    FROM user_activity_log
    WHERE customer_id = p_customer_id
    AND created_at > NOW() - INTERVAL '30 days';

    CASE
        WHEN v_feature_usage > 100 THEN v_score := v_score + 20;
        WHEN v_feature_usage > 50 THEN v_score := v_score + 15;
        WHEN v_feature_usage > 20 THEN v_score := v_score + 10;
        ELSE v_score := v_score + 5;
    END CASE;

    -- Clamp to 0-100
    RETURN GREATEST(0, LEAST(100, v_score));
END;
$$ LANGUAGE plpgsql;

-- Create default onboarding milestones for a new customer
CREATE OR REPLACE FUNCTION create_default_onboarding_milestones(p_customer_id INTEGER)
RETURNS VOID AS $$
BEGIN
    INSERT INTO customer_onboarding_milestones (customer_id, milestone_name, milestone_order, status)
    VALUES
        (p_customer_id, 'Account Setup', 1, 'in_progress'),
        (p_customer_id, 'Profile Configuration', 2, 'pending'),
        (p_customer_id, 'First Feature Usage', 3, 'pending'),
        (p_customer_id, 'Team Invitation', 4, 'pending'),
        (p_customer_id, 'Onboarding Complete', 5, 'pending');
END;
$$ LANGUAGE plpgsql;
