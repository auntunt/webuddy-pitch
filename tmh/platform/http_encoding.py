"""Lossless, explicitly negotiated transport for large evidence JSON."""
import gzip


def encode_json(body, content_type, accepted, headers=None):
    headers = dict(headers or {})
    if (len(body) >= 65536 and content_type.startswith('application/json')
            and not any(k.lower() == 'content-encoding' for k in headers)):
        headers['Vary'] = 'Accept-Encoding'
        # A bare gzip token is an explicit opt-in. Qualified/disabled values
        # retain identity encoding; old clients receive unchanged JSON bytes.
        if 'gzip' in [item.strip().lower() for item in accepted.split(',')]:
            body = gzip.compress(body, compresslevel=6, mtime=0)
            headers['Content-Encoding'] = 'gzip'
    return body, headers
