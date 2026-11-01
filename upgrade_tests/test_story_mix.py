"""Verify original-audio volume with real PCM output, without provider calls."""
from array import array
import math
import shutil
import sys
import wave

import pytest

from upgrade import narration
from upgrade.media import Runner
from upgrade.store import create, save


RATE = 48_000
MANIFEST = [{'final_start': 1., 'final_end': 2.},
            {'final_start': 3., 'final_end': 4.}]


@pytest.fixture
def tone(tmp_path):
    if not shutil.which('ffmpeg'):
        pytest.skip('FFmpeg missing')
    samples = array('h', (round(10_000 * math.sin(2 * math.pi * 1_000 * i / RATE))
                          for i in range(5 * RATE)))
    payload = array('h', samples)
    if sys.byteorder != 'little':
        payload.byteswap()
    source = tmp_path / 'source.wav'
    with wave.open(str(source), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(payload.tobytes())
    return source, samples


def filtered_samples(source, target, expression):
    Runner().run(['ffmpeg', '-v', 'error', '-y', '-i', source,
                  '-af', expression, '-c:a', 'pcm_s16le', target])
    with wave.open(str(target), 'rb') as stream:
        assert stream.getframerate() == RATE
        assert stream.getnchannels() == 1
        assert stream.getsampwidth() == 2
        result = array('h', stream.readframes(stream.getnframes()))
    if sys.byteorder != 'little':
        result.byteswap()
    return result


def rms(samples, start, end):
    window = samples[round(start * RATE):round(end * RATE)]
    assert window
    return math.sqrt(sum(value * value for value in window) / len(window))


@pytest.mark.parametrize('duck', [True, False])
def test_real_ffmpeg_original_volume_in_gaps_and_during_voice(tmp_path, tone, duck):
    source, reference = tone
    expression = narration.gain_expression(MANIFEST, original_gain=.4, duck_gain=.15, duck=duck)
    output = filtered_samples(source, tmp_path / 'mixed.wav', expression)
    assert len(output) == len(reference)
    # Stay away from transition ramps and audio-frame boundaries.
    for start, end in ((.25, .75), (2.25, 2.75), (4.25, 4.75)):
        assert rms(output, start, end) / rms(reference, start, end) == pytest.approx(.4, abs=.002)
    for start, end in ((1.25, 1.75), (3.25, 3.75)):
        expected = .15 if duck else .4
        assert rms(output, start, end) / rms(reference, start, end) == pytest.approx(expected, abs=.002)


def test_real_ffmpeg_empty_voice_manifest_keeps_original_at_forty_percent(tmp_path, tone):
    source, reference = tone
    output = filtered_samples(source, tmp_path / 'no_voice.wav',
                              narration.gain_expression([], original_gain=.4, duck_gain=.15, duck=True))
    assert len(output) == len(reference)
    assert rms(output, .25, 4.75) / rms(reference, .25, 4.75) == pytest.approx(.4, abs=.002)


def test_twelve_second_default_slots_cover_the_story_without_reserved_time_share():
    slots = narration.make_slots(12.)
    assert narration.validate_slots(slots, 12.) == slots
    assert slots[0]['role'] == 'hook'
    assert (slots[0]['start'], slots[0]['end']) == (0., 3.)
    assert slots[-1]['role'] == 'punchline'
    assert slots[-1]['end'] == 12.
    assert sum(slot['end'] - slot['start'] for slot in slots) == pytest.approx(12.)
    assert all(left['end'] == right['start'] for left, right in zip(slots, slots[1:]))


@pytest.mark.parametrize('duration,conflict,punchline', [
    (100., (50., 51.), (99., 100.)),  # 5% narration windows are valid.
    (12., (6., 7.), (11., 12.)),     # Sparse windows need no 60/40 split.
    (12., (3., 9.), (9., 12.)),     # Continuous narration is valid too.
])
def test_valid_story_slots_accept_any_positive_nonoverlapping_occupancy(duration, conflict, punchline):
    slots = [{'id': 'hook', 'role': 'hook', 'start': 0., 'end': 3.},
             {'id': 'conflict', 'role': 'conflict', 'start': conflict[0], 'end': conflict[1]},
             {'id': 'punchline', 'role': 'punchline', 'start': punchline[0], 'end': punchline[1]}]
    assert narration.validate_slots(slots, duration) == slots


@pytest.mark.parametrize('measured_ratio', [0., .05, .9, 1.])
def test_matching_final_approval_has_no_duration_ratio_gate(tmp_path, measured_ratio):
    job = create(tmp_path)
    rows, regions = [], []
    config = {'sound_source': 'source', 'original_gain': .4, 'duck_gain': .15,
              'duck': True, 'voice_gain': 1.}
    # Old jobs may retain obsolete ratio fields. They must not impose a gate.
    save(job / 'story_timing.json', {'measured_narration_ratio': measured_ratio,
                                   'measured_original_only_ratio': 1 - measured_ratio,
                                   'within_requested_range': False})
    save(job / 'story_final_approval.json',
         {'signature': narration.final_signature(job, rows, regions, config)})
    narration.require_final_review(job, rows, regions, config)


def test_final_review_still_rejects_changed_mix_settings(tmp_path):
    job = create(tmp_path)
    config = {'sound_source': 'source', 'original_gain': .4, 'duck_gain': .15,
              'duck': True, 'voice_gain': 1.}
    save(job / 'story_final_approval.json',
         {'signature': narration.final_signature(job, [], [], config)})
    with pytest.raises(ValueError):
        narration.require_final_review(job, [], [], {**config, 'original_gain': .6})
