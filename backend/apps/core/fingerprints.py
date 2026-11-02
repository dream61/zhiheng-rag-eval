import hashlib
import json

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def sample_fingerprint(sample):
    return fingerprint({k: v for k, v in sample.items() if k not in ("approved", "source_result", "regression_reason")})

def knowledge_fingerprint(asset):
    return fingerprint({"content": asset.content, "settings": {k:v for k,v in asset.settings.items() if k not in ("chunks", "index")}})
