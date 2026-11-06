from copy import deepcopy

import pytest


def sample():
    return {'schema_version': 'topic-observations.v1', 'topic': 'Trump cryptocurrency',
            'entities': ['Donald Trump'], 'captured_at': '2026-10-24T00:00:00Z', 'target_days': 30,
            'source_url': 'https://api.gdeltproject.org/api/v2/doc/doc?query=Trump%20cryptocurrency&mode=artlist&format=json&maxrecords=10&timespan=30d&sort=datedesc',
            'articles': [{'title': 'A reported lawsuit', 'url': 'https://example.org/story',
                          'seendate': '20261023T120000Z', 'domain': 'example.org', 'language': 'English', 'sourcecountry': 'United States'}],
            'social_posts': []}


def test_metadata_does_not_invent_publication_or_market_probabilities():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['articles'].append({**value['articles'][0], 'url': 'https://other.org/story', 'domain': 'other.org'})
    before = deepcopy(value)
    result = analyze_topics(value)
    assert value == before
    assert result['summary']['articles'] == 2
    assert result['summary']['headline_groups'] == 1
    assert result['summary']['social_posts'] == 0
    assert result['articles'][0]['published_at'] is None
    assert result['articles'][0]['relevance'] == 'query_match_unreviewed'
    assert result['simulation_effect'] == 'none'
    assert result['coverage']['complete_target_window'] is False
    assert result['social_status'] == 'not_connected'
    assert 'probability' not in result['articles'][0]


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://user:pass@example.org/x', 'https://127.0.0.1/x', 'https://localhost/x', 'https://example.org/x?api_key=secret', 'https://example.org/x#access_token=secret'])
def test_unsafe_or_secret_bearing_links_rejected(url):
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['articles'][0]['url'] = url
    with pytest.raises(ValueError):
        analyze_topics(value)


def test_future_seen_dates_and_bad_social_authorship_rejected():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['articles'][0]['seendate'] = '20261025T000000Z'
    with pytest.raises(ValueError):
        analyze_topics(value)
    value = sample()
    value['social_posts'] = [{'url': 'https://x.com/someone/status/123', 'author': 'Someone',
                             'created_at': '2026-10-23T01:00:00Z', 'text': 'An opinion', 'platform': 'x',
                             'identity_status': 'verified'}]
    with pytest.raises(ValueError):
        analyze_topics(value)


def test_duplicate_urls_do_not_count_as_independent_evidence():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['articles'] *= 2
    result = analyze_topics(value)
    assert result['summary']['articles'] == 1
    assert result['summary']['duplicate_urls'] == 1
    assert result['articles'][0]['first_seen_at'] == '2026-10-23T12:00:00Z'


def test_explicit_social_export_preserves_unverified_author_and_no_inference():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['social_posts'] = [{'url': 'https://x.com/someone/status/123', 'author': 'Someone',
                             'created_at': '2026-10-23T01:00:00Z', 'text': 'An opinion', 'platform': 'x',
                             'identity_status': 'declared_unverified'}]
    result = analyze_topics(value)
    assert result['social_status'] == 'imported_unverified'
    assert result['social_posts'][0]['identity_status'] == 'declared_unverified'


def test_ancient_cutoff_is_a_validation_error():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['captured_at'] = '0001-01-01T00:00:00Z'
    with pytest.raises(ValueError):
        analyze_topics(value)


def test_actual_provider_bare_domain_matches_www_article_url():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    value['articles'][0]['url'] = 'https://www.example.org/story'
    assert analyze_topics(value)['summary']['articles'] == 1


def test_social_fractional_timestamps_are_ordered_as_instants():
    from decision_lab.topic_evidence import analyze_topics
    value = sample()
    post = {'author': 'Someone', 'text': 'An opinion', 'platform': 'x', 'identity_status': 'declared_unverified'}
    value['social_posts'] = [dict(post, url='https://x.com/someone/status/1', created_at='2026-10-23T12:00:00Z'),
                             dict(post, url='https://x.com/someone/status/2', created_at='2026-10-23T12:00:00.100000Z')]
    assert analyze_topics(value)['social_posts'][0]['url'].endswith('/2')
