"""Memory store tests: CRUD, summarization, SQLite persistence."""

import pytest

from app.config import Settings
from app.memory import MemoryStore


@pytest.fixture
def settings(tmp_path):
    return Settings(
        summarise_every=5,
        llm_timeout_s=10.0,
        gateway_data_dir=tmp_path,
    )


@pytest.fixture
def memory_store(settings):
    return MemoryStore(settings)


@pytest.mark.asyncio
async def test_memory_basic(memory_store):
    """Test basic remember/forget."""
    cid = "test_conv"
    msg = {"id": "msg1", "role": "user", "content": "Hello"}

    memory_store.remember(cid, msg)
    msgs = memory_store.get_messages(cid)
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello"

    count = memory_store.forget(cid, "msg1")
    assert count == 1
    msgs = memory_store.get_messages(cid)
    assert len(msgs) == 0


@pytest.mark.asyncio
async def test_memory_forget_all(memory_store):
    """Test forget all messages."""
    cid = "test_conv"
    msgs = [
        {"id": f"msg{i}", "role": "user", "content": f"Hello {i}"}
        for i in range(3)
    ]
    for msg in msgs:
        memory_store.remember(cid, msg)

    count = memory_store.forget(cid)
    assert count == 3
    assert cid not in memory_store._store


@pytest.mark.asyncio
async def test_memory_count(memory_store):
    """Test message count."""
    cid = "test_conv"
    assert memory_store.count_messages(cid) == 0

    memory_store.remember(cid, {"id": "msg1", "role": "user", "content": "Hello"})
    assert memory_store.count_messages(cid) == 1

    memory_store.remember(cid, {"id": "msg2", "role": "assistant", "content": "Hi"})
    assert memory_store.count_messages(cid) == 2


@pytest.mark.asyncio
async def test_memory_since(memory_store):
    """Test get messages since index."""
    cid = "test_conv"
    msgs = [
        {"id": f"msg{i}", "role": "role", "content": f"msg{i}", "index": i}
        for i in range(5)
    ]
    for msg in msgs:
        memory_store.remember(cid, msg)

    # Get since index 2 (should get 3,4)
    subset = memory_store.get_messages(cid, since=2)
    assert len(subset) == 2
    assert subset[0]["index"] == 3
    assert subset[1]["index"] == 4


@pytest.mark.asyncio
async def test_summarize_threshold(memory_store, settings):
    """Test summarization when threshold reached."""
    cid = "test_conv"
    settings.summarise_every = 3

    # Add 3 messages (should trigger summarize)
    msgs = [
        {"id": f"msg{i}", "role": "user", "content": f"Hello {i}"}
        for i in range(3)
    ]
    for msg in msgs:
        memory_store.remember(cid, msg)

    # Mock LLM that returns summary
    from app.schemas import LLMProvider

    class MockLLM(LLMProvider):
        name = "mock"

        async def generate_reply(self, messages, tools=None, system_prompt=None):
            return {"text": "Conversation summary: user said hello 3 times"}

        async def health(self, timeout_s=5.0):
            return True

    llm = MockLLM()

    summary = await memory_store.maybe_summarize(llm, cid)
    assert summary == "Conversation summary: user said hello 3 times"

    # Check message store: should have 4 messages (3 original + 1 summary)
    msgs = memory_store.get_messages(cid)
    assert len(msgs) == 4
    assert msgs[-1]["role"] == "system"
    assert msgs[-1]["summary"] is True
    assert msgs[-1]["content"] == summary


@pytest.mark.asyncio
async def test_summarize_not_needed(memory_store):
    """Test no summarization when below threshold."""
    cid = "test_conv"
    settings.summarise_every = 5

    # Add 2 messages
    msgs = [
        {"id": f"msg{i}", "role": "user", "content": f"Hello {i}"}
        for i in range(2)
    ]
    for msg in msgs:
        memory_store.remember(cid, msg)

    llm = None  # not needed
    summary = await memory_store.maybe_summarize(llm, cid)
    assert summary is None


@pytest.mark.asyncio
async def test_summarize_error(memory_store, settings):
    """Test summarization error handling."""
    cid = "test_conv"
    settings.summarise_every = 3

    # Add 3 messages
    msgs = [
        {"id": f"msg{i}", "role": "user", "content": f"Hello {i}"}
        for i in range(3)
    ]
    for msg in msgs:
        memory_store.remember(cid, msg)

    # Mock LLM that raises error
    from app.schemas import LLMProvider

    class ErrorLLM(LLMProvider):
        name = "error"

        async def generate_reply(self, messages, tools=None, system_prompt=None):
            raise RuntimeError("LLM error")

        async def health(self, timeout_s=5.0):
            return False

    llm = ErrorLLM()

    summary = await memory_store.maybe_summarize(llm, cid)
    assert summary is None  # never fake data

    # Messages unchanged
    msgs = memory_store.get_messages(cid)
    assert len(msgs) == 3

@pytest.mark.asyncio
async def test_memory_persistence_across_instances(tmp_path):
    store1 = MemoryStore(Settings(gateway_data_dir=tmp_path, summarise_every=100))
    store1.remember("c1", {"id": "a", "role": "user", "content": "persist me"})
    store1.remember("c1", {"id": "b", "role": "assistant", "content": "and me"})
    store1.close()

    store2 = MemoryStore(Settings(gateway_data_dir=tmp_path, summarise_every=100))
    msgs = store2.get_messages("c1")
    assert [m["content"] for m in msgs] == ["persist me", "and me"]

    store2.forget("c1", "a")
    store2.close()

    store3 = MemoryStore(Settings(gateway_data_dir=tmp_path, summarise_every=100))
    assert store3.count_messages("c1") == 1
    assert store3.get_messages("c1")[0]["id"] == "b"
    store3.close()


@pytest.mark.asyncio
async def test_memory_forget_all_persisted(tmp_path):
    store1 = MemoryStore(Settings(gateway_data_dir=tmp_path, summarise_every=100))
    store1.remember("c1", {"id": "x", "role": "user", "content": "1"})
    assert store1.forget("c1") == 1
    store1.close()

    store2 = MemoryStore(Settings(gateway_data_dir=tmp_path, summarise_every=100))
    assert store2.count_messages("c1") == 0
    store2.close()


@pytest.mark.asyncio
async def test_memory_summary_persisted(tmp_path):
    settings = Settings(gateway_data_dir=tmp_path, summarise_every=2)
    store1 = MemoryStore(settings)
    store1.remember("c1", {"id": "1", "role": "user", "content": "a"})
    store1.remember("c1", {"id": "2", "role": "user", "content": "b"})

    class SummLLM:
        async def generate_reply(self, messages, tools=None, system_prompt=None):
            return {"spoken_text": "Two user messages."}

        async def health(self, timeout_s=5.0):
            return True

    assert await store1.maybe_summarize(SummLLM(), "c1") == "Two user messages."
    store1.close()

    store2 = MemoryStore(settings)
    msgs = store2.get_messages("c1")
    assert len(msgs) == 3
    assert msgs[-1]["summary"] is True
    store2.close()
