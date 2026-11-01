import math
import re
from PIL import ImageFont


def validate(rows, duration):
    ids = set()
    for s in rows:
        if not s.get('id') or s['id'] in ids:
            raise ValueError('ID câu phải duy nhất và không rỗng.')
        ids.add(s['id'])
        if not all(math.isfinite(float(s[k])) for k in ('start', 'end')) or not 0 <= s['start'] < s['end'] <= duration + .05:
            raise ValueError(f"Mốc thời gian sai: {s['id']}")
    if rows != sorted(rows, key=lambda x: x['start']):
        raise ValueError('Các câu phải theo thứ tự thời gian.')


def import_srt(text):
    def seconds(t):
        h, m, s = t.replace(',', '.').split(':')
        return int(h)*3600 + int(m)*60 + float(s)
    rows = []
    for block in re.split(r'\n\s*\n', text.strip().replace('\r', '')):
        lines = block.splitlines()
        n = next((i for i, l in enumerate(lines) if ' --> ' in l), None)
        if n is None:
            continue
        a, b = lines[n].split(' --> ')
        content = ' '.join(lines[n+1:])
        rows.append({'id': f's{len(rows)+1:05}', 'start': seconds(a), 'end': seconds(b.split()[0]),
                     'source': content, 'translation': content, 'tts_text': content})
    if not rows:
        raise ValueError('Không tìm thấy câu trong SRT.')
    return rows


def stamp(t, ass=False):
    units = 100 if ass else 1000
    t = round(t * units)
    h, t = divmod(t, 3600 * units)
    m, t = divmod(t, 60 * units)
    s, f = divmod(t, units)
    return f'{h}:{m:02}:{s:02}.{f:02}' if ass else f'{h:02}:{m:02}:{s:02},{f:03}'


def layout(text, font, size, minimum, width, height):
    for fs in range(size, minimum-1, -1):
        face = ImageFont.truetype(font, fs)
        lines, line = [], ''
        # Character fallback supports CJK and long tokens without truncation.
        for word in text.split():
            candidate = (line + ' ' + word).strip()
            if face.getlength(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
            line = ''
            for char in word:
                if face.getlength(line + char) > width and line:
                    lines.append(line)
                    line = ''
                line += char
        if line:
            lines.append(line)
        if len(lines) <= 2 and fs * 1.35 * len(lines) <= height and all(face.getlength(l) <= width for l in lines):
            return lines, fs
    raise ValueError('Chữ tràn vùng: tăng vùng nền hoặc rút gọn/chia câu rồi preview.')


def story_events(rows, width, height, box, font, size=36, minimum=18):
    """Make caption-only events inside measured VO spans without changing rows.

    Times are word-count approximations, not forced word alignment. Translation
    slices retain their boundary whitespace, so joining them reconstructs the
    original text exactly; export() strips this whitespace for display.
    """
    _, _, w, h = box
    events = []
    punctuation = re.compile(r'''[.!?;,:…。！？；，]["'”’»\)\]]*$''')
    for row in rows:
        text = row['translation']
        words = list(re.finditer(r'\S+', text))
        if not words:
            raise ValueError(f"Bản dịch rỗng: {row['id']}")
        try:
            start, end = float(row['final_start']), float(row['final_end'])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Cần thời gian giọng đã đo để chia phụ đề: {row['id']}") from exc
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError(f"Mốc thời gian giọng sai: {row['id']}")

        offset, previous_end, char_start, chunk_number = 0, start, 0, 0
        while offset < len(words):
            fitting, boundary = 0, 0
            for count in range(1, min(8, len(words) - offset) + 1):
                candidate = text[words[offset].start():words[offset + count - 1].end()]
                try:
                    layout(candidate, font, size, minimum, w * width - 12, h * height - 8)
                except ValueError:
                    break
                fitting = count
                if punctuation.search(words[offset + count - 1].group()):
                    boundary = count
            if not fitting:
                raise ValueError(f"Một từ vẫn tràn vùng phụ đề: {row['id']}. Tăng vùng hoặc giảm cỡ chữ.")

            count = boundary or fitting
            offset += count
            chunk_number += 1
            final_chunk = offset == len(words)
            char_end = len(text) if final_chunk else words[offset].start()
            chunk_end = end if final_chunk else start + (end - start) * offset / len(words)
            if chunk_end <= previous_end:
                raise ValueError(f"Khoảng giọng quá ngắn để chia phụ đề: {row['id']}")
            events.append({**row, 'id': f"{row['id']}:caption:{chunk_number}",
                           'caption_parent_id': row['id'],
                           'translation': text[char_start:char_end],
                           'start': previous_end, 'end': chunk_end,
                           'final_start': previous_end, 'final_end': chunk_end,
                           'timing_method': 'word_count_approximation'})
            previous_end, char_start = chunk_end, char_end
    return events


def export(job, rows, width, height, box, font, size=36, minimum=18):
    x, y, w, h = box
    header = f'''[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,3,2,0,5,0,0,0,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
    ass, srt = [header], []
    for i, s in enumerate(rows, 1):
        text = s['translation'].strip()
        if not text:
            raise ValueError(f"Bản dịch rỗng: {s['id']}")
        lines, fs = layout(text, font, size, minimum, w*width-12, h*height-8)
        safe = '\\N'.join(l.replace('\\', '／').replace('{', '｛').replace('}', '｝') for l in lines)
        pos = f'{{\\an5\\pos({(x+w/2)*width:.1f},{(y+h/2)*height:.1f})\\fs{fs}}}'
        a, b = s.get('final_start', s['start']), s.get('final_end', s['end'])
        ass.append(f'Dialogue: 0,{stamp(a,True)},{stamp(b,True)},Default,,0,0,0,,{pos}{safe}\n')
        srt.append(f'{i}\n{stamp(a)} --> {stamp(b)}\n{text}\n')
    (job/'captions.ass').write_text(''.join(ass), encoding='utf-8-sig')
    (job/'captions.srt').write_text('\n'.join(srt), encoding='utf-8-sig')
