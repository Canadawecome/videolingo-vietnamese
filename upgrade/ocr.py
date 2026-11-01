"""Conservative sampled OCR proposals. Every result requires human review."""
from .media import probe


def scan(source, roi, languages, runner, interval=.25):
    import cv2
    import easyocr
    from pathlib import Path
    model_dir = Path(__file__).resolve().parents[1]/'runtime'/'easyocr'
    model_dir.mkdir(parents=True,exist_ok=True)
    reader = easyocr.Reader(languages, gpu=False, model_storage_directory=str(model_dir), verbose=False)
    info = probe(source, runner)
    width, height = info['width'], info['height']
    x, y, w, h = roi
    left, top, right, bottom = int(x*width), int(y*height), int((x+w)*width), int((y+h)*height)
    cap = cv2.VideoCapture(str(source))
    samples = []
    try:
        t = 0.
        while t < info['duration']:
            runner.check()
            runner.message = f'OCR {t:.1f}/{info["duration"]:.1f}s'
            cap.set(cv2.CAP_PROP_POS_MSEC, t*1000)
            ok, frame = cap.read()
            if not ok:
                break
            pts = cap.get(cv2.CAP_PROP_POS_MSEC)/1000
            for polygon, text, conf in reader.readtext(frame[top:bottom,left:right]):
                xs, ys = zip(*polygon)
                bx0, by0 = max(left, left+min(xs)-8*width/1920), max(top, top+min(ys)-6*height/1080)
                bx1, by1 = min(right, left+max(xs)+8*width/1920), min(bottom, top+max(ys)+6*height/1080)
                samples.append({'timestamp': pts, 'text': text, 'confidence': float(conf),
                                'bbox': [bx0/width, by0/height, (bx1-bx0)/width, (by1-by0)/height]})
            t += interval
    finally:
        cap.release()
    regions = []
    for sample in samples:
        a, b = max(0, sample['timestamp']-.1), min(info['duration'], sample['timestamp']+interval+.1)
        if regions and a <= regions[-1]['end']:
            r = regions[-1]
            xx, yy, ww, hh = r['bbox']; sx, sy, sw, sh = sample['bbox']
            r['bbox'] = [min(xx,sx), min(yy,sy), max(xx+ww,sx+sw)-min(xx,sx), max(yy+hh,sy+sh)-min(yy,sy)]
            r['end'] = b
            r['confidence'] = min(r['confidence'], sample['confidence'])
        else:
            regions.append({'id': f'r{len(regions)+1}', 'start': a, 'end': b, 'bbox': sample['bbox'],
                            'confidence': sample['confidence'], 'source': 'auto', 'approved': False})
    return regions, samples
