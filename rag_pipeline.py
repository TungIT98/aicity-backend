"""
AI City RAG Pipeline
Integrates Ollama embeddings with Qdrant vector database
"""

import requests
import json
import hashlib
from typing import List, Dict, Optional

# Configuration
OLLAMA_BASE_URL = "http://localhost:11434"
QDRANT_HOST = "localhost"  # Use localhost for local access
QDRANT_PORT = 6333
COLLECTION_NAME = "ai_city_rag"

class RAGPipeline:
    def __init__(self, embedding_model: str = "nomic-embed-text"):
        self.embedding_model = embedding_model
        self.qdrant_url = f"http://{QDRANT_HOST}:{QDRANT_PORT}"

    def get_embedding(self, text: str) -> List[float]:
        """Generate embedding using Ollama"""
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/embeddings",
            json={"model": self.embedding_model, "prompt": text}
        )
        response.raise_for_status()
        return response.json()["embedding"]

    def create_collection(self, vector_size: int = 768):
        """Create Qdrant collection"""
        collections_url = f"{self.qdrant_url}/collections/{COLLECTION_NAME}"

        # Check if exists
        existing = requests.get(f"{self.qdrant_url}/collections")
        if COLLECTION_NAME in [c["name"] for c in existing.json().get("result", {}).get("collections", [])]:
            print(f"Collection {COLLECTION_NAME} already exists")
            return

        # Create collection
        response = requests.put(
            collections_url,
            json={
                "vectors": {
                    "size": vector_size,
                    "distance": "Cosine"
                }
            }
        )
        print(f"Collection created: {response.json()}")

    def add_documents(self, documents: List[Dict[str, str]], batch_size: int = 10):
        """Add documents to vector store"""
        points = []
        for i, doc in enumerate(documents):
            embedding = self.get_embedding(doc["content"])
            points.append({
                "id": i + 1,
                "vector": embedding,
                "payload": {
                    "title": doc.get("title", ""),
                    "content": doc["content"],
                    "metadata": doc.get("metadata", {})
                }
            })

            # Batch insert
            if len(points) >= batch_size:
                self._upsert_points(points)
                points = []

        if points:
            self._upsert_points(points)

    def _upsert_points(self, points: List[Dict]):
        """Insert points into Qdrant"""
        response = requests.post(
            f"{self.qdrant_url}/collections/{COLLECTION_NAME}/points",
            json={"points": points}
        )
        print(f"Inserted {len(points)} points: {response.json()}")

    def search(self, query: str, limit: int = 5) -> List[Dict]:
        """Semantic search"""
        query_embedding = self.get_embedding(query)

        response = requests.post(
            f"{self.qdrant_url}/collections/{COLLECTION_NAME}/points/search",
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
                "title": r["payload"]["title"],
                "content": r["payload"]["content"]
            }
            for r in results
        ]

    def delete_collection(self):
        """Delete collection"""
        response = requests.delete(f"{self.qdrant_url}/collections/{COLLECTION_NAME}")
        return response.json()


def generate_api_key(name: str) -> str:
    """Generate API key hash"""
    raw_key = f"{name}_{hashlib.random_bytes(16).hex()}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return f"aicity_{raw_key}", key_hash


if __name__ == "__main__":
    # Demo usage
    rag = RAGPipeline()

    # Create collection
    rag.create_collection()

    # Add sample documents
    docs = [
        {"title": "AI City Overview", "content": "AI City is a self-hosted AI infrastructure with Ollama, Qdrant, PostgreSQL, n8n, and Matomo."},
        {"title": "Backend Architecture", "content": "The backend uses PostgreSQL for data storage, Qdrant for vector embeddings, and Ollama for AI processing."},
        {"title": "API Development", "content": "API endpoints provide access to AI models, vector search, and dashboard analytics."}
    ]
    rag.add_documents(docs)

    # Search
    results = rag.search("Tell me about the AI infrastructure")
    print("\nSearch results:")
    for r in results:
        print(f"  - {r['title']} (score: {r['score']:.3f})")
