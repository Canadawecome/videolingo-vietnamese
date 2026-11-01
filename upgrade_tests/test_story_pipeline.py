"""Exercise the fact-review -> speech -> preview -> final path without paid API."""
from array import array
import math
import sys
from unittest.mock import patch
import pytest
from upgrade import narration, story, pipeline
from upgrade.media import Runner,probe
from upgrade.store import create,save,read


@pytest.fixture
def ready_story(tmp_path):
    r=Runner(); job=create(tmp_path)
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=640x360:rate=25:duration=12',
           '-f','lavfi','-i','sine=frequency=440:duration=12','-c:v','libx264','-c:a','aac',job/'source.mp4'])
    voice=job/'test_voice.wav'
    r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=1',voice])
    source=[{'id':'s1','start':0,'end':12,'source':'The video shows moving colors and plays a steady tone.'}]
    facts={'facts':[{'id':'f1','text':'Moving colors appear with a steady tone.','source_ids':['s1']}],
           'takeaways':[{'text':'Motion can appear alongside steady sound.','fact_ids':['f1']}]}
    slots=narration.make_slots(12)
    texts=['Watch these moving colors.','The colors keep moving.','The tone stays steady.','Motion meets steady sound.']
    rows=story.validate_story({'segments':[{'id':s['id'],'role':s['role'],'translation':texts[i],
            'tts_text':texts[i],'fact_ids':['f1']} for i,s in enumerate(slots)]},facts,slots)
    for name,data in [('source_segments.json',source),('story_facts.json',facts),('story_slots.json',slots),('segments.json',rows)]:
        save(job/name,data)
    save(job/'story_facts_approval.json',{'signature':narration.facts_signature(source,facts)})
    save(job/'story_script_approval.json',{'signature':narration.script_signature(job,rows)})
    tts={'language':'en'}
    with patch('upgrade.pipeline.speech',return_value=(voice,1.)):
        pipeline.build_audio(job,rows,tts,r)
    save(job/'tts_rows.json',rows)
    cfg={'dub':True,'mix':'story','sound_source':'original','voice_gain':1.,'original_gain':.4,'duck_gain':.15,
         'duck':True,'mask':'solid','subtitle_box':[.05,.65,.9,.3],'font':'C:/Windows/Fonts/arial.ttf','font_size':28,
         'tts':tts}
    return job,rows,cfg,r


def test_story_preview_and_final_without_occupancy_quota(ready_story):
    job,rows,cfg,r=ready_story
    # Four 1s tones, intentionally nowhere near 60% of the 12s video.
    assert read(job/'story_timing.json')['narration_seconds']==pytest.approx(4,abs=.02)
    pipeline.render(job,rows,[],cfg,r,True)
    assert probe(job/'preview.mp4')['duration']==pytest.approx(12,abs=.05)
    with pytest.raises(ValueError,match='duyệt'):
        pipeline.render(job,rows,[],cfg,r)
    save(job/'story_final_approval.json',{'signature':narration.final_signature(job,rows,[],cfg)})
    pipeline.render(job,rows,[],cfg,r)
    assert probe(job/'final.mp4')['duration']==pytest.approx(12,abs=.05)
    assert read(job/'story_render_signature.json')['signature']==narration.final_signature(job,rows,[],cfg)
    with pytest.raises(ValueError,match='duyệt'):
        pipeline.render(job,rows,[],{**cfg,'original_gain':.2},r)


def test_story_audio_cannot_borrow_following_window(ready_story):
    job,rows,cfg,r=ready_story
    with patch('upgrade.pipeline.speech',return_value=(job/'test_voice.wav',10.)):
        with pytest.raises(ValueError,match='tràn'):
            pipeline.build_audio(job,rows,{'language':'en'},r)
    assert not (job/'tts_rows.json').exists()
    assert all(e['reason']=='speech_overflow' for e in read(job/'review_report.json'))


def test_changed_facts_require_review_before_paid_tts(ready_story):
    job,rows,cfg,r=ready_story
    facts=read(job/'story_facts.json');facts['takeaways'][0]['text']='A reviewed takeaway has changed.'
    save(job/'story_facts.json',facts)
    with patch('upgrade.pipeline.speech') as paid:
        with pytest.raises(ValueError,match='duyệt'):
            pipeline.build_audio(job,rows,{'language':'en'},r)
        paid.assert_not_called()


def test_muted_narration_keeps_background_at_selected_gain(ready_story):
    job,rows,cfg,r=ready_story
    muted={**cfg,'voice_gain':0.,'original_gain':.4,'duck_gain':.15,'duck':True}
    output=pipeline.render(job,rows,[],muted,r,True)

    def decode(path):
        samples=array('f',r.run(['ffmpeg','-v','error','-i',path,'-map','0:a:0',
                                '-ac','1','-ar','48000','-c:a','pcm_f32le','-f','f32le','pipe:1']))
        if sys.byteorder!='little':
            samples.byteswap()
        return samples

    reference,rendered=decode(job/'source.mp4'),decode(output)
    def rms(samples,start,end):
        window=samples[round(start*48000):round(end*48000)]
        assert window
        return math.sqrt(sum(value*value for value in window)/len(window))

    # Include every scheduled voice clip plus a natural gap. Muting VO must
    # leave the selected 40% background gain in both, even with duck enabled.
    intervals=[(m['final_start']+.25,m['final_start']+.75)
               for m in read(job/'audio_manifest.json')]+[(1.5,2.5)]
    for start,end in intervals:
        assert rms(rendered,start,end)/rms(reference,start,end)==pytest.approx(.4,abs=.01)
    assert muted['duck'] is True  # Effective mixing must not change user settings.
