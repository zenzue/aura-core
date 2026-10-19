"""Memory store with conversation summarization."""

import asyncio
import json
from typing import Any, Dict, List, Optional

from app.config import Settings
from app.schemas import LLMProvider


class MemoryStore:
    """In-memory + SQLite conversation store with summarization."""

    def __init__(self, settings: Settings, llm: LLMProvider | None = None):
        self.settings = settings
        self.llm = llm
        self._store: Dict[str, List[Dict[str, Any]]] = {}  # conversation_id -> messages

    def remember(self, conversation_id: str, message: Dict[str, Any]) -> None:
        """Store a message."""
        if conversation_id not in self._store:
            self._store[conversation_id] = []
        self._store[conversation_id].append(message)

    def forget(self, conversation_id: str, message_id: str | None = None) -> int:
        """
        Forget messages.
        If message_id: forget that specific message.
        Else: forget all messages for conversation.
        Returns: number of messages forgotten.
        """
        if conversation_id not in self._store:
            return 0

        if message_id is None:
            count = len(self._store[conversation_id])
            del self._store[conversation_id]
            return count

        # Find and remove specific message by id
        msgs = self._store[conversation_id]
        original_count = len(msgs)
        self._store[conversation_id] = [m for m in msgs if m.get("id") != message_id]
        return original_count - len(self._store[conversation_id])

    def get_messages(self, conversation_id: str, since: int | None = None) -> List[Dict[str, Any]]:
        """Get messages optionally since message index."""
        msgs = self._store.get(conversation_id, [])
        if since is None:
            return msgs
        return [m for m in msgs if m.get("index", 0) > since]

    async def recent_messages(self, conversation_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        """Async facade: last N messages for a conversation."""
        msgs = self._store.get(conversation_id, [])
        return list(msgs[-limit:]) if limit > 0 else list(msgs)

    async def append_message(self, conversation_id: str, message: Dict[str, Any]) -> None:
        """Async facade for remember()."""
        self.remember(conversation_id, dict(message))

    def count_messages(self, conversation_id: str) -> int:
        """Count messages in conversation."""
        return len(self._store.get(conversation_id, []))

    async def maybe_summarize(
        self, llm: LLMProvider, conversation_id: str
    ) -> Optional[str]:
        """
        Summarize conversation when message count >= settings.summarise_every.
        Returns: summary text or None if not needed/error.
        """
        msgs = self._store.get(conversation_id, [])
        if len(msgs) < self.settings.summarise_every:
            return None

        # Already have summary? Check if last message is summary
        if msgs and msgs[-1].get("role") == "system" and "summary" in msgs[-1]:
            return msgs[-1]["content"]

        try:
            # Build messages for LLM
            history = [
                {
                    "role": m["role"],
                    "content": m["content"],
                }
                for m in msgs
                if m["role"] in ("user", "assistant")  # skip system/tool messages?
            ]

            # Ask LLM to summarize
            resp = await llm.generate_reply(
                system_prompt="Summarize the conversation in <=2 sentences.",
                messages=history,
                tools=None,
                json_schema=None,
                timeout_s=self.settings.llm_timeout_s,
            )

            # Extract text from response
            summary = resp.get("text", "")
            if not summary:
                return None

            # Store summary as system message
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

        except Exception as e:
            # Never fake data
            return None