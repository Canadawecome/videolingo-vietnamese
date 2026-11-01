import json
import shutil
from pathlib import Path
from unittest.mock import patch, Mock
import pytest
from upgrade import captions, pipeline, providers
from upgrade.media import Runner, probe
from upgrade.store import create, save, checkpoint, valid


def test_srt_unicode():
    rows = captions.import_srt('1\n00:00:00,100 --> 00:00:01,900\nXin chào Việt Nam!')
    captions.validate(rows,2)
    assert rows[0]['source']=='Xin chào Việt Nam!'


def test_duplicate_and_invalid_time():
    s={'id':'a','start':0,'end':1}
    with pytest.raises(ValueError): captions.validate([s,s],2)
    with pytest.raises(ValueError): captions.validate([{**s,'end':float('nan')}],2)


def test_region_review_and_bounds():
    for box,approved in [([.9,.9,.2,.2],True),([0,0,1,1],False)]:
        with pytest.raises(ValueError):
            pipeline.regions_valid([{'bbox':box,'start':0,'end':1,'approved':approved}],2)


def test_checkpoint_detects_corruption(tmp_path):
    job=create(tmp_path); p=job/'x.txt'; p.write_text('ok')
    checkpoint(job,'test',{},[p]); assert valid(job,'test',{})
    p.write_text('broken'); assert not valid(job,'test',{})


@pytest.mark.parametrize('status',[301,401,402,404])
def test_api_no_retry_or_secret_leak(status):
    with patch('upgrade.providers.requests.request',return_value=Mock(status_code=status)) as request:
        with pytest.raises(providers.ProviderError) as e:
            providers.request('https://example.com','/v1/test','SECRET')
        assert 'SECRET' not in str(e.value)
        assert request.call_count == 1
        assert request.call_args.kwargs['allow_redirects'] is False


def test_429_retry():
    retry=Mock(status_code=429,headers={'Retry-After':'0'})
    success=Mock(status_code=200)
    with patch('upgrade.providers.requests.request',side_effect=[retry,success]) as request:
        assert providers.request('https://example.com','/test','key') is success
        assert request.call_count==2


def test_translation_ids():
    response=Mock()
    response.json.return_value={'choices':[{'message':{'content':'{"segments":[]}'}}]}
    with patch('upgrade.providers.models',return_value=['model']), patch('upgrade.providers.request',return_value=response):
        with pytest.raises(providers.ProviderError):
            providers.translate([{'id':'a','source':'hi','start':0,'end':1}],'vi','',
                                {'base':'https://example.com','model':'model','key':'key'},Runner())


def test_real_render(tmp_path):
    if not shutil.which('ffmpeg'): pytest.skip('FFmpeg missing')
    job=create(tmp_path); r=Runner()
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=25:duration=3',
           '-f','lavfi','-i','sine=frequency=440:duration=3','-c:v','libx264','-c:a','aac',job/'source.mp4'])
    rows=captions.import_srt('1\n00:00:00,300 --> 00:00:02,800\nXin chào Việt Nam!')
    region={'bbox':[.1,.7,.8,.25],'start':0,'end':3,'approved':True}
    for mode in ('solid','blur','blur_background'):
        output=pipeline.render(job,rows,[region],{'dub':False,'mask':mode,'subtitle_box':region['bbox'],
                       'font':'C:/Windows/Fonts/arial.ttf','font_size':28},r)
        assert abs(probe(output)['duration']-3)<.05


def test_timestamp_rounding():
    assert captions.stamp(59.9996)=='00:01:00,000'


def test_tts_cache_and_corruption(tmp_path):
    r=Runner(); source=tmp_path/'test.mp3'
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=0.5',source])
    cfg={'base':'https://example.com','model':'test','voice':'test','route':'/tts/{voice_id}',
         'key':'secret','header':'xi-api-key','prefix':'','verified':True}
    response=Mock(content=source.read_bytes())
    with patch('upgrade.providers.request',return_value=response) as req:
        p,d=providers.speech('hello',cfg,tmp_path/'cache',r)
        providers.speech('hello',cfg,tmp_path/'cache',r)
        assert req.call_count==1
        p.write_bytes(b'broken')
        providers.speech('hello',cfg,tmp_path/'cache',r)
        assert req.call_count==2
        providers.speech('changed',cfg,tmp_path/'cache',r)
        assert req.call_count==3


def test_audio_timing_and_stale_content(tmp_path):
    r=Runner();job=create(tmp_path)
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=size=640x360:duration=3',
           '-f','lavfi','-i','sine=duration=3','-c:v','libx264','-c:a','aac',job/'source.mp4'])
    sound=job/'test.wav'
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=duration=0.5',sound])
    rows=captions.import_srt('1\n00:00:00,100 --> 00:00:02,900\nXin chào!')
    with patch('upgrade.pipeline.speech',return_value=(sound,.5)):
        pipeline.build_audio(job,rows,{},r)
    save(job/'tts_rows.json',rows)
    cfg={'dub':True,'mix':'narration','mask':'solid','subtitle_box':[.1,.7,.8,.25],
         'font':'C:/Windows/Fonts/arial.ttf','font_size':28}
    pipeline.render(job,rows,[],cfg,r)
    assert abs(probe(job/'dubbed.wav')['duration']-3)<.05
    with pytest.raises(ValueError,match='đã thay đổi'):
        pipeline.render(job,[{**rows[0],'tts_text':'Changed'}],[],cfg,r)
    with patch('upgrade.pipeline.speech',return_value=(sound,10)):
        with pytest.raises(ValueError,match='tràn'):
            pipeline.build_audio(job,rows,{},r)
