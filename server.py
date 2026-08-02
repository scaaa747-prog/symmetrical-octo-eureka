import http.server
import socketserver
import urllib.request
import urllib.parse
import json
import base64
import subprocess
import os
import sys
import ssl
import concurrent.futures
import time
import unicodedata

PORT = 3000

# -------------------------------------------------------------
# VIDEASY PRNG & DECRYPTION IN PYTHON
# -------------------------------------------------------------
PRNG_F = [1116352408, 1899447441, 3049323471, 3921009573, 961987163, 1508970993, 2453635748, 2870763221, 3624381080, 310598401, 607225278, 1426881987, 1925078388, 2162078206, 2614888103, 3248222580]
HEADER_SIG = [109, 118, 109, 49]

def uint32(x): return x & 0xFFFFFFFF
def imul(a, b): return uint32((uint32(a) * uint32(b)))

def b_func(e): return ((e * (e + 1)) & 1) == 0
def i_func(e): return ((e * (e + 1)) & 1) == 1

def w_func(e):
    e = uint32(e)
    e ^= (e >> 16)
    e = imul(e, 2246822507)
    e ^= (e >> 13)
    e = imul(e, 3266489909)
    return uint32(e ^ (e >> 16))

def v_func(e, t):
    e = uint32(e)
    t = t & 31
    if t == 0: return e
    return uint32((e << t) | (e >> (32 - t)))

def get_keystream(seed_str, tmdb_str, length):
    if i_func(len(seed_str)):
        S = list(range(256))
        s = 0
        for a in range(256):
            s = (s + S[a] + ord(seed_str[a % len(seed_str)])) & 255
            S[a], S[s] = S[s], S[a]
        t = 1732584193
        for idx in range(len(seed_str)):
            t = v_func(uint32(t ^ imul(ord(seed_str[idx]), PRNG_F[15 & idx])), 5)
        acc = w_func(t)
        state = {'S': S, 'acc': acc}
    else:
        S = [0] * 61
        t = 2166136261
        for idx in range(len(seed_str)):
            t = imul(t ^ ord(seed_str[idx]), 16777619)
        hash_t = w_func(t)
        try: tmdb_val = int(tmdb_str)
        except Exception: tmdb_val = 0
        a = w_func(hash_t ^ w_func(uint32(tmdb_val) ^ 2654435769))
        for e in range(8):
            if b_func(e):
                t_val = a % 61
                a = v_func(uint32(a + 2654435769), 7 + (7 & e))
                S[t_val] = uint32(a ^ w_func(a))
                a = w_func(uint32(a + t_val))
            else: S[e] = PRNG_F[15 & e]
        acc = w_func(2779096485 ^ a)
        state = {'S': S, 'acc': acc}

    out = bytearray(length)
    o = 0
    e_idx = 0
    while e_idx < length:
        r_state = state['S']
        acc = state['acc']
        n = acc % 61
        d = uint32(r_state[n]) if n < len(r_state) else 0
        s_val = o
        a_val = uint32(d ^ imul(2654435769, o + 1))
        i_val = 1
        l_val = uint32((s_val ^ a_val) | (s_val & a_val & i_val))
        
        l_comb = v_func(uint32(l_val + o), 31 & n) ^ v_func(o, 31 & imul(n, 7))
        new_acc = w_func(uint32(l_comb + 2654435769))
        
        if n < len(r_state): r_state[n] = new_acc
        state['acc'] = new_acc
        o += 1
        
        out[e_idx] = new_acc & 255
        e_idx += 1
        if e_idx < length: out[e_idx] = (new_acc >> 8) & 255; e_idx += 1
        if e_idx < length: out[e_idx] = (new_acc >> 16) & 255; e_idx += 1
        if e_idx < length: out[e_idx] = (new_acc >> 24) & 255; e_idx += 1
    return out

