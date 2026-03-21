"""
Globe AI City - Data Layer API (Vercel version)
FastAPI endpoints for Globe province system, production chains, discovery tree, and analytics pipeline

Owner: AI City CTO - Backend Division
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List
import psycopg2
import os
import json
import requests

router = APIRouter(prefix="/globe", tags=["Globe"])

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "neondb"),
    "user": os.getenv("DB_USER", "neondb_owner"),
    "password": os.getenv("DB_PASSWORD", ""),
}
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# Pydantic Models
class ProvinceCreate(BaseModel):
    name: str
    name_vi: Optional[str] = None
    description: Optional[str] = None
    industry_id: Optional[str] = None
    region_id: Optional[str] = None
    tier_id: Optional[str] = None
    node_size: str = "medium"
    node_color: str = "#6366f1"
    metadata: Optional[dict] = {}

class ChainInstanceCreate(BaseModel):
    chain_id: str
    province_id: Optional[str] = None
    company_name: str
    company_email: Optional[str] = None
    company_phone: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    pipeline_value: float = 0
    source: Optional[str] = None
    metadata: Optional[dict] = {}

class ChainInstanceUpdate(BaseModel):
    current_stage: Optional[str] = None
    pipeline_value: Optional[float] = None
    actual_value: Optional[float] = None
    probability: Optional[float] = None
    metadata: Optional[dict] = None

class DiscoverySearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    limit: int = 5

class DiscoverySelectRequest(BaseModel):
    node_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    selection_path: List[dict] = []
    result_context: Optional[dict] = {}

# =====================
# Reference Data
# =====================

@router.get("/industries")
async def list_industries():
    """List all Globe industries"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, name_vi, icon, color, description, metadata, is_active
            FROM globe_industries WHERE is_active = true ORDER BY name
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3],
                 "icon": r[4], "color": r[5], "description": r[6], "is_active": r[8]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.get("/regions")
async def list_regions():
    """List all Globe regions"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, name_vi, country, latitude, longitude, timezone, is_active
            FROM globe_regions WHERE is_active = true ORDER BY country, name
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3],
                 "country": r[4], "latitude": float(r[5]) if r[5] else None,
                 "longitude": float(r[6]) if r[6] else None, "timezone": r[7], "is_active": r[8]}
                for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.get("/tiers")
async def list_tiers():
    """List all Globe tiers"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, code, name, name_vi, description, min_employees, max_employees FROM globe_tiers ORDER BY min_employees")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3],
                 "description": r[4], "min_employees": r[5], "max_employees": r[6]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

# =====================
# Province Data Store
# =====================

@router.get("/provinces")
async def list_provinces(
    industry_id: Optional[str] = None,
    region_id: Optional[str] = None,
    tier_id: Optional[str] = None,
    limit: int = 100
):
    """List Globe provinces with filters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT p.id, p.name, p.name_vi, p.description, p.industry_id, p.region_id, p.tier_id,
                   p.node_size, p.node_color, p.total_companies, p.total_revenue, p.total_leads, p.is_active,
                   i.name as industry_name, r.name as region_name, r.latitude, r.longitude, t.name as tier_name
            FROM globe_provinces p
            LEFT JOIN globe_industries i ON p.industry_id = i.id
            LEFT JOIN globe_regions r ON p.region_id = r.id
            LEFT JOIN globe_tiers t ON p.tier_id = t.id
            WHERE p.is_active = true
        """
        params = []
        if industry_id:
            query += " AND p.industry_id = %s"
            params.append(industry_id)
        if region_id:
            query += " AND p.region_id = %s"
            params.append(region_id)
        if tier_id:
            query += " AND p.tier_id = %s"
            params.append(tier_id)
        query += " ORDER BY p.total_companies DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [{
            "id": str(r[0]), "name": r[1], "name_vi": r[2], "description": r[3],
            "industry_id": str(r[4]) if r[4] else None,
            "region_id": str(r[5]) if r[5] else None,
            "tier_id": str(r[6]) if r[6] else None,
            "node_size": r[7], "node_color": r[8],
            "total_companies": r[9] or 0, "total_revenue": float(r[10] or 0), "total_leads": r[11] or 0,
            "is_active": r[12],
            "industry": {"name": r[13]} if r[13] else None,
            "region": {"name": r[14], "latitude": float(r[15]) if r[15] else None, "longitude": float(r[16]) if r[16] else None} if r[14] else None,
            "tier": {"name": r[17]} if r[17] else None,
        } for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.post("/provinces")
