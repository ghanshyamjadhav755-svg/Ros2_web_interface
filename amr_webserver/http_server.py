#!/usr/bin/env python3

from aiohttp import web
import os
from ament_index_python.packages import get_package_share_directory

class HTTPServer:
    def __init__(self, port=8080):
        self.port = port
        self.app = web.Application()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_static('/static/', 
                                   path=self.get_web_directory(),
                                   name='static')
    
    def get_web_directory(self):
        """Get web files directory"""
        try:
            pkg_dir = get_package_share_directory('amr_webserver')
            return os.path.join(pkg_dir, 'web')
        except:
            return os.path.join(os.path.dirname(__file__), '..', 'web')
    
    async def index_handler(self, request):
        """Serve index.html"""
        web_dir = self.get_web_directory()
        index_path = os.path.join(web_dir, 'index.html')
        return web.FileResponse(index_path)
    
    def run(self):
        """Start HTTP server"""
        print(f'Starting HTTP server on http://0.0.0.0:{self.port}')
        web.run_app(self.app, host='0.0.0.0', port=self.port)

def main():
    server = HTTPServer(port=8080)
    server.run()

if __name__ == '__main__':
    main()