def decrypt_videasy_payload(b64_str, tmdb_id, seed):
    try:
        raw_b64 = b64_str.replace('-', '+').replace('_', '/')
        raw_b64 += '=' * ((4 - len(raw_b64) % 4) % 4)
        enc_bytes = bytearray(base64.b64decode(raw_b64))
        
        ks = get_keystream(str(seed), str(tmdb_id), len(enc_bytes))
        dec = bytearray(len(enc_bytes))
        for idx in range(len(enc_bytes)):
            dec[idx] = enc_bytes[idx] ^ ks[idx]
            
        if list(dec[:4]) == HEADER_SIG:
            return dec[4:].decode('utf-8')
    except Exception:
        pass
    return "{}"

# -------------------------------------------------------------
# SERVER STREAM RESOLVER FUNCTION
# Stream URL cache — seed is fetched once per resolve, not stored
RESOLVE_CACHE = {}
CACHE_TTL_SECONDS = 300

def clean_title_string(t):
    if not t: return "Media"
    normalized = unicodedata.normalize('NFKD', str(t)).encode('ASCII', 'ignore').decode('utf-8')
    return normalized.strip() or str(t)

# -------------------------------------------------------------
# INSTANT PARALLEL STREAM RESOLVER WITH MEMORY CACHING
# -------------------------------------------------------------
def resolve_streams(tmdb_id, media_type="movie", season="1", episode="1"):
    cache_key = f"{media_type}_{tmdb_id}_{season}_{episode}"
    now = time.time()
    # Return cached URL if still valid — no need to re-fetch seed at all
    if cache_key in RESOLVE_CACHE:
        entry = RESOLVE_CACHE[cache_key]
        if now - entry['timestamp'] < CACHE_TTL_SECONDS and entry['data'].get('sources'):
            return entry['data']

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Origin': 'https://player.videasy.to',
        'Referer': 'https://player.videasy.to/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site',
        'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        'Sec-Ch-Ua-Mobile': '?0',
        'Sec-Ch-Ua-Platform': '"Windows"'
    }

    def fetch_meta():
        try:
            meta_url = f"https://db.speedracelight.com/3/{media_type}/{tmdb_id}?append_to_response=external_ids&language=en"
            req = urllib.request.Request(meta_url, headers=headers)
            with urllib.request.urlopen(req, timeout=4) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception:
            return {}

    def fetch_seed_once():
        """Fetch seed with retry logic to handle temporary Cloudflare 429 limits."""
        for attempt in range(3):
            try:
                seed_url = f"https://api.speedracelight.com/seed?mediaId={tmdb_id}&_t={int(time.time()*1000)}"
                req = urllib.request.Request(seed_url, headers=headers)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    s = json.loads(resp.read().decode('utf-8')).get('seed')
                    if s: return s
            except Exception:
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
        return None

    # Fetch meta + seed in parallel — one shot
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_meta = executor.submit(fetch_meta)
        f_seed = executor.submit(fetch_seed_once)
        meta = f_meta.result() or {}
        seed = f_seed.result()

    raw_title = meta.get('title') or meta.get('original_title') or meta.get('name') or meta.get('original_name') or "Media"
    title = clean_title_string(raw_title)
    release_date = meta.get('release_date') or meta.get('first_air_date') or '2026-01-01'
    year = release_date.split('-')[0]
    imdb_id = meta.get('imdb_id') or (meta.get('external_ids', {}).get('imdb_id') if meta.get('external_ids') else '') or ''

    def fetch_endpoint(ep, current_seed=None):
        active_seed = current_seed or seed
        if not active_seed:
            return []
        
        for retry_count in range(2):
            try:
                params = {
                    'title': title,
                    'mediaType': media_type,
                    'year': year,
                    'tmdbId': tmdb_id,
                    'imdbId': imdb_id,
                    'enc': '2',
                    'seed': active_seed
                }
                if media_type == 'tv':
                    params['seasonId'] = season
                    params['episodeId'] = episode
                    params['totalSeasons'] = str(meta.get('number_of_seasons', 1))

                query_str = urllib.parse.urlencode(params)
                req_ep = urllib.request.Request(f"{ep}?{query_str}", headers=headers)
                with urllib.request.urlopen(req_ep, timeout=4) as resp:
                    enc_body = resp.read().decode('utf-8')
                    decrypted_str = decrypt_videasy_payload(enc_body, str(tmdb_id), active_seed)
                    parsed = json.loads(decrypted_str)
                    return parsed.get('sources', [])
            except urllib.error.HTTPError as he:
                if he.code == 401 and retry_count == 0:
                    active_seed = fetch_seed_once()
                    if not active_seed: break
                else:
                    break
            except Exception:
                break
        return []

    # Parallel fetch for all 9 Videasy speedracelight endpoints
    endpoints = [
        "https://api.speedracelight.com/vsrc/sources-with-title",
        "https://api.speedracelight.com/hdmovie/sources-with-title",
        "https://api.speedracelight.com/meine/sources-with-title",
        "https://api.speedracelight.com/hianime/sources-with-title",
        "https://api.speedracelight.com/downloader2/sources-with-title",
        "https://api.speedracelight.com/superflix/sources-with-title",
        "https://api.speedracelight.com/cdn/sources-with-title",
        "https://api.speedracelight.com/lamovie/sources-with-title",
        "https://api.speedracelight.com/m4uhd/sources-with-title"
    ]

    all_sources = []
    seen_urls = set()

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(fetch_endpoint, ep) for ep in endpoints]
        for f in concurrent.futures.as_completed(futures):
            res = f.result()
            for s in res:
                u = s.get('url')
                if u and u not in seen_urls:
                    seen_urls.add(u)
                    all_sources.append(s)

    # Smart Hybrid System: Return direct HLS if available, else fallback embed sources for Turnstile-protected titles like Naruto
    if not all_sources:
        if media_type == 'tv':
            videasy_url = f"https://player.videasy.to/tv/{tmdb_id}/{season}/{episode}"
            vidsrc_url = f"https://vidsrc.me/embed/tv?tmdb={tmdb_id}&season={season}&episode={episode}"
            vidsrc_to_url = f"https://vidsrc.to/embed/tv/{tmdb_id}/{season}/{episode}"
            multi_url = f"https://multiembed.mov/?video_id={tmdb_id}&tmdb=1&s={season}&e={episode}"
        else:
            videasy_url = f"https://player.videasy.to/movie/{tmdb_id}"
            vidsrc_url = f"https://vidsrc.me/embed/movie?tmdb={tmdb_id}"
            vidsrc_to_url = f"https://vidsrc.to/embed/movie/{tmdb_id}"
            multi_url = f"https://multiembed.mov/?video_id={tmdb_id}&tmdb=1"

        all_sources = [
            {'quality': 'Videasy Server 1', 'url': videasy_url, 'is_embed': True},
            {'quality': 'VidSrc Server 2', 'url': vidsrc_url, 'is_embed': True},
            {'quality': 'VidSrc Pro 3', 'url': vidsrc_to_url, 'is_embed': True},
            {'quality': 'MultiEmbed 4', 'url': multi_url, 'is_embed': True}
        ]

    res_data = {
        'success': True,
        'title': raw_title,
        'year': year,
        'overview': meta.get('overview', ''),
        'rating': meta.get('vote_average', 0),
        'poster_path': meta.get('poster_path'),
        'backdrop_path': meta.get('backdrop_path'),
        'genres': meta.get('genres', []),
        'sources': all_sources
    }

    if all_sources:
        RESOLVE_CACHE[cache_key] = {'timestamp': now, 'data': res_data}

    return res_data