async def create_province(province: ProvinceCreate):
    """Create a new Globe province"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO globe_provinces
            (name, name_vi, description, industry_id, region_id, tier_id, node_size, node_color, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, name_vi, description, node_size, node_color, total_companies, total_revenue, is_active
        """, (province.name, province.name_vi, province.description, province.industry_id,
              province.region_id, province.tier_id, province.node_size, province.node_color,
              json.dumps(province.metadata or {})))
        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": str(result[0]), "name": result[1], "name_vi": result[2], "node_size": result[4], "node_color": result[5]}
    except Exception as e:
        return {"error": str(e)}

@router.get("/provinces/stats")
async def get_province_stats():
    """Get aggregated province statistics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), SUM(total_companies), SUM(total_revenue), SUM(total_leads)
            FROM globe_provinces WHERE is_active = true
        """)
        row = cursor.fetchone()

        cursor.execute("""
            SELECT i.name, COUNT(p.id), SUM(p.total_companies)
            FROM globe_industries i LEFT JOIN globe_provinces p ON p.industry_id = i.id AND p.is_active = true
            GROUP BY i.id, i.name ORDER BY SUM(p.total_companies) DESC NULLS LAST
        """)
        by_industry = [{"name": r[0], "province_count": r[1], "companies": r[2] or 0} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT r.name, COUNT(p.id), SUM(p.total_companies)
            FROM globe_regions r LEFT JOIN globe_provinces p ON p.region_id = r.id AND p.is_active = true
            GROUP BY r.id, r.name ORDER BY SUM(p.total_companies) DESC NULLS LAST
        """)
        by_region = [{"name": r[0], "province_count": r[1], "companies": r[2] or 0} for r in cursor.fetchall()]

        cursor.close()
        conn.close()
        return {"total_provinces": row[0] or 0, "total_companies": row[1] or 0,
                "total_revenue": float(row[2] or 0), "total_leads": row[3] or 0,
                "by_industry": by_industry, "by_region": by_region}
    except Exception as e:
        return {"error": str(e)}

# =====================
# Production Chains
# =====================

@router.get("/chains")
async def list_chains():
    """List all production chains"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT id, chain_code, name, name_vi, description, stages, is_active FROM globe_chains WHERE is_active = true")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "chain_code": r[1], "name": r[2], "name_vi": r[3],
                 "description": r[4], "stages": r[5] if isinstance(r[5], list) else [], "is_active": r[6]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.post("/chains/instances")
async def create_chain_instance(instance: ChainInstanceCreate):
    """Create a new chain instance (Lead)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get chain stages
        cursor.execute("SELECT stages FROM globe_chains WHERE id = %s", (instance.chain_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": "Chain not found"}
        stages = row[0] if isinstance(row[0], list) else []
        first_stage = stages[0]["stage"] if stages else "lead"

        cursor.execute("""
            INSERT INTO globe_chain_instances
            (chain_id, province_id, company_name, company_email, company_phone, contact_name, contact_email,
             current_stage, stage_order, pipeline_value, source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s)
            RETURNING id, chain_id, company_name, current_stage, pipeline_value
        """, (instance.chain_id, instance.province_id, instance.company_name,
              instance.company_email, instance.company_phone, instance.contact_name, instance.contact_email,
              first_stage, instance.pipeline_value, instance.source, json.dumps(instance.metadata or {})))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": str(result[0]), "chain_id": str(result[1]), "company_name": result[2],
                "current_stage": result[3], "pipeline_value": float(result[4])}
    except Exception as e:
        return {"error": str(e)}

@router.patch("/chains/instances/{instance_id}")
async def update_chain_instance(instance_id: str, update: ChainInstanceUpdate):
    """Update chain instance (stage transition)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get old stage
        cursor.execute("SELECT current_stage, province_id FROM globe_chain_instances WHERE id = %s", (instance_id,))
        row = cursor.fetchone()
        if not row:
            return {"error": "Instance not found"}
        old_stage, province_id = row[0], row[1]

        updates = ["updated_at = NOW()"]
        values = []
        if update.current_stage:
            updates.append("current_stage = %s")
            values.append(update.current_stage)
            updates.append("stage_changed_at = NOW()")
            updates.append("stage_order = stage_order + 1")
        if update.pipeline_value is not None:
            updates.append("pipeline_value = %s")
            values.append(update.pipeline_value)
        if update.actual_value is not None:
            updates.append("actual_value = %s")
            values.append(update.actual_value)
        if update.probability is not None:
            updates.append("probability = %s")
            values.append(update.probability)
        if update.metadata:
            updates.append("metadata = %s")
            values.append(json.dumps(update.metadata))
        values.append(instance_id)

        cursor.execute(f"UPDATE globe_chain_instances SET {', '.join(updates)} WHERE id = %s RETURNING id, current_stage, pipeline_value", tuple(values))
        result = cursor.fetchone()

        # Log transition
        if update.current_stage and update.current_stage != old_stage:
            cursor.execute("INSERT INTO globe_stage_transitions (chain_instance_id, from_stage, to_stage) VALUES (%s, %s, %s)",
                           (instance_id, old_stage, update.current_stage))
            if update.current_stage == "customer" and province_id:
                cursor.execute("UPDATE globe_provinces SET total_companies = total_companies + 1, total_leads = total_leads + 1 WHERE id = %s", (province_id,))

        conn.commit()
        cursor.close()
        conn.close()
        return {"id": str(result[0]), "current_stage": result[1], "pipeline_value": float(result[2]),
                "stage_changed": update.current_stage is not None and update.current_stage != old_stage}
    except Exception as e:
        return {"error": str(e)}

