import shutil
from pathlib import Path
from . import captions, narration
from .media import probe
from .providers import speech, synthesis_config
from .store import save, read, checksum, checkpoint


def regions_valid(regions, duration):
    import math
    for r in regions:
        x,y,w,h = r['bbox']
        if not all(math.isfinite(float(v)) for v in (x,y,w,h,r['start'],r['end'])):
            raise ValueError('Vùng chứa giá trị không hữu hạn.')
        if not (0 <= x < 1 and 0 <= y < 1 and w > 0 and h > 0 and x+w <= 1.000001 and y+h <= 1.000001):
            raise ValueError('Vùng che nằm ngoài khung hình.')
        if not 0 <= r['start'] < r['end'] <= duration+.05:
            raise ValueError('Thời gian vùng che không hợp lệ.')
        if not r.get('approved'):
            raise ValueError('Cần duyệt tất cả vùng OCR trước khi render.')


def build_audio(job, rows, cfg, runner):
    # A failed rebuild must not leave a previous voice marked ready.
    (job/'tts_rows.json').unlink(missing_ok=True)
    duration = probe(job/'source.mp4', runner)['duration']
    captions.validate(rows, duration)
    story_mode = narration.is_story(rows)
    if story_mode:
        if cfg.get('language') != 'en':
            raise ValueError('Kịch bản tiếng Anh cần mã ngôn ngữ giọng en.')
        narration.require_script_review(job,rows,duration)
    manifest, issues = [], []
    for i,s in enumerate(rows):
        runner.check()
        runner.message = f'Tạo giọng {i+1}/{len(rows)}'
        next_start = rows[i+1]['start'] if i+1<len(rows) else duration
        available = next_start - s['start'] - (.05 if i+1<len(rows) else 0)
        if s.get('lock_end'):
            available = min(available,s['end']-s['start'])
        if s['end'] > next_start or available <= 0:
            issues.append({'id': s['id'], 'reason': 'source_overlap'})
            continue
        path, length = speech(s['tts_text'], cfg, job/'cache', runner)
        speed = max(1., length/available)
        if speed > 1.15:
            issues.append({'id': s['id'], 'reason': 'speech_overflow', 'seconds': length, 'available': available})
            continue
        out = job/f'voice_{i:05}.wav'
        runner.run(['ffmpeg','-v','error','-y','-i',path,'-af',f'atempo={speed},afade=t=in:d=0.01',
                    '-ar','48000','-ac','2',out])
        actual = probe(out, runner)['duration']
        final_start=round(s['start']*1000)/1000
        if s.get('lock_end') and final_start+actual>s['end']+.03:
            issues.append({'id':s['id'],'reason':'locked_window_overflow','seconds':actual,'available':available})
            continue
        manifest.append({'id':s['id'], 'path':out.name, 'checksum':checksum(out), 'duration':actual,
                         'speed':speed, 'final_start':final_start, 'final_end':final_start+actual})
    save(job/'review_report.json', issues)
    save(job/'audio_manifest.json', manifest)
    if issues:
        raise ValueError('Có câu chồng/tràn thời lượng. Xem báo cáo, sửa lời đọc và tạo lại; cache được giữ.')
    if story_mode:
        save(job/'story_timing.json',narration.timing_report(rows,manifest,duration))
    args = ['ffmpeg','-v','error','-y','-f','lavfi','-i',f'anullsrc=r=48000:cl=stereo:d={duration}']
    filters, labels = [], ['[0:a]']
    for i,m in enumerate(manifest,1):
        args += ['-i',job/m['path']]
        ms = round(m['final_start']*1000)
        filters.append(f'[{i}:a]adelay={ms}|{ms}[d{i}]')
        labels.append(f'[d{i}]')
    filters.append(''.join(labels)+f'amix=inputs={len(labels)}:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]')
    runner.run(args+['-filter_complex',';'.join(filters),'-map','[a]','-t',str(duration),job/'dubbed.wav'])
    save(job/'tts_config.json', synthesis_config(cfg))
    checkpoint(job, 'tts', {'rows': rows, 'provider': synthesis_config(cfg)},
               [job/'dubbed.wav', job/'audio_manifest.json'])


