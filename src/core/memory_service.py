"""Cross-session memory: user preferences (Mem0) + script vector search (Chroma).

Gracefully degrades: Mem0 → JSON file, Chroma → in-memory TF-IDF.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)

_MEMORY_DIR: Path | None = None


def _get_memory_dir() -> Path:
    global _MEMORY_DIR
    if _MEMORY_DIR is None:
        _MEMORY_DIR = Path(settings.storage_path) / "memory"
        _MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    return _MEMORY_DIR


# ---------------------------------------------------------------------------
# MemoryService
# ---------------------------------------------------------------------------

class MemoryService:
    """Cross-session memory for user preferences and script retrieval."""

    _instance: MemoryService | None = None

    def __new__(cls) -> MemoryService:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._initialized = True
        self._mem0: Any = None
        self._chroma: Any = None
        self._collection: Any = None
        self._embedding_fn: Any = None
        self._prefs_cache: dict[str, list[dict]] = {}

    # -- Mem0 (user preferences) ----------------------------------------------

    async def _ensure_mem0(self) -> Any:
        if self._mem0 is not None:
            return self._mem0
        key = settings.mem0_api_key
        if key:
            try:
                from mem0 import Memory
                os.environ.setdefault("MEM0_API_KEY", key)
                self._mem0 = Memory()
                logger.info("Mem0 client initialized")
                return self._mem0
            except Exception as exc:
                logger.warning("Mem0 init failed (%s), using JSON fallback", exc)
        self._mem0 = False  # sentinel: use fallback
        return False

    async def store_user_preference(self, user_id: str, preference: dict) -> None:
        """Legacy local preference writer (Mem0 is reserved for cases).

        New code should use ``PersonalizationService`` and SQL.  This method
        remains for compatibility but rejects generated/model observations and
        never writes structured preferences to Mem0.
        """
        if not user_id:
            raise ValueError("user_id is required")
        preference = dict(preference)
        source = str(preference.get("source", "user_expression"))
        if source in {"inferred", "model", "generated"}:
            logger.info("Ignoring non-user preference observation for %s", user_id)
            return
        prefs = await self.get_user_preferences(user_id)
        key = str(preference.get("key") or preference.get("preference_key") or "").strip().lower()
        value = str(preference.get("value") or preference.get("preference_value") or "").strip().lower()
        if key and not any(
            str(item.get("key") or item.get("preference_key") or "").strip().lower() == key
            and str(item.get("value") or item.get("preference_value") or "").strip().lower() == value
            for item in prefs
        ):
            prefs.append(preference)
        self._prefs_cache[user_id] = prefs
        await self._save_preferences_json(user_id, prefs)

    async def get_user_preferences(self, user_id: str) -> list[dict]:
        """Retrieve compatibility preferences from an isolated local cache.

        Structured SQL rows are authoritative and should be read through the
        personalization service.  Mem0 is intentionally not queried here.
        """
        if not user_id:
            return []
        if user_id in self._prefs_cache:
            return list(self._prefs_cache[user_id])
        loaded = await self._load_preferences_json(user_id)
        self._prefs_cache[user_id] = list(loaded)
        return loaded

    async def _save_preferences_json(self, user_id: str, prefs: list[dict]) -> None:
        path = _get_memory_dir() / f"prefs_{_safe_filename(user_id)}.json"
        await asyncio.to_thread(
            lambda: path.write_text(json.dumps(prefs, ensure_ascii=False, indent=2), encoding="utf-8"),
        )

    async def _load_preferences_json(self, user_id: str) -> list[dict]:
        path = _get_memory_dir() / f"prefs_{_safe_filename(user_id)}.json"
        if path.exists():
            try:
                data = await asyncio.to_thread(lambda: json.loads(path.read_text(encoding="utf-8")))
                return data if isinstance(data, list) else []
            except Exception:
                return []
        return []

    # -- Chroma (script vector storage) ---------------------------------------

    async def _ensure_chroma(self) -> Any | None:
        if self._chroma is not None:
            return self._chroma
        try:
            import chromadb
            persist = settings.chroma_persist_path
            Path(persist).mkdir(parents=True, exist_ok=True)
            # Run in thread to prevent ONNX model download from blocking event loop
            self._chroma = await asyncio.to_thread(
                chromadb.PersistentClient, path=persist,
            )
            self._collection = await asyncio.to_thread(
                self._chroma.get_or_create_collection,
                name="scripts",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("Chroma client initialized at %s", persist)
            return self._chroma
        except Exception as exc:
            logger.warning("Chroma init failed (%s), using in-memory fallback", exc)
            return None

    async def store_script(self, script: str, metadata: dict[str, Any]) -> str:
        """Store a script in vector DB. Returns a document ID."""
        import uuid
        doc_id = str(uuid.uuid4())

        chroma = await self._ensure_chroma()
        if chroma and self._collection is not None:
            try:
                embeddings = await self._embed(script)
                if embeddings:
                    self._collection.add(
                        ids=[doc_id],
                        documents=[script],
                        metadatas=[{k: str(v)[:512] for k, v in metadata.items()}],
                        embeddings=[embeddings],
                    )
                    logger.debug("Chroma: stored script %s", doc_id)
                    return doc_id
            except Exception as exc:
                logger.warning("Chroma store failed (%s), using JSON fallback", exc)

        # JSON fallback
        record = {"id": doc_id, "script": script, "metadata": metadata}
        _get_memory_dir().mkdir(parents=True, exist_ok=True)
        path = _get_memory_dir() / "scripts_fallback.jsonl"
        def _append():
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        await asyncio.to_thread(_append)
        return doc_id

    async def search_similar_scripts(
        self,
        query: str,
        k: int = 3,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Search historical cases, isolated to one tenant/user.

        A user scope is mandatory for useful retrieval.  When ``user_id`` is
        omitted we return an empty result instead of accidentally exposing a
        global corpus.  This is especially important for the JSONL fallback,
        where a vector database cannot enforce metadata filtering for us.
        """
        # ``filter_metadata`` is accepted for backwards compatibility; derive
        # the tenant key from it when callers have not supplied the explicit
        # keyword.  Never run an unscoped query against the shared collection.
        if not user_id and filter_metadata:
            user_id = str(filter_metadata.get("user_id") or "") or None
        if not user_id:
            return []
        metadata_filter = dict(filter_metadata or {})
        metadata_filter.setdefault("user_id", str(user_id))
        chroma = await self._ensure_chroma()
        if chroma and self._collection is not None:
            try:
                embeddings = await self._embed(query)
                where = (
                    {key: str(value) for key, value in metadata_filter.items()}
                    if metadata_filter else None
                )
                results = self._collection.query(
                    query_embeddings=[embeddings] if embeddings else None,
                    query_texts=[query] if not embeddings else None,
                    n_results=k,
                    where=where,
                )
                out = []
                ids_list = results.get("ids", [[]])[0]
                docs_list = results.get("documents", [[]])[0]
                metas_list = results.get("metadatas", [[]])[0]
                for i in range(min(len(ids_list), len(docs_list))):
                    metadata = metas_list[i] if i < len(metas_list) else {}
                    if any(str(metadata.get(key, "")) != str(value) for key, value in metadata_filter.items()):
                        continue
                    out.append({
                        "id": ids_list[i],
                        "script": docs_list[i][:500],
                        "metadata": metadata,
                    })
                return out
            except Exception as exc:
                logger.warning("Chroma search failed (%s), using TF-IDF fallback", exc)

        return await self._search_tfidf(query, k, filter_metadata=metadata_filter)

    async def _search_tfidf(
        self,
        query: str,
        k: int,
        filter_metadata: dict | None = None,
        user_id: str | None = None,
    ) -> list[dict]:
        """TF-IDF fallback search over JSONL, with strict metadata filtering."""
        metadata_filter = dict(filter_metadata or {})
        if user_id:
            metadata_filter.setdefault("user_id", str(user_id))
        # Never search a shared fallback corpus without a tenant key.
        if not metadata_filter.get("user_id"):
            return []
        path = _get_memory_dir() / "scripts_fallback.jsonl"
        if not path.exists():
            return []

        def _do():
            records = []
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
            if metadata_filter:
                def matches(record: dict) -> bool:
                    metadata = record.get("metadata") or {}
                    return all(str(metadata.get(key, "")) == str(value) for key, value in metadata_filter.items())
                records = [record for record in records if matches(record)]
            if not records:
                return []
            try:
                from sklearn.feature_extraction.text import TfidfVectorizer
                from sklearn.metrics.pairwise import cosine_similarity
                docs = [r["script"] for r in records]
                vec = TfidfVectorizer(max_features=1000)
                tfidf = vec.fit_transform([query] + docs)
                sim = cosine_similarity(tfidf[0:1], tfidf[1:]).flatten()
                top = sim.argsort()[::-1][:k]
                return [records[i] for i in top if sim[i] > 0.05]
            except ImportError:
                return records[:k]
        return await asyncio.to_thread(_do)

    # -- Embedding helper -----------------------------------------------------

    async def _embed(self, text: str) -> list[float] | None:
        try:
            from openai import AsyncOpenAI
            key = settings.openai_api_key
            base = settings.openai_base_url or "https://api.openai.com/v1"
            if not key:
                raise RuntimeError("No OpenAI key for embeddings")
            client = AsyncOpenAI(api_key=key, base_url=base)
            resp = await client.embeddings.create(
                model="text-embedding-3-small", input=text[:8000],
            )
            return resp.data[0].embedding
        except Exception as exc:
            logger.debug("OpenAI embedding failed (%s)", exc)
            return None

    # -- Context builder ------------------------------------------------------

    async def build_context_for_new_session(self, user_id: str, current_prompt: str) -> dict:
        """Build a context string to inject into a new discussion.

        Returns a dict with keys: context (str), preferences_count (int), similar_scripts (int).

        Only uses fast JSON preferences — Chroma vector search is deferred to
        post-discussion storage to avoid blocking the SSE stream on model download.
        """
        parts: list[str] = []

        prefs = await self.get_user_preferences(user_id)
        preferences_count = len(prefs)
        if prefs:
            parts.append("## 用户历史偏好")
            for p in prefs[-10:]:
                val = p.get("value") or p.get("key", "")
                if val:
                    parts.append(f"- {str(val)[:200]}")

        # Use TF-IDF fallback search (fast, no ONNX download needed).
        # Chroma is used only for post-discussion storage (off hot path).
        similar = await self._search_tfidf(current_prompt, k=2, user_id=user_id)
        similar_scripts_count = len(similar)
        if similar:
            parts.append("## 历史相关剧本参考")
            for s in similar:
                meta = s.get("metadata", {})
                style = meta.get("style", "")
                parts.append(f"- [{style}] {s.get('script', '')[:300]}")

        context_str = "\n".join(parts) if parts else ""
        return {
            "context": context_str,
            "preferences_count": preferences_count,
            "similar_scripts": similar_scripts_count,
        }

    # -- Feedback -------------------------------------------------------------

    async def record_feedback(self, user_id: str, script_id: str, feedback: dict) -> None:
        """Record feedback as a semantic historical case, not a preference."""
        await self.store_historical_case(
            user_id,
            {
                "case_ref": script_id,
                "feedback": dict(feedback),
                "content": json.dumps(feedback, ensure_ascii=False),
            },
        )
        logger.info("Recorded historical feedback case for user %s on script %s", user_id, script_id)

    async def store_historical_case(self, user_id: str, case: dict[str, Any]) -> str:
        """Store a semantic historical case in Mem0 when configured.

        Mem0 is deliberately used for *cases* (what happened and what the user
        changed), not as the authoritative structured preference store.  The
        JSON/Chroma implementation remains a deterministic fallback.
        """
        if not user_id:
            raise ValueError("user_id is required for historical case storage")
        payload = dict(case)
        payload["user_id"] = str(user_id)
        payload.setdefault("kind", "creative_case")
        mem0 = await self._ensure_mem0()
        if mem0:
            try:
                text = json.dumps(payload, ensure_ascii=False)
                result = await asyncio.to_thread(
                    mem0.add,
                    text,
                    user_id=str(user_id),
                    metadata={"kind": "creative_case", "user_id": str(user_id)},
                )
                # Mem0 versions return either an ID or a list of records.
                if isinstance(result, str):
                    return result
                if isinstance(result, list) and result and isinstance(result[0], dict):
                    return str(result[0].get("id") or result[0].get("memory") or "")
            except Exception as exc:
                logger.debug("Mem0 case store failed (%s), using script store fallback", exc)
        text = payload.get("script") or payload.get("content") or json.dumps(payload, ensure_ascii=False)
        return await self.store_script(str(text), {"user_id": str(user_id), "kind": "creative_case", **payload})

    async def search_historical_cases(self, user_id: str, query: str, k: int = 3) -> list[dict]:
        """Retrieve semantic cases for exactly one user."""
        if not user_id:
            return []
        mem0 = await self._ensure_mem0()
        if mem0:
            try:
                results = await asyncio.to_thread(
                    mem0.search,
                    query or "creative case",
                    user_id=str(user_id),
                    limit=k,
                )
                # Defensive filtering: some Mem0 deployments ignore user_id.
                out = []
                for result in results or []:
                    metadata = result.get("metadata") or {}
                    result_user = metadata.get("user_id") or result.get("user_id")
                    # Mem0 providers differ in whether they honour the
                    # user_id filter.  A result without an attributable
                    # tenant is therefore unsafe to use: accepting it would
                    # turn a provider quirk into a cross-user data leak.
                    if result_user is None or str(result_user) != str(user_id):
                        continue
                    out.append(result)
                if out:
                    return out[:k]
            except Exception as exc:
                logger.debug("Mem0 case search failed (%s), using vector fallback", exc)
        return await self.search_similar_scripts(query, k=k, user_id=str(user_id))


