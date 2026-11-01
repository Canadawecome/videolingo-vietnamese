"""Narration timing and independent voice/background gain controls."""
import math
from . import captions
from .store import read, save, digest, checksum


def make_slots(duration):
    if not math.isfinite(duration) or duration < 10:
        raise ValueError('Chế độ kịch bản cần video dài ít nhất 10 giây.')
    hook, ending = 3., min(4., max(2., duration*.16))
    middle = duration-hook-ending
    count = max(1, math.ceil(middle/5))
    slots = [{'id':'story_hook','start':0.,'end':hook,'role':'hook'}]
    cursor = hook
    for i in range(count):
        end = cursor+middle/count
        slots.append({'id':f'story_conflict_{i+1:03}','start':round(cursor,6),'end':round(end,6),'role':'conflict'})
        cursor = end
    slots.append({'id':'story_punchline','start':round(duration-ending,6),'end':duration,'role':'punchline'})
    return slots


def complement(intervals, duration):
    merged = []
    for start,end in sorted(intervals):
        start,end=max(0.,start),min(duration,end)
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1][1]=max(merged[-1][1],end)
        else:
            merged.append([start,end])
    gaps=[]; cursor=0.
    for start,end in merged:
        if start>cursor+1e-6:
            gaps.append({'start':cursor,'end':start})
        cursor=end
    if cursor<duration-1e-6:
        gaps.append({'start':cursor,'end':duration})
    return gaps


def validate_slots(slots, duration):
    captions.validate(slots,duration)
    if len(slots)<3 or slots[0].get('role')!='hook' or slots[-1].get('role')!='punchline':
        raise ValueError('Cần hook, phần xung đột/thách thức và punchline theo thứ tự.')
    if abs(slots[0]['start'])>1e-6 or abs(slots[0]['end']-3)>1e-6:
        raise ValueError('Hook phải nằm trong 0–3 giây.')
    if any(s.get('role')!='conflict' for s in slots[1:-1]):
        raise ValueError('Các đoạn giữa phải là conflict.')
    if any(a['end']>b['start'] for a,b in zip(slots,slots[1:])):
        raise ValueError('Các cửa sổ lời đọc không được chồng nhau.')
    return slots


def is_story(rows):
    return any(s.get('mode')=='story' for s in rows)


def facts_signature(source, facts):
    return digest({'source':source,'facts':facts})


def script_signature(job, rows):
    return digest({'source':read(job/'source_segments.json',[]),
                   'facts':read(job/'story_facts.json',{}),
                   'slots':read(job/'story_slots.json',[]),'rows':rows})


def require_script_review(job, rows, duration):
    from .story import validate_facts, validate_story
    if not all(s.get('mode')=='story' and s.get('lock_end') is True for s in rows):
        raise ValueError('Không trộn câu dịch thường vào kịch bản mới.')
    slots=validate_slots(read(job/'story_slots.json',[]),duration)
    facts=read(job/'story_facts.json',{})
    source=read(job/'source_segments.json',[])
    validate_facts(facts,source)
    validate_story({'segments':rows},facts,slots)
    if read(job/'story_facts_approval.json',{}).get('signature')!=facts_signature(source,facts):
        raise ValueError('Dữ kiện đã thay đổi hoặc chưa được duyệt.')
    if read(job/'story_script_approval.json',{}).get('signature')!=script_signature(job,rows):
        raise ValueError('Kịch bản/lịch đọc đã thay đổi. Duyệt lại trước khi tạo giọng.')


def timing_report(rows, manifest, duration):
    lookup={s['id']:s for s in rows}
    intervals=[]
    for m in manifest:
        row=lookup[m['id']]
        start,end=m['final_start'],m['final_end']
        if end>row['end']+.03 or start<row['start']-.001:
            raise ValueError('Audio vượt cửa sổ lời đọc đã duyệt.')
        intervals.append((start,end))
    gaps=complement(intervals,duration)
    original_seconds=sum(s['end']-s['start'] for s in gaps)
    voice_seconds=duration-original_seconds
    return {'duration':duration,
            'narration_seconds':voice_seconds,'original_only_seconds':original_seconds,
            'original_only_intervals':gaps,
            'measurement':'Thời lượng file giọng dùng để căn phụ đề; âm lượng nền được chỉnh riêng, không áp tỷ lệ thời gian.'}


def mix_settings(cfg):
    values={name:float(cfg.get(name,default)) for name,default in
            [('voice_gain',1.),('original_gain',.4),('duck_gain',.15)]}
    if any(not math.isfinite(v) or not 0<=v<=1.5 for v in values.values()):
        raise ValueError('Âm lượng phải nằm trong 0–150%.')
    values['duck_gain']=min(values['duck_gain'],values['original_gain'])
    values['duck']=bool(cfg.get('duck',True))
    return values


def gain_expression(manifest, original_gain=.4, duck_gain=.15, duck=True):
    """Absolute gain, with 100 ms fades around VO spans; not a duration quota."""
    settings=mix_settings({'original_gain':original_gain,'duck_gain':duck_gain,'duck':duck})
    original_gain,duck_gain=settings['original_gain'],settings['duck_gain']
    if not duck or not manifest:
        return f'volume={original_gain}'
    envelopes=[]
    for m in manifest:
        start,end=float(m['final_start']),float(m['final_end'])
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:
            raise ValueError('Timeline lời đọc không hợp lệ.')
        envelopes.append(f'min(clip((t-{start-.1:.6f})/0.1,0,1),clip(({end+.1:.6f}-t)/0.1,0,1))')
    active=envelopes[0]
    for envelope in envelopes[1:]:
        active=f'max({active},{envelope})'
    return f"volume='if(isnan(t),{original_gain},{original_gain}-({original_gain}-{duck_gain})*({active}))':eval=frame"


def final_signature(job, rows, regions, cfg):
    files=['audio_manifest.json','dubbed.wav','story_timing.json','source.mp4']
    if cfg.get('sound_source')=='background':
        files.append('background.wav')
    return digest({'script':script_signature(job,rows),'regions':regions,'config':cfg,
                   'files':{n:checksum(job/n) if (job/n).exists() else None for n in files}})


def require_final_review(job, rows, regions, cfg):
    signature=final_signature(job,rows,regions,cfg)
    approval=read(job/'story_final_approval.json',{})
    if approval.get('signature')!=signature:
        raise ValueError('Cần nghe/xem trước và duyệt lại âm lượng, kịch bản, vùng che trước xuất cuối.')
