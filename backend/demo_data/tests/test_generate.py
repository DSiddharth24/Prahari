from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from backend.demo_data.generate import (
    CATEGORIES,
    SOURCES,
    generate_demo_alerts,
)


def test_deterministic_output():
    """Generating with the same seed must produce identical alerts."""
    run1 = generate_demo_alerts(seed=42)
    run2 = generate_demo_alerts(seed=42)
    assert run1 == run2

    # Different seed should produce different alert IDs/timestamps
    run_other = generate_demo_alerts(seed=99)
    assert run1 != run_other


def test_total_count_and_uniqueness():
    """Dataset should contain ~400 alerts with unique IDs and valid vocabularies."""
    alerts = generate_demo_alerts(seed=42)
    assert 380 <= len(alerts) <= 420

    alert_ids = [a["source_alert_id"] for a in alerts]
    assert len(alert_ids) == len(set(alert_ids)), "Duplicate source_alert_id found!"

    # Verify sources, categories, and required keys
    required_keys = {"source", "source_alert_id", "timestamp", "title"}
    for a in alerts:
        assert required_keys.issubset(a.keys())
        assert a["source"] in SOURCES
        assert a["category"] in CATEGORIES
        assert a["timestamp"].endswith("Z")


def test_hero_scenario():
    """Hero scenario (r.sharma) must contain 4 events within 6 hours."""
    alerts = generate_demo_alerts(seed=42)
    hero_alerts = [a for a in alerts if a.get("extra", {}).get("scenario") == "hero"]
    assert len(hero_alerts) == 4

    # Verify chronological sequence and details
    # 1. identity_provider / suspicious_login (Romania)
    # 2. dlp / mass_file_access (4,812 files)
    # 3. endpoint_av / malware (FILESRV-02, rclone.exe)
    # 4. firewall / data_exfiltration (~2.4 GB out)
    assert hero_alerts[0]["source"] == "identity_provider"
    assert hero_alerts[0]["category"] == "suspicious_login"
    assert hero_alerts[0]["extra"]["country"] == "Romania"
    assert hero_alerts[0]["extra"]["country_seen_before"] is False

    assert hero_alerts[1]["source"] == "dlp"
    assert hero_alerts[1]["category"] == "mass_file_access"
    assert hero_alerts[1]["extra"]["files_count"] == 4812

    assert hero_alerts[2]["source"] == "endpoint_av"
    assert hero_alerts[2]["category"] == "malware"
    assert hero_alerts[2]["host"] == "FILESRV-02"
    assert hero_alerts[2]["process"] == "rclone.exe"

    assert hero_alerts[3]["source"] == "firewall"
    assert hero_alerts[3]["category"] == "data_exfiltration"
    assert hero_alerts[3]["extra"]["bytes_out"] > 2_000_000_000

    # Overlapping entities
    for a in hero_alerts:
        assert a["user"] == "r.sharma"
    assert hero_alerts[1]["host"] == hero_alerts[2]["host"] == hero_alerts[3]["host"] == "FILESRV-02"
    assert hero_alerts[0]["src_ip"] == hero_alerts[1]["src_ip"] == hero_alerts[3]["src_ip"] == "185.220.101.5"

    # Time span must be under 6 hours (21,600 seconds)
    t0 = datetime.fromisoformat(hero_alerts[0]["timestamp"])
    t3 = datetime.fromisoformat(hero_alerts[3]["timestamp"])
    delta_seconds = (t3 - t0).total_seconds()
    assert 0 < delta_seconds <= 6 * 3600
    assert delta_seconds == 8700  # Exactly 2h 25m


def test_scenario_b_phishing():
    """Scenario B: a.menon phishing-to-compromise sequence."""
    alerts = generate_demo_alerts(seed=42)
    phish_alerts = [a for a in alerts if a.get("extra", {}).get("scenario") == "phishing"]
    assert len(phish_alerts) == 3

    assert phish_alerts[0]["source"] == "email_security"
    assert phish_alerts[0]["category"] == "phishing"

    assert phish_alerts[1]["source"] == "identity_provider"
    assert phish_alerts[1]["category"] == "suspicious_login"

    assert phish_alerts[2]["source"] == "cloud_audit"
    assert phish_alerts[2]["category"] == "mailbox_rule_change"

    for a in phish_alerts:
        assert a["user"] == "a.menon"


