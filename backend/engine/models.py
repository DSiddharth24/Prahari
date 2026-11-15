"""
engine/models.py
ORM models for Prahari.

Shared vocabularies (section 6 of the context document):
  source:        email_security | endpoint_av | firewall | identity_provider | cloud_audit | dlp
  category:      suspicious_login | failed_login | malware | data_exfiltration |
                 mass_file_access | privilege_change | phishing | mailbox_rule_change |
                 port_scan | ransomware_behaviour | backup_activity | informational
  severity_raw:  low | medium | high | critical
  case severity: low (<35) | medium (35-59) | high (60-79) | critical (>=80)
  case status:   open | confirmed | dismissed | escalated | reported
  alert status:  new | suppressed_benign | merged_duplicate | in_case | unlinked_low_priority
  pattern:       account_takeover_then_exfiltration | ransomware_behaviour |
                 phishing_to_compromise | recon_then_access
  report status: draft | approved | submitted_manually
"""

import json
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, ForeignKey, Boolean
)
from sqlalchemy.orm import relationship

from .db import Base


def _now_utc():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Alert
# ---------------------------------------------------------------------------

class Alert(Base):
    __tablename__ = "alerts"

    id                 = Column(Integer, primary_key=True, autoincrement=True)

    # provenance
    source             = Column(String(64),  nullable=False)
    source_alert_id    = Column(String(256), nullable=False)

    # core fields
    timestamp          = Column(DateTime(timezone=True), nullable=False)
    title              = Column(String(512), nullable=False)
    description        = Column(Text,        nullable=True)
    severity_raw       = Column(String(16),  nullable=True)   # low|medium|high|critical
    category           = Column(String(64),  nullable=True)

    # optional entities
    user               = Column(String(128), nullable=True)
    host               = Column(String(128), nullable=True)
    src_ip             = Column(String(64),  nullable=True)
    dst_ip             = Column(String(64),  nullable=True)
    file               = Column(String(512), nullable=True)
    process            = Column(String(256), nullable=True)

    # original payload (JSON text)
    raw                = Column(Text, nullable=True)

    # pipeline state
    status             = Column(String(32), nullable=False, default="new")
    suppression_reason = Column(Text,       nullable=True)
    duplicate_of       = Column(Integer, ForeignKey("alerts.id"), nullable=True)
    duplicate_count    = Column(Integer, nullable=False, default=0)

    # ingestion timestamp
    ingested_at        = Column(DateTime(timezone=True), nullable=False, default=_now_utc)

    # relationships
    case_links         = relationship("CaseAlertLink", back_populates="alert")

    # -----------------------------------------------------------------
    # helpers
    # -----------------------------------------------------------------

    @property
    def extra(self):
        """Deserialise the JSON stored in `raw` and return only the `extra` dict."""
        if not self.raw:
            return {}
        try:
            data = json.loads(self.raw)
            return data.get("extra", {}) or {}
        except Exception:
            return {}

    def to_dict(self):
        return {
            "id":                 self.id,
            "source":             self.source,
            "source_alert_id":    self.source_alert_id,
            "timestamp":          self.timestamp.isoformat() if self.timestamp else None,
            "title":              self.title,
            "description":        self.description,
            "severity_raw":       self.severity_raw,
            "category":           self.category,
            "user":               self.user,
            "host":               self.host,
            "src_ip":             self.src_ip,
            "dst_ip":             self.dst_ip,
            "file":               self.file,
            "process":            self.process,
            "status":             self.status,
            "suppression_reason": self.suppression_reason,
            "duplicate_of":       self.duplicate_of,
            "duplicate_count":    self.duplicate_count,
            "extra":              self.extra,
            "ingested_at":        self.ingested_at.isoformat() if self.ingested_at else None,
        }


# ---------------------------------------------------------------------------
# Case
# ---------------------------------------------------------------------------

