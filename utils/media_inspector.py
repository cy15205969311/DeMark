"""Bounded byte validation for 818ps; URL suffixes are discovery hints only."""
import asyncio
import base64
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.parse import unquote_to_bytes

import aiohttp
from PIL import Image

MAX_MEDIA_BYTES = 32 * 1024 * 1024


def signature(data):
    if data[:6] in (b'GIF87a', b'GIF89a'):
        return 'image/gif'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'image/webp'
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'image/png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'image/jpeg'
    if data[4:8] == b'ftyp' and data[8:12] in (b'isom',b'iso2',b'mp41',b'mp42',b'avc1',b'M4V '):
        return 'video/mp4'
    if data.startswith(b'\x1a\x45\xdf\xa3') and b'webm' in data[:4096]:
        return 'video/webm'
    return None


def decode(data, result):
    media_type = signature(data)
    result['signature'] = media_type
    if not data:
        result['failureReason'] = 'empty'
        return result
    if not media_type:
        result['failureReason'] = 'invalid_signature'
        return result
    result['mediaType'] = media_type
    reported = result.get('contentType', '').split(';')[0].lower()
    result['mimeMismatch'] = bool(reported and reported not in (media_type, 'application/octet-stream'))
    # HTML error pages must never become valid media, even with a misleading suffix.
    if reported in ('text/html', 'application/xhtml+xml'):
        result['failureReason'] = 'mime_mismatch'
        return result
    if media_type.startswith('video/'):
        # The container signature establishes format, not frames or playback validity.
        result.update(valid=True, animationStatus='unknown', frameCount=None)
        return result
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            frames = getattr(image, 'n_frames', 1)
            if width * height > 40_000_000 or frames > 2000 or width * height * frames > 120_000_000:
                result['failureReason'] = 'decode_limit'
                return result
            deadline = time.monotonic() + 3
            for index in range(frames):
                if time.monotonic() > deadline:
                    result['failureReason'] = 'decode_limit'
                    return result
                image.seek(index)
                image.load()
            result.update(valid=True, width=width, height=height, frameCount=frames,
                          animationStatus='animated' if frames > 1 else 'static')
    except Exception as error:
        result.update(failureReason='decode_error', exceptionType=type(error).__name__)
    return result


async def inspect(validator, url, request_headers=None, captured=None, timeout=6,
                  max_bytes=MAX_MEDIA_BYTES):
    result = dict(url=url, finalUrl=url, httpStatus=None, contentType='', contentLength=None,
                  signature=None, valid=False, animationStatus='unknown', frameCount=None,
                  failureReason=None)
    data = None
    try:
        if captured and captured.get('originalRequestUrl'):
            result['originalRequestUrl'] = captured['originalRequestUrl']
        if captured and captured.get('httpStatus') and captured['httpStatus'] != 200:
            result.update(httpStatus=captured['httpStatus'], contentType=captured.get('contentType', ''),
                          contentLength=captured.get('contentLength'), finalUrl=captured.get('finalUrl', url),
                          failureReason='incomplete_response' if captured['httpStatus'] == 206 else 'http_error')
            return result
        if captured and captured.get('failureReason') and not captured.get('bodyBase64'):
            result['failureReason'] = captured['failureReason']
            return result
        if url.startswith('data:'):
            if len(url) > max_bytes * 4 // 3 + 1024:
                result['failureReason'] = 'size_limit'
                return result
            prefix, encoded = url.split(',', 1)
            result['contentType'] = prefix[5:].split(';')[0]
            data = base64.b64decode(encoded, validate=True) if ';base64' in prefix else unquote_to_bytes(encoded)
        elif captured and captured.get('bodyBase64') is not None:
            result.update(httpStatus=captured.get('httpStatus'), contentType=captured.get('contentType', ''),
                          contentLength=captured.get('contentLength'), finalUrl=captured.get('finalUrl', url))
            if result['httpStatus'] not in (None, 200):
                result['failureReason'] = 'http_error' if result['httpStatus'] != 206 else 'incomplete_response'
                return result
            data = base64.b64decode(captured['bodyBase64'], validate=True)
        elif url.startswith('blob:'):
            result['failureReason'] = 'blob_unavailable'
            return result
        else:
            await validator._init_async_session()
            headers = validator._get_anti_hotlink_headers(url)
            for key, value in (request_headers or {}).items():
                headers = {k: v for k, v in headers.items() if k.lower() != key.lower()}
                headers[key] = value
            headers = {k: v for k, v in headers.items() if k.lower() != 'range'}
            async with validator.session.get(url, headers=headers, allow_redirects=True,
                                             timeout=aiohttp.ClientTimeout(total=timeout, connect=min(2, timeout))) as response:
                result.update(httpStatus=response.status, contentType=response.headers.get('Content-Type', ''),
                              contentLength=response.content_length, finalUrl=str(response.url))
                if response.status != 200:
                    result['failureReason'] = 'incomplete_response' if response.status == 206 else 'http_error'
                    return result
                if response.content_length and response.content_length > max_bytes:
                    result['failureReason'] = 'size_limit'
                    return result
                data = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    data.extend(chunk)
                    if len(data) > max_bytes:
                        result['failureReason'] = 'size_limit'
                        return result
                    if len(data) >= 4096 and not signature(data):
                        result['failureReason'] = 'invalid_signature'
                        return result
                data = bytes(data)
        if len(data) > max_bytes:
            result['failureReason'] = 'size_limit'
            return result
        result = await asyncio.to_thread(decode, data, result)
        result['byteCount'] = len(data)
        if result['valid']:
            # Preserve exactly the downloaded bytes, including all animation frames.
            suffix = {'image/gif': '.gif', 'image/webp': '.webp', 'image/png': '.png',
                      'image/jpeg': '.jpg', 'video/mp4': '.mp4', 'video/webm': '.webm'}[result['mediaType']]
            target = Path(__file__).resolve().parents[1] / 'cache' / '818ps_media' / (hashlib.sha256(data).hexdigest() + suffix)
            target.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(target.write_bytes, data)
            result['mediaFile'] = str(target)
            # The existing downloader accepts URLs only. An indexed cache preserves
            # Blob/data resources and request-dependent signed media after browser close.
            index = target.parent / (hashlib.sha256(url.encode()).hexdigest() + '.json')
            await asyncio.to_thread(index.write_text, json.dumps(dict(mediaFile=str(target), mediaType=result['mediaType'])),
                                    encoding='utf-8')
    except (asyncio.TimeoutError, TimeoutError):
        result['failureReason'] = 'timeout'
    except Exception as error:
        result.update(valid=False, failureReason='request_error', exceptionType=type(error).__name__)
    return result
