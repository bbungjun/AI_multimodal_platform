from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app import prompt_credit
from app.auth.service import AuthenticatedUser
from app.credit_accounting import CreditAccountingError, ReservationReceipt
from app.models import GenerationMode
from app.prompt_enhancement import CreativityPreset
from app.schemas import PromptEnhanceRequest
from app.services.llm import enhancer
from app.services.vertex.errors import VertexRateLimitedError


def test_prompt_credit_module_interface_exists():
    assert callable(prompt_credit.execute_prompt_enhancement)


def test_prompt_credit_keys_are_bounded_and_derived_only_from_request_uuid():
    request_id = UUID("11111111-2222-3333-4444-555555555555")
    assert prompt_credit._keys(request_id) == (
        "pe_r_11111111222233334444555555555555",
        "pe_t_11111111222233334444555555555555",
    )


def test_prompt_credit_maps_only_bounded_accounting_errors():
    assert prompt_credit._mapped_accounting_error(
        CreditAccountingError("credit_plan_refused")
    ).code == "plan_feature_not_allowed"
    assert prompt_credit._mapped_accounting_error(
        CreditAccountingError("monthly_credit_exhausted")
    ).code == "monthly_credit_exhausted"
    assert prompt_credit._mapped_accounting_error(
        CreditAccountingError("credit_account_inconsistent")
    ).code == "credit_account_unavailable"


class _Session:
    def __init__(self, scalar_values):
        self.scalar_values = iter(scalar_values)
        self.transaction_open = False
        self.added = []

    @asynccontextmanager
    async def begin(self):
        assert not self.transaction_open
        self.transaction_open = True
        try:
            yield
        finally:
            self.transaction_open = False

    async def scalar(self, _statement):
        return next(self.scalar_values)

    def add(self, value):
        self.added.append(value)

    async def flush(self):
        return None


ACTOR = AuthenticatedUser(
    id=UUID(int=71),
    role="user",
    status="active",
    email="fixture@invalid.test",
)
PAYLOAD = PromptEnhanceRequest(
    request_id=UUID(int=72),
    prompt="desk lamp",
    target_mode=GenerationMode.T2I,
    target_model="imagen-4.0-fast-generate-001",
    creativity_preset=CreativityPreset.BALANCED,
)


async def test_prompt_credit_admits_before_provider_and_settles_afterward(monkeypatch):
    session = _Session([None, "held"])
    receipt = ReservationReceipt(
        reservation_id=UUID(int=73),
        operation_key="pe_r_" + PAYLOAD.request_id.hex,
        status="held",
        reserved_microcredits=99,
        rate_card_version="v1",
        replayed=False,
    )
    events = []

    async def fake_reserve(session_arg, **_kwargs):
        assert session_arg.transaction_open
        events.append("reserve")
        return receipt

    async def fake_enhance(*_args, **_kwargs):
        assert not session.transaction_open
        events.append("provider")
        return enhancer.PromptEnhancementResult(
            original=PAYLOAD.prompt,
            enhanced="A desk lamp with soft side light.",
            components={"subject": "desk lamp"},
            target_mode=PAYLOAD.target_mode,
            target_model=PAYLOAD.target_model,
            llm_model="gemini-mock",
            latency_ms=0,
            tokens_in=10,
            tokens_out=20,
            usage_source="mock_estimate",
        )

    async def fake_settle(session_arg, **kwargs):
        assert session_arg.transaction_open
        assert len(kwargs["usage"].lines) == 2
        events.append("settle")

    monkeypatch.setattr(prompt_credit, "reserve", fake_reserve)
    monkeypatch.setattr(prompt_credit, "settle", fake_settle)
    monkeypatch.setattr(prompt_credit.enhancer, "enhance_prompt", fake_enhance)
    monkeypatch.setattr(
        prompt_credit.enhancer,
        "plan_prompt_enhancement",
        lambda *_args, **_kwargs: SimpleNamespace(
            llm_model="gemini-mock",
            maximum_input_tokens=100,
            maximum_output_tokens=200,
        ),
    )

    outcome = await prompt_credit.execute_prompt_enhancement(
        session,
        actor=ACTOR,
        payload=PAYLOAD,
    )

    assert events == ["reserve", "provider", "settle"]
    assert outcome.enhancement.id == PAYLOAD.request_id
    assert outcome.replayed is False


async def test_prompt_credit_refuses_before_provider(monkeypatch):
    session = _Session([None])
    provider = AsyncMock()

    async def refused(*_args, **_kwargs):
        raise CreditAccountingError("monthly_credit_exhausted")

    monkeypatch.setattr(prompt_credit, "reserve", refused)
    monkeypatch.setattr(prompt_credit.enhancer, "enhance_prompt", provider)
    monkeypatch.setattr(
        prompt_credit.enhancer,
        "plan_prompt_enhancement",
        lambda *_args, **_kwargs: SimpleNamespace(
            llm_model="gemini-mock",
            maximum_input_tokens=100,
            maximum_output_tokens=200,
        ),
    )

    with pytest.raises(prompt_credit.PromptCreditError) as exc_info:
        await prompt_credit.execute_prompt_enhancement(
            session,
            actor=ACTOR,
            payload=PAYLOAD,
        )
    assert exc_info.value.code == "monthly_credit_exhausted"
    provider.assert_not_awaited()


async def test_prompt_credit_releases_provider_failure_in_fresh_transaction(monkeypatch):
    session = _Session([None, "held"])
    receipt = ReservationReceipt(
        reservation_id=UUID(int=73),
        operation_key="pe_r_" + PAYLOAD.request_id.hex,
        status="held",
        reserved_microcredits=99,
        rate_card_version="v1",
        replayed=False,
    )
    released = []

    async def fake_reserve(*_args, **_kwargs):
        return receipt

    async def failed_provider(*_args, **_kwargs):
        assert not session.transaction_open
        raise VertexRateLimitedError(status_code=429)

    async def fake_release(session_arg, **kwargs):
        assert session_arg.transaction_open
        released.append(kwargs)

    monkeypatch.setattr(prompt_credit, "reserve", fake_reserve)
    monkeypatch.setattr(prompt_credit, "release", fake_release)
    monkeypatch.setattr(prompt_credit.enhancer, "enhance_prompt", failed_provider)
    monkeypatch.setattr(
        prompt_credit.enhancer,
        "plan_prompt_enhancement",
        lambda *_args, **_kwargs: SimpleNamespace(
            llm_model="gemini-mock",
            maximum_input_tokens=100,
            maximum_output_tokens=200,
        ),
    )

    with pytest.raises(VertexRateLimitedError):
        await prompt_credit.execute_prompt_enhancement(
            session,
            actor=ACTOR,
            payload=PAYLOAD,
        )

    assert released[0]["reason_code"] == "provider_rate_limited"
    assert released[0]["usage"].lines == ()
    assert session.transaction_open is False