class Case(Base):
    __tablename__ = "cases"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    title               = Column(String(512), nullable=False)
    created_at          = Column(DateTime(timezone=True), nullable=False, default=_now_utc)
    first_alert_at      = Column(DateTime(timezone=True), nullable=True)
    last_alert_at       = Column(DateTime(timezone=True), nullable=True)
    detected_at         = Column(DateTime(timezone=True), nullable=True)   # defaults to created_at

    # scoring
    pattern             = Column(String(64),  nullable=True)
    score               = Column(Float,       nullable=False, default=0.0)
    score_breakdown_raw = Column(Text,        nullable=True)  # JSON: [{factor, points, explanation}]
    severity            = Column(String(16),  nullable=False, default="low")

    # analyst-facing content
    summary             = Column(Text, nullable=True)
    summary_source      = Column(String(16), nullable=True)  # "llm" | "template"
    recommended_actions_raw = Column(Text, nullable=True)    # JSON list of strings

    # workflow
    status              = Column(String(32), nullable=False, default="open")
    report_id           = Column(Integer, ForeignKey("reports.id"), nullable=True)

    # relationships
    alert_links         = relationship("CaseAlertLink", back_populates="case",
                                       cascade="all, delete-orphan")
    report              = relationship(
        "Report",
        primaryjoin="Case.report_id == Report.id",
        foreign_keys="[Case.report_id]",
        uselist=False,
    )

    # -----------------------------------------------------------------
    # computed helpers
    # -----------------------------------------------------------------

    @property
    def score_breakdown(self):
        if not self.score_breakdown_raw:
            return []
        try:
            return json.loads(self.score_breakdown_raw)
        except Exception:
            return []

    @score_breakdown.setter
    def score_breakdown(self, value):
        self.score_breakdown_raw = json.dumps(value)

    @property
    def recommended_actions(self):
        if not self.recommended_actions_raw:
            return []
        try:
            return json.loads(self.recommended_actions_raw)
        except Exception:
            return []

    @recommended_actions.setter
    def recommended_actions(self, value):
        self.recommended_actions_raw = json.dumps(value)

    @property
    def entities(self):
        """Aggregate entity lists from linked alerts."""
        users, hosts, ips = set(), set(), set()
        for link in self.alert_links:
            a = link.alert
            if a:
                if a.user:   users.add(a.user)
                if a.host:   hosts.add(a.host)
                if a.src_ip: ips.add(a.src_ip)
                if a.dst_ip: ips.add(a.dst_ip)
        return {"users": sorted(users), "hosts": sorted(hosts), "ips": sorted(ips)}

    @property
    def sources_count(self):
        sources = {link.alert.source for link in self.alert_links if link.alert}
        return len(sources)

    @property
    def deadline_at(self):
        from datetime import timedelta, timezone
        base = self.detected_at or self.created_at
        if base is None:
            return None
        # SQLite may return naive datetimes; treat as UTC
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        return base + timedelta(hours=6)

    @property
    def seconds_remaining(self):
        from datetime import timezone
        dl = self.deadline_at
        if dl is None:
            return None
        now = datetime.now(timezone.utc)
        delta = (dl - now).total_seconds()
        return int(delta)

    @property
    def countdown_state(self):
        if self.status in ("dismissed", "reported"):
            return "none"
        secs = self.seconds_remaining
        if secs is None:
            return "none"
        if secs > 10800:   # > 3 h
            return "green"
        if secs > 3600:    # 1–3 h
            return "amber"
        if secs > 0:       # < 1 h
            return "red"
        return "overdue"

    def to_list_item(self):
        return {
            "id":               self.id,
            "title":            self.title,
            "score":            self.score,
            "severity":         self.severity,
            "status":           self.status,
            "pattern":          self.pattern,
            "sources_count":    self.sources_count,
            "first_alert_at":   self.first_alert_at.isoformat() if self.first_alert_at else None,
            "detected_at":      self.detected_at.isoformat()    if self.detected_at    else None,
            "deadline_at":      self.deadline_at.isoformat()    if self.deadline_at    else None,
            "seconds_remaining": self.seconds_remaining,
            "countdown_state":  self.countdown_state,
        }

    def to_detail(self):
        d = self.to_list_item()
        d.update({
            "summary":             self.summary,
            "summary_source":      self.summary_source,
            "recommended_actions": self.recommended_actions,
            "score_breakdown":     self.score_breakdown,
            "timeline": [
                link.alert.to_dict()
                for link in sorted(self.alert_links,
                                   key=lambda lk: lk.alert.timestamp if lk.alert else _now_utc())
                if link.alert
            ],
            "entities":  self.entities,
            "report_id": self.report_id,
        })
        return d


