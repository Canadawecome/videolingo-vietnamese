"""Explicit app editions and safeguards for faithful translation editing."""
from dataclasses import dataclass

from . import captions, narration
from .store import digest, read, save


@dataclass(frozen=True)
class Edition:
    name: str
    title: str
    target_language: str
    tts_language: str
    tts_config: str
    sample_text: str
    sample_file: str
    faithful_only: bool = False


ENGLISH = Edition(
    name='en', title='VideoLingo Studio', target_language='English', tts_language='en',
    tts_config='upgrade_tts_config.json',
    sample_text='Every story deserves a voice. Warm, clear, and full of life.',
    sample_file='voice_preview.mp3')

VIETNAMESE = Edition(
    name='vi', title='VideoLingo Studio — Tiếng Việt', target_language='Vietnamese', tts_language='vi',
    tts_config='upgrade_tts_vi_config.json',
    sample_text='Xin chào! Đây là giọng thuyết minh tiếng Việt, rõ ràng, tự nhiên và dễ nghe.',
    sample_file='voice_preview_vi.mp3', faithful_only=True)


def get_edition(name='en'):
    if name == 'en':
        return ENGLISH
    if name == 'vi':
        return VIETNAMESE
    raise ValueError('Unknown application edition.')


def validate_translation_edit(edited, original, duration):
    """Keep source text, row order, IDs and source timestamps unchanged."""
    if (not isinstance(edited, list) or not isinstance(original, list) or not original
            or len(edited) != len(original)):
        raise ValueError('Bản dịch phải giữ đủ các câu nguồn theo đúng thứ tự.')
    if not all(isinstance(row, dict) for row in edited + original):
        raise ValueError('Dữ liệu câu nguồn không hợp lệ.')
    if narration.is_story(original) or narration.is_story(edited):
        raise ValueError('Khôi phục transcript nguồn trước khi dịch sát nguồn.')
    immutable = ('id', 'start', 'end', 'source')
    for row, source in zip(edited, original):
        if any(key not in row or key not in source or row[key] != source[key] for key in immutable):
            raise ValueError('Bản dịch phải giữ nguyên ID, thứ tự, nội dung nguồn và mốc thời gian.')
        for key in ('source', 'translation', 'tts_text'):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError('Nội dung nguồn, bản dịch và lời đọc không được để trống.')
    captions.validate(edited, duration)
    return edited


def restore_source_for_translation(job, duration):
    """Explicitly restore source rows, preserving the current story in a backup."""
    current = read(job/'segments.json', [])
    source = read(job/'source_segments.json', [])
    if not current or not narration.is_story(current):
        raise ValueError('Job hiện tại không dùng kịch bản cần khôi phục.')
    if not source or narration.is_story(source):
        raise ValueError('Thiếu transcript nguồn hợp lệ. Giữ nguyên kịch bản hiện tại.')
    validate_translation_edit(source, source, duration)
    backup = job/f'story_backup_before_vi_{digest(current)[:12]}.json'
    save(backup, current)
    save(job/'segments.json', source)
    return backup