@router.get("/chains/instances")
async def list_chain_instances(chain_id: Optional[str] = None, stage: Optional[str] = None, limit: int = 100):
    """List chain instances"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """SELECT ci.id, ci.chain_id, ci.province_id, ci.company_name, ci.company_email,
                          ci.contact_name, ci.current_stage, ci.stage_order, ci.pipeline_value,
                          ci.actual_value, ci.probability, ci.created_at, gc.name as chain_name
                   FROM globe_chain_instances ci
                   LEFT JOIN globe_chains gc ON ci.chain_id = gc.id WHERE 1=1"""
        params = []
        if chain_id:
            query += " AND ci.chain_id = %s"
            params.append(chain_id)
        if stage:
            query += " AND ci.current_stage = %s"
            params.append(stage)
        query += " ORDER BY ci.created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "chain_id": str(r[1]) if r[1] else None,
                 "province_id": str(r[2]) if r[2] else None, "company_name": r[3],
                 "company_email": r[4], "contact_name": r[5], "current_stage": r[6],
                 "stage_order": r[7], "pipeline_value": float(r[8]) if r[8] else 0,
                 "actual_value": float(r[9]) if r[9] else 0, "probability": float(r[10]) if r[10] else 0,
                 "created_at": str(r[11]), "chain_name": r[12]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.get("/chains/pipeline")
async def get_pipeline_stats():
    """Get production chain funnel statistics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT current_stage, COUNT(*), SUM(pipeline_value), AVG(probability)
            FROM globe_chain_instances GROUP BY current_stage ORDER BY MIN(stage_order)
        """)
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*), SUM(actual_value) FROM globe_chain_instances")
        totals = cursor.fetchone()
        cursor.close()
        conn.close()
        return {"by_stage": [{"stage": r[0], "count": r[1], "total_value": float(r[2] or 0),
                              "avg_probability": float(r[3] or 0)} for r in rows],
                "totals": {"total_instances": totals[0] or 0, "realized_value": float(totals[1] or 0)}}
    except Exception as e:
        return {"error": str(e)}

# =====================
# Discovery Tree
# =====================

@router.get("/discovery/tree")
async def get_discovery_tree(category: Optional[str] = None):
    """Get discovery tree structure"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """SELECT id, node_code, category, parent_code, name, name_vi, description,
                          node_type, keywords, icon, color, selection_count
                   FROM globe_discovery_nodes WHERE is_active = true"""
        params = []
        if category:
            query += " AND category = %s"
            params.append(category)
        query += " ORDER BY category, parent_code NULLS FIRST, node_type, name"
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        nodes = {str(r[0]): {"id": str(r[0]), "node_code": r[1], "category": r[2], "parent_code": r[3],
                              "name": r[4], "name_vi": r[5], "description": r[6], "node_type": r[7],
                              "keywords": r[8] if isinstance(r[8], list) else [], "icon": r[9],
                              "color": r[10], "selection_count": r[11] or 0, "children": []}
                 for r in rows}
        tree = []
        for node in nodes.values():
            if node["parent_code"]:
                parent = next((n for n in nodes.values() if n["node_code"] == node["parent_code"]), None)
                if parent:
                    parent["children"].append(node)
            else:
                tree.append(node)
        return {"categories": tree} if not category else tree
    except Exception as e:
        return {"error": str(e)}

@router.post("/discovery/search")
async def search_discovery(request: DiscoverySearchRequest):
    """Search discovery nodes (Qdrant or PostgreSQL fallback)"""
    try:
        # Try Qdrant first
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/globe_nodes/points/search",
                json={"vector": [0.0] * 768, "limit": request.limit, "with_payload": True},
                timeout=5
            )
            if resp.status_code == 200:
                return {"results": resp.json().get("result", []), "source": "qdrant"}
        except Exception:
            pass

        # PostgreSQL fallback
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """SELECT id, node_code, category, name, name_vi, description, node_type, icon, color
                   FROM globe_discovery_nodes WHERE is_active = true"""
        params = []
        if request.category:
            query += " AND category = %s"
            params.append(request.category)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"results": [{"id": str(r[0]), "node_code": r[1], "category": r[2], "name": r[3],
                              "name_vi": r[4], "description": r[5], "node_type": r[6], "icon": r[7], "color": r[8]}
                             for r in rows], "source": "postgresql"}
    except Exception as e:
        return {"error": str(e)}

@router.post("/discovery/select")
async def record_selection(selection: DiscoverySelectRequest):
    """Record a discovery selection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO globe_discovery_selections (node_id, user_id, session_id, selection_path, result_context)
            VALUES (%s, %s, %s, %s, %s) RETURNING id, created_at
        """, (selection.node_id, selection.user_id, selection.session_id,
              json.dumps(selection.selection_path), json.dumps(selection.result_context or {})))
        result = cursor.fetchone()
        cursor.execute("UPDATE globe_discovery_nodes SET selection_count = selection_count + 1 WHERE id = %s",
                       (selection.node_id,))
        conn.commit()
        cursor.close()
        conn.close()
        return {"id": str(result[0]), "created_at": str(result[1])}
    except Exception as e:
        return {"error": str(e)}

@router.get("/discovery/analytics")
async def get_discovery_analytics():
    """Discovery analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT dn.node_code, dn.name, dn.category, COUNT(ds.id) as sel
            FROM globe_discovery_nodes dn JOIN globe_discovery_selections ds ON ds.node_id = dn.id
            GROUP BY dn.id, dn.node_code, dn.name, dn.category ORDER BY sel DESC LIMIT 10
        """)
        top = [{"node_code": r[0], "name": r[1], "category": r[2], "selections": r[3]} for r in cursor.fetchall()]
        cursor.execute("""
            SELECT dn.category, COUNT(ds.id) FROM globe_discovery_nodes dn
            JOIN globe_discovery_selections ds ON ds.node_id = dn.id GROUP BY dn.category
        """)
        by_cat = [{"category": r[0], "selections": r[1]} for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return {"top_nodes": top, "by_category": by_cat}
    except Exception as e:
        return {"error": str(e)}

# =====================
# Pipeline
# =====================

@router.get("/pipelines")
async def list_pipelines(pipeline_type: Optional[str] = None):
    """List analytics pipelines"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = "SELECT id, pipeline_code, name, name_vi, pipeline_type, stages, source_config, destination_config, is_active FROM globe_pipelines WHERE is_active = true"
        params = []
        if pipeline_type:
            query += " AND pipeline_type = %s"
            params.append(pipeline_type)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "pipeline_code": r[1], "name": r[2], "name_vi": r[3],
                 "pipeline_type": r[4], "stages": r[5] if isinstance(r[5], list) else [],
                 "source_config": r[6] or {}, "destination_config": r[7] or {}, "is_active": r[8]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

