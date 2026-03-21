"""
Globe AI City - Data Layer API
FastAPI endpoints for Globe province system, production chains, discovery tree, and analytics pipeline

Owner: AI City CTO - Backend Division
"""

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime
import psycopg2
import requests
import os
import json
import uuid

router = FastAPI(prefix="/globe", tags=["Globe"])

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5433"),
    "database": os.getenv("DB_NAME", "promptforge"),
    "user": os.getenv("DB_USER", "promptforge"),
    "password": os.getenv("DB_PASSWORD", "promptforge123"),
}
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")

# ============================================================
# Pydantic Models
# ============================================================

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

class ProvinceResponse(BaseModel):
    id: str
    name: str
    name_vi: Optional[str]
    industry: Optional[dict]
    region: Optional[dict]
    tier: Optional[dict]
    total_companies: int
    total_revenue: float
    node_size: str
    node_color: str
    is_active: bool
    created_at: str

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
    utm_campaign: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_source: Optional[str] = None
    metadata: Optional[dict] = {}

class ChainInstanceUpdate(BaseModel):
    current_stage: Optional[str] = None
    pipeline_value: Optional[float] = None
    actual_value: Optional[float] = None
    probability: Optional[float] = None
    metadata: Optional[dict] = None

class DiscoveryNodeCreate(BaseModel):
    node_code: str
    category: str
    parent_code: Optional[str] = None
    name: str
    name_vi: Optional[str] = None
    description: Optional[str] = None
    description_vi: Optional[str] = None
    node_type: str
    keywords: List[str] = []
    related_industries: List[str] = []
    icon: Optional[str] = None
    color: Optional[str] = None
    metadata: Optional[dict] = {}

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

class PipelineCreate(BaseModel):
    pipeline_code: str
    name: str
    name_vi: Optional[str] = None
    description: Optional[str] = None
    pipeline_type: str
    stages: List[dict] = []
    source_config: Optional[dict] = {}
    destination_config: Optional[dict] = {}
    schedule_cron: Optional[str] = None

# ============================================================
# Database Helpers
# ============================================================

def get_db():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()

def row_to_dict(cursor, row):
    if row is None:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))

def get_embedding(text: str) -> List[float]:
    try:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text", "prompt": text},
            timeout=10
        )
        resp.raise_for_status()
        return resp.json()["embedding"]
    except Exception:
        return [0.0] * 768  # Fallback zero vector

# ============================================================
# Province Data Store Endpoints
# ============================================================

