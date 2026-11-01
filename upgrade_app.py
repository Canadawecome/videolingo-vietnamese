"""New isolated workflow, added 2026-10-30. Start with run-upgrade.cmd."""
import os
import sys
import base64
import threading
from pathlib import Path
import streamlit as st
from upgrade import captions, download, ocr, pipeline, providers, narration, story_ui, edition
from upgrade.media import Runner, normalize, probe
from upgrade.store import create, read, save, checksum, checkpoint, digest
from upgrade.secrets import load_genvoice_key

ROOT = Path(__file__).resolve().parent
EDITION = edition.get_edition(globals().get('APP_EDITION', 'en'))
JOBS = ROOT/'jobs'
JOBS.mkdir(exist_ok=True)
TTS_DEFAULTS = read(ROOT/EDITION.tts_config, {})
st.set_page_config(page_title=EDITION.title, page_icon='🎬', layout='wide')
st.title(EDITION.title)
st.caption('Che phụ đề gốc · Dịch sát nguồn sang tiếng Việt · Lồng tiếng nữ · Xuất video'
           if EDITION.faithful_only else 'Che phụ đề gốc · Dịch có duyệt · Lồng tiếng · Xuất video')


@st.cache_resource
def workflow_lock():
    return threading.Lock()


def start(label, fn):
    task = st.session_state.get('task')
    if task and task['thread'].is_alive():
        st.warning('Một bước đang chạy; hãy dừng hoặc chờ hoàn tất.')
        return
    runner = Runner()
    task = {'runner':runner, 'error':None, 'label':label}
    lock = workflow_lock()
    def work():
        if not lock.acquire(blocking=False):
            task['error'] = 'Một job khác đang chạy. Thử lại sau khi job đó hoàn tất.'
            return
        try:
            fn(runner)
        except Exception as e:
            task['error'] = str(e)
        finally:
            lock.release()
    task['thread'] = threading.Thread(target=work, daemon=True)
    st.session_state.task = task
    task['thread'].start()
    st.rerun()


@st.fragment(run_every=1)
def progress():
    task = st.session_state.get('task')
    if not task:
        return
    if task['thread'].is_alive():
        st.info(task['runner'].message or task['label'])
        if st.button('Dừng bước đang chạy'):
            task['runner'].cancel.set()
    elif task['error']:
        st.error(task['error'])
    else:
        st.success(task['label']+' — hoàn tất')
    if not task['thread'].is_alive() and st.button('Cập nhật kết quả'):
        st.session_state.pop('task', None)
        st.rerun()


