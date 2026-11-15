"""Unit tests for backend/reporting/summary.py.

All tests run fully offline — no Anthropic API calls are made.
LLM paths are tested via unittest.mock.patch.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.reporting.summary import (
    _extract_json_block,
    _generate_template_summary,
    format_timestamp_ist,
    generate_summary,
)

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

HERO_TIMELINE = [
    {
        "timestamp": "2024-01-10T17:35:00Z",  # 23:05 IST
        "source": "identity_provider",
        "category": "suspicious_login",
        "title": "Anomalous login from Romania",
        "user": "r.sharma",
        "host": None,
        "src_ip": "79.112.3.44",
        "dst_ip": None,
        "process": None,
        "extra": {"country": "Romania", "country_seen_before": False},
    },
    {
        "timestamp": "2024-01-10T18:10:00Z",  # 23:40 IST
        "source": "dlp",
        "category": "bulk_download",
        "title": "Bulk file download by r.sharma",
        "user": "r.sharma",
        "host": None,
        "src_ip": None,
        "dst_ip": None,
        "process": None,
        "extra": {"files_count": 4812},
    },
    {
        "timestamp": "2024-01-10T19:45:00Z",  # 01:15 IST+1
        "source": "endpoint_av",
        "category": "suspicious_process",
        "title": "rclone.exe detected on FILESRV-02",
        "user": "r.sharma",
        "host": "FILESRV-02",
        "src_ip": None,
        "dst_ip": None,
        "process": "rclone.exe",
        "extra": {},
    },
    {
        "timestamp": "2024-01-10T20:00:00Z",  # 01:30 IST+1
        "source": "firewall",
        "category": "large_outbound",
        "title": "Large outbound transfer",
        "user": "r.sharma",
        "host": "FILESRV-02",
        "src_ip": "192.168.1.50",
        "dst_ip": "104.21.44.102",
        "process": None,
        "extra": {"bytes_out": 2_576_980_378},
    },
]

HERO_FACTS = {
    "pattern": "account_takeover_then_exfiltration",
    "title": "Account takeover followed by data exfiltration",
    "severity": "critical",
    "score": 85,
    "entities": {"users": ["r.sharma"], "hosts": ["FILESRV-02"], "ips": ["79.112.3.44"]},
    "timeline": HERO_TIMELINE,
}

RANSOMWARE_TIMELINE = [
    {
        "timestamp": "2024-01-11T03:00:00Z",  # 08:30 IST
        "source": "endpoint_av",
        "category": "suspicious_process",
        "title": "vssadmin shadow deletion",
        "user": "v.patel",
        "host": "WS-ACCTS-07",
        "src_ip": None,
        "dst_ip": None,
        "process": "vssadmin.exe",
        "extra": {},
    },
    {
        "timestamp": "2024-01-11T03:12:00Z",  # 08:42 IST
        "source": "endpoint_av",
        "category": "ransomware_behaviour",
        "title": "Mass file encryption",
        "user": "v.patel",
        "host": "WS-ACCTS-07",
        "src_ip": None,
        "dst_ip": None,
        "process": None,
        "extra": {"renamed_count": 1250, "extension": ".locked"},
    },
    {
        "timestamp": "2024-01-11T03:20:00Z",  # 08:50 IST
        "source": "cloud_audit",
        "category": "backup_activity",
        "title": "Backup snapshot delete call",
        "user": "v.patel",
        "host": "WS-ACCTS-07",
        "src_ip": None,
        "dst_ip": None,
        "process": None,
        "extra": {"action": "delete"},
    },
]

RANSOMWARE_FACTS = {
    "pattern": "ransomware_behaviour",
    "title": "Ransomware execution and shadow copy tampering",
    "severity": "critical",
    "score": 92,
    "entities": {"users": ["v.patel"], "hosts": ["WS-ACCTS-07"], "ips": []},
    "timeline": RANSOMWARE_TIMELINE,
}

PHISHING_TIMELINE = [
    {
        "timestamp": "2024-01-10T08:40:00Z",  # 14:10 IST
        "source": "email_security",
        "category": "phishing_email",
        "title": "Phishing email delivered",
        "user": "a.menon",
        "host": None,
        "src_ip": None,
        "dst_ip": None,
        "process": None,
        "extra": {},
    },
    {
        "timestamp": "2024-01-10T09:15:00Z",  # 14:45 IST
        "source": "identity_provider",
        "category": "suspicious_login",
        "title": "New device login for a.menon",
        "user": "a.menon",
        "host": None,
        "src_ip": "197.210.64.12",
        "dst_ip": None,
        "process": None,
        "extra": {},
    },
    {
        "timestamp": "2024-01-10T09:45:00Z",  # 15:15 IST
        "source": "cloud_audit",
        "category": "mailbox_rule_change",
        "title": "Mailbox forwarding rule created",
        "user": "a.menon",
        "host": None,
        "src_ip": None,
        "dst_ip": None,
        "process": None,
        "extra": {"forward_to": "attacker@evil.com"},
    },
]

PHISHING_FACTS = {
    "pattern": "phishing_to_compromise",
    "title": "Phishing leading to mailbox forwarding",
    "severity": "high",
    "score": 72,
    "entities": {"users": ["a.menon"], "hosts": [], "ips": ["197.210.64.12"]},
    "timeline": PHISHING_TIMELINE,
}

RECON_TIMELINE = [
    {
        "timestamp": "2024-01-10T04:30:00Z",  # 10:00 IST
        "source": "firewall",
        "category": "port_scan",
        "title": "Port scan from known scanner",
        "user": None,
        "host": None,
        "src_ip": "80.82.77.33",
        "dst_ip": None,
        "process": None,
        "extra": {},
    },
    {
        "timestamp": "2024-01-10T05:00:00Z",  # 10:30 IST
        "source": "identity_provider",
        "category": "failed_login",
        "title": "Failed login attempt",
        "user": "p.iyer",
        "host": None,
        "src_ip": "80.82.77.33",
        "dst_ip": None,
        "process": None,
        "extra": {},
    },
]

RECON_FACTS = {
    "pattern": "recon_then_access",
    "title": "Recon followed by access attempt",
    "severity": "medium",
    "score": 45,
    "entities": {"users": ["p.iyer"], "hosts": [], "ips": ["80.82.77.33"]},
    "timeline": RECON_TIMELINE,
}


# ---------------------------------------------------------------------------
# format_timestamp_ist
# ---------------------------------------------------------------------------

def test_format_timestamp_ist_utc() -> None:
    result = format_timestamp_ist("2024-01-10T17:35:00Z")
    assert result == "23:05 IST"


def test_format_timestamp_ist_none() -> None:
    assert format_timestamp_ist(None) == "unknown time"


def test_format_timestamp_ist_invalid() -> None:
    result = format_timestamp_ist("not-a-date")
    assert "not-a-date" in result


# ---------------------------------------------------------------------------
# _extract_json_block
# ---------------------------------------------------------------------------

def test_extract_json_block_direct() -> None:
    text = '{"summary": "test", "recommended_actions": ["a"]}'
    result = _extract_json_block(text)
    assert result is not None
    assert result["summary"] == "test"


def test_extract_json_block_markdown_fence() -> None:
    text = '```json\n{"summary": "s", "recommended_actions": ["x"]}\n```'
    result = _extract_json_block(text)
    assert result is not None
    assert result["summary"] == "s"


def test_extract_json_block_brace_extraction() -> None:
    text = 'Some text before {"summary": "s2", "recommended_actions": ["y"]} trailing'
    result = _extract_json_block(text)
    assert result is not None
    assert result["summary"] == "s2"


def test_extract_json_block_invalid_returns_none() -> None:
    assert _extract_json_block("not json at all") is None


# ---------------------------------------------------------------------------
# Template: account_takeover_then_exfiltration (Scenario A / Hero)
# ---------------------------------------------------------------------------

def test_template_account_takeover_structure() -> None:
    result = _generate_template_summary(HERO_FACTS)
    assert result["summary_source"] == "template"
    assert isinstance(result["summary"], str)
    assert len(result["recommended_actions"]) == 4


def test_template_account_takeover_suspected_wording() -> None:
    result = _generate_template_summary(HERO_FACTS)
    summary = result["summary"].lower()
    assert "suspected" in summary, "Account takeover template must use 'suspected' for unverified claims"


def test_template_account_takeover_user_and_host() -> None:
    result = _generate_template_summary(HERO_FACTS)
    assert "r.sharma" in result["summary"]
    assert "FILESRV-02" in result["summary"]


def test_template_account_takeover_country() -> None:
    result = _generate_template_summary(HERO_FACTS)
    assert "Romania" in result["summary"]


def test_template_account_takeover_actions_mention_user() -> None:
    result = _generate_template_summary(HERO_FACTS)
    actions_text = " ".join(result["recommended_actions"])
    assert "r.sharma" in actions_text


# ---------------------------------------------------------------------------
# Template: ransomware_behaviour (Scenario C)
# ---------------------------------------------------------------------------

def test_template_ransomware_structure() -> None:
    result = _generate_template_summary(RANSOMWARE_FACTS)
    assert result["summary_source"] == "template"
    assert len(result["recommended_actions"]) == 4


def test_template_ransomware_suspected_wording() -> None:
    result = _generate_template_summary(RANSOMWARE_FACTS)
    assert "suspected" in result["summary"].lower(), "Ransomware template must use 'suspected'"


def test_template_ransomware_host_and_process() -> None:
    result = _generate_template_summary(RANSOMWARE_FACTS)
    assert "WS-ACCTS-07" in result["summary"]
    assert "vssadmin.exe" in result["summary"]


def test_template_ransomware_extension_in_summary() -> None:
    result = _generate_template_summary(RANSOMWARE_FACTS)
    assert ".locked" in result["summary"]


# ---------------------------------------------------------------------------
# Template: phishing_to_compromise (Scenario B)
# ---------------------------------------------------------------------------

def test_template_phishing_structure() -> None:
    result = _generate_template_summary(PHISHING_FACTS)
    assert result["summary_source"] == "template"
    assert len(result["recommended_actions"]) == 4


def test_template_phishing_suspected_wording() -> None:
    result = _generate_template_summary(PHISHING_FACTS)
    assert "suspected" in result["summary"].lower(), "Phishing template must use 'suspected'"


def test_template_phishing_forwarding_rule() -> None:
    result = _generate_template_summary(PHISHING_FACTS)
    assert "forwarding" in result["summary"].lower()
    assert "attacker@evil.com" in result["summary"]


def test_template_phishing_user_in_actions() -> None:
    result = _generate_template_summary(PHISHING_FACTS)
    actions_text = " ".join(result["recommended_actions"])
    assert "a.menon" in actions_text


# ---------------------------------------------------------------------------
# Template: recon_then_access (Scenario D-like)
# ---------------------------------------------------------------------------

def test_template_recon_structure() -> None:
    result = _generate_template_summary(RECON_FACTS)
    assert result["summary_source"] == "template"
    assert len(result["recommended_actions"]) == 4


def test_template_recon_suspected_wording() -> None:
    result = _generate_template_summary(RECON_FACTS)
    assert "suspected" in result["summary"].lower(), "Recon template must use 'suspected'"


def test_template_recon_mentions_port_scan() -> None:
    result = _generate_template_summary(RECON_FACTS)
    assert "scan" in result["summary"].lower() or "reconnaissance" in result["summary"].lower()


# ---------------------------------------------------------------------------
# Template: generic fallback (unknown / None pattern)
# ---------------------------------------------------------------------------

def test_template_generic_fallback_none_pattern() -> None:
    facts = dict(HERO_FACTS)
    facts["pattern"] = None
    result = _generate_template_summary(facts)
    assert result["summary_source"] == "template"
    assert "suspected" in result["summary"].lower()
    assert len(result["recommended_actions"]) == 4


def test_template_generic_fallback_unknown_pattern() -> None:
    facts = dict(HERO_FACTS)
    facts["pattern"] = "some_future_pattern_not_yet_implemented"
    result = _generate_template_summary(facts)
    assert result["summary_source"] == "template"
    assert len(result["recommended_actions"]) == 4


def test_template_generic_fallback_empty_timeline() -> None:
    facts = {"pattern": None, "timeline": [], "entities": {}}
    result = _generate_template_summary(facts)
    assert result["summary_source"] == "template"
    assert isinstance(result["summary"], str)


# ---------------------------------------------------------------------------
# generate_summary: template used when no API key
# ---------------------------------------------------------------------------

def test_generate_summary_no_key_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    result = generate_summary(HERO_FACTS)
    assert result["summary_source"] == "template"
    assert isinstance(result["summary"], str)


def test_generate_summary_key_set_but_no_model_uses_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    result = generate_summary(HERO_FACTS)
    assert result["summary_source"] == "template"


# ---------------------------------------------------------------------------
# generate_summary: LLM happy path (mocked)
# ---------------------------------------------------------------------------

def test_generate_summary_llm_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    fake_resp_json = json.dumps({
        "summary": "LLM-generated summary of the incident.",
        "recommended_actions": ["Action one.", "Action two.", "Action three."],
    })

    # Build a realistic mock of the anthropic response object
    mock_block = MagicMock()
    mock_block.text = fake_resp_json
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response

    mock_anthropic_cls = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
        result = generate_summary(HERO_FACTS)

    assert result["summary_source"] == "llm"
    assert result["summary"] == "LLM-generated summary of the incident."
    assert len(result["recommended_actions"]) == 3


# ---------------------------------------------------------------------------
# generate_summary: LLM fallback on exception (timeout / API error)
# ---------------------------------------------------------------------------

def test_generate_summary_llm_fallback_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = TimeoutError("connection timed out after 15s")
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
        result = generate_summary(HERO_FACTS)

    # Must fall back to template
    assert result["summary_source"] == "template"
    assert isinstance(result["summary"], str)


# ---------------------------------------------------------------------------
# generate_summary: LLM fallback on malformed JSON
# ---------------------------------------------------------------------------

def test_generate_summary_llm_fallback_on_bad_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    mock_block = MagicMock()
    mock_block.text = "This is NOT valid JSON at all, oops!"
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
        result = generate_summary(HERO_FACTS)

    assert result["summary_source"] == "template"


# ---------------------------------------------------------------------------
# generate_summary: LLM fallback on missing JSON key
# ---------------------------------------------------------------------------

def test_generate_summary_llm_fallback_on_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fake-key")
    monkeypatch.setenv("LLM_MODEL", "claude-3-5-sonnet-20241022")

    # JSON is valid but missing "recommended_actions"
    malformed = json.dumps({"summary": "partial answer"})

    mock_block = MagicMock()
    mock_block.text = malformed
    mock_response = MagicMock()
    mock_response.content = [mock_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_response
    mock_anthropic_cls = MagicMock(return_value=mock_client)

    with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
        result = generate_summary(HERO_FACTS)

    assert result["summary_source"] == "template"
