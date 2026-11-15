"""
engine/pipeline.py
Main processing pipeline.

Pipeline order (section 4):
    ingest (done by engine.ingest)
    → normalise     (clean/canonicalise field values)
    → suppress benign
    → de-duplicate
    → correlate into cases
    → detect pattern
    → score
    → (API layer adds summary)

Public interface (section 7.2):
    run_pipeline(actor="system")
        -> {suppressed, merged, in_cases, cases_created, unlinked_low_priority}
"""

import json
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address, ip_network

import yaml

from .db import get_session
from .models import Alert, Case, CaseAlertLink
from . import audit as _audit
from .settings import get_settings, get_rules_yaml

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _now_utc():
    return datetime.now(timezone.utc)


def _load_rules() -> dict:
    """Parse rules.yaml; return empty dict on any error."""
    text = get_rules_yaml()
    if not text:
        return {}
    try:
        return yaml.safe_load(text) or {}
    except Exception:
        return {}


def _ip_in_list(ip_str: str | None, networks: list[str]) -> bool:
    if not ip_str:
        return False
    try:
        addr = ip_address(ip_str)
        for net_str in networks:
            try:
                if addr in ip_network(net_str, strict=False):
                    return True
            except Exception:
                if ip_str == net_str:
                    return True
    except Exception:
        pass
    return False


def _alert_matches_conditions(alert: Alert, conditions: dict) -> bool:
    """Return True if the alert satisfies ALL conditions in the dict."""
    for key, expected in conditions.items():
        if key == "source":
            if alert.source != expected:
                return False
        elif key == "category":
            if alert.category != expected:
                return False
        elif key == "severity_raw":
            if alert.severity_raw != expected:
                return False
        elif key == "title_contains":
            if not alert.title or expected.lower() not in alert.title.lower():
                return False
        elif key == "host_contains":
            if not alert.host or expected.lower() not in alert.host.lower():
                return False
        elif key == "process_contains":
            if not alert.process or expected.lower() not in alert.process.lower():
                return False
        elif key == "user_contains":
            if not alert.user or expected.lower() not in alert.user.lower():
                return False
        elif key == "src_ip_in":
            if not _ip_in_list(alert.src_ip, expected):
                return False
    return True


# ---------------------------------------------------------------------------
# Step 1 — Normalise
# ---------------------------------------------------------------------------

def _normalise(session, new_alerts: list[Alert]) -> None:
    """
    Light normalisation pass on freshly ingested alerts.
    Canonicalises severity.  Other field cleaning can be added here.
    Currently a no-op for already-normalised fields (ingest.py handles severity).
    """
    # Nothing to do beyond what ingest already did; hook left for extensibility.
    pass


# ---------------------------------------------------------------------------
# Step 2 — Suppress benign
# ---------------------------------------------------------------------------

def _suppress(session, rules: dict, new_alerts: list[Alert]) -> int:
    """Mark matching alerts as suppressed_benign.  Returns count suppressed."""
    suppression_rules = rules.get("suppression_rules", [])
    count = 0
    for alert in new_alerts:
        if alert.status != "new":
            continue
        for rule in suppression_rules:
            conditions = rule.get("conditions", {})
            if _alert_matches_conditions(alert, conditions):
                alert.status = "suppressed_benign"
                alert.suppression_reason = rule.get("reason", rule.get("id", "matched suppression rule"))
                _audit.record(
                    actor="system",
                    action="alert_suppressed",
                    target_type="alert",
                    target_id=alert.id,
                    details={"rule": rule.get("id"), "reason": alert.suppression_reason},
                    session=session,
                )
                count += 1
                break  # first matching rule wins
    return count


# ---------------------------------------------------------------------------
# Step 3 — Deduplicate
# ---------------------------------------------------------------------------

