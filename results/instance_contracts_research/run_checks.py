"""Run existing in-process contract checks with a cold-import research prototype."""
import json
from pathlib import Path
import runpy
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
mode=sys.argv[1]
runpy.run_path(str(OUT/'probe.py'),run_name='prototype_setup')
sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'src')]
names=[
    'test_contracts_compatibility',
    'test_p4_new_families.P43ConfigurationAndPairingTests.test_instance_records_freeze_p4_3_provenance_and_round_trip',
    'test_p4_new_families.P43ConfigurationAndPairingTests.test_instance_records_reject_invalid_p4_3_parameters',
    'test_p4_new_families.P43ConfigurationAndPairingTests.test_unique_fixed_size_record_requires_unique_measured_sets',
    'test_p4_new_families.P43ConfigurationAndPairingTests.test_disjoint_anchor_proof_is_rejected_for_other_families',
    'test_p4_new_families.P43ConfigurationAndPairingTests.test_mixed_cluster_record_accepts_only_referenced_small_clusters',
    'test_p4_adversarial.AdversarialSeverityIntegrationTests.test_instance_record_rejects_non_integer_construction_version',
    'test_p4_adversarial.LegacyAdversarialCompatibilityTests',
]

if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    (OUT/(mode+'-existing-tests.json')).write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),
        'errors':len(result.errors),'skipped':len(result.skipped),'success':result.wasSuccessful()}),encoding='utf-8')
    raise SystemExit(not result.wasSuccessful())
