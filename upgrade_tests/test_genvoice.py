"""Offline contract tests for the resumable Genvoice TTS adapter."""
import json
from urllib.parse import urlparse

import pytest
import requests

from upgrade import providers
from upgrade.media import Runner


AUDIO = b'fake-mp3-for-mocked-ffprobe'


def response(url, *, data=None, content=AUDIO, status=200):
    result = requests.Response()
    result.status_code = status
    result.url = url
    result._content = json.dumps(data).encode() if data is not None else content
    result._content_consumed = True
    result.headers['Content-Type'] = 'application/json' if data is not None else 'audio/mpeg'
    result.headers['Retry-After'] = '0'
    return result


@pytest.fixture
def cfg():
    return {
        'base': 'https://genvoice.example',
        'route': '/v1/text-to-speech/{voice_id}',
        'key': 'test-secret-do-not-send-to-audio',
        'header': 'xi-api-key',
        'prefix': '',
        'verified': True,
        'protocol': 'genvoice_async',
        'provider': 'elevenlabs',
        'voice': 'english-female-voice',
        'model': 'supported-model',
        'language': 'en',
        'settings': {'stability': 0.5, 'similarity_boost': 0.75},
    }


@pytest.fixture(autouse=True)
def no_network_or_ffprobe(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('Unexpected real network request')

    monkeypatch.setattr(requests.sessions.Session, 'send', forbidden)
    monkeypatch.setattr(providers.time, 'sleep', lambda seconds: None)

    def fake_probe(path, runner=None):
        assert path.read_bytes() == AUDIO
        return {'duration': 1.25, 'audio': True, 'width': 0, 'height': 0}

    monkeypatch.setattr(providers, 'probe', fake_probe)


@pytest.fixture
def runner(monkeypatch):
    result = Runner()
    monkeypatch.setattr(result.cancel, 'wait', lambda seconds=None: False)
    return result


@pytest.fixture
def transport(monkeypatch):
    """Intercept both requests.request and requests.get without real I/O."""
    def install(handler):
        calls = []

        def dispatch(method, url, **kwargs):
            method = method.upper()
            calls.append((method, url, kwargs))
            return handler(method, url, kwargs)

        monkeypatch.setattr(providers.requests, 'request', dispatch)
        monkeypatch.setattr(providers.requests, 'get', lambda url, **kwargs: dispatch('GET', url, **kwargs))
        monkeypatch.setattr(requests.sessions.Session, 'request',
                            lambda session, method, url, **kwargs: dispatch(method, url, **kwargs))
        return calls

    return install


def completed_task(base, task_id='task-1', audio_url=None):
    return {
        'id': task_id,
        'status': 'completed',
        'result': {'audio_url': audio_url or f'{base}/audio/{task_id}.mp3'},
    }


def assert_anonymous_download(kwargs, secret):
    headers = {key.lower(): value for key, value in (kwargs.get('headers') or {}).items()}
    assert 'xi-api-key' not in headers
    assert 'authorization' not in headers
    assert not kwargs.get('auth')
    assert secret not in repr(kwargs)
    assert kwargs.get('allow_redirects') is False


def test_async_speech_downloads_without_credentials_and_reuses_cache(tmp_path, cfg, runner, transport):
    def handle(method, url, kwargs):
        assert kwargs.get('allow_redirects') is False
        if method == 'POST':
            assert url == cfg['base'] + '/v1/text-to-speech/' + cfg['voice']
            return response(url, data={'id': 'task-1', 'status': 'pending'})
        if url == cfg['base'] + '/v1/history/task-1':
            return response(url, data=completed_task(cfg['base']))
        if url == cfg['base'] + '/audio/task-1.mp3':
            assert_anonymous_download(kwargs, cfg['key'])
            return response(url)
        pytest.fail(f'Unexpected request: {method} {url}')

    calls = transport(handle)
    path, duration = providers.speech('Hello world.', cfg, tmp_path / 'cache', runner)
    assert path.read_bytes() == AUDIO
    assert duration == 1.25
    assert providers.speech('Hello world.', cfg, tmp_path / 'cache', runner) == (path, duration)
    assert [method for method, _, _ in calls].count('POST') == 1
    assert len(calls) == 3
    for metadata in (tmp_path / 'cache').glob('*.json'):
        assert cfg['key'] not in metadata.read_text(encoding='utf-8')


def test_pending_task_resumes_without_second_paid_post(tmp_path, cfg, runner, transport):
    history_calls = 0

    def handle(method, url, kwargs):
        nonlocal history_calls
        if method == 'POST':
            return response(url, data={'id': 'task-1', 'status': 'pending'})
        if url == cfg['base'] + '/v1/history/task-1':
            history_calls += 1
            if history_calls == 1:
                raise requests.Timeout('simulated interrupted polling')
            return response(url, data=completed_task(cfg['base']))
        if url == cfg['base'] + '/audio/task-1.mp3':
            assert_anonymous_download(kwargs, cfg['key'])
            return response(url)
        pytest.fail(f'Unexpected request: {method} {url}')

    calls = transport(handle)
    cache = tmp_path / 'cache'
    with pytest.raises(providers.ProviderError):
        providers.speech('Please resume this sentence.', cfg, cache, runner)
    path, duration = providers.speech('Please resume this sentence.', cfg, cache, runner)
    assert path.read_bytes() == AUDIO
    assert duration == 1.25
    assert [method for method, _, _ in calls].count('POST') == 1
    assert history_calls == 2


@pytest.mark.parametrize('corrupt_metadata', ['{broken json', '[]', 'null'])
def test_direct_audio_recovers_malformed_cache_metadata(tmp_path, cfg, runner, transport, corrupt_metadata):
    direct_cfg = {key: value for key, value in cfg.items() if key != 'protocol'}

    def handle(method, url, kwargs):
        assert method == 'POST'
        return response(url)

    calls = transport(handle)
    path, duration = providers.speech('Direct audio remains supported.', direct_cfg, tmp_path / 'cache', runner)
    path.with_suffix('.json').write_text(corrupt_metadata, encoding='utf-8')
    new_path, new_duration = providers.speech('Direct audio remains supported.', direct_cfg, tmp_path / 'cache', runner)
    assert (new_path, new_duration) == (path, duration)
    assert path.read_bytes() == AUDIO
    assert len(calls) == 2


@pytest.mark.parametrize('change', [
    {'language': 'fr'},
    {'settings': {'stability': 0.8, 'similarity_boost': 0.75}},
    {'voice': 'another-voice'},
    {'model': 'another-model'},
])
def test_synthesis_config_includes_audio_affecting_choices(cfg, change):
    assert providers.synthesis_config(cfg) != providers.synthesis_config({**cfg, **change})


def test_synthesis_config_ignores_secrets_and_ui_metadata(cfg):
    public = providers.synthesis_config(cfg)
    changed = {**cfg, 'key': 'rotated-test-secret', 'verified': False, 'voice_name': 'Friendly display name'}
    assert providers.synthesis_config(changed) == public
    assert cfg['key'] not in json.dumps(public)


@pytest.mark.parametrize('change', [
    {'language': 'fr'},
    {'settings': {'stability': 0.8, 'similarity_boost': 0.75}},
])
def test_changed_language_or_settings_creates_new_audio(tmp_path, cfg, runner, transport, change):
    posts = 0

    def handle(method, url, kwargs):
        nonlocal posts
        if method == 'POST':
            posts += 1
            return response(url, data={'id': f'task-{posts}', 'status': 'pending'})
        if '/v1/history/' in url:
            return response(url, data=completed_task(cfg['base'], url.rsplit('/', 1)[-1]))
        if '/audio/' in url:
            assert_anonymous_download(kwargs, cfg['key'])
            return response(url)
        pytest.fail(f'Unexpected request: {method} {url}')

    transport(handle)
    cache = tmp_path / 'cache'
    first, _ = providers.speech('Same text.', cfg, cache, runner)
    second, _ = providers.speech('Same text.', {**cfg, **change}, cache, runner)
    assert first != second
    assert posts == 2


def test_paid_post_server_error_is_not_automatically_retried(cfg, runner, transport):
    calls = transport(lambda method, url, kwargs: response(url, data={'error': 'server failure'}, status=500))
    with pytest.raises(providers.ProviderError) as error:
        providers.request(cfg['base'], '/v1/text-to-speech/voice', cfg['key'], 'POST', {'text': 'Hello'}, runner=runner)
    assert len(calls) == 1
    assert cfg['key'] not in str(error.value)


@pytest.mark.parametrize('audio_url', [
    'https://other.example/audio.mp3',
    'http://genvoice.example/audio.mp3',
    'https://genvoice.example.other.example/audio.mp3',
])
def test_external_or_insecure_audio_url_is_blocked(tmp_path, cfg, runner, transport, audio_url):
    def handle(method, url, kwargs):
        if method == 'POST':
            return response(url, data={'id': 'task-1', 'status': 'pending'})
        if url == cfg['base'] + '/v1/history/task-1':
            return response(url, data=completed_task(cfg['base'], audio_url=audio_url))
        pytest.fail(f'Audio URL must be rejected before requesting it: {url}')

    calls = transport(handle)
    with pytest.raises(providers.ProviderError):
        providers.speech('Untrusted download location.', cfg, tmp_path / 'cache', runner)
    assert all(urlparse(url).netloc == 'genvoice.example' for _, url, _ in calls)
    assert len(calls) == 2