def _dedup(session, rules: dict, settings: dict, new_alerts: list[Alert]) -> int:
    """
    Merge duplicate alerts.
    Two alerts are duplicates if they share the same dedup_key values and
    their timestamps are within dedupe_window_minutes of one another.
    The chronologically first alert (lowest id) is canonical.
    Returns count of alerts marked merged_duplicate.
    """
    window_mins = int(settings.get("dedupe_window_minutes", 10))
    dedup_keys  = rules.get("dedup_keys", [["category", "user"], ["category", "host"]])
    count       = 0

    for alert in new_alerts:
        if alert.status != "new":
            continue

        window_start = alert.timestamp - timedelta(minutes=window_mins)
        window_end   = alert.timestamp + timedelta(minutes=window_mins)

        for key_combo in dedup_keys:
            filter_vals = {}
            skip = False
            for field in key_combo:
                val = getattr(alert, field, None)
                if val is None:
                    skip = True
                    break
                filter_vals[field] = val
            if skip:
                continue

            # Find an earlier alert (by id) with the same key values in window
            # Canonical must have a lower id (ingested earlier) and NOT already be a duplicate
            q = session.query(Alert).filter(
                Alert.id < alert.id,                              # strictly earlier
                Alert.status.in_(["new", "in_case"]),            # active alert
                Alert.timestamp >= window_start,
                Alert.timestamp <= window_end,
            )
            for field, val in filter_vals.items():
                q = q.filter(getattr(Alert, field) == val)

            canonical = q.order_by(Alert.timestamp.asc(), Alert.id.asc()).first()
            if canonical:
                alert.status = "merged_duplicate"
                alert.duplicate_of = canonical.id
                canonical.duplicate_count = (canonical.duplicate_count or 0) + 1
                _audit.record(
                    actor="system",
                    action="alert_merged",
                    target_type="alert",
                    target_id=alert.id,
                    details={"canonical_id": canonical.id, "key": key_combo},
                    session=session,
                )
                count += 1
                break  # first matching key wins

    return count


# ---------------------------------------------------------------------------
# Step 4 — Correlate into cases
# ---------------------------------------------------------------------------

def _linking_entity(a: Alert) -> set[str]:
    """Return the set of entity tokens for this alert (used to link alerts into cases)."""
    tokens = set()
    if a.user:   tokens.add(f"user:{a.user.lower()}")
    if a.host:   tokens.add(f"host:{a.host.lower()}")
    if a.src_ip: tokens.add(f"ip:{a.src_ip}")
    if a.dst_ip: tokens.add(f"ip:{a.dst_ip}")
    return tokens