@router.get("/provinces", response_model=List[ProvinceResponse])
async def list_provinces(
    industry_id: Optional[str] = None,
    region_id: Optional[str] = None,
    tier_id: Optional[str] = None,
    is_active: bool = True,
    limit: int = 100
):
    """List all Globe provinces with optional filters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT p.*, i.name as industry_name, r.name as region_name, t.name as tier_name,
                   i.color as industry_color, r.latitude, r.longitude
            FROM globe_provinces p
            LEFT JOIN globe_industries i ON p.industry_id = i.id
            LEFT JOIN globe_regions r ON p.region_id = r.id
            LEFT JOIN globe_tiers t ON p.tier_id = t.id
            WHERE 1=1
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
        query += " AND p.is_active = %s"
        params.append(is_active)
        query += " ORDER BY p.total_companies DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        provinces = []
        for row in rows:
            cols = [desc[0] for desc in cursor.description] if cursor.description else []
            # Rebuild from original cursor
            d = {
                "id": str(row[0]), "name": row[1], "name_vi": row[2], "description": row[3],
                "industry_id": str(row[4]) if row[4] else None,
                "region_id": str(row[5]) if row[5] else None,
                "tier_id": str(row[6]) if row[6] else None,
                "metadata": row[7] if isinstance(row[7], dict) else {},
                "node_size": row[8], "node_color": row[9],
                "total_companies": row[10] or 0, "total_revenue": float(row[11] or 0),
                "total_leads": row[12] or 0, "is_active": row[13],
                "created_at": str(row[14]),
            }
            d["industry"] = {"id": str(row[4]) if row[4] else None, "name": row[15]} if row[15] else None
            d["region"] = {"id": str(row[5]) if row[5] else None, "name": row[16], "lat": row[18], "lng": row[19]} if row[16] else None
            d["tier"] = {"id": str(row[6]) if row[6] else None, "name": row[17]} if row[17] else None
            provinces.append(d)

        return provinces
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/provinces", response_model=ProvinceResponse)
async def create_province(province: ProvinceCreate):
    """Create a new Globe province"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO globe_provinces
            (name, name_vi, description, industry_id, region_id, tier_id, node_size, node_color, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, name, name_vi, description, industry_id, region_id, tier_id, metadata,
                      node_size, node_color, total_companies, total_revenue, total_leads, is_active, created_at
        """, (
            province.name, province.name_vi, province.description,
            province.industry_id, province.region_id, province.tier_id,
            province.node_size, province.node_color, json.dumps(province.metadata or {})
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return ProvinceResponse(
            id=str(result[0]), name=result[1], name_vi=result[2], description=result[3],
            industry_id=str(result[4]) if result[4] else None,
            region_id=str(result[5]) if result[5] else None,
            tier_id=str(result[6]) if result[6] else None,
            metadata=result[7] or {}, node_size=result[8], node_color=result[9],
            total_companies=result[10] or 0, total_revenue=float(result[11] or 0), node_size=result[8],
            is_active=result[13], created_at=str(result[14]),
            industry=None, region=None, tier=None
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/provinces/stats")
async def get_province_stats():
    """Get aggregated province statistics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                COUNT(*) as total_provinces,
                SUM(total_companies) as total_companies,
                SUM(total_revenue) as total_revenue,
                SUM(total_leads) as total_leads
            FROM globe_provinces WHERE is_active = true
        """)
        row = cursor.fetchone()

        cursor.execute("""
            SELECT i.name, COUNT(p.id) as province_count, SUM(p.total_companies) as companies
            FROM globe_industries i
            LEFT JOIN globe_provinces p ON p.industry_id = i.id AND p.is_active = true
            GROUP BY i.id, i.name ORDER BY companies DESC
        """)
        by_industry = [{"name": r[0], "province_count": r[1], "companies": r[2] or 0} for r in cursor.fetchall()]

        cursor.execute("""
            SELECT r.name, COUNT(p.id) as province_count, SUM(p.total_companies) as companies
            FROM globe_regions r
            LEFT JOIN globe_provinces p ON p.region_id = r.id AND p.is_active = true
            GROUP BY r.id, r.name ORDER BY companies DESC
        """)
        by_region = [{"name": r[0], "province_count": r[1], "companies": r[2] or 0} for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        return {
            "total_provinces": row[0] or 0,
            "total_companies": row[1] or 0,
            "total_revenue": float(row[2] or 0),
            "total_leads": row[3] or 0,
            "by_industry": by_industry,
            "by_region": by_region
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Reference Data Endpoints
# ============================================================

@router.get("/industries")
async def list_industries():
    """List all Globe industries"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, name_vi, icon, color, description, parent_id, metadata, is_active
            FROM globe_industries WHERE is_active = true ORDER BY name
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "icon": r[4],
             "color": r[5], "description": r[6], "parent_id": str(r[7]) if r[7] else None,
             "metadata": r[8] or {}, "is_active": r[9]}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/regions")
async def list_regions():
    """List all Globe regions"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, name_vi, country, latitude, longitude, timezone, metadata, is_active
            FROM globe_regions WHERE is_active = true ORDER BY country, name
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "country": r[4],
             "latitude": float(r[5]) if r[5] else None, "longitude": float(r[6]) if r[6] else None,
             "timezone": r[7], "metadata": r[8] or {}, "is_active": r[9]}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tiers")
async def list_tiers():
    """List all Globe tiers"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, code, name, name_vi, description, min_employees, max_employees, metadata
            FROM globe_tiers ORDER BY min_employees
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {"id": str(r[0]), "code": r[1], "name": r[2], "name_vi": r[3], "description": r[4],
             "min_employees": r[5], "max_employees": r[6], "metadata": r[7] or {}}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Production Chain Endpoints
