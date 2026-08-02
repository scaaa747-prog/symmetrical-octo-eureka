from http.server import BaseHTTPRequestHandler
import urllib.parse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import resolve_streams, stream_download_mp4

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        path_parts = [p for p in parsed_path.path.split('/') if p]
        tmdb_id = path_parts[-1] if path_parts else query.get('id', ['550'])[0]
        media_type = query.get('type', ['movie'])[0]

        res = resolve_streams(tmdb_id, media_type)
        if res.get('success') and res.get('sources'):
            m3u8_url = res['sources'][0]['url']
            title = res.get('title', 'video')
            stream_download_mp4(m3u8_url, title, self)
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Error: Stream resolution failed.")
