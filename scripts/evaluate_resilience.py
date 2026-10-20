"""Reproducible offline system/adversarial evaluation. Never enables paid calls."""
import argparse
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
REPORT=ROOT/'docs/evaluation-resilience.json'


def fingerprints():
    files=[*ROOT.glob('*.py'),*(ROOT/'scripts').glob('*.py'),*(ROOT/'tests').glob('test_*.py')]
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        for p in sorted(files)}


def run(check=False):
    if check:
        saved=json.loads(REPORT.read_text(encoding='utf-8'))
        if saved['fingerprints']!=fingerprints():raise SystemExit('Resilience record is stale; rerun offline evaluation')
        if not saved['successful']:raise SystemExit('Recorded resilience run contains failures')
        print('Recorded resilience suite fingerprints match; zero inference.');return
    os.environ['MESH_ENABLE_PAID']='0'
    os.environ['MESH_ENABLE_MEDIA_PAID']='0'
    os.environ['MESH_API_KEY']='offline-validation-no-usable-key'
    temp=ROOT/'data/evaluation-test-tmp';temp.mkdir(parents=True,exist_ok=True)
    os.environ['TEMP']=os.environ['TMP']=str(temp)
    import httpx
    class Results(unittest.TextTestResult):
        def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.rows=[]
        def addSuccess(self,test):super().addSuccess(test);self.rows.append(dict(test=test.id(),status='passed'))
        def addFailure(self,test,err):super().addFailure(test,err);self.rows.append(dict(test=test.id(),status='failed'))
        def addError(self,test,err):super().addError(test,err);self.rows.append(dict(test=test.id(),status='error'))
        def addSkip(self,test,reason):super().addSkip(test,reason);self.rows.append(dict(test=test.id(),status='skipped',reason=reason))
        def addSubTest(self,test,subtest,err):
            super().addSubTest(test,subtest,err)
            if err:self.rows.append(dict(test=str(subtest),status='failed_subtest'))
    # MockTransport and in-process FastAPI TestClient still work. Any accidental
    # request through a normal httpx network transport fails before network I/O.
    output=io.StringIO();stream=io.StringIO()
    with patch.object(httpx.HTTPTransport,'handle_request',side_effect=AssertionError('External HTTP disabled in offline evaluation')), \
         patch.object(httpx.AsyncHTTPTransport,'handle_async_request',side_effect=AssertionError('External HTTP disabled in offline evaluation')), \
         redirect_stdout(output),redirect_stderr(output):
        suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),top_level_dir=str(ROOT))
        result=unittest.TextTestRunner(stream=stream,resultclass=Results,verbosity=1).run(suite)
    grounding=json.loads((ROOT/'docs/evaluation-grounding.json').read_text(encoding='utf-8'))
    report=dict(evaluated_at=datetime.now(timezone.utc).isoformat(),evaluation='offline-system-and-adversarial-v1',
        successful=result.wasSuccessful(),tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        adversarial_tests=sum('test_adversarial_' in r['test'] and r['status']=='passed' for r in result.rows),
        ai_calls=0,spend_usd=0,network_policy='Normal httpx transports blocked; scripted agents and mocked provider transports only.',
        cases=result.rows,fingerprints=fingerprints(),
        grounding_fixture_metrics=grounding['after']['metrics'],unsupported_grounding_fixtures_remaining=grounding['after']['unsupported_claims'],
        limitations=['Passing deterministic contracts is not a live model quality or factuality score.',
            'Nonnumeric assertion discovery and semantic entailment still depend on the model.',
            'No public posting, OAuth authorization, real platform analytics or paid Mesh inference ran.',
            'Tests use isolated synthetic records; customer databases and brand samples are not evaluation fixtures.',
            'Client budget locks and reservations do not replace provider-side spending controls.'])
    REPORT.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('successful','tests_run','adversarial_tests','failures','errors','skipped','ai_calls','spend_usd')}))
    if not result.wasSuccessful():
        print(stream.getvalue());raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--check-recorded',action='store_true')
    run(parser.parse_args().check_recorded)