def _correlate(session, rules: dict, settings: dict, new_alerts: list[Alert]) -> dict:
    """
    Group new alerts into existing or new cases by shared entity within
    correlation_window_hours.

    Returns {"cases_created": int, "in_cases": int}
    """
    window_hours = int(settings.get("correlation_window_hours", 6))
    corr_rules   = rules.get("correlation_rules", [])
    cases_created = 0
    in_cases_count = 0

    # Only process alerts that are still "new"
    eligible = [a for a in new_alerts if a.status == "new"]
    if not eligible:
        return {"cases_created": 0, "in_cases": 0}

    # Cluster eligible alerts by shared entities within the time window
    # using a union-find approach
    # -----------------------------------------------------------------
    # Build entity → alert index for all existing in_case alerts within window
    cutoff = _now_utc() - timedelta(hours=window_hours)
    existing_in_case = (
        session.query(Alert)
        .filter(Alert.status == "in_case", Alert.timestamp >= cutoff)
        .all()
    )

    # entity_to_case_id: entity_token -> case_id
    entity_to_case: dict[str, int] = {}
    for a in existing_in_case:
        for tok in _linking_entity(a):
            # Find this alert's case
            link = session.query(CaseAlertLink).filter(CaseAlertLink.alert_id == a.id).first()
            if link:
                entity_to_case[tok] = link.case_id

    # Also track entity_to_case for newly added alerts in this run
    # so alerts within the same batch can link to each other
    new_entity_map: dict[str, list[int]] = {}  # entity -> list of alert ids
    for a in eligible:
        for tok in _linking_entity(a):
            new_entity_map.setdefault(tok, []).append(a.id)

    # Process each eligible alert
    for alert in eligible:
        toks = _linking_entity(alert)

        # 1. Can we attach to an existing case?
        matched_case_id = None
        for tok in toks:
            if tok in entity_to_case:
                matched_case_id = entity_to_case[tok]
                break

        if matched_case_id:
            # Attach to existing case
            case = session.query(Case).filter(Case.id == matched_case_id).first()
            if case:
                _attach_alert_to_case(session, alert, case)
                for tok in toks:
                    entity_to_case[tok] = case.id
                in_cases_count += 1
                continue

        # 2. Can this alert join another alert from THIS batch?
        peer_id = None
        for tok in toks:
            peers = new_entity_map.get(tok, [])
            for pid in peers:
                if pid != alert.id:
                    peer_id = pid
                    break
            if peer_id:
                break

        if peer_id:
            peer_alert = session.query(Alert).filter(Alert.id == peer_id).first()
            if peer_alert and peer_alert.status == "in_case":
                # peer already placed in a case — join it
                link = session.query(CaseAlertLink).filter(
                    CaseAlertLink.alert_id == peer_id).first()
                if link:
                    case = session.query(Case).filter(Case.id == link.case_id).first()
                    if case:
                        _attach_alert_to_case(session, alert, case)
                        for tok in toks:
                            entity_to_case[tok] = case.id
                        in_cases_count += 1
                        continue

            # peer is still unlinked — create a new case for both
            case = _create_case(session)
            session.flush()  # get case.id
            cases_created += 1

            if peer_alert:
                _attach_alert_to_case(session, peer_alert, case)
                for tok in _linking_entity(peer_alert):
                    entity_to_case[tok] = case.id

            _attach_alert_to_case(session, alert, case)
            for tok in toks:
                entity_to_case[tok] = case.id
            in_cases_count += 1
            continue

        # 3. Alert has no linkable peers — mark unlinked_low_priority if low severity
        if alert.severity_raw in (None, "low"):
            alert.status = "unlinked_low_priority"
        # else: leave as "new" — will get picked up in pattern/score pass or next run

    return {"cases_created": cases_created, "in_cases": in_cases_count}


def _create_case(session) -> Case:
    case = Case(
        title="Pending investigation",  # overwritten by pattern detection
        detected_at=_now_utc(),
    )
    session.add(case)
    return case


def _attach_alert_to_case(session, alert: Alert, case: Case) -> None:
    # Avoid double-linking
    existing = session.query(CaseAlertLink).filter(
        CaseAlertLink.alert_id == alert.id,
        CaseAlertLink.case_id  == case.id,
    ).first()
    if existing:
        return
    link = CaseAlertLink(case_id=case.id, alert_id=alert.id)
    session.add(link)
    alert.status = "in_case"

    # Update case time range
    if case.first_alert_at is None or alert.timestamp < case.first_alert_at:
        case.first_alert_at = alert.timestamp
    if case.last_alert_at is None or alert.timestamp > case.last_alert_at:
        case.last_alert_at = alert.timestamp


# ---------------------------------------------------------------------------
# Step 5 — Detect pattern
# ---------------------------------------------------------------------------

