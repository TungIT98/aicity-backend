-- ============================================================
-- Globe AI City Data Layer - PostgreSQL Schema
-- Anno 117-inspired modular data structure
-- CTO: AI City Backend Division
-- ============================================================

-- ============================================================
-- 1. PROVINCE DATA STORE
-- Industry / Region / Tier classification system
-- ============================================================

-- Industries (ngành)
CREATE TABLE IF NOT EXISTS globe_industries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    description TEXT,
    icon VARCHAR(50),
    color VARCHAR(7),  -- hex color for UI
    parent_id UUID REFERENCES globe_industries(id),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Regions (vùng)
CREATE TABLE IF NOT EXISTS globe_regions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    country VARCHAR(100) DEFAULT 'Vietnam',
    latitude NUMERIC(10, 6),
    longitude NUMERIC(10, 6),
    timezone VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Company Tiers (cấp)
CREATE TABLE IF NOT EXISTS globe_tiers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    name_vi VARCHAR(100),
    description TEXT,
    min_employees INTEGER,
    max_employees INTEGER,
    revenue_range VARCHAR(50),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Province = Industry + Region + Tier intersection
CREATE TABLE IF NOT EXISTS globe_provinces (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    description TEXT,
    industry_id UUID REFERENCES globe_industries(id),
    region_id UUID REFERENCES globe_regions(id),
    tier_id UUID REFERENCES globe_tiers(id),
    -- Anno 117 style metadata
    metadata JSONB DEFAULT '{}',
    -- Visual data for Globe UI
    node_size VARCHAR(20) DEFAULT 'medium',  -- small, medium, large
    node_color VARCHAR(7) DEFAULT '#6366f1',
    -- Statistics
    total_companies INTEGER DEFAULT 0,
    total_revenue NUMERIC(15, 0) DEFAULT 0,
    total_leads INTEGER DEFAULT 0,
    -- Status
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_provinces_industry ON globe_provinces(industry_id);
CREATE INDEX IF NOT EXISTS idx_provinces_region ON globe_provinces(region_id);
CREATE INDEX IF NOT EXISTS idx_provinces_tier ON globe_provinces(tier_id);
CREATE INDEX IF NOT EXISTS idx_provinces_active ON globe_provinces(is_active);

-- ============================================================
-- 2. PRODUCTION CHAIN TRACKING
-- Lead -> Contact -> Qualified -> Customer flow
-- ============================================================

-- Production chain definition (chain templates)
CREATE TABLE IF NOT EXISTS globe_chains (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    description TEXT,
    stages JSONB NOT NULL DEFAULT '[]',  -- [{stage, name, name_vi, duration_days, conversion_rate}]
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Individual chain instances (companies in the chain)
CREATE TABLE IF NOT EXISTS globe_chain_instances (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_id UUID REFERENCES globe_chains(id),
    province_id UUID REFERENCES globe_provinces(id),
    -- Company info
    company_name VARCHAR(255) NOT NULL,
    company_email VARCHAR(255),
    company_phone VARCHAR(50),
    contact_name VARCHAR(255),
    contact_email VARCHAR(255),
    -- Current stage
    current_stage VARCHAR(50) NOT NULL DEFAULT 'lead',
    stage_order INTEGER DEFAULT 0,
    -- Pipeline data
    pipeline_value NUMERIC(15, 0) DEFAULT 0,  -- Expected value in VND
    actual_value NUMERIC(15, 0) DEFAULT 0,     -- Realized value
    probability NUMERIC(5, 2) DEFAULT 0,        -- 0-100%
    -- Timing
    entered_at TIMESTAMP DEFAULT NOW(),
    stage_changed_at TIMESTAMP DEFAULT NOW(),
    closed_at TIMESTAMP,
    -- Funnel source
    source VARCHAR(100),
    utm_campaign VARCHAR(255),
    utm_medium VARCHAR(100),
    utm_source VARCHAR(100),
    -- Metadata
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chain_instances_chain ON globe_chain_instances(chain_id);
CREATE INDEX IF NOT EXISTS idx_chain_instances_province ON globe_chain_instances(province_id);
CREATE INDEX IF NOT EXISTS idx_chain_instances_stage ON globe_chain_instances(current_stage);
CREATE INDEX IF NOT EXISTS idx_chain_instances_created ON globe_chain_instances(created_at DESC);

-- Stage transitions log
CREATE TABLE IF NOT EXISTS globe_stage_transitions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chain_instance_id UUID REFERENCES globe_chain_instances(id) ON DELETE CASCADE,
    from_stage VARCHAR(50),
    to_stage VARCHAR(50) NOT NULL,
    duration_days INTEGER,
    outcome VARCHAR(50),  -- converted, lost, stalled
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stage_transitions_instance ON globe_stage_transitions(chain_instance_id);

-- ============================================================
-- 3. DISCOVERY TREE STRUCTURE
-- Tech / Business / Growth knowledge tree
-- ============================================================

-- Discovery tree nodes
CREATE TABLE IF NOT EXISTS globe_discovery_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_code VARCHAR(50) UNIQUE NOT NULL,
    category VARCHAR(20) NOT NULL,  -- tech, business, growth
    parent_code VARCHAR(50),         -- for tree hierarchy
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    description TEXT,
    description_vi TEXT,
    -- Node type
    node_type VARCHAR(20) NOT NULL,  -- category, domain, capability, action
    -- Content for AI discovery
    keywords JSONB DEFAULT '[]',     -- search keywords
    related_industries JSONB DEFAULT '[]',
    -- AI content (vector stored in Qdrant)
    qdrant_collection VARCHAR(100),
    qdrant_point_id VARCHAR(100),
    -- UI display
    icon VARCHAR(50),
    color VARCHAR(7),
    -- Analytics
    search_count INTEGER DEFAULT 0,
    selection_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT true,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_discovery_category ON globe_discovery_nodes(category);
CREATE INDEX IF NOT EXISTS idx_discovery_parent ON globe_discovery_nodes(parent_code);
CREATE INDEX IF NOT EXISTS idx_discovery_type ON globe_discovery_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_discovery_active ON globe_discovery_nodes(is_active);

-- Discovery selections (user picks)
CREATE TABLE IF NOT EXISTS globe_discovery_selections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID REFERENCES globe_discovery_nodes(id),
    user_id UUID,  -- NULL for anonymous
    session_id VARCHAR(100),
    selection_path JSONB NOT NULL DEFAULT '[]',  -- [{category, node_code, node_name}]
    result_context JSONB DEFAULT '{}',  -- selected province, chain context
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_selections_user ON globe_discovery_selections(user_id);
CREATE INDEX IF NOT EXISTS idx_selections_session ON globe_discovery_selections(session_id);
CREATE INDEX IF NOT EXISTS idx_selections_created ON globe_discovery_selections(created_at DESC);

-- ============================================================
-- 4. ANALYTICS PIPELINE
-- Crawl -> Process -> Analyze -> Visualize
-- ============================================================

-- Pipeline definitions
CREATE TABLE IF NOT EXISTS globe_pipelines (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_code VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    name_vi VARCHAR(255),
    description TEXT,
    pipeline_type VARCHAR(50) NOT NULL,  -- crawl, process, analyze, visualize, custom
    stages JSONB NOT NULL DEFAULT '[]',
    source_config JSONB DEFAULT '{}',     -- {type: web_api, url: ..., frequency: ...}
    destination_config JSONB DEFAULT '{}', -- {type: qdrant, collection: ...}
    is_active BOOLEAN DEFAULT true,
    schedule_cron VARCHAR(50),
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Pipeline runs
CREATE TABLE IF NOT EXISTS globe_pipeline_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID REFERENCES globe_pipelines(id),
    run_status VARCHAR(20) NOT NULL DEFAULT 'queued',  -- queued, running, completed, failed
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    records_processed INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    run_log TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pipeline_runs_pipeline ON globe_pipeline_runs(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_status ON globe_pipeline_runs(run_status);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_created ON globe_pipeline_runs(created_at DESC);

-- Pipeline data artifacts
CREATE TABLE IF NOT EXISTS globe_pipeline_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id UUID REFERENCES globe_pipelines(id),
    pipeline_run_id UUID REFERENCES globe_pipeline_runs(id),
    artifact_type VARCHAR(50) NOT NULL,  -- raw, processed, analyzed, report, chart
    artifact_name VARCHAR(255),
    storage_path VARCHAR(500),
    storage_type VARCHAR(20) DEFAULT 'local',  -- local, s3, qdrant
    qdrant_collection VARCHAR(100),
    qdrant_point_count INTEGER,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_artifacts_pipeline ON globe_pipeline_artifacts(pipeline_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON globe_pipeline_artifacts(pipeline_run_id);

-- ============================================================
-- 5. QDRANT COLLECTIONS SETUP (not run as SQL, reference only)
--
-- Globe nodes collection:
--   Collection: globe_nodes
--   Vector: 768-dim (nomic-embed-text)
--   Payload: {node_id, node_code, category, name, name_vi, keywords, industry_ids}
--
-- Globe content collection:
--   Collection: globe_content
--   Vector: 768-dim
--   Payload: {content_id, title, body, province_id, pipeline_run_id}
--
-- ============================================================

-- ============================================================
-- SEED DATA: Default Globe structure
-- ============================================================

-- Industries
INSERT INTO globe_industries (code, name, name_vi, icon, color, description) VALUES
    ('fintech', 'Fintech', 'Tài chính', '💰', '#10b981', 'Financial technology and digital banking'),
    ('ecommerce', 'E-commerce', 'Thương mại điện tử', '🛒', '#f59e0b', 'Online retail and marketplace platforms'),
    ('manufacturing', 'Manufacturing', 'Sản xuất', '🏭', '#6366f1', 'Industrial manufacturing and supply chain'),
    ('healthcare', 'Healthcare', 'Y tế', '🏥', '#ef4444', 'Healthcare and medical technology'),
    ('retail', 'Retail', 'Bán lẻ', '🏪', '#ec4899', 'Physical retail and omnichannel'),
    ('saas', 'SaaS', 'Phần mềm', '☁️', '#8b5cf6', 'Software as a Service platforms')
ON CONFLICT (code) DO NOTHING;

-- Regions
INSERT INTO globe_regions (code, name, name_vi, country, latitude, longitude, timezone) VALUES
    ('VN_NORTH', 'Northern Vietnam', 'Miền Bắc', 'Vietnam', 21.0285, 105.8542, 'Asia/Ho_Chi_Minh'),
    ('VN_CENTRAL', 'Central Vietnam', 'Miền Trung', 'Vietnam', 16.0544, 108.2022, 'Asia/Ho_Chi_Minh'),
    ('VN_SOUTH', 'Southern Vietnam', 'Miền Nam', 'Vietnam', 10.8231, 106.6297, 'Asia/Ho_Chi_Minh'),
    ('SEA', 'Southeast Asia', 'Đông Nam Á', 'Regional', 13.7563, 100.5018, 'Asia/Bangkok'),
    ('GLOBAL', 'Global', 'Toàn cầu', 'International', 0, 0, 'UTC')
ON CONFLICT (code) DO NOTHING;

-- Tiers
INSERT INTO globe_tiers (code, name, name_vi, description, min_employees, max_employees) VALUES
    ('startup', 'Startup', 'Khởi nghiệp', 'Early stage, 1-10 employees', 1, 10),
    ('sme', 'SME', 'Doanh nghiệp vừa', 'Growing, 11-200 employees', 11, 200),
    ('enterprise', 'Enterprise', 'Doanh nghiệp lớn', 'Established, 200+ employees', 200, NULL)
ON CONFLICT (code) DO NOTHING;

-- Discovery Tree Nodes - Tech Category
INSERT INTO globe_discovery_nodes (node_code, category, parent_code, name, name_vi, node_type, keywords, icon, color, description) VALUES
    ('tech', 'tech', NULL, 'Technology', 'Công nghệ', 'category', '["tech", "technology", "ai", "software"]', '💡', '#6366f1', 'Technology and AI solutions'),
    ('tech_agents', 'tech', 'tech', 'AI Agents', 'Đại lý AI', 'domain', '["ai agent", "agentic", "llm", "automation"]', '🤖', '#8b5cf6', 'Autonomous AI agents for business'),
    ('tech_agents_cap_1', 'tech', 'tech_agents', 'Customer Service Agents', 'Agent chăm sóc khách hàng', 'capability', '["chatbot", "support", "nlu", "voice"]', '🎧', '#a78bfa', 'AI agents for customer support'),
    ('tech_agents_cap_2', 'tech', 'tech_agents', 'Sales Automation', 'Tự động hóa bán hàng', 'capability', '["sales", "crm", "lead", "outreach"]', '📈', '#a78bfa', 'Automated sales workflows'),
    ('tech_agents_cap_3', 'tech', 'tech_agents', 'Data Processing Agents', 'Agent xử lý dữ liệu', 'capability', '["data", "etl", "pipeline", "analytics"]', '🔄', '#a78bfa', 'AI agents for data operations'),
    ('tech_automation', 'tech', 'tech', 'Automation', 'Tự động hóa', 'domain', '["workflow", "automation", "n8n", "zapier"]', '⚡', '#10b981', 'Workflow and process automation'),
    ('tech_analytics', 'tech', 'tech', 'Analytics', 'Phân tích', 'domain', '["analytics", "bi", "dashboard", "metrics"]', '📊', '#f59e0b', 'Business intelligence and analytics'),
    ('business', 'business', NULL, 'Business', 'Kinh doanh', 'category', '["business", "sales", "marketing", "operations"]', '💼', '#f59e0b', 'Business functions and processes'),
    ('business_sales', 'business', 'business', 'Sales', 'Bán hàng', 'domain', '["sales", "crm", "pipeline", "revenue"]', '🎯', '#ef4444', 'Sales and revenue generation'),
    ('business_marketing', 'business', 'business', 'Marketing', 'Marketing', 'domain', '["marketing", "seo", "content", "ads"]', '📢', '#ec4899', 'Marketing and brand growth'),
    ('business_ops', 'business', 'business', 'Operations', 'Vận hành', 'domain', '["operations", "process", "efficiency", "workflow"]', '⚙️', '#64748b', 'Business operations optimization'),
    ('growth', 'growth', NULL, 'Growth', 'Tăng trưởng', 'category', '["growth", "scaling", "hiring", "funding"]', '🚀', '#10b981', 'Company growth and scaling'),
    ('growth_scaling', 'growth', 'growth', 'Scaling', 'Mở rộng', 'domain', '["scaling", "expansion", "franchise"]', '📈', '#10b981', 'Business scaling strategies'),
    ('growth_hiring', 'growth', 'growth', 'Hiring', 'Tuyển dụng', 'domain', '["hiring", "recruitment", "talent", "team"]', '👥', '#8b5cf6', 'Talent acquisition and team building'),
    ('growth_funding', 'growth', 'growth', 'Funding', 'Gọi vốn', 'domain', '["funding", "investment", "vc", "capital"]', '💰', '#f59e0b', 'Fundraising and investment')
ON CONFLICT (node_code) DO NOTHING;

-- Default Production Chain
INSERT INTO globe_chains (chain_code, name, name_vi, description, stages) VALUES
    ('sales_pipeline', 'Sales Pipeline', 'Phễu bán hàng', 'Standard B2B sales pipeline from lead to customer',
     '[{"stage": "lead", "name": "Lead", "name_vi": "Khách tiềm năng", "duration_days": 3, "conversion_rate": 100},
       {"stage": "contact", "name": "Contacted", "name_vi": "Đã liên hệ", "duration_days": 7, "conversion_rate": 60},
       {"stage": "qualified", "name": "Qualified", "name_vi": "Đủ điều kiện", "duration_days": 14, "conversion_rate": 30},
       {"stage": "proposal", "name": "Proposal", "name_vi": "Gửi báo giá", "duration_days": 7, "conversion_rate": 50},
       {"stage": "negotiation", "name": "Negotiation", "name_vi": "Đàm phán", "duration_days": 14, "conversion_rate": 70},
       {"stage": "customer", "name": "Customer", "name_vi": "Khách hàng", "duration_days": 0, "conversion_rate": 100}]')
ON CONFLICT (chain_code) DO NOTHING;
