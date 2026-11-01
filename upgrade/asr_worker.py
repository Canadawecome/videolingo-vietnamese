"""Runs upstream Qwen in a separate process with job-local config/output."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    job = Path(sys.argv[1]).resolve()
    language = sys.argv[2]
    os.chdir(job)
    from ruamel.yaml import YAML
    yaml = YAML()
    config = yaml.load((ROOT/'config.yaml').read_text(encoding='utf-8'))
    # Never copy provider credentials to a job manifest/config.
    def scrub(value):
        if isinstance(value, dict):
            return {k: ('' if any(t in str(k).lower() for t in ('key','token','password','cookie')) else scrub(v)) for k,v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        return value
    config = scrub(config)
    config['whisper']['language'] = language
    with (job/'config.yaml').open('w',encoding='utf-8') as f:
        yaml.dump(config,f)
    from upgrade.media import Runner, probe
    from upgrade.store import save
    from core.asr_backend.qwen_asr_local import transcribe_audio
    runner = Runner()
    runner.run(['ffmpeg','-v','error','-y','-i','source.mp4','-vn','-ar','16000','-ac','1','asr.wav'])
    data = transcribe_audio('asr.wav','asr.wav',0,probe('source.mp4')['duration'])
    rows=[]
    for segment in data['segments']:
        words = segment.get('words') or [{'word':segment['text'],'start':segment['start'],'end':segment['end']}]
        group=[]
        for word in words:
            group.append(word)
            if word['end']-group[0]['start']>=4 or str(word.get('word',word.get('text',''))).rstrip().endswith(('.', '?','!','。','？','！')):
                rows.append(group); group=[]
        if group: rows.append(group)
    output=[]
    for i,group in enumerate(rows):
        text=' '.join(w.get('word',w.get('text','')).strip() for w in group)
        output.append({'id':f's{i+1:05}','start':group[0]['start'],'end':group[-1]['end'],
                       'source':text,'translation':text,'tts_text':text})
    save(job/'segments.json',output)
    save(job/'asr_result.json',data)


if __name__=='__main__':
    main()
