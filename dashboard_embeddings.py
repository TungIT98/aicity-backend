"""
AI City Dashboard Embeddings
Generate and query vector embeddings for dashboard analytics content
"""

import requests
import json
from typing import List, Dict, Optional
from datetime import datetime

QDRANT_URL = "http://localhost:6333"
OLLAMA_URL = "http://localhost:11434"
COLLECTION_NAME = "dashboard_research"


def get_embedding(text: str) -> List[float]:
    """Get embedding from Ollama"""
    response = requests.post(
        f"{OLLAMA_URL}/api/embeddings",
        json={"model": "nomic-embed-text", "prompt": text}
    )
    response.raise_for_status()
    return response.json()["embedding"]


def create_dashboard_collection():
    """Create dashboard research collection if not exists"""
    # Check if exists
    response = requests.get(f"{QDRANT_URL}/collections")
    collections = response.json().get("result", {}).get("collections", [])
    collection_names = [c["name"] for c in collections]

    if COLLECTION_NAME in collection_names:
        print(f"Collection {COLLECTION_NAME} already exists")
        return

    # Create collection
    response = requests.put(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}",
        json={
            "vectors": {
                "size": 768,
                "distance": "Cosine"
            }
        }
    )
    print(f"Created collection: {response.json()}")


def add_dashboard_content(title: str, content: str, content_type: str = "general", metadata: Optional[Dict] = None):
    """Add dashboard content to vector store"""
    embedding = get_embedding(content)

    import uuid
    point_id = int(str(uuid.uuid4().int)[:8], 10)

    payload = {
        "title": title,
        "content": content,
        "content_type": content_type,
        "created_at": datetime.now().isoformat(),
        "metadata": metadata or {}
    }

    response = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points",
        json={
            "points": [{
                "id": point_id,
                "vector": embedding,
                "payload": payload
            }],
            "ids": [point_id]
        }
    )

    if response.status_code in (200, 201):
        print(f"Added: {title}")
        return point_id
    else:
        print(f"Error adding {title}: {response.text}")
        return None


def search_dashboard(query: str, limit: int = 5) -> List[Dict]:
    """Semantic search on dashboard content"""
    query_embedding = get_embedding(query)

    response = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search",
        json={
            "vector": query_embedding,
            "limit": limit,
            "with_payload": True
        }
    )

    results = response.json().get("result", [])
    return [
        {
            "id": r["id"],
            "score": r["score"],
            "title": r["payload"].get("title", ""),
            "content": r["payload"].get("content", ""),
            "content_type": r["payload"].get("content_type", ""),
            "created_at": r["payload"].get("created_at", "")
        }
        for r in results
    ]


def get_collection_stats():
    """Get collection statistics"""
    try:
        response = requests.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
        return response.json()
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    # Create collection
    create_dashboard_collection()

    # Sample dashboard content
    dashboard_docs = [
        {
            "title": "User Analytics Overview",
            "content": "Dashboard shows user engagement metrics including daily active users, session duration, and user retention rates. Key KPIs: DAU 1,234, retention rate 67%.",
            "content_type": "metrics"
        },
        {
            "title": "API Usage Statistics",
            "content": "API endpoint usage data showing top endpoints, error rates, and response times. Total requests: 45,678/day, avg response time: 234ms.",
            "content_type": "api"
        },
        {
            "title": "Content Performance",
            "content": "Content analytics including page views, bounce rates, and conversion rates. Top performing content: AI guides, product pages.",
            "content_type": "content"
        },
        {
            "title": "Revenue Dashboard",
            "content": "Revenue metrics including monthly recurring revenue, customer lifetime value, and churn rate. MRR: $12,450, Churn: 2.3%.",
            "content_type": "revenue"
        },
        {
            "title": "Technical Performance",
            "content": "System health metrics including server uptime, database performance, and API latency. Uptime: 99.9%, DB query avg: 45ms.",
            "content_type": "technical"
        }
    ]

    # Add sample content
    print("\nAdding sample dashboard content...")
    for doc in dashboard_docs:
        add_dashboard_content(
            title=doc["title"],
            content=doc["content"],
            content_type=doc["content_type"]
        )

    # Test search
    print("\nTesting search...")
    results = search_dashboard("Show me user engagement and API performance")
    print("\nSearch results:")
    for r in results:
        print(f"  - {r['title']} ({r['content_type']}) - score: {r['score']:.3f}")
        print(f"    {r['content'][:100]}...")
