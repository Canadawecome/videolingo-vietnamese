"""Edition regressions using isolated jobs, mocked credentials and no network."""
from copy import deepcopy
from pathlib import Path
import shutil
from unittest.mock import Mock

import pytest
from streamlit.testing.v1 import AppTest

from upgrade import edition, media, providers, secrets
from upgrade.store import read, save


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def source_rows():
    return [
        {'id': 's1', 'start': 0., 'end': 2.5, 'source': 'The train arrived at noon.',
         'translation': 'The train arrived at noon.', 'tts_text': 'The train arrived at noon.'},
        {'id': 's2', 'start': 3., 'end': 5.5, 'source': 'We boarded at the next station.',
         'translation': 'We boarded at the next station.', 'tts_text': 'We boarded at the next station.'},
    ]


@pytest.fixture
def app_dir(tmp_path, monkeypatch, source_rows):
    # The app's ROOT resolves to this copied entrypoint, never the user's jobs.
    app_dir = tmp_path/'app'
    app_dir.mkdir()
    for name in ('upgrade_app.py', 'upgrade_app_vi.py'):
        shutil.copy2(ROOT/name, app_dir/name)
    component = app_dir/'upgrade'/'region_component'
    component.mkdir(parents=True)
    (component/'index.html').write_text('<html></html>', encoding='utf-8')
    job = app_dir/'jobs'/'test-job'
    job.mkdir(parents=True)
    (job/'source.mp4').write_bytes(b'isolated-video-fixture')
    (job/'region_frame.jpg').write_bytes(b'isolated-frame-fixture')
    save(job/'frame_time.json', 1.)
    save(job/'job.json', {'id': 'test-job', 'steps': {}})
    save(job/'segments.json', source_rows)
    save(job/'source_segments.json', source_rows)
    save(job/'ocr_regions.json', [])
    save(app_dir/'upgrade_tts_config.json', {'language': 'en', 'voice': 'english-voice',
                                           'voice_name': 'English fixture', 'model': 'english-model'})
    save(app_dir/'upgrade_tts_vi_config.json', {'language': 'vi', 'voice': 'vietnamese-voice',
                                              'voice_name': 'Vietnamese fixture', 'model': 'vietnamese-model'})
    monkeypatch.setattr(secrets, 'load_genvoice_key', Mock(return_value=''))
    monkeypatch.setattr(media, 'probe', Mock(return_value={
        'duration': 12., 'width': 640, 'height': 360, 'audio': True}))
    monkeypatch.setattr(media.Runner, 'run', Mock(side_effect=AssertionError('No process expected in UI tests')))
    monkeypatch.setattr(providers.requests, 'request', Mock(side_effect=AssertionError('Live API forbidden')))
    for key in ('TROUTER_API_KEY', 'GENVOICE_API_KEY', 'GENVOICE_VOICE_ID', 'GENVOICE_MODEL_ID',
                'GENVOICE_VI_VOICE_ID', 'GENVOICE_VI_MODEL_ID', 'GENVOICE_BASE_URL', 'TROUTER_BASE_URL'):
        monkeypatch.delenv(key, raising=False)
    return app_dir


def element_by_label(elements, label):
    return next(element for element in elements if element.label == label)


def test_vietnamese_defaults_hide_story_controls_and_enable_dubbing(app_dir):
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == 'VideoLingo Studio — Tiếng Việt'
    assert element_by_label(app.text_input, 'Ngôn ngữ đích').value == 'Vietnamese'
    assert element_by_label(app.text_input, 'Mã ngôn ngữ giọng').value == 'vi'
    assert element_by_label(app.text_input, 'Voice ID').value == 'vietnamese-voice'
    assert element_by_label(app.text_input, 'Model TTS').value == 'vietnamese-model'
    assert element_by_label(app.text_area, 'Câu nghe thử').value.startswith('Xin chào!')
    assert element_by_label(app.checkbox, 'Lồng tiếng').value is True
    assert not app.radio
    labels = [button.label for button in app.button]
    assert 'Dịch bằng Trouter (gọi API)' in labels
    assert 'Lưu bản dịch và lời đọc' in labels
    assert not any('Facts' in label or 'Hook' in label or 'kịch bản' in label for label in labels)
    assert [element_by_label(app.slider, label).value for label in (
        'Âm lượng thuyết minh (%)', 'Âm lượng tiếng gốc / nền (%)', 'Tiếng gốc khi có lời đọc (%)')] == [100, 40, 15]