# -------------------------------------------------------------
# REAL-TIME INSTANT STREAMING MP4 DOWNLOAD PROXY
# -------------------------------------------------------------
def resolve_master_m3u8_to_direct(m3u8_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://player.videasy.to',
        'Referer': 'https://player.videasy.to/'
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(m3u8_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            final_url = resp.geturl()
            content = resp.read().decode('utf-8', errors='ignore')

            if '#EXT-X-STREAM-INF' in content:
                best_url = None
                max_bw = -1
                lines = content.splitlines()
                for idx, line in enumerate(lines):
                    if line.startswith('#EXT-X-STREAM-INF'):
                        bw = 0
                        if 'BANDWIDTH=' in line:
                            try:
                                bw = int(line.split('BANDWIDTH=')[1].split(',')[0].split('\n')[0])
                            except: pass
                        for j in range(idx + 1, len(lines)):
                            sub = lines[j].strip()
                            if sub and not sub.startswith('#'):
                                abs_sub = urllib.parse.urljoin(final_url, sub)
                                if bw >= max_bw:
                                    max_bw = bw
                                    best_url = abs_sub
                                break
                if best_url:
                    return best_url
            return final_url
    except Exception:
        pass
    return m3u8_url

def parse_segment_urls(variant_m3u8_url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://player.videasy.to',
        'Referer': 'https://player.videasy.to/'
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(variant_m3u8_url, headers=headers)
        with urllib.request.urlopen(req, timeout=12, context=ctx) as resp:
            base_url = resp.geturl().rsplit('/', 1)[0] + '/'
            content = resp.read().decode('utf-8', errors='ignore')
            
            segments = []
            for line in content.splitlines():
                line_str = line.strip()
                if line_str and not line_str.startswith('#'):
                    full_url = urllib.parse.urljoin(base_url, line_str)
                    segments.append(full_url)
            return segments
    except Exception:
        return []

def download_single_segment(index, seg_url, retries=3):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Origin': 'https://player.videasy.to',
        'Referer': 'https://player.videasy.to/'
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            req = urllib.request.Request(seg_url, headers=headers)
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                data = resp.read()
                if len(data) > 0:
                    return index, data
        except Exception:
            time.sleep(0.4)
    return index, None

def stream_download_mp4(m3u8_url, title_str, handler):
    safe_filename = "".join(c for c in title_str if c.isalnum() or c in (' ', '_', '-')).strip()
    if not safe_filename: safe_filename = "video"
    safe_filename = safe_filename.replace(' ', '_') + ".mp4"

    direct_url = resolve_master_m3u8_to_direct(m3u8_url)
    segment_urls = parse_segment_urls(direct_url)

    if not segment_urls:
        handler.send_response(404)
        handler.send_header('Content-Type', 'text/plain')
        handler.end_headers()
        handler.wfile.write(b"Error: Could not extract video segments.")
        return

    handler.send_response(200)
    handler.send_header('Content-Type', 'video/mp4')
    handler.send_header('Content-Disposition', f'attachment; filename="{safe_filename}"')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()

    import concurrent.futures

    downloaded = {}
    next_to_send = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(download_single_segment, idx, url): idx for idx, url in enumerate(segment_urls)}
        
        for future in concurrent.futures.as_completed(futures):
            idx, seg_bytes = future.result()
            if seg_bytes:
                downloaded[idx] = seg_bytes
            else:
                _, retry_bytes = download_single_segment(idx, segment_urls[idx], retries=5)
                if retry_bytes:
                    downloaded[idx] = retry_bytes

            while next_to_send in downloaded:
                chunk = downloaded.pop(next_to_send)
                try:
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
                except Exception:
                    # Browser disconnected or user cancelled download
                    return
                next_to_send += 1

# -------------------------------------------------------------
# THREADED HTTP SERVER CLASS (PREVENTS BLOCKING)
# -------------------------------------------------------------
# -------------------------------------------------------------
# M3U8 & TS CORS PROXY FOR HLS PLAYBACK
# -------------------------------------------------------------
def proxy_m3u8(m3u8_url, handler):
    client_ip = handler.headers.get('X-Forwarded-For') or handler.headers.get('X-Real-IP') or '127.0.0.1'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'identity',
        'Origin': 'https://player.videasy.to',
        'Referer': 'https://player.videasy.to/',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'cross-site'
    }
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(m3u8_url, headers=headers)

    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                content_type = resp.headers.get('Content-Type', '')
                body = resp.read()
                
                if 'mpegurl' in content_type or 'text' in content_type or m3u8_url.endswith('.m3u8') or body.startswith(b'#EXTM3U'):
                    text = body.decode('utf-8', errors='ignore')
                    base_url = m3u8_url.rsplit('/', 1)[0] + '/'
                    lines = text.splitlines()
                    new_lines = []
                    for line in lines:
                        line_str = line.strip()
                        if line_str and not line_str.startswith('#'):
                            full_url = urllib.parse.urljoin(base_url, line_str)
                            proxied = f"/api/m3u8-proxy?url={urllib.parse.quote(full_url)}"
                            new_lines.append(proxied)
                        elif line_str.startswith('#EXT-X-KEY:') or line_str.startswith('#EXT-X-MAP:'):
                            if 'URI="' in line_str:
                                parts = line_str.split('URI="')
                                uri_part = parts[1].split('"')[0]
                                full_uri = urllib.parse.urljoin(base_url, uri_part)
                                proxied_uri = f"/api/m3u8-proxy?url={urllib.parse.quote(full_uri)}"
                                line_str = parts[0] + 'URI="' + proxied_uri + '"' + parts[1][len(uri_part)+1:]
                            new_lines.append(line_str)
                        else:
                            new_lines.append(line)
                    new_body = "\n".join(new_lines).encode('utf-8')
                    handler.send_response(200)
                    handler.send_header('Content-Type', 'application/vnd.apple.mpegurl')
                    handler.send_header('Access-Control-Allow-Origin', '*')
                    handler.end_headers()
                    handler.wfile.write(new_body)
                else:
                    handler.send_response(200)
                    handler.send_header('Content-Type', content_type or 'video/MP2T')
                    handler.send_header('Content-Length', str(len(body)))
                    handler.send_header('Accept-Ranges', 'bytes')
                    handler.send_header('Access-Control-Allow-Origin', '*')
                    handler.end_headers()
                    handler.wfile.write(body)
                return
        except Exception:
            handler.send_response(302)
            handler.send_header('Location', m3u8_url)
            handler.send_header('Access-Control-Allow-Origin', '*')
            handler.end_headers()

# -------------------------------------------------------------
# THREADED HTTP SERVER CLASS (PREVENTS BLOCKING)
# -------------------------------------------------------------
class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # Silently suppress broken pipe and socket disconnects
        pass

class RequestHandler(http.server.SimpleHTTPRequestHandler):
    do_HEAD = lambda self: self.do_GET()

    def handle_one_request(self):
        try:
            super().handle_one_request()
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            pass

    def end_headers(self):
        self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Expires', '0')
        try:
            super().end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/api/resolve':
            query = urllib.parse.parse_qs(parsed_path.query)
            tmdb_id = query.get('tmdbId', ['1081003'])[0]
            media_type = query.get('type', ['movie'])[0]
            season = query.get('season', ['1'])[0]
            episode = query.get('episode', ['1'])[0]

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            try:
                result = resolve_streams(tmdb_id, media_type, season, episode)
                self.wfile.write(json.dumps(result).encode('utf-8'))
            except Exception as e:
                err_resp = {'success': False, 'error': str(e)}
                self.wfile.write(json.dumps(err_resp).encode('utf-8'))

        elif parsed_path.path == '/ofcmovies_project.zip':
            self.send_response(200)
            self.send_header('Content-Type', 'application/zip')
            self.send_header('Content-Disposition', 'attachment; filename="ofcmovies_project.zip"')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            zip_path = '/root/ofcmovies_project.zip'
            if os.path.exists(zip_path):
                with open(zip_path, 'rb') as f:
                    self.wfile.write(f.read())
            return

        elif parsed_path.path == '/api/m3u8-proxy':
            raw_q = parsed_path.query
            m3u8_url = urllib.parse.unquote(raw_q.split('url=', 1)[1]) if 'url=' in raw_q else ''
            if not m3u8_url:
                self.send_response(400)
                self.end_headers()
                return
            proxy_m3u8(m3u8_url, self)

        elif parsed_path.path == '/api/download-video':
            query = urllib.parse.parse_qs(parsed_path.query)
            m3u8_url = query.get('url', [''])[0]
            title_str = query.get('title', ['video'])[0]
            if not m3u8_url:
                self.send_response(400)
                self.end_headers()
                return

            stream_download_mp4(m3u8_url, title_str, self)

        elif parsed_path.path.startswith('/dwn'):
            query = urllib.parse.parse_qs(parsed_path.query)
            path_parts = [p for p in parsed_path.path.split('/') if p]
            
            tmdb_id = None
            media_type = query.get('type', ['movie'])[0]
            season = query.get('season', ['1'])[0]
            episode = query.get('episode', ['1'])[0]
            
            if len(path_parts) >= 2:
                tmdb_id = path_parts[1]
                if len(path_parts) >= 4:
                    media_type = 'tv'
                    season = path_parts[2]
                    episode = path_parts[3]
            elif query.get('id'):
                tmdb_id = query.get('id')[0]

            if not tmdb_id:
                self.send_response(400)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(b"Error: Missing TMDB ID in request (e.g. /dwn/550 or /dwn/46260/1/1)")
                return

            try:
                result = resolve_streams(tmdb_id, media_type, season, episode)
                if result.get('success') and result.get('sources') and len(result['sources']) > 0:
                    m3u8_url = result['sources'][0]['url']
                    title_str = result.get('title', f"video_{tmdb_id}")
                    if media_type == 'tv':
                        title_str = f"{title_str}_S{season}E{episode}"
                    if result.get('year'):
                        title_str = f"{title_str}_{result['year']}"
                    stream_download_mp4(m3u8_url, title_str, self)
                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Error: Could not resolve valid download stream for this media ID.")
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error resolving download: {str(e)}".encode('utf-8'))

        elif parsed_path.path.startswith('/test-dwn'):
            query = urllib.parse.parse_qs(parsed_path.query)
            path_parts = [p for p in parsed_path.path.split('/') if p]
            tmdb_id = path_parts[1] if len(path_parts) >= 2 else (query.get('id', ['550'])[0])
            
            try:
                import sys
                if '/root' not in sys.path: sys.path.append('/root')
                if '/root/test' not in sys.path: sys.path.append('/root/test')
                from test_stitcher import parse_segment_urls, download_single_segment
                import concurrent.futures
                
                res = resolve_streams(tmdb_id, 'movie')
                if res.get('success') and res.get('sources'):
                    m3u8_url = res['sources'][0]['url']
                    title = res.get('title', 'video').replace(' ', '_')
                    direct_variant_url = resolve_master_m3u8_to_direct(m3u8_url)
                    segment_urls = parse_segment_urls(direct_variant_url)
                    
                    # Test limit: download first 3 segments (exactly ~10 seconds of HD video sample)
                    test_segs = segment_urls[:3]
                    segments_data = [None] * len(test_segs)
                    
                    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                        futures = [executor.submit(download_single_segment, idx, url) for idx, url in enumerate(test_segs)]
                        for future in concurrent.futures.as_completed(futures):
                            idx, seg_bytes = future.result()
                            if seg_bytes:
                                segments_data[idx] = seg_bytes

                    self.send_response(200)
                    self.send_header('Content-Type', 'video/mp4')
                    self.send_header('Content-Disposition', f'attachment; filename="{title}_10sec_Sample.mp4"')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()

                    for chunk in segments_data:
                        if chunk:
                            self.wfile.write(chunk)
                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'text/plain')
                    self.end_headers()
                    self.wfile.write(b"Error: Stream resolution failed.")
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain')
                self.end_headers()
                self.wfile.write(f"Error: {str(e)}".encode('utf-8'))

        elif (parsed_path.path.startswith('/movie/') or parsed_path.path.startswith('/tv/')) and not parsed_path.path.endswith(('.css', '.js', '.png', '.jpg', '.ico', '.svg', '.json', '.woff', '.woff2', '.ttf')):
            self.path = '/index.html'
            super().do_GET()
        else:
            super().do_GET()

if __name__ == '__main__':
    server = ThreadedHTTPServer(("0.0.0.0", PORT), RequestHandler)
    if os.path.exists('/root/cert.pem') and os.path.exists('/root/key.pem'):
        try:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ctx.load_cert_chain('/root/cert.pem', '/root/key.pem')
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            print(f"SSL Certificate Enabled! Serving HTTPS on port {PORT}")
        except Exception as e:
            print(f"SSL Load Notice: {e}")
    else:
        print(f"Serving HTTP on port {PORT}")
    server.serve_forever()