with st.sidebar:
    st.header('Dự án')
    if st.button('＋ Tạo job'):
        st.session_state.job = str(create(JOBS))
        st.rerun()
    jobs = sorted([p.name for p in JOBS.iterdir() if p.is_dir()], reverse=True)
    if not jobs:
        st.session_state.job = str(create(JOBS))
        st.rerun()
    selected = st.selectbox('Mở job', jobs, index=jobs.index(Path(st.session_state.get('job',JOBS/jobs[0])).name))
    job = JOBS/selected
    st.session_state.job = str(job)
    st.caption(f'Job {selected}')
    language = st.text_input('Ngôn ngữ đích', EDITION.target_language if EDITION.faithful_only else
                             ('English' if TTS_DEFAULTS.get('language') == 'en' else 'Vietnamese'))
    context = st.text_area('Ngữ cảnh / tên riêng / xưng hô')
    with st.expander('Dịch — Trouter'):
        llm = {'base':st.text_input('Base URL dịch',os.getenv('TROUTER_BASE_URL','https://api.trouter.cloud/v1')),
               'key':st.text_input('TROUTER_API_KEY',os.getenv('TROUTER_API_KEY',''),type='password'),
               'model':st.text_input('Model dịch',os.getenv('TRANSLATION_MODEL_ID','gpt-5.6-sol'))}
        if st.button('Kiểm tra model dịch'):
            try:
                st.write(providers.models(llm))
            except Exception as e:
                st.error(str(e))
    with st.expander('Giọng — Genvoice'):
        st.caption('Genvoice · ElevenLabs. Tạo giọng theo tác vụ nền, có lưu task để tiếp tục khi gián đoạn.')
        base = st.text_input('Base URL TTS',os.getenv('GENVOICE_BASE_URL',TTS_DEFAULTS.get('base','https://api.genvoice.pro')))
        typed_key = st.text_input('API key khác (để trống để dùng key đã lưu)',type='password')
        stored_key = load_genvoice_key() if base.rstrip('/') == 'https://api.genvoice.pro' else ''
        if stored_key and not typed_key:
            st.caption('Đang dùng key từ biến môi trường / Windows Credential Manager.')
        tts = {**TTS_DEFAULTS, 'base':base, 'key':typed_key or stored_key,
               'protocol':'genvoice_async','provider':'elevenlabs',
               'route':'/v1/text-to-speech/{voice_id}','header':'xi-api-key','prefix':'','verified':True}
        tts['language'] = st.text_input('Mã ngôn ngữ giọng',TTS_DEFAULTS.get('language',EDITION.tts_language))
        if st.button('Cập nhật danh sách giọng / model'):
            try:
                catalog = providers.genvoice_catalog(tts)
                save(ROOT/'runtime'/'genvoice_models.json',catalog['models'])
                save(ROOT/'runtime'/'genvoice_voices.json',{'voices':catalog['voices']})
                st.success('Đã kiểm tra kết nối và cập nhật danh sách.')
            except Exception as e:
                st.error(str(e))
        catalog_voices = read(ROOT/'runtime'/'genvoice_voices.json',{}).get('voices',[])
        female_voices = [v for v in catalog_voices if v.get('gender')=='female' and
                         (v.get('language') == tts['language'] or any(l.get('language')==tts['language'] for l in v.get('verified_languages',[])))]
        voice_ids = [v['voice_id'] for v in female_voices]
        voice_labels = {v['voice_id']:v['name'] for v in female_voices}
        default_voice = os.getenv('GENVOICE_VI_VOICE_ID' if EDITION.faithful_only else 'GENVOICE_VOICE_ID',TTS_DEFAULTS.get('voice',''))
        if EDITION.faithful_only and voice_ids and default_voice and default_voice not in voice_ids:
            voice_ids.insert(0,default_voice)
            voice_labels[default_voice]=TTS_DEFAULTS.get('voice_name',default_voice) if default_voice==TTS_DEFAULTS.get('voice') else default_voice
        if voice_ids:
            tts['voice'] = st.selectbox('Giọng nữ',voice_ids,index=voice_ids.index(default_voice) if default_voice in voice_ids else 0,format_func=lambda x:voice_labels[x])
        else:
            tts['voice'] = st.text_input('Voice ID',default_voice)
        model_rows = read(ROOT/'runtime'/'genvoice_models.json',[])
        model_ids = [m['model_id'] for m in model_rows if m.get('can_do_text_to_speech') and
                     any(l.get('language_id') == tts['language'] for l in m.get('languages',[]))]
        default_model = os.getenv('GENVOICE_VI_MODEL_ID' if EDITION.faithful_only else 'GENVOICE_MODEL_ID',TTS_DEFAULTS.get('model',''))
        if model_ids:
            tts['model'] = st.selectbox('Model TTS',model_ids,index=model_ids.index(default_model) if default_model in model_ids else 0)
        else:
            tts['model'] = st.text_input('Model TTS',default_model)
        chosen_model = next((m for m in model_rows if m['model_id']==tts['model']),{})
        tts['settings'] = {'stability':.5,'similarity_boost':.75,'speed':1.0}
        if chosen_model.get('can_use_style'):
            tts['settings']['style']=0.
        if chosen_model.get('can_use_speaker_boost'):
            tts['settings']['use_speaker_boost']=True
        preview_text = st.text_area('Câu nghe thử',EDITION.sample_text)
        if st.button('Thử giọng ngắn (gọi API)'):
            def preview_voice(r):
                import shutil
                path,_ = providers.speech(preview_text,tts,job/'cache',r)
                shutil.copy2(path,job/EDITION.sample_file)
            start('Thử giọng',preview_voice)
        voice_sample = job/EDITION.sample_file
        if not voice_sample.exists():
            voice_sample = ROOT/'demo'/('vietnamese-female-preview.mp3' if EDITION.faithful_only else 'bella-english-preview.mp3')
        if voice_sample.exists():
            sample_label=('Mẫu nữ tiếng Việt · '+TTS_DEFAULTS.get('voice_name','cấu hình mặc định')) if EDITION.faithful_only else 'Mẫu Bella · tiếng Anh · Multilingual v2 đã tạo thử'
            st.caption('Mẫu mới nhất của job' if voice_sample.parent==job else sample_label)
            st.audio(str(voice_sample))
