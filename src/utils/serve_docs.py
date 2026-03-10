#!/usr/bin/env python3
"""
Simple HTTP Server for Architecture Maps

This script starts a simple HTTP server to serve the docs/visual_architecture
directory on port 8001.

Usage:
    python3 src/utils/serve_docs.py

Then open your browser to: http://localhost:8001
"""

import http.server
import os
import socketserver
import sys


def serve_docs():
    """Start HTTP server to serve docs/visual_architecture directory."""

    # Directory to serve
    serve_dir = "docs/visual_architecture"

    # Check if directory exists
    if not os.path.exists(serve_dir):
        print(f"ERROR: Directory '{serve_dir}' does not exist.")
        print("Please run 'make map' first to generate the architecture maps.")
        sys.exit(1)

    # Change to the directory to serve
    try:
        os.chdir(serve_dir)
    except OSError as e:
        print(f"ERROR: Failed to change to directory '{serve_dir}': {e}")
        sys.exit(1)

    # Port to serve on
    PORT = 8001

    # Create custom handler
    class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            """Suppress default logging for cleaner output."""
            pass

    # Create server
    with socketserver.TCPServer(("", PORT), MyHTTPRequestHandler) as httpd:
        print(f"Serving Architecture Map at http://localhost:{PORT}")
        print(f"Serving directory: {os.path.abspath(serve_dir)}")
        print("Press Ctrl+C to stop the server.")

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nServer stopped.")


if __name__ == "__main__":
    serve_docs()
