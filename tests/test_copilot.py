"""
Tests for Phase 5 — AI Safety Copilot.

We mock the Anthropic SDK so no real API calls are made.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.copilot.context import build_site_context
from src.copilot.prompts import (
    SUGGESTED_QUESTIONS_TAG,
    build_system_prompt,
)
from src.copilot.router import _parse_response


# ── _parse_response ───────────────────────────────────────────────────────────

class TestParseResponse:
    def test_well_formed(self):
        questions = ["q1", "q2", "q3"]
        text = f'Here is my answer.\n{SUGGESTED_QUESTIONS_TAG}{json.dumps(questions)}'
        answer, qs = _parse_response(text)
        assert answer == "Here is my answer."
        assert qs == questions

    def test_missing_tag_returns_empty_list(self):
        text = "An answer with no suggested questions."
        answer, qs = _parse_response(text)
        assert answer == text
        assert qs == []

    def test_malformed_json_returns_empty_list(self):
        text = f"Answer.\n{SUGGESTED_QUESTIONS_TAG}not-valid-json"
        answer, qs = _parse_response(text)
        assert answer == "Answer."
        assert qs == []

    def test_caps_at_three_questions(self):
        many = ["q1", "q2", "q3", "q4", "q5"]
        text = f"Answer.\n{SUGGESTED_QUESTIONS_TAG}{json.dumps(many)}"
        _, qs = _parse_response(text)
        assert len(qs) == 3

    def test_whitespace_in_answer_is_stripped(self):
        text = f"  My answer.  \n{SUGGESTED_QUESTIONS_TAG}[]"
        answer, _ = _parse_response(text)
        assert answer == "My answer."


# ── build_system_prompt ───────────────────────────────────────────────────────

class TestBuildSystemPrompt:
    def test_includes_role_instructions(self):
        prompt = build_system_prompt("safety_officer", "CONTEXT")
        assert "OSHA" in prompt
        assert "Safety Officer" in prompt

    def test_includes_site_context(self):
        prompt = build_system_prompt("executive", "CONTEXT_BLOCK_XYZ")
        assert "CONTEXT_BLOCK_XYZ" in prompt

    def test_unknown_role_uses_default(self):
        prompt = build_system_prompt("unknown_role", "CTX")
        assert len(prompt) > 50  # falls back gracefully

    def test_includes_suggested_questions_tag_instruction(self):
        prompt = build_system_prompt("site_manager", "CTX")
        assert SUGGESTED_QUESTIONS_TAG in prompt

    def test_all_known_roles(self):
        for role in ("safety_officer", "site_manager", "executive", "auditor"):
            prompt = build_system_prompt(role, "CTX")
            assert len(prompt) > 100


# ── build_site_context ────────────────────────────────────────────────────────

class TestBuildSiteContext:
    def _make_store(self, events=None):
        store = MagicMock()
        store.get_events.return_value = events or []
        return store

    def _make_risk_engine(self):
        engine = MagicMock()

        summary = MagicMock()
        summary.overall_risk_level    = "HIGH"
        summary.overall_risk_score    = 67.5
        summary.total_violations_24h  = 12
        summary.total_violations_7d   = 45
        summary.highest_risk_zone     = "forklift_lane"
        summary.rising_risk_zones     = ["forklift_lane"]
        summary.repeat_offender_count = 2
        engine.site_summary.return_value = summary

        zone = MagicMock()
        zone.zone_id          = "forklift_lane"
        zone.risk_score       = 75.0
        zone.risk_level       = "CRITICAL"
        zone.trend            = "RISING"
        zone.trend_pct        = 35.0
        zone.violations_24h   = 12
        zone.violations_7d    = 45
        engine.zone_risks.return_value = [zone]

        offender = MagicMock()
        offender.track_id          = 42
        offender.violations_24h    = 5
        offender.violation_count   = 18
        offender.most_common_type  = "zone_intrusion"
        offender.most_common_zone  = "forklift_lane"
        engine.repeat_offenders.return_value = [offender]

        return engine

    def test_no_events(self, tmp_path):
        ctx = build_site_context(self._make_store(), self._make_risk_engine(), tmp_path / "zones.json")
        assert "no events recorded yet" in ctx

    def test_includes_event_fields(self, tmp_path):
        events = [
            {
                "event_id":    "abc123",
                "event_type":  "missing_ppe",
                "track_id":    7,
                "zone_id":     "weld_area",
                "missing_ppe": ["hardhat"],
                "osha_codes":  ["29 CFR 1926.100(a)"],
                "fine_min_usd": 1000,
                "fine_max_usd": 15000,
                "confidence":  0.91,
                "severity":    "WARNING",
                "end_frame":   None,
                "created_at":  "2024-01-15T09:30:00",
            }
        ]
        ctx = build_site_context(self._make_store(events), self._make_risk_engine(), tmp_path / "zones.json")
        assert "Worker #7" in ctx
        assert "weld_area" in ctx
        assert "hardhat" in ctx
        assert "91%" in ctx

    def test_includes_risk_summary(self, tmp_path):
        ctx = build_site_context(self._make_store(), self._make_risk_engine(), tmp_path / "zones.json")
        assert "HIGH" in ctx
        assert "67.5" in ctx
        assert "forklift_lane" in ctx

    def test_includes_repeat_offender(self, tmp_path):
        ctx = build_site_context(self._make_store(), self._make_risk_engine(), tmp_path / "zones.json")
        assert "Worker #42" in ctx
        assert "5 violations today" in ctx

    def test_reads_zones_json(self, tmp_path):
        zones_file = tmp_path / "zones.json"
        zones_file.write_text(json.dumps({
            "required_ppe": ["hardhat", "vest"],
            "zones": [
                {"id": "lane", "name": "Forklift Lane", "rule": "no_entry", "polygon": []},
            ],
        }))
        ctx = build_site_context(self._make_store(), self._make_risk_engine(), zones_file)
        assert "Forklift Lane" in ctx
        assert "no_entry" in ctx
        assert "hardhat" in ctx

    def test_graceful_when_zones_missing(self, tmp_path):
        ctx = build_site_context(self._make_store(), self._make_risk_engine(), tmp_path / "missing.json")
        assert "zones.json not found" in ctx


# ── /copilot/ask endpoint ─────────────────────────────────────────────────────

@pytest.fixture
def client_with_copilot(tmp_path):
    """Return a TestClient with the full app, real auth, mocked Anthropic."""
    from src.api.main import app
    return TestClient(app, raise_server_exceptions=True)


def _get_auth_token(client):
    """Register + login and return bearer token."""
    client.post("/auth/register", json={
        "org_name": "Test Org", "email": "cop@test.com", "password": "secret123"
    })
    res = client.post("/auth/login", json={"email": "cop@test.com", "password": "secret123"})
    return res.json()["access_token"]


class TestCopilotEndpoint:
    def _mock_anthropic_response(self, text: str):
        """Build a mock Anthropic Messages response."""
        content_block = MagicMock()
        content_block.text = text

        usage = MagicMock()
        usage.input_tokens  = 100
        usage.output_tokens = 50
        usage.cache_read_input_tokens = 80

        msg = MagicMock()
        msg.content = [content_block]
        msg.usage   = usage
        return msg

    def test_missing_api_key_returns_503(self, client_with_copilot):
        token = _get_auth_token(client_with_copilot)
        with patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("ANTHROPIC_API_KEY", None)
            res = client_with_copilot.post(
                "/copilot/ask",
                json={"message": "Hello", "history": [], "role": "safety_officer"},
                headers={"Authorization": f"Bearer {token}"},
            )
        assert res.status_code == 503
        assert "ANTHROPIC_API_KEY" in res.json()["detail"]

    def test_successful_response(self, client_with_copilot):
        token    = _get_auth_token(client_with_copilot)
        q_list   = ["Follow-up 1", "Follow-up 2", "Follow-up 3"]
        answer   = "The site has no critical violations right now."
        raw_text = f"{answer}\n{SUGGESTED_QUESTIONS_TAG}{json.dumps(q_list)}"

        mock_msg = self._mock_anthropic_response(raw_text)

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
            with patch("src.copilot.router.anthropic.Anthropic") as MockClient:
                MockClient.return_value.messages.create.return_value = mock_msg
                res = client_with_copilot.post(
                    "/copilot/ask",
                    json={
                        "message": "What is the current site risk level?",
                        "history": [],
                        "role":    "executive",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )

        assert res.status_code == 200
        body = res.json()
        assert body["answer"] == answer
        assert body["suggested_questions"] == q_list

    def test_unauthenticated_returns_401(self, client_with_copilot):
        res = client_with_copilot.post(
            "/copilot/ask",
            json={"message": "Hello", "history": [], "role": "safety_officer"},
        )
        assert res.status_code == 401

    def test_history_is_forwarded_to_claude(self, client_with_copilot):
        token  = _get_auth_token(client_with_copilot)
        q_list = ["q1", "q2", "q3"]
        raw_text = f"Answer.\n{SUGGESTED_QUESTIONS_TAG}{json.dumps(q_list)}"
        mock_msg = self._mock_anthropic_response(raw_text)

        history = [
            {"role": "user",      "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ]

        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-123"}):
            with patch("src.copilot.router.anthropic.Anthropic") as MockClient:
                mock_create = MockClient.return_value.messages.create
                mock_create.return_value = mock_msg
                client_with_copilot.post(
                    "/copilot/ask",
                    json={
                        "message": "Follow-up question",
                        "history": history,
                        "role":    "safety_officer",
                    },
                    headers={"Authorization": f"Bearer {token}"},
                )
                call_kwargs = mock_create.call_args.kwargs
                # History + new message = 3 messages total
                assert len(call_kwargs["messages"]) == 3
                assert call_kwargs["messages"][0]["content"] == "Earlier question"
                assert call_kwargs["messages"][2]["content"] == "Follow-up question"