def test_english_entrypoint_keeps_story_option_and_original_defaults(app_dir):
    app = AppTest.from_file(str(app_dir/'upgrade_app.py')).run(timeout=15)
    assert not app.exception
    assert app.title[0].value == 'VideoLingo Studio'
    assert element_by_label(app.text_input, 'Ngôn ngữ đích').value == 'English'
    assert element_by_label(app.text_input, 'Mã ngôn ngữ giọng').value == 'en'
    assert element_by_label(app.text_area, 'Câu nghe thử').value.startswith('Every story')
    assert element_by_label(app.radio, 'Cách tạo nội dung').value == 'Viết kịch bản từ dữ kiện'
    assert element_by_label(app.checkbox, 'Lồng tiếng').value is False


def test_vietnamese_does_not_play_english_job_preview_or_bella_fallback(app_dir):
    (app_dir/'demo').mkdir()
    (app_dir/'demo'/'bella-english-preview.mp3').write_bytes(b'old-bella-sample')
    (app_dir/'jobs'/'test-job'/'voice_preview.mp3').write_bytes(b'old-job-english-sample')
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert len(app.get('audio')) == 0
    assert not any('Bella' in element.value for element in app.caption)


def test_vietnamese_uses_only_its_preview_if_available(app_dir):
    (app_dir/'demo').mkdir()
    (app_dir/'demo'/'vietnamese-female-preview.mp3').write_bytes(b'vi-audio-fixture')
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert len(app.get('audio')) == 1
    assert any('Mẫu nữ tiếng Việt' in element.value for element in app.caption)


def test_vietnamese_config_survives_unrelated_catalog_and_english_env(app_dir, monkeypatch):
    monkeypatch.setenv('GENVOICE_VOICE_ID', 'legacy-english-voice')
    monkeypatch.setenv('GENVOICE_MODEL_ID', 'legacy-english-model')
    (app_dir/'runtime').mkdir()
    save(app_dir/'runtime'/'genvoice_voices.json', {'voices': [
        {'voice_id': 'other-voice', 'name': 'Other supported voice', 'gender': 'female', 'language': 'vi'}]})
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert element_by_label(app.selectbox, 'Giọng nữ').value == 'vietnamese-voice'
    assert element_by_label(app.text_input, 'Model TTS').value == 'vietnamese-model'


def test_existing_story_requires_explicit_restore_and_preserves_backup(app_dir, source_rows):
    job = app_dir/'jobs'/'test-job'
    active_story = [{**source_rows[0], 'id': 'story-hook', 'mode': 'story', 'lock_end': True}]
    save(job/'segments.json', active_story)
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert read(job/'segments.json') == active_story
    assert not list(job.glob('story_backup_before_vi_*.json'))
    labels = [button.label for button in app.button]
    assert 'Dịch bằng Trouter (gọi API)' not in labels
    assert 'Tạo / cập nhật giọng (gọi API)' not in labels
    element_by_label(app.button, 'Khôi phục transcript nguồn để dịch tiếng Việt').click().run(timeout=15)
    assert not app.exception
    assert read(job/'segments.json') == source_rows
    assert read(job/'source_segments.json') == source_rows
    backups = list(job.glob('story_backup_before_vi_*.json'))
    assert len(backups) == 1
    assert read(backups[0]) == active_story
    assert 'Dịch bằng Trouter (gọi API)' in [button.label for button in app.button]


def test_existing_story_without_source_is_left_intact(app_dir, source_rows):
    job = app_dir/'jobs'/'test-job'
    active_story = [{**source_rows[0], 'mode': 'story'}]
    save(job/'segments.json', active_story)
    (job/'source_segments.json').unlink()
    app = AppTest.from_file(str(app_dir/'upgrade_app_vi.py')).run(timeout=15)
    assert not app.exception
    assert element_by_label(app.button, 'Khôi phục transcript nguồn để dịch tiếng Việt').disabled
    assert read(job/'segments.json') == active_story
    assert not list(job.glob('story_backup_before_vi_*.json'))


@pytest.mark.parametrize('change', ['order', 'id', 'start', 'end', 'source', 'missing', 'empty', 'story'])
def test_faithful_edits_cannot_change_source_contract(change, source_rows):
    edited = deepcopy(source_rows)
    if change == 'order':
        edited.reverse()
    elif change in ('id', 'source'):
        edited[0][change] = 'changed'
    elif change in ('start', 'end'):
        edited[0][change] += .1
    elif change == 'missing':
        edited.pop()
    elif change == 'empty':
        edited[0]['translation'] = ''
    else:
        edited[0]['mode'] = 'story'
    with pytest.raises(ValueError):
        edition.validate_translation_edit(edited, source_rows, 12.)


def test_faithful_edits_allow_vietnamese_translation_and_spoken_text(source_rows):
    edited = deepcopy(source_rows)
    edited[0]['translation'] = 'Tàu đến vào buổi trưa.'
    edited[0]['tts_text'] = 'Tàu đến vào buổi trưa.'
    assert edition.validate_translation_edit(edited, source_rows, 12.) == edited
    assert source_rows[0]['translation'] == 'The train arrived at noon.'
