"""Indexer: validated documents → units + chunks (+ embeddings) in Postgres.

Idempotent per doc_id: re-ingesting replaces that document's units/chunks in one
transaction. Exact duplicates (content_hash) inside a collection are dropped and
logged. Every embedding goes through app.retrieval.embedder (Rule 1).
"""

import uuid
from collections.abc import Awaitable, Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.legal import authority_for
from app.db.models import Chunk, Document, Unit
from app.ingestion.chunker import ChunkDraft, CountTokens, chunk_unit
from app.ingestion.contract import DocumentIn, UnitIn
from app.retrieval import embedder

Embed = Callable[[list[str]], Awaitable[list[list[float]]]]


def _status(doc: DocumentIn, unit: UnitIn) -> str:
    if doc.status == "repealed":
        return "repealed"
    return "amended" if unit.valid_to else doc.status


async def _index_one(
    session: AsyncSession,
    doc: DocumentIn,
    collection_id: int,
    count_tokens: CountTokens,
    embed: Embed,
    dropped: list[dict],
) -> tuple[int, int]:
    drafts: list[tuple[UnitIn, ChunkDraft]] = []
    for unit in doc.units:
        chunks, why = await chunk_unit(doc, unit, count_tokens)
        dropped.extend({"doc_id": doc.doc_id, **d} for d in why)
        drafts.extend((unit, c) for c in chunks)

    await session.execute(delete(Document).where(Document.id == doc.doc_id))

    hashes = {c.content_hash for _, c in drafts}
    taken = set(
        (
            await session.execute(
                select(Chunk.content_hash).where(
                    Chunk.collection_id == collection_id, Chunk.content_hash.in_(hashes)
                )
            )
        ).scalars()
    )
    kept: list[tuple[UnitIn, ChunkDraft]] = []
    for unit, c in drafts:
        if c.content_hash in taken:
            dropped.append({"doc_id": doc.doc_id, "unit_id": unit.unit_id, "reason": "duplicate",
                            "text": c.text[:120]})
            continue
        taken.add(c.content_hash)
        kept.append((unit, c))

    vectors = await embed(
        [embedder.build_passage_input({"context_header": c.context_header, "text": c.text}) for _, c in kept]
    )

    authority = authority_for(doc.doc_type, doc.court_level)
    model = get_settings().embedding_model
    session.add(
        Document(
            id=doc.doc_id,
            doc_type=doc.doc_type,
            title_ar=doc.title_ar,
            number=doc.number,
            year=doc.year,
            issuing_authority=doc.issuing_authority,
            issue_date=doc.issue_date,
            effective_date=doc.effective_date,
            status=doc.status,
            repealed_by=doc.repealed_by,
            gazette_ref=doc.gazette_ref,
            legal_domain=doc.legal_domain,
            language=doc.language,
            jurisdiction=doc.jurisdiction,
            authority_level=authority,
            source_uri=doc.source_uri,
            collection_id=collection_id,
        )
    )
    await session.flush()
    default_from = doc.effective_date or doc.issue_date
    for unit in doc.units:
        session.add(
            Unit(
                id=unit.unit_id,
                document_id=doc.doc_id,
                unit_type=unit.unit_type,
                path=unit.path or None,
                article_number=unit.article_number,
                article_label=unit.article_label,
                text=unit.text,
                valid_from=unit.valid_from or default_from,
                valid_to=unit.valid_to,
                amended_by=unit.amended_by,
            )
        )
    await session.flush()
    for (unit, c), vec in zip(kept, vectors, strict=True):
        session.add(
            Chunk(
                id=uuid.uuid4(),
                unit_id=unit.unit_id,
                document_id=doc.doc_id,
                collection_id=collection_id,
                chunk_kind=c.chunk_kind,
                context_header=c.context_header,
                text=c.text,
                text_norm=c.text_norm,
                token_count=c.token_count,
                embedding=vec,
                embedding_model=model,
                doc_type=doc.doc_type,
                authority_level=authority,
                status=_status(doc, unit),
                valid_from=unit.valid_from or default_from,
                valid_to=unit.valid_to,
                legal_domain=doc.legal_domain,
                content_hash=c.content_hash,
            )
        )
    await session.flush()
    return len(doc.units), len(kept)


async def index_documents(
    session: AsyncSession,
    docs: list[DocumentIn],
    collection_id: int,
    count_tokens: CountTokens = embedder.count_tokens,
    embed: Embed = embedder.embed_texts,
) -> dict:
    stats: dict = {"documents": 0, "units": 0, "chunks": 0, "dropped": [], "errors": []}
    for doc in docs:
        try:
            units, chunks = await _index_one(session, doc, collection_id, count_tokens, embed, stats["dropped"])
            await session.commit()
        except Exception as e:
            await session.rollback()
            stats["errors"].append({"doc_id": doc.doc_id, "error": str(e)[:500]})
            continue
        stats["documents"] += 1
        stats["units"] += units
        stats["chunks"] += chunks
    return stats
