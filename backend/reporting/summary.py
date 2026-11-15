"""Prahari Case Summary Generation Module.

Data Handling & Privacy Notice:
--------------------------------
Privacy and local data sovereignty are strictly preserved by design:
- All alert processing, correlation, deduplication, and case scoring run locally.
- Nothing leaves the local machine except high-level structured case facts (title,
  pattern, severity, score, entities, timeline event metadata) sent to the LLM API,
  and ONLY when ANTHROPIC_API_KEY is explicitly set in the environment.
- Raw security logs, raw payloads, and unredacted event blobs are NEVER transmitted
  to external APIs.
- When ANTHROPIC_API_KEY is unset or empty (or LLM_MODEL is unset/empty), summary
  generation runs 100% locally and offline using deterministic expert templates.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------


def format_timestamp_ist(ts_utc_iso: str | None) -> str:
    """Format UTC ISO-8601 timestamp string into HH:MM IST representation."""
    if not ts_utc_iso:
        return "unknown time"
    try:
        clean = ts_utc_iso.replace("Z", "+00:00")
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        dt_ist = dt.astimezone(IST)
        return dt_ist.strftime("%H:%M IST")
    except (ValueError, TypeError):
        return str(ts_utc_iso)


# ---------------------------------------------------------------------------
# Template summary generator (offline default)
# ---------------------------------------------------------------------------


def _generate_template_summary(case_facts: dict[str, Any]) -> dict[str, Any]:
    """Generate deterministic pattern-specific narrative and recommendations offline."""
    pattern = case_facts.get("pattern")
    timeline = case_facts.get("timeline") or []
    entities = case_facts.get("entities") or {}

    users = entities.get("users") or [a.get("user") for a in timeline if a.get("user")]
    hosts = entities.get("hosts") or [a.get("host") for a in timeline if a.get("host")]

    user_name = users[0] if users else "an unverified user"
    host_name = hosts[0] if hosts else "affected systems"

    # ------------------------------------------------------------------ A
    if pattern == "account_takeover_then_exfiltration":
        t1 = format_timestamp_ist(timeline[0]["timestamp"]) if len(timeline) > 0 else "23:05 IST"
        t2 = format_timestamp_ist(timeline[1]["timestamp"]) if len(timeline) > 1 else "23:40 IST"
        t3 = format_timestamp_ist(timeline[2]["timestamp"]) if len(timeline) > 2 else "01:15 IST"
        t4 = format_timestamp_ist(timeline[3]["timestamp"]) if len(timeline) > 3 else "01:30 IST"

        country = "an unrecognized country"
        if len(timeline) > 0:
            country = timeline[0].get("extra", {}).get("country") or country

        files_count = 4812
        if len(timeline) > 1:
            files_count = timeline[1].get("extra", {}).get("files_count") or files_count

        process = "rclone.exe"
        if len(timeline) > 2:
            process = timeline[2].get("process") or process
            host_name = timeline[2].get("host") or host_name

        bytes_gb = 2.4
        if len(timeline) > 3:
            raw_bytes = timeline[3].get("extra", {}).get("bytes_out") or 2_576_980_378
            bytes_gb = raw_bytes / (1024 ** 3)

        summary = (
            f"At {t1}, user {user_name} authenticated from {country}, a location not previously"
            f" seen on this account. This is confirmed anomalous. At {t2}, the account"
            f" downloaded {files_count:,} loan and KYC records in rapid succession — the"
            f" volume and velocity are confirmed anomalous. At {t3}, the utility {process}"
            f" was executed on host {host_name}; this tool is not authorised on this host and"
            f" its presence is suspected staging for exfiltration. At {t4}, approximately"
            f" {bytes_gb:.1f} GB of outbound data was recorded to an unclassified public IP;"
            f" the destination and volume indicate suspected data exfiltration."
        )
        recommended_actions = [
            f"Revoke all active sessions and immediately reset credentials for user {user_name}.",
            f"Isolate host {host_name} from the network to prevent further egress or lateral movement.",
            "Preserve authentication, DLP, and perimeter firewall logs as evidence for forensic investigation.",
            "Notify the Information Security Officer and assess CERT-In mandatory 6-hour reporting obligation.",
        ]

    # ------------------------------------------------------------------ C
    elif pattern == "ransomware_behaviour":
        t1 = format_timestamp_ist(timeline[0]["timestamp"]) if len(timeline) > 0 else "08:30 IST"
        t2 = format_timestamp_ist(timeline[1]["timestamp"]) if len(timeline) > 1 else "08:42 IST"
        t3 = format_timestamp_ist(timeline[2]["timestamp"]) if len(timeline) > 2 else "08:50 IST"

        proc = "vssadmin.exe"
        if len(timeline) > 0:
            proc = timeline[0].get("process") or proc
            host_name = timeline[0].get("host") or host_name

        renamed = 1250
        ext = ".locked"
        if len(timeline) > 1:
            renamed = timeline[1].get("extra", {}).get("renamed_count", renamed)
            ext = timeline[1].get("extra", {}).get("extension", ext)

        summary = (
            f"At {t1}, the system utility {proc} was invoked on host {host_name} with arguments"
            f" consistent with shadow copy deletion. This is confirmed suspicious use of a"
            f" legitimate tool. At {t2}, {renamed:,} files were rapidly renamed with the"
            f" extension '{ext}'; this mass-rename pattern is a confirmed ransomware indicator."
            f" At {t3}, an API call suspected to delete the volume snapshot backup for the"
            f" affected host was recorded — suspected ransomware anti-recovery action."
        )
        recommended_actions = [
            f"Immediately disconnect host {host_name} from the network and all shared drives.",
            "Verify the integrity of offline or immutable backups before initiating any restoration workflow.",
            "Collect volatile memory dumps and disk snapshots for ransomware variant attribution.",
            "File CERT-In incident report within the mandated 6-hour window and notify executive leadership.",
        ]

    # ------------------------------------------------------------------ B
    elif pattern == "phishing_to_compromise":
        t1 = format_timestamp_ist(timeline[0]["timestamp"]) if len(timeline) > 0 else "14:10 IST"
        t2 = format_timestamp_ist(timeline[1]["timestamp"]) if len(timeline) > 1 else "14:45 IST"
        t3 = format_timestamp_ist(timeline[2]["timestamp"]) if len(timeline) > 2 else "15:15 IST"

        forward_to = None
        if len(timeline) > 2:
            forward_to = timeline[2].get("extra", {}).get("forward_to")

        fwd_text = f" forwarding to {forward_to}" if forward_to else ""

        summary = (
            f"At {t1}, a credential-harvesting phishing email was confirmed delivered to user"
            f" {user_name}. At {t2}, a login for the same user from an unrecognised device in an"
            f" anomalous location was recorded; this is suspected credential theft resulting from"
            f" the phishing lure. At {t3}, an automated mailbox forwarding rule{fwd_text} was"
            f" created on the account; this is suspected attacker persistence and email interception."
        )
        recommended_actions = [
            f"Remove the malicious inbox forwarding rule from user {user_name}'s mailbox immediately.",
            f"Terminate active sessions and enforce a password reset plus hardware MFA for user {user_name}.",
            "Quarantine and purge the phishing email from all corporate mailboxes using subject and sender filters.",
            "Review all email sent and received during the forwarding window for sensitive data exposure.",
        ]

    # ------------------------------------------------------------------ D-like
    elif pattern == "recon_then_access":
        t1 = format_timestamp_ist(timeline[0]["timestamp"]) if len(timeline) > 0 else "10:00 IST"
        t2 = format_timestamp_ist(timeline[1]["timestamp"]) if len(timeline) > 1 else "10:30 IST"

        summary = (
            f"At {t1}, systematic port scanning consistent with external perimeter reconnaissance was"
            f" detected. This network discovery activity is confirmed malicious probing. At {t2},"
            f" authentication probes against internal systems originating from the same source were"
            f" observed; this targeted access attempt is suspected follow-on activity from the"
            f" preceding reconnaissance phase."
        )
        recommended_actions = [
            "Block all identified reconnaissance source IPs at the perimeter firewall.",
            "Audit authentication logs for any successful sign-ins from the suspect IP ranges.",
            "Confirm all public-facing administrative and debug service ports are closed.",
            "Increase IDS/IPS alert sensitivity for the affected subnets for the next 72 hours.",
        ]

    # ------------------------------------------------------------------ Generic
    else:
        t_start = format_timestamp_ist(timeline[0]["timestamp"]) if timeline else "N/A"
        t_end = format_timestamp_ist(timeline[-1]["timestamp"]) if timeline else "N/A"
        sources = sorted({a.get("source") for a in timeline if a.get("source")})
        sources_str = ", ".join(sources) if sources else "multiple tools"
        event_count = len(timeline)

        summary = (
            f"A cluster of {event_count} correlated security events across {sources_str} was"
            f" recorded between {t_start} and {t_end}, involving user '{user_name}' and host"
            f" '{host_name}'. The nature of the activity is suspected anomalous; human analyst"
            f" review is required to confirm or dismiss the incident."
        )
        recommended_actions = [
            "Review the full alert timeline and verify activity legitimacy with asset owners.",
            "Isolate any suspicious hosts and rotate credentials if unauthorised activity is confirmed.",
            "Preserve all system and network telemetry logs for incident triage documentation.",
            "Assess whether this incident meets regulatory reporting criteria under CERT-In directions.",
        ]

    return {
        "summary": summary,
        "recommended_actions": recommended_actions,
        "summary_source": "template",
    }


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------


def _extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract and parse JSON object from raw LLM response text."""
    # 1. Direct parse
    try:
        return json.loads(text.strip())  # type: ignore[return-value]
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Inside markdown fence
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())  # type: ignore[return-value]
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. First/last brace extraction
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace: last_brace + 1].strip())  # type: ignore[return-value]
        except (json.JSONDecodeError, ValueError):
            pass

    return None