def test_scenario_c_ransomware():
    """Scenario C: WS-ACCTS-07 ransomware sequence."""
    alerts = generate_demo_alerts(seed=42)
    rw_alerts = [a for a in alerts if a.get("extra", {}).get("scenario") == "ransomware"]
    assert len(rw_alerts) == 3

    assert rw_alerts[0]["source"] == "endpoint_av"
    assert rw_alerts[0]["category"] == "malware"
    assert rw_alerts[0]["process"] == "vssadmin.exe"

    assert rw_alerts[1]["source"] == "endpoint_av"
    assert rw_alerts[1]["category"] == "ransomware_behaviour"
    assert rw_alerts[1]["extra"]["renamed_count"] == 1250

    assert rw_alerts[2]["source"] == "cloud_audit"
    assert rw_alerts[2]["category"] == "backup_activity"
    assert rw_alerts[2]["extra"]["action"] == "delete"

    for a in rw_alerts:
        assert a["host"] == "WS-ACCTS-07"


def test_scenario_d_decoy():
    """Scenario D: Decoy port scan and unrelated failed login hours apart."""
    alerts = generate_demo_alerts(seed=42)
    decoy_alerts = [a for a in alerts if a.get("extra", {}).get("scenario") == "decoy"]
    assert len(decoy_alerts) == 2

    assert decoy_alerts[0]["source"] == "firewall"
    assert decoy_alerts[0]["category"] == "port_scan"
    assert decoy_alerts[0]["severity"] == "low"

    assert decoy_alerts[1]["source"] == "identity_provider"
    assert decoy_alerts[1]["category"] == "failed_login"
    assert decoy_alerts[1]["user"] == "p.iyer"
    assert decoy_alerts[1]["severity"] == "low"

    # Must be hours apart
    t0 = datetime.fromisoformat(decoy_alerts[0]["timestamp"])
    t1 = datetime.fromisoformat(decoy_alerts[1]["timestamp"])
    assert (t1 - t0).total_seconds() > 10 * 3600


def test_benign_coverage():
    """Ensure noisy/benign alert types are present in expected volumes."""
    alerts = generate_demo_alerts(seed=42)
    benign_types = {a.get("extra", {}).get("benign_type") for a in alerts}
    assert "scanner" in benign_types
    assert "scheduled_backup" in benign_types
    assert "edr_info" in benign_types
    assert "duplicate_repeat" in benign_types
    assert "known_country_login" in benign_types
    assert "test_host" in benign_types

    # TEST-* host check
    test_host_alerts = [a for a in alerts if a.get("host", "") and a["host"].startswith("TEST-")]
    assert len(test_host_alerts) >= 50

    # country_seen_before check
    seen_countries = [a for a in alerts if a.get("extra", {}).get("country_seen_before") is True]
    assert len(seen_countries) >= 50


def test_cli_execution(tmp_path: Path):
    """Test CLI execution with --seed and --out flags in both modes."""
    # 1. From workspace root as backend.demo_data.generate
    out_file1 = tmp_path / "test_demo1.json"
    cmd1 = [
        sys.executable,
        "-m",
        "backend.demo_data.generate",
        "--seed",
        "42",
        "--out",
        str(out_file1),
    ]
    result1 = subprocess.run(cmd1, capture_output=True, text=True, check=True)
    assert "Successfully generated" in result1.stdout
    assert out_file1.exists()

    # 2. From backend directory as demo_data.generate
    out_file2 = tmp_path / "test_demo2.json"
    cmd2 = [
        sys.executable,
        "-m",
        "demo_data.generate",
        "--seed",
        "42",
        "--out",
        str(out_file2),
    ]
    backend_dir = Path(__file__).resolve().parent.parent.parent
    result2 = subprocess.run(cmd2, cwd=str(backend_dir), capture_output=True, text=True, check=True)
    assert "Successfully generated" in result2.stdout
    assert out_file2.exists()

    with open(out_file1, encoding="utf-8") as f1, open(out_file2, encoding="utf-8") as f2:
        data1 = json.load(f1)
        data2 = json.load(f2)
    assert data1 == data2
    assert len(data1) >= 380
