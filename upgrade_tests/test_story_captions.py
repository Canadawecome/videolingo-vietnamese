from copy import deepcopy

import pytest
from PIL import ImageFont

from upgrade import captions


@pytest.fixture
def font():
    for candidate in ('C:/Windows/Fonts/arial.ttf', 'DejaVuSans.ttf'):
        try:
            ImageFont.truetype(candidate, 18)
        except OSError:
            continue
        return candidate
    pytest.skip('No test font available')


def voice_row(text, identity='voice1', start=0.25, end=4.75):
    return {'id': identity, 'start': 0., 'end': 10., 'translation': text,
            'tts_text': text, 'final_start': start, 'final_end': end}


def split(rows, font, box=(0., 0., 1., 1.), width=1920, height=1080):
    return captions.story_events(rows, width, height, box, font)


def test_preserves_unicode_whitespace_and_original_tts_rows(font):
    text = '  “Café déjà vu!”\t Việt Nam — 東京.  This story keeps every single word intact.\n'
    rows = [voice_row(text)]
    original = deepcopy(rows)
    events = split(rows, font)

    assert len(events) > 1
    assert ''.join(event['translation'] for event in events) == text
    assert rows == original
    assert all(event is not rows[0] for event in events)
    assert all(1 <= len(event['translation'].split()) <= 8 for event in events)
    assert all(event['timing_method'] == 'word_count_approximation' for event in events)
    assert len({event['id'] for event in events}) == len(events)


def test_favors_punctuation_before_eight_word_limit(font):
    events = split([voice_row('Wait, look closer. One two three four five six seven eight nine.')], font)
    assert events[0]['translation'].strip() == 'Wait, look closer.'
    assert all(len(event['translation'].split()) <= 8 for event in events)


def test_word_count_timing_stays_in_measured_spans_and_out_of_gaps(font):
    rows = [voice_row('one two three four five six seven eight nine ten', end=2.25),
            voice_row('The second voice starts later.', identity='voice2', start=6., end=7.)]
    events = split(rows, font)
    for row in rows:
        group = [event for event in events if event['caption_parent_id'] == row['id']]
        assert group[0]['final_start'] == row['final_start']
        assert group[-1]['final_end'] == row['final_end']
        for event in group:
            assert row['final_start'] <= event['start'] < event['end'] <= row['final_end']
            assert event['final_start'] == event['start']
            assert event['final_end'] == event['end']
            fraction = len(event['translation'].split()) / len(row['translation'].split())
            assert event['end'] - event['start'] == pytest.approx(
                fraction * (row['final_end'] - row['final_start']))
        assert all(left['end'] == right['start'] for left, right in zip(group, group[1:]))
    assert not any(event['start'] < 6. and event['end'] > 2.25 for event in events)


def test_chunks_use_measured_layout_and_export_successfully(font, tmp_path):
    text = 'Wide words require smaller subtitle chunks while every detail stays present.'
    box = (0., 0., .25, .3)
    events = split([voice_row(text)], font, box=box, width=640, height=360)
    assert len(events) > 2
    assert ''.join(event['translation'] for event in events) == text
    for event in events:
        lines, _ = captions.layout(event['translation'], font, 36, 18,
                                   box[2] * 640 - 12, box[3] * 360 - 8)
        assert len(lines) <= 2
    captions.export(tmp_path, events, 640, 360, box, font)
    srt = (tmp_path / 'captions.srt').read_text(encoding='utf-8-sig')
    assert ' '.join(row['translation'] for row in captions.import_srt(srt)) == text


def test_single_long_word_that_fits_can_wrap_without_losing_characters(font):
    text = 'W' * 8
    events = split([voice_row(text)], font, box=(0., 0., .2, .3), width=640, height=360)
    assert len(events) == 1
    assert events[0]['translation'] == text


def test_single_overflowing_token_is_rejected_without_truncation(font):
    rows = [voice_row('W' * 120)]
    original = deepcopy(rows)
    with pytest.raises(ValueError, match='Một từ vẫn tràn'):
        split(rows, font, box=(0., 0., .2, .3), width=640, height=360)
    assert rows == original


@pytest.mark.parametrize('changes', [
    {'final_start': None}, {'final_end': float('nan')},
    {'final_end': .25}, {'final_start': -1.},
])
def test_rejects_unusable_measured_voice_spans(font, changes):
    with pytest.raises(ValueError):
        split([{**voice_row('Keep this text.'), **changes}], font)


def test_requires_actual_tts_times_and_rejects_empty_text(font):
    row = voice_row('Keep this text.')
    row.pop('final_end')
    with pytest.raises(ValueError, match='đã đo'):
        split([row], font)
    with pytest.raises(ValueError, match='Bản dịch rỗng'):
        split([voice_row(' \t\n')], font)
    assert split([], font) == []
