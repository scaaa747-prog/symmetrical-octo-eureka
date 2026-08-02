from http.server import BaseHTTPRequestHandler
import urllib.parse
import sys
import os

cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.append(cwd)
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

try:
    from server import proxy_m3u8
except Exception:
    import urllib.request, ssl
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

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        raw_q = parsed_path.query
        m3u8_url = urllib.parse.unquote(raw_q.split('url=', 1)[1]) if 'url=' in raw_q else ''
        if not m3u8_url:
            self.send_response(400)
            self.end_headers()
            return
        proxy_m3u8(m3u8_url, self)
