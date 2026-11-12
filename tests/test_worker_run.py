from datetime import datetime, timezone
import json
import re
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import worker_run as worker
from worker_schedule import publication_target

NOW=datetime(2026,11,11,14,tzinfo=timezone.utc)


class WorkerRunTests(unittest.TestCase):
    def test_new_target_week_evidence_reopens_the_worker_without_unrelated_backfill(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); folder = root/'data/weekly-preparation/2026-11-02'
            folder.mkdir(parents=True); (root/'scripts').mkdir()
            for name in ('prepared_article_readings.py', 'comprehensive_readings.py',
                         'reading_progress.py', 'preparation_pipeline.py', 'worker_run.py'):
                shutil.copyfile(Path(worker.__file__).parent/name, root/'scripts'/name)
            packet = {'target_publication_window': {'from':'2026-11-02','to':'2026-11-08','timezone':'UTC'}, 'items':[]}
            (folder/'packet.json').write_text(json.dumps(packet))
            # A first pass must also work before acquisition/readings files exist.
            (root/'data/weekly.json').write_text(json.dumps({'items':[]}))
            library = [{'url':'https://example.org/current','published':'2026-11-05','title':'Current'},
                       {'url':'https://example.org/old','published':'2025-01-01','title':'Old'}]
            def save(): (root/'data/library.json').write_text(json.dumps(library))
            save(); before = worker.input_hash(root, 'closed', NOW)
            library[1]['full_text'] = 'Historical backfill'; save()
            self.assertEqual(worker.input_hash(root, 'closed', NOW), before)
            library[0]['full_text'] = 'New target-week results'; save()
            self.assertNotEqual(worker.input_hash(root, 'closed', NOW), before)

    def test_workflow_cron_fields_fit_github_ranges(self):
        bounds = ((0,59),(0,23),(1,31),(1,12),(0,6))
        workflows = Path(__file__).resolve().parents[1]/'.github/workflows'
        for path in workflows.glob('*.yml'):
            for cron in re.findall(r"cron:\s*['\"]([^'\"]+)['\"]",path.read_text()):
                fields=cron.split()
                self.assertEqual(len(fields),5,(path,cron))
                for field,(low,high) in zip(fields,bounds):
                    for part in field.split(','):
                        span,*step=part.split('/')
                        if step:
                            self.assertGreater(int(step[0]),0,(path,cron))
                        if span=='*': continue
                        values=[int(v) for v in span.split('-')]
                        self.assertTrue(all(low<=v<=high for v in values),(path,cron))
                        self.assertEqual(values,sorted(values),(path,cron))

    def test_token_saved_privately_and_not_printed_or_returned(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'lease.json'
            store=Mock()
            store._call.return_value={'claimed':True,'id':'a'*8+'-'+'a'*4+'-'+'a'*4+'-'+'a'*4+'-'+'a'*12,
                                      'lease_token':'b'*8+'-'+'b'*4+'-'+'b'*4+'-'+'b'*4+'-'+'b'*12}
            with patch.object(worker,'input_hash',return_value='a'*64):
                result=worker.begin(Path(tmp),'closed',file,store,NOW)
            self.assertNotIn('lease_token',result)
            self.assertIn('lease_token',json.loads(file.read_text()))
            self.assertEqual(file.stat().st_mode & 0o777,0o600)
            self.assertEqual(store._call.call_args.kwargs['week'],'2026-11-02')

    def test_busy_worker_does_not_create_a_lease_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'lease.json';store=Mock()
            store._call.return_value={'claimed':False,'reason':'another_worker_running'}
            with patch.object(worker,'input_hash',return_value='a'*64):
                self.assertFalse(worker.begin(Path(tmp),'closed',file,store,NOW)['claimed'])
            self.assertFalse(file.exists())

    def test_failed_save_is_a_retry_and_stale_completion_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'lease.json';file.write_text(json.dumps({'id':'job','lease_token':'token'}))
            store=Mock();store._call.return_value={'saved':True}
            result=worker.finish(Path(tmp),file,store,False,'',NOW)
            self.assertEqual(store._call.call_args.args,('fail_run',))
            self.assertFalse(result['weekly_publication_verified'])
            store._call.return_value={'saved':False}
            with self.assertRaisesRegex(ValueError,'expired_or_replaced'):
                worker.finish(Path(tmp),file,store,False,'',NOW)

    def test_target_follows_dst_and_keeps_original_week_in_utc(self):
        summer=publication_target(datetime(2026,7,6,15,tzinfo=timezone.utc))
        winter=publication_target(datetime(2026,11,9,18,tzinfo=timezone.utc))
        self.assertEqual(summer['target_at'],'2026-07-06T12:00:00-04:00')
        self.assertEqual(winter['target_at'],'2026-11-09T12:00:00-05:00')
        self.assertFalse(summer['deadline_elapsed']);self.assertTrue(winter['deadline_elapsed'])
        self.assertEqual(winter['source_window'],{'from':'2026-11-02','to':'2026-11-08','timezone':'UTC'})
        sunday=publication_target(datetime(2026,11,9,1,tzinfo=timezone.utc))
        self.assertEqual(sunday['target_collection_week'],'2026-11-09')
        self.assertFalse(sunday['deadline_elapsed'])


if __name__=='__main__':unittest.main()
