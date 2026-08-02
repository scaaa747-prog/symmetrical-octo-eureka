from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import resolve_streams, proxy_m3u8, stream_download_mp4

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        
        if parsed_path.path.startswith('/api/resolve'):
            query = urllib.parse.parse_qs(parsed_path.query)
            tmdb_id = query.get('tmdbId', ['550'])[0]
            media_type = query.get('type', ['movie'])[0]
            season = query.get('season', ['1'])[0]
            episode = query.get('episode', ['1'])[0]

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            result = resolve_streams(tmdb_id, media_type, season, episode)
            self.wfile.write(json.dumps(result).encode('utf-8'))

        elif parsed_path.path.startswith('/api/m3u8-proxy'):
            query = urllib.parse.parse_qs(parsed_path.query)
            m3u8_url = query.get('url', [''])[0]
            if not m3u8_url:
                self.send_response(400)
                self.end_headers()
                return
            proxy_m3u8(m3u8_url, self)

        elif parsed_path.path.startswith('/api/download-video'):
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
            tmdb_id = path_parts[1] if len(path_parts) >= 2 else (query.get('id', ['550'])[0])
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

        else:
            self.send_response(404)
            self.end_headers()
