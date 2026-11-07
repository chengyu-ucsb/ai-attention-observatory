import datetime as dt
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import xml.etree.ElementTree as ET
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import editorial_feed_cache as cache
import discover_editorial as ed

NOW = dt.datetime(2026, 11, 4, 12, tzinfo=dt.timezone.utc)
NEXT_WEEK = dt.datetime(2026, 11, 9, 12, tzinfo=dt.timezone.utc)
FEED = {'id':'one','name':'Example','url':'https://example.org/feed','article_hosts':['example.org'], 'source_type':'journalism'}


def rss(day='2026-11-03', slug='article', next_url=''):
    nxt = f'<atom:link rel="next" href="{next_url}"/>' if next_url else ''
    return ET.fromstring(f'''<rss xmlns:atom="http://www.w3.org/2005/Atom"><channel><item>
    <title>AI and human attention in learning</title><link>https://example.org/{slug}</link>
    <pubDate>{day}</pubDate><description>Artificial intelligence changes learning, attention and cognitive offloading. PRIVATE SOURCE BODY MUST NOT BE SAVED.</description>
    <category>Analysis</category></item>{nxt}</channel></rss>''')


def capture(state=None, root=None, now=NOW, **kwargs):
    return cache.capture(state, feeds=[FEED], now=now, fetcher=lambda _: root if root is not None else rss(), **kwargs)