def detect_script_tone(script: str) -> str:
    """Detect the dominant tone/genre from a generated script."""
    script_lower = script.lower()
    tones = {
        "comedy": ["搞笑", "幽默", "喜剧", "笑话", "funny", "comedy", "轻松"],
        "dramatic": ["紧张", "悬疑", "冲突", "矛盾", "dramatic", "tense", "压抑"],
        "romantic": ["爱情", "浪漫", "恋爱", "romantic", "love", "温馨"],
        "action": ["动作", "打斗", "战斗", "action", "fight", "激烈"],
        "horror": ["恐怖", "惊悚", "horror", "scary", "诡异"],
        "fantasy": ["奇幻", "魔法", "fantasy", "magic", "神话"],
        "tragedy": ["悲剧", "牺牲", "死亡", "tragedy", "离别"],
        "slice_of_life": ["日常", "平淡", "生活", "温馨", "治愈"],
    }
    for tone, keywords in tones.items():
        if any(kw in script_lower for kw in keywords):
            return tone
    return "narrative"


def _safe_filename(s: str) -> str:
    """Return a collision-resistant, path-safe user key.

    Sanitizing by removing characters is not sufficient (``a/b`` and ``ab``
    used to share a file).  A SHA-256 digest gives stable isolation even for
    long or Unicode IDs while avoiding user-controlled path components.
    """
    raw = str(s).encode("utf-8", errors="strict")
    return hashlib.sha256(raw).hexdigest()


# Module-level singleton
memory_service = MemoryService()