def render(job, rows, regions, cfg, runner, preview=False):
    source = job/'source.mp4'
    info = probe(source, runner)
    captions.validate(rows, info['duration'])
    regions_valid(regions, info['duration'])
    story_mode=narration.is_story(rows)
    story_revision=narration.final_signature(job,rows,regions,cfg) if story_mode else None
    if story_mode:
        if not cfg['dub'] or cfg['mix']!='story':
            raise ValueError('Kịch bản mới cần chế độ phối lời đọc và tiếng gốc.')
        narration.require_script_review(job,rows,info['duration'])
        if not preview:
            narration.require_final_review(job,rows,regions,cfg)
    issues = []
    if cfg['dub']:
        gains=narration.mix_settings(cfg)
        # A muted voice must not lower the audible background track.
        gains['duck']=gains['duck'] and gains['voice_gain']>0
        if 'tts' in cfg and read(job/'tts_config.json') != synthesis_config(cfg['tts']):
            raise ValueError('Giọng/model/ngôn ngữ đã thay đổi. Tạo lại giọng trước khi xuất.')
        manifest = read(job/'audio_manifest.json', [])
        saved = read(job/'job.json')['steps'].get('tts', {})
        # Compare content separately: prevent edited text being paired with stale speech.
        if read(job/'tts_rows.json') != rows or not (job/'dubbed.wav').exists():
            raise ValueError('Bản dịch đã thay đổi hoặc chưa có giọng. Tạo lại giọng trước khi xuất.')
        if saved.get('outputs', {}).get('dubbed.wav') != checksum(job/'dubbed.wav'):
            raise ValueError('Audio checkpoint không hợp lệ.')
        if saved.get('outputs', {}).get('audio_manifest.json') != checksum(job/'audio_manifest.json'):
            raise ValueError('Timeline audio checkpoint không hợp lệ; tạo lại giọng.')
        lookup = {m['id']:m for m in manifest}
        rows = [{**s, 'final_start': lookup[s['id']]['final_start'], 'final_end': lookup[s['id']]['final_end']} for s in rows]
    try:
        caption_rows = captions.story_events(rows,info['width'],info['height'],cfg['subtitle_box'],cfg['font'],cfg['font_size']) if story_mode else rows
        captions.export(job, caption_rows, info['width'], info['height'], cfg['subtitle_box'], cfg['font'], cfg['font_size'])
    except ValueError as e:
        save(job/'review_report.json', [{'reason': 'subtitle_overflow', 'message': str(e)}])
        raise
    args = ['ffmpeg','-v','error','-y','-i','source.mp4']
    graph, current = [], '[0:v]'
    for i,r in enumerate(regions):
        x,y,w,h = r['bbox']; W,H = info['width'],info['height']
        xx,yy,ww,hh = int(x*W),int(y*H),max(2,int(w*W)),max(2,int(h*H))
        enable = f"between(t,{r['start']},{r['end']})"
        out = f'[m{i}]'
        if cfg['mask'] == 'solid':
            graph.append(f'{current}drawbox=x={xx}:y={yy}:w={ww}:h={hh}:color=black:t=fill:enable=\'{enable}\'{out}')
        else:
            graph.append(f'{current}split[b{i}][c{i}]')
            radius = min(cfg.get('blur', 12), max(1,min(ww,hh)//2-1))
            graph.append(f'[c{i}]crop={ww}:{hh}:{xx}:{yy},boxblur={radius}:2[p{i}]')
            graph.append(f'[b{i}][p{i}]overlay={xx}:{yy}:enable=\'{enable}\'{out}')
            if cfg['mask'] == 'blur_background':
                graph.append(f'{out}drawbox=x={xx}:y={yy}:w={ww}:h={hh}:color=black@0.65:t=fill:enable=\'{enable}\'[n{i}]')
                out = f'[n{i}]'
        current = out
    graph.append(f"{current}ass=captions.ass[v]")
    if cfg['dub']:
        args += ['-i','dubbed.wav']
        if story_mode:
            track='0:a'
            if cfg.get('sound_source')=='background':
                bg=job/'background.wav'
                if not bg.exists():
                    raise ValueError('Chưa có stem âm thanh gốc đã chuẩn bị.')
                bg_info=probe(bg,runner)
                if not bg_info['audio'] or abs(bg_info['duration']-info['duration'])>.1:
                    raise ValueError('Stem nền phải có audio và cùng thời lượng video.')
                args += ['-i','background.wav']
                track='2:a'
            elif not info['audio']:
                raise ValueError('Video không có tiếng gốc; cần nhập stem nền để dùng chế độ này.')
            graph += [f'[{track}]{narration.gain_expression(manifest,gains["original_gain"],gains["duck_gain"],gains["duck"])}[bg]',
                      f'[1:a]volume={gains["voice_gain"]}[vo]',
                      '[bg][vo]amix=inputs=2:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]']
        elif cfg['mix'] == 'voice_only' or not info['audio']:
            graph.append(f'[1:a]volume={gains["voice_gain"]},alimiter=limit=0.95:level=0:latency=1[a]')
        elif cfg['mix'] == 'narration':
            graph += [f'[0:a]{narration.gain_expression(manifest,gains["original_gain"],gains["duck_gain"],gains["duck"])}[bg]',
                      f'[1:a]volume={gains["voice_gain"]}[vo]',
                      '[bg][vo]amix=inputs=2:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]']
        else:
            background = job/'background.wav'
            if not background.exists():
                raise ValueError('Chưa có stem nền. Tách bằng Demucs hoặc nhập stem nền trước khi xuất.')
            bg_info = probe(background,runner)
            if abs(bg_info['duration']-info['duration']) > .1:
                raise ValueError('Stem nền lệch thời lượng nguồn; kiểm tra đồng bộ trước xuất.')
            args += ['-i','background.wav']
            graph += [f'[2:a]{narration.gain_expression(manifest,gains["original_gain"],gains["duck_gain"],gains["duck"])}[bg]',
                      f'[1:a]volume={gains["voice_gain"]}[vo]',
                      '[bg][vo]amix=inputs=2:normalize=0,alimiter=limit=0.95:level=0:latency=1[a]']
        audio_map = ['-map','[a]']
    else:
        audio_map = ['-map','0:a?']
    target = 'preview.mp4' if preview else 'final.mp4'
    temp = 'render.partial.mp4'
    runner.message = 'Đang render preview' if preview else 'Đang xuất video'
    runner.run(args+['-filter_complex',';'.join(graph),'-map','[v]']+audio_map+
               ['-t',str(min(20,info['duration']) if preview and not story_mode else info['duration']),
                '-fps_mode','vfr','-c:v','libx264','-preset','fast','-crf','20','-c:a','aac','-movflags','+faststart',temp], cwd=job)
    output_info = probe(job/temp, runner)
    if not preview and abs(output_info['duration']-info['duration']) > .05:
        raise ValueError('Thời lượng đầu ra lệch trên 50 ms; cần kiểm tra.')
    (job/temp).replace(job/target)
    save(job/'review_report.json', issues)
    checkpoint(job, 'preview' if preview else 'render', {'rows':rows,'regions':regions,'config':cfg}, [job/target])
    if story_mode:
        save(job/('story_preview_signature.json' if preview else 'story_render_signature.json'),{'signature':story_revision})
    return job/target
