import json
import subprocess
import threading
from pathlib import Path


class Cancelled(RuntimeError):
    pass


class Runner:
    def __init__(self):
        self.cancel = threading.Event()
        self.message = ""

    def check(self):
        if self.cancel.is_set():
            raise Cancelled("Đã dừng; các bước hoàn tất được giữ lại.")

    def run(self, args, cwd=None):
        self.check()
        with subprocess.Popen([str(a) for a in args], cwd=cwd, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)) as p:
            while True:
                try:
                    out, err = p.communicate(timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    if self.cancel.is_set():
                        p.terminate()
                        try:
                            p.communicate(timeout=3)
                        except subprocess.TimeoutExpired:
                            p.kill()
                            p.communicate()
                        self.check()
            if p.returncode:
                raise RuntimeError("Tiến trình thất bại: " + err.decode('utf-8', errors='replace')[-2000:])
            return out


def probe(path, runner=None):
    data = json.loads((runner or Runner()).run(['ffprobe', '-v', 'error', '-show_streams',
                      '-show_format', '-of', 'json', path]))
    duration = float(data['format'].get('duration', 0))
    if duration <= 0:
        raise ValueError('Media rỗng hoặc không có thời lượng hợp lệ')
    v = next((s for s in data['streams'] if s['codec_type'] == 'video'), None)
    return {'duration': duration, 'width': v['width'] if v else 0,
            'height': v['height'] if v else 0,
            'audio': any(s['codec_type'] == 'audio' for s in data['streams']), 'raw': data}


def normalize(source, target, runner):
    # FFmpeg autorotation precedes filters; all further coordinates refer to this file.
    runner.run(['ffmpeg', '-v', 'error', '-y', '-i', source, '-map', '0:v:0', '-map', '0:a?',
                '-vf', 'scale=trunc(iw/2)*2:trunc(ih/2)*2,setsar=1', '-fps_mode', 'vfr',
                '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-c:a', 'aac', target])
    return probe(target, runner)