progress()
busy = st.session_state.get('task') and st.session_state.task['thread'].is_alive()
if busy:
    st.caption('Chờ bước hiện tại hoàn tất trước khi chỉnh dữ liệu hoặc đổi job.')
    st.stop()
tabs = st.tabs(['1 · Video','2 · Vùng che','3 · Nội dung','4 · Giọng & xuất'])
with tabs[0]:
    upload = st.file_uploader('Nhập video',type=['mp4','mkv','mov','webm','avi'])
    if upload and st.button('Nạp video',disabled=(job/'source.mp4').exists()):
        src = job/('input'+Path(upload.name).suffix)
        src.write_bytes(upload.getbuffer())
        def ingest(r):
            normalize(src,job/'source.mp4',r)
            checkpoint(job,'ready',{'source_checksum':checksum(src)},[job/'source.mp4'])
        start('Chuẩn hóa video',ingest)
    url = st.text_area('Hoặc dán URL / đoạn chia sẻ')
    quality = st.selectbox('Chất lượng',['1080','720','best'])
    cookie = st.text_input('File cookies cục bộ (tùy chọn)',type='password')
    if st.button('Phân tích link'):
        try:
            clean = download.extract_url(url)
            st.session_state.download_info = (clean,download.inspect(clean))
        except Exception as e:
            st.error(str(e))
    inspected = st.session_state.get('download_info')
    if inspected:
        clean, meta = inspected
        st.write(meta['title'])
        if meta['entries']:
            entry = st.selectbox('Chọn đúng một phần',meta['entries'],format_func=lambda e:e['title'] or e['id'])
            clean = entry['url']
        if st.button('Tải video đã chọn',disabled=(job/'source.mp4').exists()):
            def fetch(r):
                src = download.download(clean,job,quality,r,cookie or None)
                normalize(src,job/'source.mp4',r)
                checkpoint(job,'ready',{'source_checksum':checksum(src)},[job/'source.mp4'])
            start('Tải video',fetch)
    if (job/'source.mp4').exists():
        st.video(str(job/'source.mp4'))
if not (job/'source.mp4').exists():
    st.stop()