# ---------------------------------------------------------------------------
# CaseAlertLink  (many-to-many)
# ---------------------------------------------------------------------------

class CaseAlertLink(Base):
    __tablename__ = "case_alert_links"

    id       = Column(Integer, primary_key=True, autoincrement=True)
    case_id  = Column(Integer, ForeignKey("cases.id"),  nullable=False)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)

    case  = relationship("Case",  back_populates="alert_links")
    alert = relationship("Alert", back_populates="case_links")


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

class Report(Base):
    __tablename__ = "reports"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    case_id       = Column(Integer, ForeignKey("cases.id"), nullable=False)
    incident_type = Column(String(128), nullable=True)
    fields_raw    = Column(Text, nullable=True)   # JSON dict  (see section 7.5)
    narrative     = Column(Text, nullable=True)
    generated_at  = Column(DateTime(timezone=True), nullable=False, default=_now_utc)
    status        = Column(String(32), nullable=False, default="draft")  # draft|approved|submitted_manually
    version       = Column(Integer, nullable=False, default=1)

    # Back-reference to the case that owns this report (one Report → one Case via case_id)
    case          = relationship(
        "Case",
        primaryjoin="Report.case_id == Case.id",
        foreign_keys="[Report.case_id]",
        uselist=False,
    )

    @property
    def fields(self):
        if not self.fields_raw:
            return {}
        try:
            return json.loads(self.fields_raw)
        except Exception:
            return {}

    @fields.setter
    def fields(self, value):
        self.fields_raw = json.dumps(value)

    def to_dict(self, history=None):
        fields_data = self.fields or {}
        # history is stored inside fields_raw under the "_history" key for the real engine
        extracted_history = fields_data.pop("_history", []) if isinstance(fields_data, dict) else []
        if history is None:
            history = extracted_history
        d = {
            "id":            self.id,
            "case_id":       self.case_id,
            "incident_type": self.incident_type,
            "fields":        fields_data,
            "narrative":     self.narrative,
            "generated_at":  self.generated_at.isoformat() if self.generated_at and hasattr(self.generated_at, 'isoformat') else self.generated_at,
            "status":        self.status,
            "version":       self.version,
        }
        if history is not None:
            d["history"] = history
        return d


# ---------------------------------------------------------------------------
# AuditEvent  (append-only)
# ---------------------------------------------------------------------------

class AuditEvent(Base):
    __tablename__ = "audit_events"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    timestamp   = Column(DateTime(timezone=True), nullable=False, default=_now_utc)
    actor       = Column(String(128), nullable=False)
    action      = Column(String(64),  nullable=False)
    target_type = Column(String(64),  nullable=True)
    target_id   = Column(String(64),  nullable=True)
    details_raw = Column(Text,        nullable=True)  # JSON

    @property
    def details(self):
        if not self.details_raw:
            return None
        try:
            return json.loads(self.details_raw)
        except Exception:
            return self.details_raw

    def to_dict(self):
        return {
            "id":          self.id,
            "timestamp":   self.timestamp.isoformat() if self.timestamp else None,
            "actor":       self.actor,
            "action":      self.action,
            "target_type": self.target_type,
            "target_id":   self.target_id,
            "details":     self.details,
        }
