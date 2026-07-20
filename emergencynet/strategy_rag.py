"""ChromaDB dual-collection RAG store.

Two collections live side-by-side in ``data/chroma_db``:

    hazmat_rag    — chunks from ERG 2024, CDC Blast, HazMat refs
    command_rag   — chunks from FEMA NIMS IS-100/200/700, WHO MCI

Embeddings: ``sentence-transformers/all-MiniLM-L6-v2`` exported to ONNX
and run on CPU. We use Chroma's built-in ONNX MiniLM embedding function
which loads from the package itself (no internet required at runtime).

Build path (run-once, offline):
    1. Operator runs ``scripts/build_rag_db.py`` against a folder of
       JSON files (one per source) following the schema documented in
       ``scripts/CHATGPT_PROMPT_HAZMAT.md`` / ``CHATGPT_PROMPT_COMMAND.md``
    2. Deprecated for runtime strategy (ADR 0005 / v5.3); use offline
       ``scripts/build_rag_db.py`` only.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional

DEFAULT_HAZMAT = "hazmat_rag"
DEFAULT_COMMAND = "command_rag"


class RAGStore:
    """Thin wrapper around two persistent Chroma collections."""

    def __init__(
        self,
        persist_dir: str | Path = "data/chroma_db",
        hazmat_name: str = DEFAULT_HAZMAT,
        command_name: str = DEFAULT_COMMAND,
    ):
        self.persist_dir = str(persist_dir)
        self.hazmat_name = hazmat_name
        self.command_name = command_name
        self._client = None
        self._embed_fn = None
        self._hazmat = None
        self._command = None

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------
    def _ensure(self) -> None:
        if self._client is not None:
            return
        try:
            import chromadb                                            # type: ignore
            from chromadb.utils import embedding_functions as ef       # type: ignore
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for RAG. pip install chromadb sentence-transformers"
            ) from exc

        Path(self.persist_dir).mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=self.persist_dir)
        # ONNX MiniLM is bundled with Chroma — no network required.
        self._embed_fn = ef.ONNXMiniLM_L6_V2()

        self._hazmat = self._client.get_or_create_collection(
            name=self.hazmat_name, embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )
        self._command = self._client.get_or_create_collection(
            name=self.command_name, embedding_function=self._embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------
    # Ingest
    # ------------------------------------------------------------------
    def ingest_chunks(
        self,
        collection: str,
        chunks: List[Dict[str, Any]],
        batch_size: int = 64,
    ) -> int:
        """Add chunks to a collection. Each chunk dict must contain at
        least: ``id``, ``text``, ``source`` and may add arbitrary
        metadata fields."""
        self._ensure()
        col = self._pick(collection)
        added = 0
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            col.upsert(
                ids=[c["id"] for c in batch],
                documents=[c["text"] for c in batch],
                metadatas=[
                    {k: v for k, v in c.items() if k not in ("id", "text")}
                    for c in batch
                ],
            )
            added += len(batch)
        return added

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------
    def query(
        self,
        collection: str,
        text: str,
        k: int = 4,
        where: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        self._ensure()
        col = self._pick(collection)
        res = col.query(query_texts=[text], n_results=k, where=where)

        out: List[Dict[str, Any]] = []
        if not res or not res.get("documents"):
            return out
        docs = res["documents"][0]
        metas = (res.get("metadatas") or [[]])[0]
        ids = (res.get("ids") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        for i, doc in enumerate(docs):
            out.append({
                "id": ids[i] if i < len(ids) else None,
                "text": doc,
                "metadata": metas[i] if i < len(metas) else {},
                "distance": dists[i] if i < len(dists) else None,
            })
        return out

    def _pick(self, collection: str):
        if collection == self.hazmat_name or collection.lower() == "hazmat":
            return self._hazmat
        if collection == self.command_name or collection.lower() == "command":
            return self._command
        raise ValueError(f"unknown collection: {collection}")

    def stats(self) -> Dict[str, int]:
        self._ensure()
        return {
            self.hazmat_name: self._hazmat.count(),
            self.command_name: self._command.count(),
        }
