"""Bounded news metadata/social export normalization, without inference or fetching."""
from collections import Counter
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import re
from urllib.parse import parse_qsl, urlsplit

from .wallet_evidence import _bounded_json, _date, _iso, _keys, _text


def _link(value):
    _text(value, 'source URL', 2048)
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment or url.port not in (None, 443):
        raise ValueError('public HTTPS source URL required')
    host = url.hostname.lower()
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.test')):
        raise ValueError('public source URL required')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('literal source IP addresses are not supported')
    if any(re.search('key|token|secret|auth|password|signature', key, re.I) for key, _ in parse_qsl(url.query)):
        raise ValueError('secret-bearing source URLs are not supported')
    return value


def analyze_topics(snapshot):
    _bounded_json(snapshot)
    _keys(snapshot, {'schema_version', 'topic', 'entities', 'captured_at', 'target_days', 'source_url', 'articles', 'social_posts'}, 'topic snapshot')
    if snapshot['schema_version'] != 'topic-observations.v1' or type(snapshot['target_days']) is not int or snapshot['target_days'] != 30:
        raise ValueError('topic-observations.v1 with a 30-day target required')
    topic = _text(snapshot['topic'], 'topic', 256)
    captured = _date(snapshot['captured_at'], 'captured_at')
    try:
        start = captured - timedelta(days=30)
    except OverflowError:
        raise ValueError('capture date cannot define a 30-day window') from None
    entities = snapshot['entities']
    if type(entities) is not list or not 1 <= len(entities) <= 20:
        raise ValueError('one to twenty declared entities required')
    for entity in entities:
        _text(entity, 'entity', 128)
    source = _link(snapshot['source_url'])
    if urlsplit(source).netloc != 'api.gdeltproject.org' or urlsplit(source).path != '/api/v2/doc/doc':
        raise ValueError('GDELT DOC metadata source URL required')
    raw, posts = snapshot['articles'], snapshot['social_posts']
    if type(raw) is not list or len(raw) > 250 or type(posts) is not list or len(posts) > 250:
        raise ValueError('at most 250 news and 250 social records supported')
    seen, articles, excluded, duplicates = {}, [], 0, 0
    for row in raw:
        if type(row) is not dict:
            raise ValueError('article metadata required')
        title = _text(row.get('title'), 'headline', 512)
        url = _link(row.get('url'))
        date = row.get('seendate')
        if type(date) is not str or not re.fullmatch(r'\d{8}T\d{6}Z', date):
            raise ValueError('GDELT seendate required')
        when = datetime.strptime(date, '%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
        if when > captured:
            raise ValueError('article first seen after capture')
        if when < start:
            excluded += 1
            continue
        domain = _text(row.get('domain'), 'domain', 256)
        if urlsplit(url).hostname.lower().removeprefix('www.') != domain.lower().removeprefix('www.'):
            raise ValueError('article domain does not match source URL')
        normalized_title = re.sub(r'\W+', ' ', title.casefold()).strip()
        article = {'title': title, 'url': url, 'domain': domain, 'first_seen_at': _iso(when),
                   'published_at': None, 'headline_group': hashlib.sha256(normalized_title.encode()).hexdigest()[:16],
                   'relevance': 'query_match_unreviewed', 'truth_status': 'not_verified',
                   'language': _text(row.get('language', 'Unknown'), 'language', 64)}
        if url in seen:
            if seen[url] != article:
                raise ValueError('conflicting metadata for one article URL')
            duplicates += 1
            continue
        seen[url] = article
        articles.append(article)
    social, social_urls = [], set()
    for row in posts:
        _keys(row, {'url', 'author', 'created_at', 'text', 'platform', 'identity_status'}, 'social record')
        url = _link(row['url'])
        when = _date(row['created_at'], 'created_at')
        if when > captured:
            raise ValueError('social post after capture')
        if when < start:
            excluded += 1
            continue
        if row['identity_status'] != 'declared_unverified':
            raise ValueError('import cannot authenticate social authorship')
        for key, maximum in (('author', 128), ('text', 2048), ('platform', 64)):
            _text(row[key], key, maximum)
        if url in social_urls:
            raise ValueError('duplicate social URL')
        social_urls.add(url)
        social.append(dict(row))
    articles.sort(key=lambda row: (_date(row['first_seen_at'], 'first_seen_at'), row['url']), reverse=True)
    social.sort(key=lambda row: (_date(row['created_at'], 'created_at'), row['url']), reverse=True)
    groups = Counter(row['headline_group'] for row in articles)
    return {'schema_version': 'topic-evidence.v1', 'topic': topic, 'entities': list(entities),
            'captured_at': _iso(captured), 'target_window': {'start': _iso(start), 'end': _iso(captured), 'requested_days': 30},
            'summary': {'articles': len(articles), 'headline_groups': len(groups), 'social_posts': len(social),
                        'duplicate_urls': duplicates, 'outside_window': excluded},
            'coverage': {'complete_target_window': False, 'status': 'bounded_search_results', 'max_articles': 250},
            'source_metadata': {'source_url': source, 'provider': 'GDELT DOC', 'verification': 'declared_unverified'},
            'social_status': 'imported_unverified' if social else 'not_connected', 'simulation_effect': 'none',
            'articles': articles, 'social_posts': social,
            'limitations': ['Search matches are leads for review, not established facts or confirmed relevance.',
                            'GDELT seendate is an indexing timestamp, not the original publication time.',
                            'Equal normalized headlines are grouped to expose syndication; different wording can still repeat one story.',
                            'Article counts and opinions do not determine event probability, causality, audience reach or trading intent.',
                            'No full article text is fetched or retained. Social imports do not authenticate the named author.',
                            'This evidence does not change simulation parameters or create executable behavior automatically.']}