def _detect_patterns(session, rules: dict) -> None:
    """
    For each open case with no pattern yet (or any case after a new alert
    was just added), check if any correlation rule's required_categories
    are all present.  Assign the best-matching pattern and update title.
    """
    corr_rules = rules.get("correlation_rules", [])

    open_cases = session.query(Case).filter(Case.status == "open").all()
    for case in open_cases:
        # Gather categories present in this case
        linked_alerts = [lk.alert for lk in case.alert_links if lk.alert]
        present_cats  = {a.category for a in linked_alerts if a.category}

        best_pattern = None
        best_score   = -1

        for rule in corr_rules:
            required = set(rule.get("required_categories", []))
            if not required:
                continue
            if not required.issubset(present_cats):
                continue

            supporting  = set(rule.get("supporting_categories", []))
            match_score = len(required) + len(supporting & present_cats)

            if match_score > best_score:
                best_score   = match_score
                best_pattern = rule["pattern"]

        if best_pattern and case.pattern != best_pattern:
            case.pattern = best_pattern
            case.title   = _pattern_to_title(best_pattern)
            _audit.record(
                actor="system",
                action="case_pattern_detected",
                target_type="case",
                target_id=case.id,
                details={"pattern": best_pattern},
                session=session,
            )


def _pattern_to_title(pattern: str) -> str:
    titles = {
        "account_takeover_then_exfiltration": "Possible account takeover followed by data exfiltration",
        "ransomware_behaviour":               "Suspected ransomware activity",
        "phishing_to_compromise":             "Suspected phishing leading to account compromise",
        "recon_then_access":                  "Network reconnaissance followed by access attempt",
    }
    return titles.get(pattern, pattern.replace("_", " ").title())


# ---------------------------------------------------------------------------
# Step 6 — Score
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}

