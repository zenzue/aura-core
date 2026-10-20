"""ProviderService: failover semantics, cloud guard, admin switch,
credential redaction. No network."""
from __future__ import annotations

import httpx
import pytest

from app.app import create_app
from app.config import Settings
from app.providers.service import ProviderService
from app.providers.llm_base import ProviderCapabilities


class FakeProvider:
    def __init__(self, name: str, model: str = "m", fail: bool = False) -> None:
        self.name = name
        self.model = model
        self.fail = fail
        self.calls = 0

    async def generate_reply(self, messages, tools=None, system_prompt=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError(f"{self.name} down")
        return {"spoken_text": f"from {self.name}", "emotion": "neutral",
                "expression_intensity": 1.0, "animation_hint": "none",
                "action": "none"}

    async def health(self, timeout_s: float = 5.0) -> bool:
        return not self.fail

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(provider=self.name)

    async def list_models(self, timeout_s: float = 10.0) -> list[str]:
        return [self.model]


def _bare_service(**kw) -> ProviderService:
    base = dict(ai_provider="ollama", ollama_model="m",
                llamacpp_base_url="http://h:8080/v1")
    base.update(kw)
    svc = ProviderService.__new__(ProviderService)
    svc.settings = Settings(**base)
    svc.active = None
    svc.failover = []
    return svc


def test_cloud_failover_excluded_by_default() -> None:
    svc = ProviderService(Settings(
        ai_provider="ollama", ollama_model="m",
        llamacpp_base_url="http://h:8080/v1",
        llm_failover_chain="llamacpp,gemini", allow_cloud_failover=False))
    names = [p.name for p in svc.failover]
    assert "gemini" not in names
    assert "llamacpp" in names


def test_cloud_failover_requires_allow_and_key() -> None:
    svc = ProviderService(Settings(
        ai_provider="ollama", ollama_model="m",
        llamacpp_base_url="http://h:8080/v1",
        llm_failover_chain="gemini", allow_cloud_failover=True))
    assert [p.name for p in svc.failover] == []  # no GEMINI_API_KEY -> excluded

    svc2 = ProviderService(Settings(
        ai_provider="ollama", ollama_model="m", gemini_api_key="gk",
        llm_failover_chain="gemini", allow_cloud_failover=True))
    assert "gemini" in [p.name for p in svc2.failover]


@pytest.mark.asyncio
async def test_failover_to_second_local_provider() -> None:
    svc = _bare_service()
    first = FakeProvider("ollama", fail=True)
    svc.active = first
    svc.failover = [FakeProvider("llamacpp")]
    reply = await svc.ask([{"role": "user", "content": "hi"}])
    assert reply["spoken_text"] == "from llamacpp"
    assert first.calls == 1


@pytest.mark.asyncio
async def test_all_providers_fail_raises() -> None:
    svc = _bare_service()
    svc.active = FakeProvider("ollama", fail=True)
    svc.failover = [FakeProvider("llamacpp", fail=True)]
    with pytest.raises(RuntimeError):
        await svc.ask([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_no_providers_raises() -> None:
    svc = _bare_service()
    with pytest.raises(RuntimeError):
        await svc.ask([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_service_health_dict_and_status() -> None:
    svc = _bare_service()
    svc.active = FakeProvider("ollama")
    info = await svc.check_health()
    assert info["healthy"] is True and info["provider"] == "ollama"
    assert "capabilities" in info
    assert svc.status()["provider"] == "ollama"
    assert await svc.health() is True


def test_secrets_never_in_str_or_repr() -> None:
    settings = Settings(gemini_api_key="sk-SUPERSECRET", admin_token="adminpw123")
    text = str(settings) + repr(settings)
    assert "sk-SUPERSECRET" not in text
    assert "adminpw123" not in text
    assert settings.gemini_api_key.get_secret_value() == "sk-SUPERSECRET"


def test_admin_api_disabled_without_token() -> None:
    assert Settings().admin_api_enabled is False
    assert Settings(admin_token="x").admin_api_enabled is True


@pytest.fixture
async def admin_client():
    settings = Settings(ai_provider="ollama", ollama_model="m",
                        llamacpp_base_url="http://h:8080/v1",
                        admin_token="adminpw", rate_limit_per_min=1000)
    app = create_app(settings)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        client.app = app
        yield client


@pytest.mark.asyncio
async def test_admin_switch_requires_token(admin_client) -> None:
    client = admin_client
    r = await client.post("/v1/admin/provider", json={"provider": "ollama"})
    assert r.status_code == 403

    r = await client.post("/v1/admin/provider", json={"provider": "ollama"},
                          headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 403

    headers = {"Authorization": "Bearer adminpw"}
    r = await client.post("/v1/admin/provider", json={"provider": "bogus"},
                          headers=headers)
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_admin_switch_works_when_configured(admin_client) -> None:
    client = admin_client
    headers = {"Authorization": "Bearer adminpw"}
    r = await client.post("/v1/admin/provider", json={"provider": "llamacpp"},
                          headers=headers)
    assert r.status_code == 200
    assert r.json()["provider"] == "llamacpp"
    assert client.app.state.llm_service.name == "llamacpp"

    r = await client.get("/v1/admin/provider", headers=headers)
    assert r.status_code == 200
    assert r.json()["provider"] == "llamacpp"


@pytest.mark.asyncio
async def test_admin_disabled_returns_403_even_with_token() -> None:
    app = create_app(Settings(ai_provider="ollama", ollama_model="m"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/v1/admin/provider",
                             headers={"Authorization": "Bearer whatever"})
        assert r.status_code == 403


def test_provider_switch_unit() -> None:
    svc = _bare_service()
    result = svc.switch("ollama")
    assert result["ok"] is True and result["provider"] == "ollama"
    assert svc.active is not None and svc.active.name == "ollama"
