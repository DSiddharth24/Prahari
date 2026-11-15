"""Demo data generator for Prahari.

Generates reproducible simulated security alerts across 48 hours representing
both benign/noisy enterprise background events and specific multi-stage attack scenarios.
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

# Shared vocabularies per specification
SOURCES = [
    "email_security",
    "endpoint_av",
    "firewall",
    "identity_provider",
    "cloud_audit",
    "dlp",
]

CATEGORIES = [
    "suspicious_login",
    "failed_login",
    "malware",
    "data_exfiltration",
    "mass_file_access",
    "privilege_change",
    "phishing",
    "mailbox_rule_change",
    "port_scan",
    "ransomware_behaviour",
    "backup_activity",
    "informational",
]

SEVERITIES = ["low", "medium", "high", "critical"]

IST = timezone(timedelta(hours=5, minutes=30))


def ist_to_utc_iso(dt_ist: datetime) -> str:
    """Convert an IST datetime to a UTC ISO-8601 formatted string."""
    if dt_ist.tzinfo is None:
        dt_ist = dt_ist.replace(tzinfo=IST)
    dt_utc = dt_ist.astimezone(UTC)
    return dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_alert(
    *,
    source: str,
    title: str,
    description: str,
    severity: str,
    category: str,
    timestamp_utc: str,
    user: str | None = None,
    host: str | None = None,
    src_ip: str | None = None,
    dst_ip: str | None = None,
    file: str | None = None,
    process: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "source": source,
        "source_alert_id": "",  # Populated after ordering
        "timestamp": timestamp_utc,
        "title": title,
        "description": description,
        "severity": severity,
        "category": category,
        "user": user,
        "host": host,
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "file": file,
        "process": process,
        "extra": extra or {},
    }


def generate_demo_alerts(seed: int = 42) -> list[dict[str, Any]]:
    """Generate ~400 deterministic simulated alerts across 48 hours.

    Scenarios included:
      - Scenario A (Hero): NBFC account takeover + data theft (r.sharma)
      - Scenario B: Phishing-to-compromise (a.menon)
      - Scenario C: Ransomware-like behaviour (WS-ACCTS-07)
      - Scenario D: Decoy scanner port scan + separate failed login (p.iyer)
      - ~300+ Benign/noisy events (scanners, scheduled backups, EDR info, duplicates, TEST-* hosts, known countries)
    """
    rng = random.Random(seed)
    alerts: list[dict[str, Any]] = []

    # 48-hour base window: 2026-11-14 00:00:00 IST to 2026-11-15 23:59:59 IST
    base_start_ist = datetime(2026, 11, 14, 0, 0, 0, tzinfo=IST)

    # -------------------------------------------------------------------------
    # Scenario A (Hero): NBFC Account Takeover + Data Theft
    # 23:05 IST: identity_provider / suspicious_login (Romania)
    # 23:40 IST: dlp / mass_file_access (4,812 files)
    # 01:15 IST (next day): endpoint_av / malware (FILESRV-02, rclone.exe)
    # 01:30 IST (next day): firewall / data_exfiltration (~2.4 GB out)
    # -------------------------------------------------------------------------
    hero_user = "r.sharma"
    hero_ip = "185.220.101.5"
    hero_host = "FILESRV-02"

    hero_1 = _build_alert(
        source="identity_provider",
        title="Suspicious login from unusual location",
        description=f"User {hero_user} authenticated from Romania, an anomaly for this profile.",
        severity="high",
        category="suspicious_login",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 23, 5, 0, tzinfo=IST)),
        user=hero_user,
        src_ip=hero_ip,
        extra={
            "scenario": "hero",
            "country": "Romania",
            "country_seen_before": False,
            "city": "Bucharest",
        },
    )

    hero_2 = _build_alert(
        source="dlp",
        title="Mass customer file access detected",
        description=f"User {hero_user} read 4,812 customer loan & KYC records in 10 minutes.",
        severity="high",
        category="mass_file_access",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 23, 40, 0, tzinfo=IST)),
        user=hero_user,
        host=hero_host,
        src_ip=hero_ip,
        file="/shares/nbfc_kyc_vault/records_active.tar.gz",
        extra={
            "scenario": "hero",
            "files_count": 4812,
            "department": "Retail Lending",
        },
    )

    hero_3 = _build_alert(
        source="endpoint_av",
        title="Suspicious program rclone.exe executed",
        description=f"Potentially unwanted data synchronization tool rclone.exe launched on {hero_host}.",
        severity="medium",
        category="malware",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 15, 1, 15, 0, tzinfo=IST)),
        user=hero_user,
        host=hero_host,
        file="C:\\Windows\\Temp\\rclone.exe",
        process="rclone.exe",
        extra={
            "scenario": "hero",
            "action": "quarantine_failed",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
    )

    hero_4 = _build_alert(
        source="firewall",
        title="Large outbound data transfer to unknown destination",
        description=f"Outbound transfer of ~2.4 GB from {hero_host} to unclassified public IP.",
        severity="high",
        category="data_exfiltration",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 15, 1, 30, 0, tzinfo=IST)),
        user=hero_user,
        host=hero_host,
        src_ip=hero_ip,
        dst_ip="198.51.100.77",
        extra={
            "scenario": "hero",
            "bytes_out": 2576980378,
            "protocol": "TCP/443",
        },
    )
    alerts.extend([hero_1, hero_2, hero_3, hero_4])

    # -------------------------------------------------------------------------
    # Scenario B: Phishing to Compromise
    # 14:10 IST: email_security / phishing
    # 14:45 IST: identity_provider / suspicious_login
    # 15:15 IST: cloud_audit / mailbox_rule_change
    # -------------------------------------------------------------------------
    phish_user = "a.menon"
    phish_ip = "197.210.64.12"

    phish_1 = _build_alert(
        source="email_security",
        title="Phishing email delivered to employee inbox",
        description=f"Message with deceptive credential harvesting link delivered to {phish_user}.",
        severity="medium",
        category="phishing",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 14, 10, 0, tzinfo=IST)),
        user=phish_user,
        src_ip="203.0.113.88",
        extra={
            "scenario": "phishing",
            "sender": "it-support@secure-nbfc-update.com",
            "subject": "Urgent: Mandated Portal Re-Authentication",
        },
    )

    phish_2 = _build_alert(
        source="identity_provider",
        title="Login from unrecognized new device",
        description=f"User {phish_user} logged in from an unfamiliar mobile user agent in Nigeria.",
        severity="high",
        category="suspicious_login",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 14, 45, 0, tzinfo=IST)),
        user=phish_user,
        src_ip=phish_ip,
        extra={
            "scenario": "phishing",
            "device": "Linux / Firefox 120",
            "country": "Nigeria",
            "country_seen_before": False,
        },
    )

    phish_3 = _build_alert(
        source="cloud_audit",
        title="Mailbox forwarding rule created",
        description=f"User {phish_user} created inbox rule forwarding all incoming mail externally.",
        severity="high",
        category="mailbox_rule_change",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 15, 15, 0, tzinfo=IST)),
        user=phish_user,
        src_ip=phish_ip,
        extra={
            "scenario": "phishing",
            "forward_to": "drop@external-inbox.com",
            "rule_name": "RedirectAll",
        },
    )
    alerts.extend([phish_1, phish_2, phish_3])

    # -------------------------------------------------------------------------
    # Scenario C: Ransomware-like Behaviour
    # 08:30 IST: endpoint_av / malware (vssadmin.exe)
    # 08:42 IST: endpoint_av / ransomware_behaviour (1,250 renamed files)
    # 08:50 IST: cloud_audit / backup_activity (action: delete)
    # -------------------------------------------------------------------------
    rw_host = "WS-ACCTS-07"
    rw_user = "v.patel"

    rw_1 = _build_alert(
        source="endpoint_av",
        title="Suspicious system utility execution: vssadmin.exe",
        description=f"Shadow volume administrative command invoked on {rw_host}.",
        severity="high",
        category="malware",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 15, 8, 30, 0, tzinfo=IST)),
        user=rw_user,
        host=rw_host,
        process="vssadmin.exe",
        file="C:\\Windows\\System32\\vssadmin.exe",
        extra={
            "scenario": "ransomware",
            "command_line": "vssadmin delete shadows /all /quiet",
        },
    )

    rw_2 = _build_alert(
        source="endpoint_av",
        title="Mass file rename activity detected",
        description=f"Multiple accounting directories rapidly appended with ransomware extension on {rw_host}.",
        severity="critical",
        category="ransomware_behaviour",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 15, 8, 42, 0, tzinfo=IST)),
        user=rw_user,
        host=rw_host,
        process="cryptlock.exe",
        file="C:\\Accounting\\Ledgers\\2026_Q3.xlsx.locked",
        extra={
            "scenario": "ransomware",
            "renamed_count": 1250,
            "extension": ".locked",
        },
    )

    rw_3 = _build_alert(
        source="cloud_audit",
        title="Shadow copy / backup deletion attempt",
        description=f"API request initiated to delete volume snapshot backup for {rw_host}.",
        severity="high",
        category="backup_activity",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 15, 8, 50, 0, tzinfo=IST)),
        user=rw_user,
        host=rw_host,
        extra={
            "scenario": "ransomware",
            "action": "delete",
            "target_snapshot": "snap-daily-accts-07",
        },
    )
    alerts.extend([rw_1, rw_2, rw_3])

    # -------------------------------------------------------------------------
    # Scenario D (Decoy): Port scan + unrelated failed login hours apart
    # 06:15 IST: firewall / port_scan (low)
    # 20:45 IST: identity_provider / failed_login (low, p.iyer)
    # -------------------------------------------------------------------------
    decoy_1 = _build_alert(
        source="firewall",
        title="Port scan detected from known scanner IP",
        description="Routine inbound sweep against external edge firewall.",
        severity="low",
        category="port_scan",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 6, 15, 0, tzinfo=IST)),
        src_ip="71.6.232.4",
        dst_ip="203.0.113.1",
        extra={
            "scenario": "decoy",
            "scanner": "shadowserver",
            "ports_scanned": [80, 443, 8080],
        },
    )

    decoy_2 = _build_alert(
        source="identity_provider",
        title="Single failed password attempt",
        description="Single incorrect credential entered for user p.iyer.",
        severity="low",
        category="failed_login",
        timestamp_utc=ist_to_utc_iso(datetime(2026, 11, 14, 20, 45, 0, tzinfo=IST)),
        user="p.iyer",
        src_ip="10.0.12.44",
        extra={
            "scenario": "decoy",
            "reason": "bad_password",
        },
    )
    alerts.extend([decoy_1, decoy_2])

    # -------------------------------------------------------------------------
    # Benign / Noisy Background Alerts (~390 alerts across 48h)
    # -------------------------------------------------------------------------
    scanner_ips = ["198.20.99.1", "162.142.125.1", "167.94.138.42", "71.6.232.4"]
    scanner_names = ["shodan", "censys", "shadowserver"]

    # 1. Known scanner IPs (~75 alerts)
    for _ in range(75):
        offset_minutes = rng.randint(0, 48 * 60 - 1)
        ts = base_start_ist + timedelta(minutes=offset_minutes)
        sc_ip = rng.choice(scanner_ips)
        sc_name = rng.choice(scanner_names)
        alerts.append(
            _build_alert(
                source="firewall",
                title="Port scan detected from known scanner IP",
                description=f"Inbound network discovery sweep from recognized research scanner {sc_name}.",
                severity="low",
                category="port_scan",
                timestamp_utc=ist_to_utc_iso(ts),
                src_ip=sc_ip,
                dst_ip="203.0.113.10",
                extra={
                    "scanner": sc_name,
                    "known_scanner": True,
                    "benign_type": "scanner",
                },
            )
        )

    # 2. Scheduled backup jobs (~60 alerts)
    backup_hosts = ["DB-CLUSTER-01", "BACKUP-NODE-01", "CORE-BANK-DB", "VAULT-SRV-01"]
    for _ in range(60):
        offset_minutes = rng.randint(0, 48 * 60 - 1)
        ts = base_start_ist + timedelta(minutes=offset_minutes)
        b_host = rng.choice(backup_hosts)
        alerts.append(
            _build_alert(
                source="cloud_audit",
                title="Scheduled backup job completed",
                description=f"Automated policy snapshot execution finished successfully on {b_host}.",
                severity="low",
                category="backup_activity",
                timestamp_utc=ist_to_utc_iso(ts),
                host=b_host,
                extra={
                    "scheduled": True,
                    "action": "backup_complete",
                    "job_name": f"daily_snapshot_{b_host.lower()}",
                    "benign_type": "scheduled_backup",
                },
            )
        )

    # 3. Informational EDR events (~75 alerts)
    edr_hosts = ["WS-ENG-12", "LAPTOP-MKT-04", "SRV-APP-02", "WS-OPS-22", "LAPTOP-EXEC-01"]
    edr_titles = [
        ("Routine EDR definition update installed", "Agent definition signatures refreshed."),
        ("Agent health beacon received", "Standard endpoint heartbeat confirmed."),
        ("USB device connected - approved asset", "Company-enrolled encrypted USB drive mounted."),
    ]
    for _ in range(75):
        offset_minutes = rng.randint(0, 48 * 60 - 1)
        ts = base_start_ist + timedelta(minutes=offset_minutes)
        host = rng.choice(edr_hosts)
        title, desc = rng.choice(edr_titles)
        alerts.append(
            _build_alert(
                source="endpoint_av",
                title=title,
                description=desc,
                severity="low",
                category="informational",
                timestamp_utc=ist_to_utc_iso(ts),
                host=host,
                extra={
                    "component": "edr_agent",
                    "event_type": "policy_check",
                    "benign_type": "edr_info",
                },
            )
        )

    # 4. Same-title repeats within minutes (duplicates to be merged by dedupe) (~70 alerts)
    # 14 clusters of 5 duplicate alerts spaced 30 to 90 seconds apart
    dup_templates = [
        ("firewall", "firewall_drop", "Firewall dropped invalid TCP packet", "informational", "low"),
        ("email_security", "spam_blocked", "Inbound spam message quarantined", "phishing", "low"),
        ("endpoint_av", "edr_beacon", "Routine background process telemetry ping", "informational", "low"),
    ]
    for _ in range(14):
        base_min = rng.randint(0, 48 * 60 - 30)
        base_ts = base_start_ist + timedelta(minutes=base_min)
        src, _tid, title, cat, sev = rng.choice(dup_templates)
        dup_host = rng.choice(edr_hosts) if src != "firewall" else None
        dup_ip = f"10.0.1.{rng.randint(2, 250)}"
        for k in range(5):
            t_offset = timedelta(seconds=k * rng.randint(30, 80))
            ts = base_ts + t_offset
            alerts.append(
                _build_alert(
                    source=src,
                    title=title,
                    description=f"Automated event notification ({title}).",
                    severity=sev,
                    category=cat,
                    timestamp_utc=ist_to_utc_iso(ts),
                    host=dup_host,
                    src_ip=dup_ip,
                    extra={
                        "benign_type": "duplicate_repeat",
                        "cluster_idx": k,
                    },
                )
            )

    # 5. Logins from previously seen countries (extra.country_seen_before: true) (~55 alerts)
    known_users = ["k.nair", "s.verma", "m.gupta", "d.das", "n.joshi"]
    for _ in range(55):
        offset_minutes = rng.randint(0, 48 * 60 - 1)
        ts = base_start_ist + timedelta(minutes=offset_minutes)
        user = rng.choice(known_users)
        alerts.append(
            _build_alert(
                source="identity_provider",
                title="User login from previously seen location",
                description=f"User {user} successfully authenticated from verified corporate location in India.",
                severity="low",
                category="suspicious_login",
                timestamp_utc=ist_to_utc_iso(ts),
                user=user,
                src_ip=f"103.21.{rng.randint(10, 80)}.{rng.randint(1, 250)}",
                extra={
                    "country": "India",
                    "country_seen_before": True,
                    "benign_type": "known_country_login",
                },
            )
        )

    # 6. Alerts on hosts named TEST-* (~55 alerts)
    test_hosts = ["TEST-SRV-01", "TEST-DB-02", "TEST-WORKER-03", "TEST-SANDBOX-09"]
    test_templates = [
        ("endpoint_av", "malware", "low", "EICAR test string detected in test suite", "Automated QA malware check."),
        ("dlp", "mass_file_access", "low", "Automated QA test file read batch", "Synthetic file benchmark execution."),
        ("cloud_audit", "privilege_change", "low", "Test service account role updated", "Ephemeral test runner IAM grant."),
    ]
    for _ in range(55):
        offset_minutes = rng.randint(0, 48 * 60 - 1)
        ts = base_start_ist + timedelta(minutes=offset_minutes)
        t_host = rng.choice(test_hosts)
        src, cat, sev, title, desc = rng.choice(test_templates)
        alerts.append(
            _build_alert(
                source=src,
                title=title,
                description=desc,
                severity=sev,
                category=cat,
                timestamp_utc=ist_to_utc_iso(ts),
                host=t_host,
                extra={
                    "environment": "sandbox_testing",
                    "test_run": True,
                    "benign_type": "test_host",
                },
            )
        )

    # Sort all alerts chronologically by UTC timestamp
    alerts.sort(key=lambda a: a["timestamp"])

    # Assign deterministic, unique source_alert_id per alert
    for idx, alert in enumerate(alerts, start=1):
        src_prefix = alert["source"][:3]
        alert["source_alert_id"] = f"{src_prefix}-{seed}-{idx:05d}"

    return alerts


def main() -> None:
    """CLI entrypoint for generating demo alert dataset."""
    parser = argparse.ArgumentParser(
        description="Prahari Demo Alert Dataset Generator"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible generation (default: 42)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Output file path (e.g. demo.json)",
    )
    args = parser.parse_args()

    alerts = generate_demo_alerts(seed=args.seed)

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(alerts, f, indent=2)
        print(f"Successfully generated {len(alerts)} alerts to {args.out}")
    else:
        print(f"Generated {len(alerts)} demo alerts (seed={args.seed}).")


if __name__ == "__main__":
    main()