def _score_cases(session, rules: dict, settings: dict) -> None:
    """Recompute score and severity for every open case."""
    scoring_cfg     = rules.get("scoring", {})
    critical_assets = set(a.lower() for a in settings.get("critical_assets", []))
    bytes_threshold = int(settings.get("outbound_bytes_threshold", 1_000_000_000))

    open_cases = session.query(Case).filter(Case.status == "open").all()
    for case in open_cases:
        linked_alerts = [lk.alert for lk in case.alert_links if lk.alert]
        if not linked_alerts:
            continue

        breakdown = []
        total     = 0

        # --- pattern points ---
        pm_cfg = scoring_cfg.get("pattern_match", {})
        p_pts  = pm_cfg.get(case.pattern or "none", 0)
        if p_pts:
            breakdown.append({
                "factor":      "Pattern match",
                "points":      p_pts,
                "explanation": f"Attack pattern '{case.pattern}' detected across correlated alerts.",
            })
            total += p_pts

        # --- source diversity ---
        sd_cfg   = scoring_cfg.get("source_diversity", {})
        sources  = {a.source for a in linked_alerts if a.source}
        extra_s  = max(0, len(sources) - 1)
        sd_pts   = min(extra_s * int(sd_cfg.get("per_extra_source", 5)),
                       int(sd_cfg.get("max", 15)))
        if sd_pts:
            breakdown.append({
                "factor":      "Source diversity",
                "points":      sd_pts,
                "explanation": f"Alerts from {len(sources)} distinct tools: {', '.join(sorted(sources))}.",
            })
            total += sd_pts

        # --- max severity ---
        sev_cfg = scoring_cfg.get("severity_max", {})
        max_sev = max(
            (a.severity_raw for a in linked_alerts if a.severity_raw),
            key=lambda s: _SEVERITY_ORDER.get(s, 0),
            default=None,
        )
        if max_sev:
            sev_pts = int(sev_cfg.get(max_sev, 0))
            if sev_pts:
                breakdown.append({
                    "factor":      "Highest alert severity",
                    "points":      sev_pts,
                    "explanation": f"Most severe individual alert in this case is '{max_sev}'.",
                })
                total += sev_pts

        # --- alert count ---
        ac_cfg = scoring_cfg.get("alert_count", {})
        n_alerts = len(linked_alerts)
        ac_pts   = 0
        for band in ac_cfg.get("thresholds", []):
            if band["min"] <= n_alerts <= band["max"]:
                ac_pts = int(band["points"])
                break
        if ac_pts:
            breakdown.append({
                "factor":      "Alert volume",
                "points":      ac_pts,
                "explanation": f"{n_alerts} distinct alerts linked to this case.",
            })
            total += ac_pts

        # --- critical asset ---
        ca_pts = int(scoring_cfg.get("critical_asset_hit", 15))
        hit_assets = set()
        for a in linked_alerts:
            if a.host  and a.host.lower()  in critical_assets: hit_assets.add(a.host)
            if a.user  and a.user.lower()  in critical_assets: hit_assets.add(a.user)
        if hit_assets:
            breakdown.append({
                "factor":      "Critical asset involved",
                "points":      ca_pts,
                "explanation": f"Alerts touch known critical assets: {', '.join(sorted(hit_assets))}.",
            })
            total += ca_pts

        # --- large outbound ---
        lo_pts = int(scoring_cfg.get("large_outbound", 10))
        large_out = any(
            int(a.extra.get("bytes_out", 0) or 0) > bytes_threshold
            for a in linked_alerts
        )
        if large_out:
            breakdown.append({
                "factor":      "Large outbound transfer",
                "points":      lo_pts,
                "explanation": f"At least one alert reports outbound data exceeding threshold ({bytes_threshold:,} bytes).",
            })
            total += lo_pts

        # --- time compression ---
        tc_cfg = scoring_cfg.get("time_compression", {})
        tc_window = int(tc_cfg.get("window_minutes", 60))
        tc_pts    = int(tc_cfg.get("points", 5))
        timestamps = sorted(a.timestamp for a in linked_alerts if a.timestamp)
        if len(timestamps) >= 2:
            span_mins = (timestamps[-1] - timestamps[0]).total_seconds() / 60
            if span_mins <= tc_window:
                breakdown.append({
                    "factor":      "Rapid sequence",
                    "points":      tc_pts,
                    "explanation": f"All {len(timestamps)} alerts occurred within {int(span_mins)} minutes.",
                })
                total += tc_pts

        # Cap at 100
        total = min(total, 100)

        # Derive severity from score
        if total >= 80:
            severity = "critical"
        elif total >= 60:
            severity = "high"
        elif total >= 35:
            severity = "medium"
        else:
            severity = "low"

        case.score           = float(total)
        case.score_breakdown = breakdown
        case.severity        = severity


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(actor: str = "system") -> dict:
    """
    Run the full pipeline over all alerts currently in status 'new'.

    Returns
    -------
    {
        "suppressed":           int,
        "merged":               int,
        "in_cases":             int,
        "cases_created":        int,
        "unlinked_low_priority": int,
    }
    """
    rules    = _load_rules()
    settings = get_settings()

    session = get_session()
    try:
        new_alerts = session.query(Alert).filter(Alert.status == "new").all()

        if not new_alerts:
            return {
                "suppressed": 0, "merged": 0,
                "in_cases": 0, "cases_created": 0,
                "unlinked_low_priority": 0,
            }

        # Step 1 – normalise (in-place, no DB writes needed here)
        _normalise(session, new_alerts)

        # Step 2 – suppress
        suppressed = _suppress(session, rules, new_alerts)
        session.flush()

        # Step 3 – deduplicate (only un-suppressed alerts)
        merged = _dedup(session, rules, settings, new_alerts)
        session.flush()

        # Step 4 – correlate
        corr = _correlate(session, rules, settings, new_alerts)
        session.flush()

        # Step 5 – pattern detection (all open cases)
        _detect_patterns(session, rules)
        session.flush()

        # Step 6 – score (all open cases)
        _score_cases(session, rules, settings)

        session.commit()

        # Count unlinked_low_priority among originally-new alerts
        session.expire_all()
        unlinked = sum(
            1 for a in new_alerts
            if a.status == "unlinked_low_priority"
        )

        result = {
            "suppressed":            suppressed,
            "merged":                merged,
            "in_cases":              corr["in_cases"],
            "cases_created":         corr["cases_created"],
            "unlinked_low_priority": unlinked,
        }

        _audit.record(
            actor=actor,
            action="pipeline_run",
            target_type=None,
            target_id=None,
            details=result,
        )

        return result

    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