@router.get("/pipelines/runs")
async def list_pipeline_runs(pipeline_id: Optional[str] = None, limit: int = 20):
    """List pipeline runs"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        query = """SELECT pr.id, pr.pipeline_id, pr.run_status, pr.started_at, pr.completed_at,
                          pr.records_processed, pr.records_failed, pr.error_message, gp.pipeline_code
                   FROM globe_pipeline_runs pr LEFT JOIN globe_pipelines gp ON pr.pipeline_id = gp.id WHERE 1=1"""
        params = []
        if pipeline_id:
            query += " AND pr.pipeline_id = %s"
            params.append(pipeline_id)
        query += " ORDER BY pr.created_at DESC LIMIT %s"
        params.append(limit)
        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [{"id": str(r[0]), "pipeline_id": str(r[1]) if r[1] else None, "run_status": r[2],
                 "started_at": str(r[3]) if r[3] else None, "completed_at": str(r[4]) if r[4] else None,
                 "records_processed": r[5] or 0, "records_failed": r[6] or 0, "error_message": r[7],
                 "pipeline_code": r[8]} for r in rows]
    except Exception as e:
        return {"error": str(e)}

# =====================
# Dashboard
# =====================

@router.get("/dashboard")
async def get_globe_dashboard():
    """Globe overview dashboard"""
    try:
        province_stats = await get_province_stats()
        pipeline_stats = await get_pipeline_stats()
        discovery_analytics = await get_discovery_analytics()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM globe_industries WHERE is_active = true")
        ind_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_regions WHERE is_active = true")
        reg_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_discovery_nodes WHERE is_active = true")
        node_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM globe_pipelines WHERE is_active = true")
        pipe_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()

        return {"status": "operational", "provinces": province_stats, "pipeline": pipeline_stats,
                "discovery": discovery_analytics, "counts": {"industries": ind_count, "regions": reg_count,
                "discovery_nodes": node_count, "pipelines": pipe_count}}
    except Exception as e:
        return {"status": "error", "message": str(e)}
