"""
Test suite for Qdrant Vector Search integration in BankOps SmartDoc.

Verifies:
1. Qdrant client initialization (in-memory mode).
2. Collection creation with vector configuration (Cosine distance, 768 dimensions).
3. Point upsertion with rich payload (SOP document metadata, tenant scoping).
4. Semantic vector similarity search and payload filtering.
5. Strict dimension mismatch validation.
"""

import pytest
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)


@pytest.fixture
def qdrant_client():
    client = QdrantClient(":memory:")
    yield client
    client.close()


def test_qdrant_collection_creation_and_vector_search(qdrant_client):
    collection_name = "smartdoc_kc03"
    vector_dim = 768

    # 1. Create collection
    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
    )

    info = qdrant_client.get_collection(collection_name)
    assert info.status == "green"
    assert info.config.params.vectors.size == vector_dim
    assert info.config.params.vectors.distance == Distance.COSINE

    # 2. Seed SOP vectors
    # SOP-01: Maker-Checker rule
    vec_maker_checker = [0.1] * vector_dim
    # SOP-02: FEFO inventory rule
    vec_fefo = [0.0] * vector_dim
    for i in range(0, vector_dim, 2):
        vec_fefo[i] = 0.2

    points = [
        PointStruct(
            id=1,
            vector=vec_maker_checker,
            payload={
                "document_id": "SOP-01",
                "title": "Quy trinh Kiem soat kep Maker-Checker",
                "tenant_id": "bankops-main",
                "category": "security",
            },
        ),
        PointStruct(
            id=2,
            vector=vec_fefo,
            payload={
                "document_id": "SOP-02",
                "title": "Quy chuan quan ly han su dung FEFO",
                "tenant_id": "bankops-main",
                "category": "inventory",
            },
        ),
    ]

    qdrant_client.upsert(collection_name=collection_name, points=points)

    # 3. Query vector search for Maker-Checker
    query_vec = [0.095] * vector_dim  # Very close to vec_maker_checker
    search_result = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vec,
        limit=2,
    ).points

    assert len(search_result) == 2
    assert search_result[0].payload["document_id"] == "SOP-01"
    assert search_result[0].score > 0.99

    # 4. Filtered search by tenant and category
    filtered_result = qdrant_client.query_points(
        collection_name=collection_name,
        query=query_vec,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="category",
                    match=MatchValue(value="inventory"),
                )
            ]
        ),
        limit=1,
    ).points

    assert len(filtered_result) == 1
    assert filtered_result[0].payload["document_id"] == "SOP-02"


def test_qdrant_dimension_validation(qdrant_client):
    collection_name = "dim_test"
    vector_dim = 768

    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
    )

    # Reject 512-dim vector into 768-dim collection
    with pytest.raises(Exception):
        qdrant_client.upsert(
            collection_name=collection_name,
            points=[
                PointStruct(
                    id=99,
                    vector=[0.1] * 512,
                    payload={"doc": "mismatch"},
                )
            ],
        )