# ============================================================

@router.get("/chains")
async def list_chains():
    """List all production chains"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, chain_code, name, name_vi, description, stages, is_active, created_at
            FROM globe_chains WHERE is_active = true ORDER BY name
        """)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return [
            {"id": str(r[0]), "chain_code": r[1], "name": r[2], "name_vi": r[3],
             "description": r[4], "stages": r[5] if isinstance(r[5], list) else [],
             "is_active": r[6], "created_at": str(r[7])}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/chains/instances")
async def create_chain_instance(instance: ChainInstanceCreate):
    """Create a new chain instance (company in the pipeline)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get chain stages to determine starting stage
        cursor.execute("SELECT stages FROM globe_chains WHERE id = %s", (instance.chain_id,))
        chain_row = cursor.fetchone()
        if not chain_row:
            raise HTTPException(status_code=404, detail="Chain not found")

        stages = chain_row[0] if isinstance(chain_row[0], list) else []
        first_stage = stages[0]["stage"] if stages else "lead"
        stage_order = 0

        cursor.execute("""
            INSERT INTO globe_chain_instances
            (chain_id, province_id, company_name, company_email, company_phone, contact_name, contact_email,
             current_stage, stage_order, pipeline_value, source, utm_campaign, utm_medium, utm_source, metadata)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, chain_id, province_id, company_name, current_stage, stage_order, pipeline_value, created_at
        """, (
            instance.chain_id, instance.province_id, instance.company_name,
            instance.company_email, instance.company_phone, instance.contact_name, instance.contact_email,
            first_stage, stage_order, instance.pipeline_value,
            instance.source, instance.utm_campaign, instance.utm_medium, instance.utm_source,
            json.dumps(instance.metadata or {})
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {
            "id": str(result[0]), "chain_id": str(result[1]), "province_id": str(result[2]) if result[2] else None,
            "company_name": result[3], "current_stage": result[4], "stage_order": result[5],
            "pipeline_value": float(result[6]) if result[6] else 0,
            "created_at": str(result[7])
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/chains/instances/{instance_id}")
async def update_chain_instance(instance_id: str, update: ChainInstanceUpdate):
    """Update a chain instance (stage transition, value change)"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Get current stage for transition log
        cursor.execute("SELECT current_stage FROM globe_chain_instances WHERE id = %s", (instance_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Instance not found")

        old_stage = row[0]
        new_stage = update.current_stage or old_stage

        # Build update query
        updates = []
        values = []
        if update.current_stage is not None:
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
        if update.metadata is not None:
            updates.append("metadata = %s")
            values.append(json.dumps(update.metadata))
        updates.append("updated_at = NOW()")
        values.append(instance_id)

        cursor.execute(f"""
            UPDATE globe_chain_instances SET {', '.join(updates)}
            WHERE id = %s
            RETURNING id, chain_id, province_id, company_name, current_stage, stage_order,
                      pipeline_value, actual_value, probability, metadata, updated_at
        """, tuple(values))

        result = cursor.fetchone()
        conn.commit()

        # Log stage transition
        if update.current_stage and update.current_stage != old_stage:
            cursor.execute("""
                INSERT INTO globe_stage_transitions (chain_instance_id, from_stage, to_stage)
                VALUES (%s, %s, %s)
            """, (instance_id, old_stage, new_stage))

            # Update province stats
            if new_stage == "customer":
                cursor.execute("""
                    UPDATE globe_provinces
                    SET total_companies = total_companies + 1,
                        total_leads = total_leads + 1,
                        updated_at = NOW()
                    WHERE id = (SELECT province_id FROM globe_chain_instances WHERE id = %s)
                """, (instance_id,))

        cursor.close()
        conn.close()

        return {
            "id": str(result[0]), "chain_id": str(result[1]), "province_id": str(result[2]) if result[2] else None,
            "company_name": result[3], "current_stage": result[4], "stage_order": result[5],
            "pipeline_value": float(result[6]) if result[6] else 0,
            "actual_value": float(result[7]) if result[7] else 0,
            "probability": float(result[8]) if result[8] else 0,
            "metadata": result[9] or {},
            "updated_at": str(result[10]),
            "stage_changed": update.current_stage is not None and update.current_stage != old_stage
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chains/instances")
async def list_chain_instances(
    chain_id: Optional[str] = None,
    stage: Optional[str] = None,
    province_id: Optional[str] = None,
    limit: int = 100
):
    """List chain instances with filters"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT ci.*, gc.name as chain_name, gp.name as province_name
            FROM globe_chain_instances ci
            LEFT JOIN globe_chains gc ON ci.chain_id = gc.id
            LEFT JOIN globe_provinces gp ON ci.province_id = gp.id
            WHERE 1=1
        """
        params = []
        if chain_id:
            query += " AND ci.chain_id = %s"
            params.append(chain_id)
        if stage:
            query += " AND ci.current_stage = %s"
            params.append(stage)
        if province_id:
            query += " AND ci.province_id = %s"
            params.append(province_id)
        query += " ORDER BY ci.created_at DESC LIMIT %s"
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {"id": str(r[0]), "chain_id": str(r[1]), "province_id": str(r[2]) if r[2] else None,
             "company_name": r[3], "company_email": r[4], "company_phone": r[5],
             "contact_name": r[6], "contact_email": r[7], "current_stage": r[8],
             "stage_order": r[9], "pipeline_value": float(r[10]) if r[10] else 0,
             "actual_value": float(r[11]) if r[11] else 0, "probability": float(r[12]) if r[12] else 0,
             "created_at": str(r[18]), "chain_name": r[23], "province_name": r[24]}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/chains/pipeline")
async def get_pipeline_stats():
    """Get production chain funnel statistics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT current_stage, COUNT(*) as count, SUM(pipeline_value) as total_value,
                   AVG(probability) as avg_probability
            FROM globe_chain_instances
            GROUP BY current_stage
            ORDER BY MIN(stage_order)
        """)
        rows = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) as total, SUM(actual_value) as realized,
                   SUM(CASE WHEN current_stage = 'customer' THEN 1 ELSE 0 END) as customers
            FROM globe_chain_instances
        """)
        totals = cursor.fetchone()

        cursor.close()
        conn.close()

        return {
            "by_stage": [
                {"stage": r[0], "count": r[1], "total_value": float(r[2] or 0),
                 "avg_probability": float(r[3] or 0)}
                for r in rows
            ],
            "totals": {
                "total_instances": totals[0] or 0,
                "realized_value": float(totals[1] or 0),
                "total_customers": totals[2] or 0
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Discovery Tree Endpoints
# ============================================================

@router.get("/discovery/tree")
async def get_discovery_tree(category: Optional[str] = None):
    """Get the full discovery tree structure"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT id, node_code, category, parent_code, name, name_vi, description,
                   description_vi, node_type, keywords, related_industries, icon, color,
                   search_count, selection_count, is_active
            FROM globe_discovery_nodes
            WHERE is_active = true
        """
        params = []
        if category:
            query += " AND category = %s"
            params.append(category)
        query += " ORDER BY category, parent_code NULLS FIRST, node_type, name"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Build tree structure
        nodes = {}
        for r in rows:
            node_id = str(r[0])
            node = {
                "id": node_id, "node_code": r[1], "category": r[2], "parent_code": r[3],
                "name": r[4], "name_vi": r[5], "description": r[6], "description_vi": r[7],
                "node_type": r[8], "keywords": r[9] if isinstance(r[9], list) else [],
                "related_industries": r[10] if isinstance(r[10], list) else [],
                "icon": r[11], "color": r[12],
                "search_count": r[13] or 0, "selection_count": r[14] or 0,
                "children": []
            }
            nodes[node_id] = node

        # Build hierarchy
        tree = []
        for node in nodes.values():
            if node["parent_code"]:
                parent = next((n for n in nodes.values() if n["node_code"] == node["parent_code"]), None)
                if parent:
                    parent["children"].append(node)
            else:
                tree.append(node)

        if category:
            return tree
        return {"categories": tree}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discovery/search")
async def search_discovery_nodes(request: DiscoverySearchRequest):
    """Semantic search across discovery nodes using Qdrant"""
    try:
        embedding = get_embedding(request.query)

        # Search in Qdrant
        try:
            resp = requests.post(
                f"{QDRANT_URL}/collections/globe_nodes/points/search",
                json={
                    "vector": embedding,
                    "limit": request.limit,
                    "with_payload": True,
                    "score_threshold": 0.5
                },
                timeout=10
            )

            if resp.status_code == 200:
                results = resp.json().get("result", [])
                return {"results": [
                    {"id": r["id"], "score": r["score"], "payload": r["payload"]}
                    for r in results
                ], "source": "qdrant"}
        except Exception:
            pass

        # Fallback to keyword search in PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT id, node_code, category, name, name_vi, description, node_type, icon, color
            FROM globe_discovery_nodes
            WHERE is_active = true
        """
        params = []
        if request.category:
            query += " AND category = %s"
            params.append(request.category)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return {
            "results": [
                {"id": str(r[0]), "node_code": r[1], "category": r[2], "name": r[3],
                 "name_vi": r[4], "description": r[5], "node_type": r[6], "icon": r[7], "color": r[8]}
                for r in rows
            ],
            "source": "postgresql"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/discovery/select")
async def record_discovery_selection(selection: DiscoverySelectRequest):
    """Record a discovery tree selection"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO globe_discovery_selections
            (node_id, user_id, session_id, selection_path, result_context)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, created_at
        """, (
            selection.node_id, selection.user_id, selection.session_id,
            json.dumps(selection.selection_path),
            json.dumps(selection.result_context or {})
        ))

        result = cursor.fetchone()

        # Update node selection count
        cursor.execute("""
            UPDATE globe_discovery_nodes
            SET selection_count = selection_count + 1, updated_at = NOW()
            WHERE id = %s
        """, (selection.node_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {"id": str(result[0]), "created_at": str(result[1])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/discovery/analytics")
async def get_discovery_analytics():
    """Get discovery tree analytics"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Top selected nodes
        cursor.execute("""
            SELECT dn.node_code, dn.name, dn.category, COUNT(ds.id) as selections
            FROM globe_discovery_nodes dn
            JOIN globe_discovery_selections ds ON ds.node_id = dn.id
            GROUP BY dn.id, dn.node_code, dn.name, dn.category
            ORDER BY selections DESC LIMIT 10
        """)
        top_nodes = [{"node_code": r[0], "name": r[1], "category": r[2], "selections": r[3]} for r in cursor.fetchall()]

        # Selections by category
        cursor.execute("""
            SELECT dn.category, COUNT(ds.id) as selections
            FROM globe_discovery_nodes dn
            JOIN globe_discovery_selections ds ON ds.node_id = dn.id
            GROUP BY dn.category
            ORDER BY selections DESC
        """)
        by_category = [{"category": r[0], "selections": r[1]} for r in cursor.fetchall()]

        cursor.close()
        conn.close()

        return {"top_nodes": top_nodes, "by_category": by_category}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Analytics Pipeline Endpoints
# ============================================================

@router.get("/pipelines")
async def list_pipelines(pipeline_type: Optional[str] = None):
    """List all analytics pipelines"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = "SELECT * FROM globe_pipelines WHERE is_active = true"
        params = []
        if pipeline_type:
            query += " AND pipeline_type = %s"
            params.append(pipeline_type)
        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        return [
            {"id": str(r[0]), "pipeline_code": r[1], "name": r[2], "name_vi": r[3],
             "description": r[4], "pipeline_type": r[5], "stages": r[6] if isinstance(r[6], list) else [],
             "source_config": r[7] or {}, "destination_config": r[8] or {},
             "is_active": r[9], "schedule_cron": r[10],
             "last_run_at": str(r[11]) if r[11] else None,
             "next_run_at": str(r[12]) if r[12] else None}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipelines")
async def create_pipeline(pipeline: PipelineCreate):
    """Create a new analytics pipeline"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO globe_pipelines
            (pipeline_code, name, name_vi, description, pipeline_type, stages, source_config, destination_config, schedule_cron)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, pipeline_code, name, created_at
        """, (
            pipeline.pipeline_code, pipeline.name, pipeline.name_vi, pipeline.description,
            pipeline.pipeline_type, json.dumps(pipeline.stages),
            json.dumps(pipeline.source_config or {}),
            json.dumps(pipeline.destination_config or {}),
            pipeline.schedule_cron
        ))

        result = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {"id": str(result[0]), "pipeline_code": result[1], "name": result[2], "created_at": str(result[3])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/pipelines/runs")
async def list_pipeline_runs(pipeline_id: Optional[str] = None, limit: int = 20):
    """List pipeline run history"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        query = """
            SELECT pr.*, gp.pipeline_code, gp.name
            FROM globe_pipeline_runs pr
            LEFT JOIN globe_pipelines gp ON pr.pipeline_id = gp.id
            WHERE 1=1
        """
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

        return [
            {"id": str(r[0]), "pipeline_id": str(r[1]) if r[1] else None,
             "run_status": r[2], "started_at": str(r[3]) if r[3] else None,
             "completed_at": str(r[4]) if r[4] else None,
             "records_processed": r[5] or 0, "records_failed": r[6] or 0,
             "error_message": r[7], "pipeline_code": r[10], "pipeline_name": r[11]}
            for r in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/pipelines/{pipeline_id}/run")
async def trigger_pipeline_run(pipeline_id: str):
    """Trigger a pipeline run"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Create run record
        cursor.execute("""
            INSERT INTO globe_pipeline_runs (pipeline_id, run_status, started_at)
            VALUES (%s, 'queued', NOW())
            RETURNING id
        """, (pipeline_id,))
        run_id = str(cursor.fetchone()[0])

        # Update pipeline last_run
        cursor.execute("""
            UPDATE globe_pipelines SET last_run_at = NOW(), updated_at = NOW()
            WHERE id = %s
        """, (pipeline_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return {"run_id": run_id, "status": "queued", "message": "Pipeline run queued"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================
# Globe Overview Dashboard
# ============================================================

@router.get("/dashboard")
async def get_globe_dashboard():
    """Get comprehensive Globe AI City data layer overview"""
    try:
        province_stats = await get_province_stats()
        pipeline_stats = await get_pipeline_stats()
        discovery_analytics = await get_discovery_analytics()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Globe health check
        cursor.execute("""
            SELECT COUNT(*) FROM globe_industries WHERE is_active = true
        """)
        industry_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM globe_regions WHERE is_active = true
        """)
        region_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM globe_discovery_nodes WHERE is_active = true
        """)
        discovery_node_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM globe_pipelines WHERE is_active = true
        """)
        pipeline_count = cursor.fetchone()[0]

        cursor.close()
        conn.close()

        return {
            "status": "operational",
            "provinces": province_stats,
            "pipeline": pipeline_stats,
            "discovery": discovery_analytics,
            "counts": {
                "industries": industry_count,
                "regions": region_count,
                "discovery_nodes": discovery_node_count,
                "pipelines": pipeline_count
            }
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
