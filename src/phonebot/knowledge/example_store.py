"""Few-shot example store for RAG-style retrieval.

Uses ChromaDB (embedded, no server) to store transcript→ground_truth pairs
as a searchable vector collection. At extraction time, retrieves the most
similar past transcripts with their correct extractions, formatted as
few-shot examples for the LLM prompt.

This is the highest-impact knowledge grounding component: the hardest cases
(foreign names like "García" transcribed as "Gassia") benefit enormously
from seeing a similar solved example in-context.

Usage:
    store = ExampleStore()
    store.index_ground_truth(ground_truth, transcripts_dir)

    # At extraction time
    examples = store.retrieve("Mein Name ist Gassia...", k=2)
    # Returns formatted few-shot examples for prompt injection
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from phonebot.pipeline.transcribe import get_transcript_text


class ExampleStore:
    """Vector-backed store for transcript→extraction example retrieval.

    Uses ChromaDB embedded mode — no server required. The collection is
    persisted to disk so it survives restarts.
    """

    def __init__(
        self,
        persist_dir: str = ".chromadb",
        collection_name: str = "phonebot_examples",
    ) -> None:
        import chromadb

        self._client = chromadb.PersistentClient(path=persist_dir)
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    @property
    def count(self) -> int:
        """Number of examples in the store."""
        return self._collection.count()

    def index_ground_truth(
        self,
        ground_truth: dict[str, dict],
        transcripts_dir: Path = Path("data/transcripts"),
    ) -> int:
        """Index all ground truth examples with their transcript text.

        Args:
            ground_truth: Dict keyed by recording_id with expected values.
            transcripts_dir: Directory containing cached transcript JSON files.

        Returns:
            Number of examples indexed.
        """
        ids: list[str] = []
        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []

        for rec_id, expected in sorted(ground_truth.items()):
            cache_path = transcripts_dir / f"{rec_id}.json"
            if not cache_path.exists():
                continue

            transcript = get_transcript_text(cache_path)
            if not transcript:
                continue

            # Store expected extraction as metadata
            metadata: dict[str, Any] = {
                "recording_id": rec_id,
                "first_name": expected.get("first_name") or "",
                "last_name": expected.get("last_name") or "",
                "email": expected.get("email") or "",
                "phone_number": (
                    expected.get("phone_number")
                    if isinstance(expected.get("phone_number"), str)
                    else ""
                ),
            }

            ids.append(rec_id)
            documents.append(transcript)
            metadatas.append(metadata)

        if ids:
            # Upsert to handle re-indexing
            self._collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
            )

        return len(ids)

    def retrieve(
        self,
        query_transcript: str,
        k: int = 2,
        exclude_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve the most similar examples for a transcript.

        Args:
            query_transcript: The transcript to find similar examples for.
            k: Number of examples to retrieve.
            exclude_id: Recording ID to exclude (e.g., the current recording
                        to avoid retrieving its own ground truth).

        Returns:
            List of dicts with keys: recording_id, transcript, expected,
            similarity_score.
        """
        # Fetch extra to allow filtering
        n_results = k + (1 if exclude_id else 0)
        n_results = min(n_results, self.count or 1)

        results = self._collection.query(
            query_texts=[query_transcript],
            n_results=n_results,
        )

        examples = []
        for i in range(len(results["ids"][0])):
            rec_id = results["ids"][0][i]

            # Skip self-retrieval
            if exclude_id and rec_id == exclude_id:
                continue

            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i] if results.get("distances") else None

            examples.append({
                "recording_id": rec_id,
                "transcript": results["documents"][0][i],
                "expected": {
                    "first_name": metadata.get("first_name") or None,
                    "last_name": metadata.get("last_name") or None,
                    "email": metadata.get("email") or None,
                    "phone_number": metadata.get("phone_number") or None,
                },
                "similarity_score": round(1 - distance, 3) if distance is not None else None,
            })

            if len(examples) >= k:
                break

        return examples

    def format_few_shot_prompt(
        self,
        examples: list[dict[str, Any]],
        max_transcript_chars: int = 500,
    ) -> str:
        """Format retrieved examples as a few-shot prompt section.

        Args:
            examples: Output from retrieve().
            max_transcript_chars: Truncate transcript to this length.

        Returns:
            Formatted string to prepend to the extraction prompt.
        """
        if not examples:
            return ""

        parts = ["Here are examples of similar transcripts with correct extractions:\n"]

        for i, ex in enumerate(examples, 1):
            transcript = ex["transcript"]
            if len(transcript) > max_transcript_chars:
                transcript = transcript[:max_transcript_chars] + "..."

            expected = ex["expected"]
            parts.append(f"--- Example {i} ---")
            parts.append(f"Transcript: {transcript}")
            parts.append("Correct extraction:")
            parts.append(f"  first_name: {expected.get('first_name') or 'null'}")
            parts.append(f"  last_name: {expected.get('last_name') or 'null'}")
            parts.append(f"  email: {expected.get('email') or 'null'}")
            parts.append(f"  phone_number: {expected.get('phone_number') or 'null'}")
            parts.append("")

        parts.append("Now extract from the following transcript:\n")
        return "\n".join(parts)
