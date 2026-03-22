"""
Storage Infrastructure API - PostgreSQL + Qdrant Vector DB.
Endpoints for storage health, vector search, and ETL pipeline management.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import os
import logging

from storage.database import check_connection as check_pg_connection
from storage.qdrant_service import QdrantService, get_qdrant_service, CollectionConfig, DEFAULT_COLLECTIONS
from storage.etl_pipeline import EmbeddingPipeline

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/storage", tags=["Storage"])


# ---- Health ----

@router.get("/health")
async def storage_health():
    """Combined health check for PostgreSQL, pgvector (primary), and Qdrant (optional)."""
    from storage.pgvector_service import get_pgvector_service

    pg = await check_pg_connection()
    pgvector = await get_pgvector_service().health_check()
    qdrant = get_qdrant_service().health_check()

    # pgvector is primary (Neon-based, always accessible from Vercel)
    # Qdrant is optional (requires public endpoint)
    pgvector_ok = pgvector.get("status") == "ok"
    qdrant_ok = qdrant.get("status") == "ok"

    return {
        "postgresql": pg,
        "pgvector": pgvector,
        "qdrant": qdrant,
        "primary_vector_store": "pgvector",
        "overall": "ok" if pgvector_ok else "degraded",
        "note": "pgvector (Neon) is the primary vector store - Vercel compatible. Qdrant is optional.",
    }


@router.get("/health/pg")
async def pg_health():
    """PostgreSQL health check."""
    return await check_pg_connection()


@router.get("/health/qdrant")
async def qdrant_health():
    """Qdrant health check."""
    return get_qdrant_service().health_check()


# ---- Qdrant Collections ----

class CreateCollectionRequest(BaseModel):
    name: str
    vector_size: int = 768
    distance: str = "Cosine"
    hnsw_m: int = 16
    hnsw_ef_construct: int = 128
    description: str = ""


class UpsertPointRequest(BaseModel):
    collection: str
    point_id: str
    vector: list[float]
    payload: Optional[dict] = None


class SearchRequest(BaseModel):
    collection: str
    query_vector: list[float]
    limit: int = 5
    score_threshold: Optional[float] = None


@router.get("/qdrant/collections")
async def list_collections():
    """List all Qdrant collections."""
    service = get_qdrant_service()
    health = service.health_check()
    if health.get("status") == "unavailable":
        raise HTTPException(503, f"Qdrant unavailable: {health.get('error')}")
    return {"collections": health.get("collections", [])}


@router.post("/qdrant/collections")
async def create_collection(req: CreateCollectionRequest):
    """Create a new Qdrant collection."""
    from qdrant_client.models import Distance as QdrantDistance

    distance_map = {"Cosine": QdrantDistance.COSINE, "Euclidean": QdrantDistance.EUCLID, "Dot": QdrantDistance.DOT}
    if req.distance not in distance_map:
        raise HTTPException(400, f"Invalid distance: {req.distance}. Use: Cosine, Euclidean, Dot")

    config = CollectionConfig(
        name=req.name,
        vector_size=req.vector_size,
        distance=distance_map[req.distance],
        hnsw_m=req.hnsw_m,
        hnsw_ef_construct=req.hnsw_ef_construct,
        description=req.description,
    )
    result = get_qdrant_service().create_collection(config)
    return result


@router.get("/qdrant/collections/{collection}")
async def get_collection(collection: str):
    """Get collection info."""
    info = get_qdrant_service().get_collection_info(collection)
    if "error" in info:
        raise HTTPException(404, info["error"])
    return info


@router.delete("/qdrant/collections/{collection}")
async def delete_collection(collection: str):
    """Delete a collection."""
    result = get_qdrant_service().delete_collection(collection)
    if result.get("status") == "error":
        raise HTTPException(500, result["error"])
    return result


@router.post("/qdrant/collections/initialize")
async def initialize_default_collections():
    """Initialize all default AI City collections."""
    results = get_qdrant_service().initialize_collections()
    return {"results": results}


# ---- Vector Operations ----

@router.post("/qdrant/search")
async def vector_search(req: SearchRequest):
    """Semantic vector search in a collection."""
    results = get_qdrant_service().search(
        collection=req.collection,
        query_vector=req.query_vector,
        limit=req.limit,
        score_threshold=req.score_threshold,
    )
    if results and "error" in results[0]:
        raise HTTPException(500, results[0]["error"])
    return {"results": results}


# ---- ETL Pipeline ----

class SyncDocumentsRequest(BaseModel):
    collection: str
    text_field: str = "content"
    id_field: str = "id"


@router.post("/etl/sync")
async def trigger_sync(req: SyncDocumentsRequest):
    """
    Trigger ETL sync from PostgreSQL documents to Qdrant.
    Note: In production, this would read from the async DB session.
    Returns pipeline status for manual/scheduled runs.
    """
    pipeline = EmbeddingPipeline()
    return {
        "status": "ready",
        "collection": req.collection,
        "note": "Call embedding_pipeline.sync_documents() with actual DB data",
        "qdrant_collections": list(DEFAULT_COLLECTIONS.keys()),
    }


@router.post("/etl/embed")
async def embed_and_upsert(req: UpsertPointRequest):
    """Generate embedding and upsert to Qdrant."""
    pipeline = EmbeddingPipeline()
    result = pipeline.upsert_embedding(
        collection=req.collection,
        doc_id=req.point_id,
        text=req.payload.get("text", "") if req.payload else "",
        payload=req.payload,
    )
    return result


# ---- pgvector (Primary Vector Store) ----

class VectorSearchRequest(BaseModel):
    query: str
    table: str = "embeddings"
    limit: int = 5
    score_threshold: Optional[float] = None
    entity_type: Optional[str] = None


class UpsertVectorRequest(BaseModel):
    content: str
    table: str = "embeddings"
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    metadata: Optional[dict] = None


class BatchUpsertRequest(BaseModel):
    documents: list[dict]
    table: str = "embeddings"
    text_field: str = "content"
    entity_type: Optional[str] = None


@router.get("/pgvector/health")
async def pgvector_health():
    """Check pgvector extension and embedding tables status."""
    from storage.pgvector_service import get_pgvector_service
    return await get_pgvector_service().health_check()


@router.post("/pgvector/tables/init")
async def init_pgvector_table(table: str = "embeddings"):
    """Initialize embeddings table with pgvector extension."""
    from storage.pgvector_service import get_pgvector_service
    from storage.database import async_session
    async with async_session() as session:
        try:
            ext = await get_pgvector_service().ensure_extension(session)
            table_result = await get_pgvector_service().create_embeddings_table(session, table)
            return {"extension": ext, "table": table_result}
        finally:
            await session.close()


@router.post("/pgvector/upsert")
async def upsert_vector(req: UpsertVectorRequest):
    """Generate embedding and upsert to pgvector (Neon)."""
    from storage.etl_pipeline import EmbeddingPipeline
    pipeline = EmbeddingPipeline()
    return await pipeline.upsert_embedding_pgvector(
        content=req.content,
        table=req.table,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        metadata=req.metadata,
    )


@router.post("/pgvector/batch")
async def batch_upsert_vectors(req: BatchUpsertRequest):
    """Batch upsert documents with embeddings to pgvector."""
    from storage.etl_pipeline import EmbeddingPipeline
    pipeline = EmbeddingPipeline()
    return await pipeline.batch_upsert_pgvector(
        documents=req.documents,
        table=req.table,
        text_field=req.text_field,
        entity_type=req.entity_type,
    )


@router.post("/pgvector/search")
async def search_vectors(req: VectorSearchRequest):
    """
    Vector similarity search via pgvector (Neon).
    Generates embedding from query text and finds similar documents.
    """
    from storage.pgvector_service import get_pgvector_service
    from storage.database import async_session
    from storage.etl_pipeline import get_ollama_embedding_async

    vector = await get_ollama_embedding_async(req.query)
    if not vector:
        raise HTTPException(503, "Ollama unavailable for embedding. Set OLLAMA_BASE_URL or use pre-computed vectors.")

    async with async_session() as session:
        try:
            results = await get_pgvector_service().search_similar(
                session=session,
                query_vector=vector,
                table=req.table,
                limit=req.limit,
                score_threshold=req.score_threshold,
                entity_type=req.entity_type,
            )
            if results and "error" in results[0]:
                raise HTTPException(500, results[0]["error"])
            return {"results": results, "query": req.query, "store": "pgvector"}
        finally:
            await session.close()


@router.get("/pgvector/stats")
async def pgvector_stats(table: str = "embeddings"):
    """Get embedding table statistics."""
    from storage.pgvector_service import get_pgvector_service
    from storage.database import async_session
    async with async_session() as session:
        try:
            return await get_pgvector_service().get_table_stats(session, table)
        finally:
            await session.close()


@router.delete("/pgvector/{id}")
async def delete_vector(id: str, table: str = "embeddings"):
    """Delete an embedding by ID."""
    from storage.pgvector_service import get_pgvector_service
    from storage.database import async_session
    async with async_session() as session:
        try:
            result = await get_pgvector_service().delete_embedding(session, id, table)
            return result
        finally:
            await session.close()


# ---- PostgreSQL Analysis & Warehouse ----

class VacuumRequest(BaseModel):
    table: str


class WarehouseViewRequest(BaseModel):
    view: str  # specific view name, or "all"


@router.get("/pg/analyze")
async def pg_analyze():
    """Run full PostgreSQL analysis: slow queries, index usage, table sizes, connection stats."""
    from storage.database import (
        analyze_slow_queries, analyze_index_usage,
        analyze_table_sizes, analyze_connection_stats, run_full_analysis
    )
    results = await run_full_analysis()
    return results


@router.get("/pg/tables")
async def pg_table_sizes():
    """Get table size statistics for all tables."""
    from storage.database import analyze_table_sizes
    return await analyze_table_sizes()


@router.get("/pg/indexes")
async def pg_index_usage():
    """Get index usage statistics."""
    from storage.database import analyze_index_usage
    return await analyze_index_usage()


@router.get("/pg/slow-queries")
async def pg_slow_queries(limit: int = 10):
    """Get slowest queries from pg_stat_statements."""
    from storage.database import analyze_slow_queries
    return await analyze_slow_queries(limit=limit)


@router.get("/pg/connections")
async def pg_connection_stats():
    """Get PostgreSQL connection and activity statistics."""
    from storage.database import analyze_connection_stats
    return await analyze_connection_stats()


@router.post("/pg/vacuum")
async def pg_vacuum(req: VacuumRequest):
    """Run VACUUM ANALYZE on a specific table."""
    from storage.database import vacuum_analyze_table, get_db
    async for session in get_db():
        try:
            result = await vacuum_analyze_table(session, req.table)
            return result
        finally:
            await session.close()
            break


@router.get("/pg/warehouse/views")
async def pg_warehouse_views():
    """List available data warehouse views."""
    views = [
        "v_revenue_summary",
        "v_lead_funnel",
        "v_subscription_status",
        "v_invoice_summary",
        "v_payment_status",
    ]
    return {"views": views}


@router.post("/pg/warehouse/views/create")
async def pg_create_warehouse_views():
    """Create or replace all data warehouse views."""
    from storage.database import create_warehouse_views, get_db
    async for session in get_db():
        try:
            results = await create_warehouse_views(session)
            return {"results": results}
        finally:
            await session.close()
            break
