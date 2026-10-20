"""Conversation memory: SQLite persistence with in-memory cache facade.

Messages are the source of truth in SQLite (gateway_data_dir/memory.sqlite3).
A per-conversation list cache is loaded lazily and kept in sync on every
write. If the database cannot be opened, the store degrades to pure
in-memory operation and logs the reason; it never claims persistence it
does not have.
"""

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.schemas import LLMProvider

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    rowid    INTEGER PRIMARY KEY AUTOINCREMENT,
    conv_id  TEXT NOT NULL,
    payload  TEXT NOT NULL,
    summary  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conv_id, rowid);
"""


def _payload_id(payload: str) -> str | None:
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    value = obj.get("id")
    return value if isinstance(value, str) else None


class MemoryStore:
    """Conversation store backed by SQLite, with summarization support."""

    def __init__(self, settings: Settings, llm: LLMProvider | None = None):
        self.settings = settings
        self.llm = llm
        self._store: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self._db: sqlite3.Connection | None = None

        db_path = Path(settings.gateway_data_dir) / "memory.sqlite3"
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(str(db_path), check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(_SCHEMA)
            self._db.commit()
            logger.info("memory store using %s", db_path)
        except sqlite3.Error as exc:
            logger.warning("memory persistence unavailable (%s); in-memory only", exc)
            self._db = None

    # ---------- persistence helpers ----------

    def _load(self, conversation_id: str) -> List[Dict[str, Any]]:
        if conversation_id in self._store:
            return self._store[conversation_id]
        msgs: List[Dict[str, Any]] = []
        if self._db is not None:
            with self._lock:
                cur = self._db.execute(
                    "SELECT payload FROM messages WHERE conv_id=? ORDER BY rowid",
                    (conversation_id,),
                )
                for (payload,) in cur.fetchall():
                    try:
                        msgs.append(json.loads(payload))
                    except json.JSONDecodeError:
                        logger.warning("memory: skipping unreadable row")
        self._store[conversation_id] = msgs
        return msgs

    def _persist_insert(self, conversation_id: str, message: Dict[str, Any]) -> None:
        if self._db is None:
            return
        try:
            payload = json.dumps(message, ensure_ascii=False)
        except (TypeError, ValueError):
            logger.warning("memory: message not serializable; cached only")
            return
        with self._lock:
            self._db.execute(
                "INSERT INTO messages(conv_id, payload, summary) VALUES (?,?,?)",
                (conversation_id, payload, 1 if message.get("summary") else 0),
            )
            self._db.commit()

    def _persist_delete_payload(self, conversation_id: str, message_id: str) -> None:
        if self._db is None:
            return
        with self._lock:
            cur = self._db.execute(
                "SELECT rowid, payload FROM messages WHERE conv_id=?", (conversation_id,)
            )
            doomed = [
                rowid
                for (rowid, payload) in cur.fetchall()
                if _payload_id(payload) == message_id
            ]
            if doomed:
                marks = ",".join("?" for _ in doomed)
                self._db.execute(f"DELETE FROM messages WHERE rowid IN ({marks})", doomed)
                self._db.commit()

    def _persist_delete_all(self, conversation_id: str) -> None:
        if self._db is None:
            return
        with self._lock:
            self._db.execute("DELETE FROM messages WHERE conv_id=?", (conversation_id,))
            self._db.commit()

    # ---------- facade API ----------

    def remember(self, conversation_id: str, message: Dict[str, Any]) -> None:
        msgs = self._load(conversation_id)
        msgs.append(message)
        self._persist_insert(conversation_id, message)

    def forget(self, conversation_id: str, message_id: str | None = None) -> int:
        if conversation_id not in self._store and self._db is None:
            return 0
        if message_id is None:
            count = len(self._load(conversation_id))
            self._store.pop(conversation_id, None)
            self._persist_delete_all(conversation_id)
            return count

        msgs = self._load(conversation_id)
        removed = [m for m in msgs if m.get("id") == message_id]
        if not removed:
            return 0
        self._store[conversation_id] = [m for m in msgs if m.get("id") != message_id]
        self._persist_delete_payload(conversation_id, message_id)
        return len(removed)

    def get_messages(self, conversation_id: str, since: int | None = None) -> List[Dict[str, Any]]:
        msgs = self._load(conversation_id)
        if since is None:
            return list(msgs)
        return [m for m in msgs if m.get("index", 0) > since]

    async def recent_messages(self, conversation_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        msgs = self._load(conversation_id)
        return list(msgs[-limit:]) if limit > 0 else list(msgs)

    async def append_message(self, conversation_id: str, message: Dict[str, Any]) -> None:
        self.remember(conversation_id, dict(message))

    def count_messages(self, conversation_id: str) -> int:
        return len(self._load(conversation_id))

    def close(self) -> None:
        if self._db is not None:
            with self._lock:
                self._db.close()
                self._db = None

    # ---------- summarization ----------

    async def maybe_summarize(
        self, llm: LLMProvider, conversation_id: str
    ) -> Optional[str]:
        """
        Summarize conversation when message count >= settings.summarise_every.
        Returns: summary text or None if not needed/error.
        """
        msgs = self._load(conversation_id)
        if len(msgs) < self.settings.summarise_every:
            return None

        history = [m for m in msgs if m.get("role") != "system"]
        if not history:
            return None

        try:
            resp = await llm.generate_reply(
                messages=history,
                tools=None,
                system_prompt=(
                    "Summarize the conversation in at most 2 sentences. "
                    'Reply as JSON: {"spoken_text": "<summary>", "emotion": "neutral", '
                    '"expression_intensity": 0.5, "animation_hint": "none", "action": "none"}'
                ),
            )

            summary = (
                resp.get("spoken_text")
                or resp.get("display_text")
                or resp.get("text")
                or ""
            )
            summary = str(summary).strip()
            if not summary:
                return None

            self.remember(
                conversation_id,
                {
                    "id": f"summary_{len(msgs)}",
                    "role": "system",
                    "content": summary,
                    "summary": True,
                },
            )

            return summary

        except Exception:  # noqa: BLE001
            return None