# ---------------------------------------------------------------------------
# LLM summary generator (optional)
# ---------------------------------------------------------------------------


def _build_safe_case_facts(case_facts: dict[str, Any]) -> dict[str, Any]:
    """Extract only structured, non-raw fields safe for external API transmission."""
    timeline_summary = []
    for alert in case_facts.get("timeline") or []:
        timeline_summary.append({
            "timestamp_ist": format_timestamp_ist(alert.get("timestamp")),
            "source": alert.get("source"),
            "category": alert.get("category"),
            "title": alert.get("title"),
            "user": alert.get("user"),
            "host": alert.get("host"),
            "src_ip": alert.get("src_ip"),
            "dst_ip": alert.get("dst_ip"),
            "process": alert.get("process"),
            "extra_structured": {
                k: v for k, v in (alert.get("extra") or {}).items()
                if isinstance(v, (str, int, float, bool))
            },
        })

    return {
        "pattern": case_facts.get("pattern"),
        "title": case_facts.get("title"),
        "severity": case_facts.get("severity"),
        "score": case_facts.get("score"),
        "score_breakdown": case_facts.get("score_breakdown"),
        "entities": case_facts.get("entities"),
        "timeline_events": timeline_summary,
    }


def _generate_llm_summary(
    case_facts: dict[str, Any],
    api_key: str,
    model_name: str,
) -> dict[str, Any]:
    """Call Anthropic LLM API with structured case facts only (no raw logs transmitted)."""
    import anthropic

    safe_facts = _build_safe_case_facts(case_facts)

    system_prompt = (
        "You are an expert security incident analyst for Prahari, a triage platform for Indian"
        " financial institutions regulated under CERT-In. Describe what happened in strict"
        " chronological order using only the structured facts provided. Distinguish confirmed"
        " facts from suspected activity by using the word 'suspected' for any unverified attacker"
        " intent or unconfirmed actions. Never invent details, IP addresses, hostnames, or"
        " usernames not present in the input. Output ONLY strict JSON with exactly two keys:"
        " \"summary\" (a concise narrative string) and \"recommended_actions\" (a list of 3-4"
        " concrete remediation action strings)."
    )

    user_content = (
        f"Case facts:\n{json.dumps(safe_facts, indent=2)}\n\n"
        "Return JSON with 'summary' and 'recommended_actions' (list of 3-4 strings)."
    )

    client = anthropic.Anthropic(api_key=api_key, timeout=15.0)

    response = client.messages.create(
        model=model_name,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )

    resp_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            resp_text += block.text

    parsed = _extract_json_block(resp_text)
    if not isinstance(parsed, dict):
        raise TypeError(f"Could not parse valid JSON dict from LLM response (got {type(parsed).__name__})")

    summary_text = parsed.get("summary")
    actions = parsed.get("recommended_actions")

    if not isinstance(summary_text, str) or not summary_text.strip():
        raise ValueError("Missing or empty 'summary' in LLM JSON response")

    if not isinstance(actions, list) or not actions:
        raise ValueError("Missing or empty 'recommended_actions' list in LLM JSON response")

    clean_actions = [str(a).strip() for a in actions if str(a).strip()]
    if not clean_actions:
        raise ValueError("All recommended_actions entries were blank")

    return {
        "summary": summary_text.strip(),
        "recommended_actions": clean_actions,
        "summary_source": "llm",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def generate_summary(case_facts: dict[str, Any]) -> dict[str, Any]:
    """Generate a case summary and recommended actions.

    If ANTHROPIC_API_KEY and LLM_MODEL environment variables are both set,
    attempts LLM generation with a 15-second hard timeout. On any failure
    (timeout, missing key, bad JSON, API error), falls back automatically
    to the deterministic offline template generator.

    Returns:
        dict with keys:
            summary (str): Chronological narrative of the incident.
            recommended_actions (list[str]): 3-4 concrete remediation steps.
            summary_source ("llm" | "template"): Origin of the summary.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    model_name = os.getenv("LLM_MODEL", "").strip()

    if api_key and model_name:
        try:
            return _generate_llm_summary(case_facts, api_key=api_key, model_name=model_name)
        except Exception as err:  # noqa: BLE001
            logger.warning(
                "LLM summary generation failed (%s); falling back to template.", err
            )

    return _generate_template_summary(case_facts)
