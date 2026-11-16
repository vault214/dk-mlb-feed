#!/usr/bin/env python3
"""Regression checks for source-reported claims vs forward-only paper performance."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("build_capper_consensus.py")
spec = importlib.util.spec_from_file_location("capper_builder", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

POLICY = {
    "minSettledPicksPerSport": 200,
    "requirePositiveAuditedROI": True,
    "requireMultiSeasonRecord": True,
    "requireConsistentSubperiods": True,
    "requireTimestampedPregamePicks": True,
}
FULL_AUDIT = {
    "sourceType": "INDEPENDENT_FULL_LEDGER",
    "independentAudit": True,
    "auditUrl": "https://example.com/audit",
    "settledPicks": 300,
    "roiPct": 3.2,
    "seasons": ["2024", "2025"],
    "nonoverlappingPeriods": [{"roiPct": 1.2}, {"roiPct": 4.7}],
    "allPicksPregameTimestamped": True,
}

class QualificationTests(unittest.TestCase):
    def test_claims_are_not_qualification(self):
        reported = FULL_AUDIT | {"sourceType": "PUBLISHER_REPORTED"}
        self.assertFalse(mod.qualify(reported, POLICY))
        self.assertFalse(mod.qualify(None, POLICY))

    def test_qualifying_evidence_must_be_independent_and_consistent(self):
        self.assertTrue(mod.qualify(FULL_AUDIT, POLICY))
        for bad in (
            {"roiPct": -0.1},
            {"settledPicks": 199},
            {"seasons": ["2025"]},
            {"nonoverlappingPeriods": [{"roiPct": 5}, {"roiPct": -1}]},
            {"allPicksPregameTimestamped": False},
            {"independentAudit": False},
            {"auditUrl": "http://not-secure"},
        ):
            self.assertFalse(mod.qualify(FULL_AUDIT | bad, POLICY), bad)

    def test_paper_units_price_aware(self):
        self.assertAlmostEqual(mod.paper_profit(-115, "WIN"), 100 / 115, places=5)
        self.assertEqual(mod.paper_profit(140, "WIN"), 1.4)
        self.assertEqual(mod.paper_profit(-120, "LOSS"), -1)
        self.assertEqual(mod.paper_profit(-120, "PUSH"), 0)
        self.assertIsNone(mod.paper_profit(-120, "PENDING"))

    def test_previous_sample_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            files = {
                "OUTPUT": {"schemaVersion": 2, "cappers": [], "picks": [{"id":"old"}]},
                "INPUT": {"submissions": []},
                "QUAL": {"policy": POLICY, "roster": [{"id":"koerner","name":"Sean Koerner","handle":"@The_Oddsmaker","role":"PRIMARY_BENCHMARK","sports":["NFL"]}], "independentlyAuditedRecords":[]},
                "ARCHIVE": {"picks":[{"id":"old"}]},
            }
            saved = {}
            try:
                for key, value in files.items():
                    saved[key] = getattr(mod, key)
                    path = root / (key.lower() + ".json")
                    path.write_text(json.dumps(value))
                    setattr(mod, key, path)
                mod.build()
                output = json.loads(mod.OUTPUT.read_text())
                self.assertEqual(output["picks"], [])
                self.assertEqual(output["qualificationsBySport"]["koerner:NFL"], "NOT_YET_QUALIFIED")
            finally:
                for key, value in saved.items():
                    setattr(mod, key, value)

if __name__ == "__main__":
    unittest.main()
