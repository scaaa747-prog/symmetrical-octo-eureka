from http.server import BaseHTTPRequestHandler
import urllib.parse
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import proxy_m3u8

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed_path.query)
        m3u8_url = query.get('url', [''])[0]
        if not m3u8_url:
            self.send_response(400)
            self.end_headers()
            return
        proxy_m3u8(m3u8_url, self)