info = probe(job/'source.mp4')
with tabs[1]:
    st.caption('Tọa độ theo tỷ lệ 0–1 trên video đã chuẩn hóa. OCR là đề xuất, bắt buộc duyệt trước xuất.')
    import streamlit.components.v1 as components
    picker = components.declare_component('region_picker',path=str(ROOT/'upgrade'/'region_component'))
    at = st.slider('Khung hình xem vùng (giây)',0.,max(.1,info['duration']-.05),min(1.,max(0.,info['duration']-.05)),step=.1)
    frame = job/'region_frame.jpg'
    if read(job/'frame_time.json') != at or not frame.exists():
        Runner().run(['ffmpeg','-v','error','-y','-ss',str(at),'-i',job/'source.mp4','-frames:v','1',frame])
        save(job/'frame_time.json',at)
    initial_box = read(job/'subtitle_box.json',[.05,.75,.9,.2])
    picked = picker(image='data:image/jpeg;base64,'+base64.b64encode(frame.read_bytes()).decode(),box=initial_box,default=initial_box,key=f'picker_{selected}')
    if picked != initial_box:
        save(job/'subtitle_box.json',picked)
        st.rerun()
    cols = st.columns(4)
    roi = [cols[i].number_input(label,0.,1.,float(value),step=.01,key=f'{selected}_{i}_{value}') for i,(label,value) in enumerate(zip(['Trái','Trên','Rộng','Cao'],picked))]
    languages = st.text_input('Mã ngôn ngữ EasyOCR, cách nhau dấu phẩy','ch_sim,en')
    if st.button('Quét OCR'):
        def detect(r):
            pipeline.regions_valid([{'bbox':roi,'start':0,'end':info['duration'],'approved':True}],info['duration'])
            regions,samples = ocr.scan(job/'source.mp4',roi,languages.split(','),r)
            save(job/'ocr_regions.json',regions)
            save(job/'ocr_samples.json',samples)
        start('Phân tích OCR',detect)
    if st.button('Dùng vùng thủ công cho toàn video'):
        regions = [{'id':'manual1','start':0.,'end':info['duration'],'bbox':roi,'confidence':1.,'source':'manual','approved':True}]
        try:
            pipeline.regions_valid(regions,info['duration'])
            save(job/'ocr_regions.json',regions)
            st.success('Đã lưu vùng thủ công.')
        except Exception as e:
            st.error(str(e))
    regions = read(job/'ocr_regions.json',[])
    flat = [{**{k:v for k,v in r.items() if k!='bbox'},**dict(zip(['x','y','w','h'],r['bbox']))} for r in regions]
    if flat:
        edited = st.data_editor(flat,num_rows='dynamic',key=f'regions_{selected}')
        if st.button('Lưu chỉnh vùng'):
            try:
                updated = [{**{k:v for k,v in r.items() if k not in ('x','y','w','h')},'bbox':[r[k] for k in ('x','y','w','h')]} for r in edited]
                pipeline.regions_valid(updated,info['duration'])
                save(job/'ocr_regions.json',updated)
                st.success('Đã lưu.')
            except Exception as e:
                st.error(str(e))
    if st.button('Không che sub gốc'):
        save(job/'ocr_regions.json',[])
        st.rerun()
with tabs[2]:
    translation_blocked = EDITION.faithful_only and narration.is_story(read(job/'segments.json',[]))
    st.caption('Nhận dạng bằng Qwen của VideoLingo hoặc nhập transcript SRT. Qwen cần cài đầy đủ dependency upstream và tải model lần đầu.')
    source_language = st.text_input('Ngôn ngữ nguồn (auto, zh, en, vi...)','auto')
    if st.button('Nhận dạng Qwen + căn thời gian',disabled=translation_blocked):
        def transcribe(r):
            import importlib.util
            if not importlib.util.find_spec('qwen_asr'):
                raise ValueError('Chưa cài Qwen: chạy python installer.py trong thư mục VideoLingo, hoặc nhập SRT để tiếp tục.')
            r.run([sys.executable,ROOT/'upgrade'/'asr_worker.py',job,source_language])
            save(job/'source_segments.json',read(job/'segments.json'))
            checkpoint(job,'asr',{'source':checksum(job/'source.mp4'),'language':source_language},[job/'segments.json'])
        start('Nhận dạng lời nói',transcribe)
    sub = st.file_uploader('Transcript SRT',type=['srt'])
    if sub and st.button('Nhập transcript',disabled=translation_blocked):
        try:
            rows = captions.import_srt(sub.getvalue().decode('utf-8-sig'))
            captions.validate(rows,info['duration'])
            save(job/'segments.json',rows)
            save(job/'source_segments.json',rows)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    rows = read(job/'segments.json',[])
    if EDITION.faithful_only:
        method='Dịch sát nguồn'
        st.info('Dịch sát nội dung gốc sang tiếng Việt: giữ dữ kiện, thứ tự câu và mốc thời gian. Chỉ sửa bản dịch và lời đọc sau khi đối chiếu nguồn.')
        if narration.is_story(rows):
            st.warning('Job này đang dùng kịch bản viết mới. Khôi phục transcript nguồn để dịch tiếng Việt; bản kịch bản hiện tại sẽ được giữ thành bản sao riêng.')
            source_rows=read(job/'source_segments.json',[])
            can_restore=bool(source_rows) and not narration.is_story(source_rows)
            if st.button('Khôi phục transcript nguồn để dịch tiếng Việt',disabled=not can_restore):
                try:
                    edition.restore_source_for_translation(job,info['duration'])
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
            if not can_restore:
                st.error('Không tìm thấy transcript nguồn hợp lệ. Tạo job mới và nhập transcript để giữ nguyên kịch bản hiện tại.')
    else:
        method=st.radio('Cách tạo nội dung',['Viết kịch bản từ dữ kiện','Dịch sát nguồn'],horizontal=True)
    if rows and method=='Viết kịch bản từ dữ kiện':
        story_ui.editor(job,info,context,llm,start)
    elif rows and not narration.is_story(rows):
        edited = st.data_editor(rows,num_rows='fixed' if EDITION.faithful_only else 'dynamic',
                                disabled=['id','source','start','end'] if EDITION.faithful_only else ['id'],
                                key=f'segments_{selected}_{digest(rows)}')
        if st.button('Lưu bản dịch và lời đọc' if EDITION.faithful_only else 'Lưu nội dung và thời gian'):
            try:
                if EDITION.faithful_only:
                    edition.validate_translation_edit(edited,rows,info['duration'])
                else:
                    captions.validate(edited,info['duration'])
                save(job/'segments.json',edited)
                st.success('Đã lưu; cần tạo lại giọng nếu đổi nội dung.')
            except Exception as e:
                st.error(str(e))
        if st.button('Dịch bằng Trouter (gọi API)'):
            def translate(r):
                translated = providers.translate(rows,language,context,llm,r)
                if EDITION.faithful_only:
                    edition.validate_translation_edit(translated,rows,info['duration'])
                save(job/'segments.json',translated)
            start('Dịch nội dung',translate)
