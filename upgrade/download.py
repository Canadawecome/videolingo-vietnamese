import re
from pathlib import Path
from .store import save, checksum
from .media import probe


def extract_url(text):
    urls = re.findall(r'https?://[^\s<>"\u3002]+', text)
    urls = [u.rstrip(').,;!') for u in urls]
    if len(urls) != 1:
        raise ValueError('Nhập đúng một URL; chọn riêng video nếu có nhiều link.')
    return urls[0]


class Quiet:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass


def inspect(url):
    from yt_dlp import YoutubeDL
    try:
        with YoutubeDL({'quiet':True, 'logger':Quiet(), 'extract_flat':True, 'skip_download':True,
                        'socket_timeout':20, 'retries':2}) as ydl:
            data = ydl.extract_info(url, download=False)
    except Exception:
        raise ValueError('Không phân tích được link: extractor chưa hỗ trợ, cần cookie hoặc nguồn không truy cập được. Có thể nhập file.') from None
    return {'title':data.get('title'), 'duration':data.get('duration'), 'extractor':data.get('extractor'),
            'entries':[{'id':e.get('id'), 'title':e.get('title'), 'url':e.get('webpage_url') or e.get('url')}
                       for e in (data.get('entries') or []) if e]}


def download(url, job, quality, runner, cookie=None):
    from yt_dlp import YoutubeDL, version
    folder = job/'download'
    folder.mkdir(exist_ok=True)
    def progress(d):
        runner.check()
        runner.message = f"Tải: {d.get('downloaded_bytes',0)//1024} KB · {d.get('status','')}"
    fmt = 'bv*+ba/b' if quality=='best' else f'bv*[height<={quality}]+ba/b[height<={quality}]'
    opts = {'format':fmt, 'noplaylist':True, 'outtmpl':str(folder/'%(id)s.%(ext)s'),
            'quiet':True, 'logger':Quiet(), 'progress_hooks':[progress], 'retries':2,
            'fragment_retries':2, 'socket_timeout':20, 'continuedl':True}
    if cookie:
        opts['cookiefile'] = cookie
    try:
        with YoutubeDL(opts) as ydl:
            data = ydl.extract_info(url, download=True)
    except Exception:
        runner.check()
        raise ValueError('Tải thất bại: kiểm tra hỗ trợ extractor/cookie/mạng/dung lượng. File dở được giữ để tiếp tục.') from None
    candidates = [p for p in folder.iterdir() if p.suffix not in ('.part','.ytdl','.tmp')]
    path = next((p for p in candidates if p.stem == str(data['id'])), None)
    if path is None:
        raise ValueError('Không xác định được file tải hoàn tất.')
    probe(path, runner)
    save(job/'download_manifest.json', {'platform':data.get('extractor'), 'media_id':data['id'],
         'title':data.get('title'), 'duration':data.get('duration'), 'quality':quality,
         'selected_format_ids':data.get('format_id'), 'local_path':str(path),
         'checksum':checksum(path), 'yt_dlp_version':version.__version__})
    return path
