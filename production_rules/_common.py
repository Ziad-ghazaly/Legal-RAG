"""Shared helpers for production-rule checks: env config, DB, reporting."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # dotenv optional
    pass

REPORT_DIR = Path(os.getenv("RULES_REPORT_DIR", Path(__file__).parent / "reports"))


def env(name: str, default: str | None = None, required: bool = True) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        print(f"[config] missing required env var: {name}", file=sys.stderr)
        sys.exit(2)
    return val  # type: ignore[return-value]


def db_connect():
    import psycopg

    return psycopg.connect(env("DATABASE_URL"), autocommit=True)


@dataclass
class CheckResult:
    name: str
    passed: bool
    value: Any = None
    threshold: Any = None
    detail: str = ""


@dataclass
class Report:
    rule: str
    results: list[CheckResult] = field(default_factory=list)

    def add(self, name: str, passed: bool, value: Any = None, threshold: Any = None, detail: str = "") -> None:
        self.results.append(CheckResult(name, bool(passed), value, threshold, detail))
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}: value={value} threshold={threshold} {detail}")

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results)

    def write(self, extra: dict | None = None) -> Path:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        base = REPORT_DIR / f"{self.rule}_{ts}"
        payload = {
            "rule": self.rule,
            "timestamp_utc": ts,
            "passed": self.passed,
            "results": [r.__dict__ for r in self.results],
            **(extra or {}),
        }
        base.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        lines = [f"# {self.rule} — {'PASS' if self.passed else 'FAIL'} ({ts})", "", "| Check | Result | Value | Threshold | Detail |", "|---|---|---|---|---|"]
        for r in self.results:
            lines.append(f"| {r.name} | {'PASS' if r.passed else 'FAIL'} | {r.value} | {r.threshold} | {r.detail} |")
        base.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nReport: {base}.json / .md")
        return base

    def exit(self) -> None:
        sys.exit(0 if self.passed else 1)
