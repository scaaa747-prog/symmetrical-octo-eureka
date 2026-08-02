from http.server import BaseHTTPRequestHandler
import json
import urllib.parse
import sys
import os

cwd = os.getcwd()
if cwd not in sys.path:
    sys.path.append(cwd)
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from server import resolve_streams

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
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
