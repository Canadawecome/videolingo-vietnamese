import hashlib
import json
import uuid
from pathlib import Path

BASE_SHA = '01f843492759be9bbfd1a5cb697b799cc9de1609'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def checksum(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    temp.replace(path)


def read(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8')) if Path(path).exists() else default


def create(root):
    path = Path(root) / uuid.uuid4().hex[:12]
    path.mkdir(parents=True)
    save(path / 'job.json', {'id': path.name, 'base_commit': BASE_SHA, 'state': 'queued', 'steps': {}})
    save(path / 'segments.json', [])
    save(path / 'ocr_regions.json', [])
    return path


def checkpoint(job, step, inputs, outputs):
    data = read(job / 'job.json')
    data['steps'][step] = {'input_hash': digest(inputs),
                          'outputs': {Path(p).name: checksum(p) for p in outputs}}
    data['state'] = step
    save(job / 'job.json', data)


def valid(job, step, inputs):
    data = read(job / 'job.json')['steps'].get(step, {})
    return data.get('input_hash') == digest(inputs) and all(
        (job / p).exists() and checksum(job / p) == h for p, h in data.get('outputs', {}).items())
