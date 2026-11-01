from pathlib import Path
from upgrade.media import Runner, probe
from upgrade.store import create, save, checkpoint, checksum
from upgrade.pipeline import render
from upgrade.captions import import_srt

root=Path(__file__).resolve().parents[1]
demo=root/'demo'
demo.mkdir(exist_ok=True)
r=Runner()
original=demo/'before.mp4'
r.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=960x540:rate=30:duration=6',
       '-f','lavfi','-i','sine=frequency=330:duration=6','-vf',
       "drawbox=x=80:y=420:w=800:h=90:color=black@0.4:t=fill,drawtext=fontfile='C\\:/Windows/Fonts/arial.ttf':text='Original burned-in subtitles':fontsize=36:fontcolor=white:x=(w-text_w)/2:y=445",
       '-c:v','libx264','-c:a','aac',original])
job=create(root/'jobs')
import shutil
shutil.copy2(original,job/'source.mp4')
rows=import_srt('1\n00:00:00,000 --> 00:00:03,000\nXin chào Việt Nam!\n\n2\n00:00:03,000 --> 00:00:06,000\nPhụ đề mới có đầy đủ dấu.')
regions=[{'id':'demo','bbox':[.08,.77,.84,.18],'start':0.,'end':6.,'confidence':1.,'source':'manual','approved':True}]
save(job/'segments.json',rows);save(job/'ocr_regions.json',regions)
config={'dub':False,'mask':'solid','subtitle_box':regions[0]['bbox'],'font':'C:/Windows/Fonts/arial.ttf','font_size':36}
out=render(job,rows,regions,config,r)
shutil.copy2(out,demo/'after.mp4')
for name in ('captions.ass','captions.srt','review_report.json'):
    shutil.copy2(job/name,demo/name)
r.run(['ffmpeg','-v','error','-y','-ss','1','-i',demo/'after.mp4','-frames:v','1',demo/'after.png'])
print(f'Demo job: {job.name}; before={probe(original)["duration"]}, after={probe(demo/"after.mp4")["duration"]}')