with tabs[3]:
    active_rows=read(job/'segments.json',[])
    story_mode=narration.is_story(active_rows)
    if EDITION.faithful_only and story_mode:
        st.info('Sang tab Nội dung và khôi phục transcript nguồn trước khi tạo giọng hoặc xuất bản tiếng Việt.')
        st.stop()
    sound_source='original'
    if story_mode:
        dub=True; mix='story'
        st.info('Kịch bản mới: Hook 3 giây → Conflict → Punchline bằng tiếng Anh.')
        sound_source=st.selectbox('Nguồn tiếng động',['original','background'],format_func=lambda x:'Âm thanh gốc trong video' if x=='original' else 'Stem nền / tiếng động đã chuẩn bị')
        st.caption('Tiếng gốc có thể gồm cả thoại và nhạc; dùng stem nền nếu muốn tách khỏi lời thoại cũ.')
    else:
        dub = st.checkbox('Lồng tiếng',value=EDITION.faithful_only)
        mix = st.selectbox('Âm thanh',['narration','replace','voice_only'],format_func=lambda x:{'narration':'Thuyết minh: giảm và duck tiếng gốc','replace':'Thay thoại: giữ stem nền đã tách','voice_only':'Chỉ giọng mới: bỏ tiếng gốc'}[x])
    voice_gain,original_gain,duck_gain,duck=1.,.4,.15,True
    if dub:
        volume_cols=st.columns(2)
        voice_gain=volume_cols[0].slider('Âm lượng thuyết minh (%)',0,150,100,key=f'vo_gain_{job.name}')/100
        original_gain=volume_cols[1].slider('Âm lượng tiếng gốc / nền (%)',0,100,40,key=f'bg_gain_{job.name}')/100
        duck=st.checkbox('Tự hạ tiếng gốc khi có lời thuyết minh',True,key=f'duck_{job.name}')
        if duck:
            duck_gain=st.slider('Tiếng gốc khi có lời đọc (%)',0,100,15,key=f'duck_gain_{job.name}')/100
            if duck_gain>original_gain:
                st.caption(f'Tiếng gốc dưới lời đọc sẽ giới hạn ở {original_gain:.0%}, bằng mức nền đã chọn.')
        st.caption('Mặc định: giọng 100%, nền 40%, nền dưới lời đọc 15%. Mỗi mức chỉnh riêng so với âm lượng ban đầu của lớp tiếng đó, không cần cộng thành 100% và không chia thời lượng video. Hãy nghe video xem trước để cân lại theo nguồn.')
    if mix == 'replace' or (story_mode and sound_source=='background'):
        background = st.file_uploader('Stem nền đã tách, cùng mốc bắt đầu và thời lượng',type=['wav','mp3','flac'])
        if background and st.button('Nạp stem nền'):
            input_bg = job/('background_input'+Path(background.name).suffix)
            input_bg.write_bytes(background.getbuffer())
            def load_bg(r):
                r.run(['ffmpeg','-v','error','-y','-i',input_bg,'-ar','48000','-ac','2',job/'background.wav'])
            start('Nạp stem nền',load_bg)
        if st.button('Tách nền bằng Demucs (cần cài demucs)'):
            def separate(r):
                r.run([sys.executable,'-m','demucs','--two-stems','vocals','-o',job/'stems',job/'source.mp4'])
                stem = next((job/'stems').rglob('no_vocals.wav'),None)
                if stem is None:
                    raise ValueError('Demucs không tạo stem nền; chọn chế độ khác hoặc nhập stem.')
                import shutil
                shutil.copy2(stem,job/'background.wav')
            start('Tách nền',separate)
    mask = st.selectbox('Kiểu che',['solid','blur','blur_background'])
    font = st.text_input('Font đo bố cục',str(Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/'arial.ttf'))
    font_size = st.slider('Cỡ chữ',18,90,36)
    st.caption('Vị trí sub dùng khung bên tab Vùng che; sub dài sẽ bị chặn nếu không vừa tối đa hai dòng.')
    config = {'dub':dub,'mix':mix,'mask':mask,'subtitle_box':roi,'font':font,'font_size':font_size,
              'tts':providers.synthesis_config(tts),'sound_source':sound_source,
              'voice_gain':voice_gain,'original_gain':original_gain,'duck_gain':duck_gain,'duck':duck}
    rows = read(job/'segments.json',[])
    if st.button('Tạo / cập nhật giọng (gọi API)',disabled=not rows):
        def voices(r):
            pipeline.build_audio(job,rows,tts,r)
            save(job/'tts_rows.json',rows)
        start('Tạo giọng',voices)
    regions=read(job/'ocr_regions.json',[])
    review_id=narration.final_signature(job,rows,regions,config) if story_mode else digest({'job':job.name,'rows':rows,'regions':regions,'config':config})
    reviewed = st.checkbox('Đã nghe/xem trước, duyệt nội dung, tiếng gốc và tất cả vùng che',key=f'review_{review_id}')
    preview_label='Xem trước toàn bộ kịch bản' if story_mode else 'Xem trước 20 giây'
    if st.button(preview_label,disabled=not rows):
        start(preview_label,lambda r:pipeline.render(job,rows,regions,config,r,True))
    if st.button('Xuất MP4',disabled=not reviewed or not rows):
        if story_mode:
            save(job/'story_final_approval.json',{'signature':review_id})
        start('Xuất MP4',lambda r:pipeline.render(job,rows,regions,config,r,False))
    for name in ['preview.mp4','final.mp4']:
        if story_mode and read(job/('story_preview_signature.json' if name=='preview.mp4' else 'story_render_signature.json'),{}).get('signature')!=review_id:
            continue
        if (job/name).exists():
            st.video(str(job/name))
    audio_current=(read(job/'tts_rows.json')==rows and read(job/'tts_config.json')==config['tts'])
    if audio_current and (job/'dubbed.wav').exists():
        st.caption('Nghe riêng giọng đã tạo. Âm lượng phối với tiếng gốc áp dụng trong video xem trước / video xuất.')
        st.audio(str(job/'dubbed.wav'))
    for name in ['final.mp4','captions.srt','captions.ass','dubbed.wav','review_report.json']:
        if name=='dubbed.wav' and not audio_current:
            continue
        if story_mode and name in ('final.mp4','captions.srt','captions.ass') and read(job/'story_render_signature.json',{}).get('signature')!=review_id:
            continue
        if (job/name).exists():
            st.download_button('Tải '+name,(job/name).read_bytes(),file_name=name)
    report = read(job/'review_report.json',[])
    if report:
        st.json(report)
