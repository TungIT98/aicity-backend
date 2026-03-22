"""Initial schema - PostgreSQL + pgvector

Revision ID: 001_initial
Revises:
Create Date: 2026-03-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), server_default="user"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # API Keys table
    op.create_table(
        "api_keys",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("key_hash", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100)),
        sa.Column("rate_limit", sa.Integer(), server_default="100"),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime()),
    )

    # Documents table for RAG
    op.create_table(
        "documents",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.String(500)),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(50)),
        sa.Column("metadata", sa.JSON(), server_default="{}"),
        sa.Column("embedding", sa.LargeBinary()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Create IVFFlat index for vector similarity search
    # Note: vector type requires pgvector extension
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_documents_embedding
        ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)

    # Dashboard analytics
    op.create_table(
        "dashboard_analytics",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("query_text", sa.Text()),
        sa.Column("result_data", sa.JSON()),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # API Request logs
    op.create_table(
        "api_logs",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("api_key_id", sa.UUID(), sa.ForeignKey("api_keys.id", ondelete="SET NULL")),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("status_code", sa.Integer()),
        sa.Column("response_time_ms", sa.Integer()),
        sa.Column("request_data", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Lead tracking
    op.create_table(
        "leads",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("nextval('leads_id_seq')")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50)),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), server_default="new"),
        sa.Column("metadata", sa.JSON(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Reports
    op.create_table(
        "reports",
        sa.Column("id", sa.UUID(), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column("report_type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
    )

    # Invoices
    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("nextval('invoice_id_seq')")),
        sa.Column("invoice_id", sa.String(50), unique=True, nullable=False),
        sa.Column("invoice_number", sa.String(50), unique=True, nullable=False),
        sa.Column("invoice_serial", sa.String(20), nullable=False),
        sa.Column("company_name", sa.String(255), server_default="AI City"),
        sa.Column("company_tax_id", sa.String(20), server_default="0123456789"),
        sa.Column("company_address", sa.Text()),
        sa.Column("company_email", sa.String(255)),
        sa.Column("company_phone", sa.String(50)),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("users.id")),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_tax_id", sa.String(20)),
        sa.Column("customer_address", sa.Text()),
        sa.Column("customer_email", sa.String(255)),
        sa.Column("subtotal", sa.Numeric(15, 2), server_default="0"),
        sa.Column("vat_rate", sa.Numeric(5, 2), server_default="10"),
        sa.Column("vat_amount", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total", sa.Numeric(15, 2), server_default="0"),
        sa.Column("total_in_words", sa.String(500)),
        sa.Column("payment_method", sa.String(50)),
        sa.Column("payment_status", sa.String(20), server_default="pending"),
        sa.Column("payment_transaction_id", sa.String(100)),
        sa.Column("line_items", sa.JSON(), server_default="[]"),
        sa.Column("notes", sa.Text()),
        sa.Column("invoice_pattern", sa.String(20)),
        sa.Column("invoice_type", sa.String(20), server_default="electronic"),
        sa.Column("tax_authority_status", sa.String(20), server_default="pending"),
        sa.Column("submitted_at", sa.DateTime()),
        sa.Column("accepted_at", sa.DateTime()),
        sa.Column("submission_deadline", sa.DateTime()),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("issued_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Payments
    op.create_table(
        "payments",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("nextval('payment_id_seq')")),
        sa.Column("payment_id", sa.String(50), unique=True, nullable=False),
        sa.Column("order_id", sa.String(50), nullable=False),
        sa.Column("amount", sa.Numeric(15, 0), nullable=False),
        sa.Column("currency", sa.String(10), server_default="VND"),
        sa.Column("status", sa.String(20), server_default="pending"),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("checkout_url", sa.String(500)),
        sa.Column("qr_code", sa.String(1000)),
        sa.Column("transaction_id", sa.String(100)),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("metadata", sa.JSON(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Revenue transactions
    op.create_table(
        "revenue_transactions",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("nextval('revenue_id_seq')")),
        sa.Column("transaction_id", sa.String(50), unique=True, nullable=False),
        sa.Column("payment_id", sa.String(50), sa.ForeignKey("payments.payment_id")),
        sa.Column("order_id", sa.String(50)),
        sa.Column("amount", sa.Numeric(15, 0), nullable=False),
        sa.Column("currency", sa.String(10), server_default="VND"),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("customer_name", sa.String(255)),
        sa.Column("customer_location", sa.String(100)),
        sa.Column("payment_method", sa.String(20), nullable=False),
        sa.Column("transaction_ref", sa.String(100)),
        sa.Column("status", sa.String(20), server_default="completed"),
        sa.Column("latitude", sa.Numeric(10, 6)),
        sa.Column("longitude", sa.Numeric(10, 6)),
        sa.Column("metadata", sa.JSON(), server_default="{}"),
        sa.Column("transaction_date", sa.Date(), server_default=sa.text("CURRENT_DATE")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Subscriptions
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True, server_default=sa.text("nextval('subscription_id_seq')")),
        sa.Column("subscription_id", sa.String(50), unique=True, nullable=False),
        sa.Column("customer_id", sa.UUID(), sa.ForeignKey("users.id")),
        sa.Column("customer_email", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(20), nullable=False),
        sa.Column("plan_name", sa.String(50)),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("paused_at", sa.DateTime()),
        sa.Column("cancelled_at", sa.DateTime()),
        sa.Column("payment_id", sa.String(50), sa.ForeignKey("payments.payment_id")),
        sa.Column("ai_runs_used", sa.Integer(), server_default="0"),
        sa.Column("ai_runs_limit", sa.Integer()),
        sa.Column("documents_limit", sa.Integer()),
        sa.Column("auto_renew", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()")),
    )

    # Create sequences
    op.execute("CREATE SEQUENCE IF NOT EXISTS leads_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS invoice_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS payment_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS revenue_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS subscription_id_seq")
    op.execute("CREATE SEQUENCE IF NOT EXISTS invoice_serial_seq START WITH 1")

    # Create indexes
    op.create_index("idx_documents_created", "documents", ["created_at"], unique=False)
    op.create_index("idx_api_logs_created", "api_logs", ["created_at"], unique=False)
    op.create_index("idx_dashboard_analytics_created", "dashboard_analytics", ["created_at"], unique=False)
    op.create_index("idx_leads_status", "leads", ["status"], unique=False)
    op.create_index("idx_leads_source", "leads", ["source"], unique=False)
    op.create_index("idx_leads_created", "leads", ["created_at"], unique=False)
    op.create_index("idx_reports_generated", "reports", ["generated_at"], unique=False)
    op.create_index("idx_invoices_invoice_id", "invoices", ["invoice_id"], unique=False)
    op.create_index("idx_invoices_invoice_number", "invoices", ["invoice_number"], unique=False)
    op.create_index("idx_invoices_customer_id", "invoices", ["customer_id"], unique=False)
    op.create_index("idx_invoices_status", "invoices", ["status"], unique=False)
    op.create_index("idx_invoices_payment_status", "invoices", ["payment_status"], unique=False)
    op.create_index("idx_invoices_created", "invoices", ["created_at"], unique=False)
    op.create_index("idx_payments_payment_id", "payments", ["payment_id"], unique=False)
    op.create_index("idx_payments_order_id", "payments", ["order_id"], unique=False)
    op.create_index("idx_payments_status", "payments", ["status"], unique=False)
    op.create_index("idx_payments_customer_email", "payments", ["customer_email"], unique=False)
    op.create_index("idx_payments_expires", "payments", ["expires_at"], unique=False)
    op.create_index("idx_revenue_transaction_id", "revenue_transactions", ["transaction_id"], unique=False)
    op.create_index("idx_revenue_customer_email", "revenue_transactions", ["customer_email"], unique=False)
    op.create_index("idx_revenue_status", "revenue_transactions", ["status"], unique=False)
    op.create_index("idx_revenue_transaction_date", "revenue_transactions", ["transaction_date"], unique=False)
    op.create_index("idx_revenue_payment_method", "revenue_transactions", ["payment_method"], unique=False)
    op.create_index("idx_subscriptions_subscription_id", "subscriptions", ["subscription_id"], unique=False)
    op.create_index("idx_subscriptions_customer_email", "subscriptions", ["customer_email"], unique=False)
    op.create_index("idx_subscriptions_status", "subscriptions", ["status"], unique=False)
    op.create_index("idx_subscriptions_expires", "subscriptions", ["expires_at"], unique=False)

    # Composite indexes for performance
    op.create_index("idx_leads_status_source", "leads", ["status", "source"], unique=False)
    op.create_index("idx_leads_status_created", "leads", ["status", "created_at"], unique=False)
    op.create_index("idx_revenue_transactions_status_date", "revenue_transactions", ["status", "transaction_date"], unique=False)
    op.create_index("idx_subscriptions_status_expires", "subscriptions", ["status", "expires_at"], unique=False)

    # Insert seed users
    op.execute("""
        INSERT INTO users (email, name, role)
        VALUES ('admin@aicity.local', 'AI City Admin', 'admin'),
               ('api@aicity.local', 'API Service', 'service')
        ON CONFLICT (email) DO NOTHING
    """)


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("subscriptions")
    op.drop_table("revenue_transactions")
    op.drop_table("payments")
    op.drop_table("invoices")
    op.drop_table("reports")
    op.drop_table("leads")
    op.drop_table("api_logs")
    op.drop_table("dashboard_analytics")
    op.drop_table("documents")
    op.drop_table("api_keys")
    op.drop_table("users")

    op.execute("DROP SEQUENCE IF EXISTS subscription_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS revenue_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS payment_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS invoice_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS leads_id_seq")
    op.execute("DROP SEQUENCE IF EXISTS invoice_serial_seq")