class FeedCacheTests(unittest.TestCase):
    def test_current_week_metadata_waits_until_next_week(self):
        state, report = capture()
        self.assertEqual(len(state['sources']['one']['items']), 1)
        self.assertEqual(cache.candidate_items(state, [FEED], now=NOW)['one'], [])
        selected = cache.candidate_items(state, [FEED], now=NEXT_WEEK)['one']
        self.assertEqual(selected[0]['date'], '2026-11-03')
        self.assertEqual(selected[0]['description'], '')
        self.assertIn('No current-week articles retrieved', report['scope'])

    def test_cache_contains_no_source_body_or_description(self):
        state, _ = capture()
        serialized = json.dumps(state)
        self.assertNotIn('PRIVATE SOURCE BODY', serialized)
        self.assertNotIn('description', serialized)
        self.assertNotIn('overview', serialized)
        self.assertEqual(state['sources']['one']['items'][0]['categories'], ['Analysis'])

    def test_older_than_target_week_not_promoted(self):
        state, _ = capture(root=rss('2026-10-28'))
        self.assertEqual(cache.candidate_items(state, [FEED], now=NEXT_WEEK)['one'], [])

    def test_unknown_and_updated_only_dates_not_staged(self):
        root = ET.fromstring('''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
        <title>AI and attention in learning</title><link href="https://example.org/a"/>
        <updated>2026-11-03T00:00:00Z</updated><summary>AI attention and learning</summary></entry></feed>''')
        self.assertEqual(capture(root=root)[0]['sources']['one']['items'], [])

    def test_contradictory_dates_are_preserved_not_overwritten(self):
        state, _ = capture(root=rss('2026-11-03'))
        state, _ = capture(state, root=rss('2026-11-02'), now=NOW+dt.timedelta(hours=6))
        self.assertEqual({x['date'] for x in state['sources']['one']['items']}, {'2026-11-02','2026-11-03'})
        candidates = cache.candidate_items(state, [FEED], now=NEXT_WEEK)
        added, status, _ = ed.collect([], now=NEXT_WEEK, feeds=[FEED], searches=[],
            fetcher=lambda _: ET.fromstring('<rss><channel/></rss>'), sleep=lambda _:None,
            cached_items=candidates)
        self.assertEqual(status['accepted'], 0)
        self.assertEqual(added[0]['publication_date_provenance']['status'], 'unresolved')

    def test_outside_window_conflicting_evidence_is_not_filtered_away(self):
        state,_=capture(root=rss('2026-11-03'))
        state,_=capture(state,root=rss('2026-10-31'),now=NOW+dt.timedelta(hours=6))
        candidates=cache.candidate_items(state,[FEED],now=NEXT_WEEK)
        self.assertEqual({x['date'] for x in candidates['one']},{'2026-11-03','2026-10-31'})
        added,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],
            cached_items=candidates,live=False,sleep=lambda _:None)
        self.assertEqual(status['accepted'],0)
        self.assertEqual(added[0]['publication_date_provenance']['status'],'unresolved')
        self.assertEqual(status['sources'][0]['cached_candidates'],1)
        self.assertEqual(status['sources'][0]['cached_evidence_rows'],2)

    def test_cross_feed_date_conflict_is_preserved_globally(self):
        second=dict(FEED,id='two',url='https://example.org/opinion-feed')
        pages={FEED['url']:rss('2026-11-03'),second['url']:rss('2026-10-31')}
        state,_=cache.capture(feeds=[FEED,second],now=NOW,fetcher=pages.__getitem__)
        selected=cache.candidate_items(state,[FEED,second],now=NEXT_WEEK)
        self.assertEqual(len(selected['two']),1)
        added,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED,second],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
        self.assertEqual(status['accepted'],0)
        self.assertEqual(added[0]['publication_date_provenance']['status'],'unresolved')

    def test_old_or_future_contradiction_retained_by_observation_date(self):
        for conflicting in ('2026-10-01','2027-01-01'):
            state,_=capture(root=rss('2026-11-03'))
            state,_=capture(state,root=rss(conflicting),now=NOW+dt.timedelta(hours=6))
            selected=cache.candidate_items(state,[FEED],now=NEXT_WEEK)
            self.assertEqual({x['date'] for x in selected['one']},{'2026-11-03',conflicting})
            _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
            self.assertEqual(status['accepted'],0)

    def test_known_url_date_correction_survives_changed_topic_preview(self):
        state,_=capture(root=rss('2026-11-03'))
        changed=ET.fromstring('<rss><channel><item><title>Renamed story</title><link>https://example.org/article</link>'
            '<pubDate>2026-10-01</pubDate><description>Short preview.</description></item></channel></rss>')
        state,_=capture(state,root=changed,now=NOW+dt.timedelta(hours=6))
        selected=cache.candidate_items(state,[FEED],now=NEXT_WEEK)
        self.assertEqual({x['date'] for x in selected['one']},{'2026-11-03','2026-10-01'})
        _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
        self.assertEqual(status['accepted'],0)

    def test_same_capture_conflict_does_not_depend_on_feed_or_page_order(self):
        second=dict(FEED,id='two',url='https://example.org/opinion-feed')
        changed=ET.fromstring('<rss><channel><item><title>Updated article</title><link>https://example.org/article</link>'
            '<pubDate>2026-10-31</pubDate><description>Short preview.</description></item></channel></rss>')
        for first, later in ((changed,rss()),(rss(),changed)):
            pages={FEED['url']:first,second['url']:later}
            snapshots=[]
            state,_=cache.capture(feeds=[FEED,second],now=NOW,fetcher=pages.__getitem__,
                checkpoint=lambda value:snapshots.append(json.loads(json.dumps(value))))
            selected=cache.candidate_items(state,[FEED,second],now=NEXT_WEEK)
            self.assertEqual({row['date'] for values in selected.values() for row in values},{'2026-10-31','2026-11-03'})
            _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED,second],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
            self.assertEqual(status['accepted'],0)
            self.assertEqual(snapshots[-1],state)

    def test_removed_and_mismatched_sources_still_require_metadata_only_schema(self):
        state,_=capture()
        for stale in ('removed','mismatch'):
            for where in ('source','item','http_status','retry_after'):
                bad=json.loads(json.dumps(state))
                source=bad['sources'].pop('one')
                bad['sources']['removed' if stale=='removed' else 'one']=source
                if stale=='mismatch':source['fingerprint']='0'*64
                if where=='source':source['article_body']='PRIVATE BODY'
                elif where=='item':source['items'][0]['article_body']='PRIVATE BODY'
                else:source[where]={'article_body':'PRIVATE BODY'}
                with self.subTest(stale=stale,where=where),self.assertRaises(ValueError):
                    cache.validate_state(bad,[FEED])
                with tempfile.TemporaryDirectory() as folder:
                    path=Path(folder)/'cache.json'
                    with self.assertRaises(ValueError):cache.save_cache(path,bad,[FEED])
                    self.assertFalse(path.exists())

    def test_removed_valid_source_not_served_and_pruned_next_capture(self):
        state,_=capture()
        state['sources']['removed']=state['sources'].pop('one')
        self.assertEqual(cache.candidate_items(state,[FEED],now=NEXT_WEEK),{})
        updated,_=capture(state)
        self.assertNotIn('removed',updated['sources'])

    def test_capacity_limit_cannot_erase_known_date_conflict(self):
        second=dict(FEED,id='two',url='https://example.org/opinion-feed')
        root=rss()
        root.find('channel').append(rss(slug='other').find('channel/item'))
        with patch.object(cache,'MAX_ITEMS',2):
            state,_=cache.capture(feeds=[FEED,second],now=NOW,fetcher=lambda _:root)
            state,_=cache.capture(state,feeds=[FEED,second],now=NOW+dt.timedelta(hours=6),fetcher=lambda _:rss('2026-10-31'))
            for source in state['sources'].values():
                self.assertEqual(source['status'],'partial')
                row=next(row for row in source['items'] if row['url'].endswith('/article'))
                self.assertEqual(row['conflicting_dates'],['2026-10-31','2026-11-03'])
            selected=cache.candidate_items(state,[FEED,second],now=NEXT_WEEK)
            _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED,second],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
            self.assertEqual(status['accepted'],1)  # Only the unrelated article.
            state,_=cache.capture(state,feeds=[FEED,second],now=NOW+dt.timedelta(hours=12),fetcher=lambda _:rss())
            selected=cache.candidate_items(state,[FEED,second],now=NEXT_WEEK)
            _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED,second],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
            self.assertEqual(status['accepted'],1)
            existing=[ed.to_record(ed.parse_feed(rss())[0],FEED['name'],'article',feed=FEED,today=NOW.date())]
            _,status,_=ed.collect(existing,now=NEXT_WEEK,feeds=[FEED,second],searches=[],cached_items=selected,live=False,sleep=lambda _:None)
            updated=ed.apply_discovery_evidence(existing,status)
            self.assertEqual(updated[0]['publication_date_provenance']['status'],'unresolved')

    def test_budget_does_not_starve_later_feeds_on_resume(self):
        feeds=[dict(FEED,id=f'feed{i}',url=f'https://example.org/feed{i}') for i in range(3)]
        calls=[]
        def fetch(url):calls.append(url);return rss()
        state,_=cache.capture(feeds=feeds,now=NOW,fetcher=fetch,max_requests=1)
        state,_=cache.capture(state,feeds=feeds,now=NOW+dt.timedelta(hours=6),fetcher=fetch,max_requests=1)
        self.assertEqual(calls,[feeds[0]['url'],feeds[1]['url']])

    def test_unrepresentable_retry_after_is_not_shortened(self):
        error=HTTPError(FEED['url'],429,'limited',{'Retry-After':str(10**40)},None)
        value,_=cache.retry_time(error,NOW,1)
        self.assertEqual(value,dt.datetime.max.replace(tzinfo=dt.timezone.utc).isoformat())

    def test_exact_date_and_url_validation_before_reuse(self):
        state, _ = capture()
        state['sources']['one']['items'][0]['date'] = '2026-11-04'
        with self.assertRaises(ValueError):
            cache.candidate_items(state, [FEED], now=NEXT_WEEK)

    def test_unknown_fields_and_body_rejected(self):
        state, _ = capture()
        state['sources']['one']['items'][0]['description'] = 'Not allowed'
        with self.assertRaises(ValueError):
            cache.validate_state(state, [FEED])

    def test_foreign_article_url_rejected(self):
        state, _ = capture()
        state['sources']['one']['items'][0]['url'] = 'https://example.org.evil.test/a'
        with self.assertRaises(ValueError):
            cache.validate_state(state, [FEED])

    def test_changed_source_config_invalidates_cache(self):
        state, _ = capture()
        changed = dict(FEED, url='https://example.org/new-feed')
        self.assertEqual(cache.candidate_items(state, [changed], now=NEXT_WEEK), {})
        report = cache.coverage_report(state, [changed], now=NEXT_WEEK)
        self.assertEqual(report['one']['snapshots_during_publication_week'], 0)

    def test_retry_after_seconds_survives_process_restart(self):
        fail = Mock(side_effect=HTTPError(FEED['url'],429,'limited',{'Retry-After':'7200'},None))
        state, _ = cache.capture(feeds=[FEED],now=NOW,fetcher=fail)
        self.assertEqual(state['sources']['one']['next_retry_at'],(NOW+dt.timedelta(hours=2)).isoformat())
        no_call = Mock()
        state, report = cache.capture(state,feeds=[FEED],now=NOW+dt.timedelta(hours=1),fetcher=no_call)
        no_call.assert_not_called()
        self.assertEqual(report['sources'][0]['status'],'deferred_provider_pause')
        state, _ = cache.capture(state,feeds=[FEED],now=NOW+dt.timedelta(hours=3),fetcher=lambda _:rss())
        self.assertEqual(state['sources']['one']['status'],'ok')

    def test_retry_after_http_date(self):
        error = HTTPError(FEED['url'],429,'limited',{'Retry-After':'Wed, 04 Nov 2026 18:00:00 GMT'},None)
        value, _ = cache.retry_time(error,NOW,1)
        self.assertEqual(value,'2026-11-04T18:00:00+00:00')

    def test_access_refusal_not_automatically_retried(self):
        state, _ = cache.capture(feeds=[FEED],now=NOW,
            fetcher=Mock(side_effect=HTTPError(FEED['url'],403,'blocked',{},None)))
        no_call = Mock()
        _, report = cache.capture(state,feeds=[FEED],now=NOW+dt.timedelta(days=3),fetcher=no_call)
        no_call.assert_not_called()
        self.assertIsNone(report['sources'][0]['next_retry_at'])

    def test_one_host_pause_does_not_block_other_provider(self):
        other = dict(FEED,id='other',url='https://other.org/feed',article_hosts=['other.org'])
        calls=[]
        def fetch(url):
            calls.append(url)
            if url==FEED['url']:raise HTTPError(url,429,'limited',{},None)
            return ET.fromstring('<rss><channel/></rss>')
        state, _ = cache.capture(feeds=[FEED,other],now=NOW,fetcher=fetch)
        self.assertEqual(len(calls),2)
        self.assertEqual(state['sources']['other']['status'],'ok')

    def test_budget_continuation_resumes_older_page_after_root(self):
        p2='https://example.org/feed?page=2'
        pages={FEED['url']:rss('2026-11-03',next_url=p2),p2:rss('2026-11-02',slug='older')}
        state, _ = cache.capture(feeds=[FEED],now=NOW,fetcher=pages.__getitem__,max_requests=1)
        self.assertEqual(state['sources']['one']['continuation_url'],p2)
        self.assertEqual(state['sources']['one']['status'],'partial')
        calls=[]
        def fetch(url):calls.append(url);return pages[url]
        state, _ = cache.capture(state,feeds=[FEED],now=NOW+dt.timedelta(hours=6),fetcher=fetch,max_requests=3)
        self.assertEqual(calls,[FEED['url'],p2])
        self.assertEqual(len(state['sources']['one']['items']),2)

    def test_mutable_feed_does_not_skip_new_intermediate_page_entries(self):
        p2='https://example.org/feed?page=2'
        p3='https://example.org/feed?page=3'
        first={FEED['url']:rss('2026-11-03',next_url=p2),p2:rss('2026-11-02',slug='old-p2',next_url=p3)}
        state,_=cache.capture(feeds=[FEED],now=NOW,fetcher=first.__getitem__,max_requests=2)
        self.assertEqual(state['sources']['one']['continuation_url'],p3)
        second={FEED['url']:rss('2026-11-04',slug='new-root',next_url=p2),
                p2:rss('2026-11-03',slug='missed-new-p2',next_url=p3),p3:rss('2026-11-02',slug='old-p3')}
        calls=[]
        def fetch(url):calls.append(url);return second[url]
        state,_=cache.capture(state,feeds=[FEED],now=NOW+dt.timedelta(hours=6),fetcher=fetch,max_requests=3)
        self.assertEqual(calls,[FEED['url'],p2,p3])
        self.assertIn('https://example.org/missed-new-p2',{x['url'] for x in state['sources']['one']['items']})

    def test_credential_urls_not_staged_or_leaked_in_quarantine(self):
        root=rss(slug='article?api_key=SECRET_VALUE')
        state,_=capture(root=root)
        self.assertEqual(state['sources']['one']['items'],[])
        self.assertNotIn('SECRET_VALUE',json.dumps(state))
        _,_,quarantine=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],fetcher=lambda _:root,sleep=lambda _:None)
        self.assertNotIn('SECRET_VALUE',json.dumps(quarantine))
        self.assertEqual(quarantine[0]['url'],'https://example.org/article')
        self.assertTrue(ed.allowed_article('https://example.org/?article_id=123',FEED))

    def test_credential_continuation_rejected(self):
        root=rss(next_url='https://example.org/feed?token=SECRET_VALUE')
        state,_=capture(root=root)
        self.assertNotIn('SECRET_VALUE',json.dumps(state))
        self.assertEqual(state['sources']['one']['status'],'unavailable')

    def test_successful_candidate_survives_later_page_failure(self):
        root=rss(next_url='https://example.org/feed?page=2')
        def fetch(url):
            if 'page=2' in url:raise TimeoutError()
            return root
        state, _ = cache.capture(feeds=[FEED],now=NOW,fetcher=fetch)
        self.assertEqual(len(state['sources']['one']['items']),1)
        self.assertEqual(state['sources']['one']['status'],'unavailable')

    def test_no_false_historical_sampling_claim(self):
        state, _ = capture()
        report=cache.coverage_report(state,[FEED],now=NOW)['one']
        self.assertEqual(report['snapshots_during_publication_week'],0)
        self.assertEqual(report['largest_unobserved_interval_hours'],168)
        report=cache.coverage_report(state,[FEED],now=NEXT_WEEK)['one']
        self.assertEqual(report['snapshots_during_publication_week'],1)
        self.assertIn('not verified',report['coverage_claim'])

    def test_snapshot_candidates_survive_live_feed_outage(self):
        state, _ = capture()
        selected=cache.candidate_items(state,[FEED],now=NEXT_WEEK)
        added,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],
            cached_items=selected,fetcher=Mock(side_effect=TimeoutError()),sleep=lambda _:None)
        self.assertEqual(len(added),1)
        self.assertEqual(added[0]['published'],'2026-11-03')
        self.assertEqual(added[0]['reading']['level'],'citation_only')
        self.assertEqual(status['sources'][0]['status'],'failed')
        self.assertEqual(status['sources'][0]['cached_candidates'],1)

    def test_stale_feed_flagged_even_if_it_reaches_older_dates(self):
        _,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],searches=[],
            fetcher=lambda _:rss('2026-10-15'),sleep=lambda _:None)
        self.assertEqual(status['sources'][0]['status'],'partial')
        self.assertIn('newest_feed_entry_predates_publication_window',status['sources'][0]['warnings'])

    def test_cached_recovery_does_not_issue_network_requests(self):
        state,_=capture()
        no_call=Mock()
        selected=cache.candidate_items(state,[FEED],now=NEXT_WEEK)
        added,status,_=ed.collect([],now=NEXT_WEEK,feeds=[FEED],cached_items=selected,
            fetcher=no_call,sleep=lambda _:None,live=False)
        no_call.assert_not_called()
        self.assertEqual(len(added),1)
        self.assertEqual(status['status'],'partial')

    def test_atomic_save_load(self):
        state,_=capture()
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'cache.json'
            cache.save_cache(target,state,[FEED])
            self.assertEqual(cache.load_cache(target,[FEED]),state)
            self.assertFalse(target.with_suffix('.json.tmp').exists())

    def test_retention_removes_aged_metadata(self):
        state,_=capture(root=rss('2026-10-10'))
        self.assertEqual(len(state['sources']['one']['items']),1)
        state,_=capture(state,root=rss('2026-11-03'),now=NOW+dt.timedelta(days=29))
        self.assertNotIn('2026-10-10',{x['date'] for x in state['sources']['one']['items']})


if __name__=='__main__':unittest.main()
