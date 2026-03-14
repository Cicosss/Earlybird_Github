#!/usr/bin/env python3
"""
Simple HTTP Server for Architecture Maps

This script starts a simple HTTP server to serve the docs/visual_architecture
directory on port 8001.

Usage:
    python3 src/utils/serve_docs.py [--verbose]

Then open your browser to: http://localhost:8001

Options:
    --verbose    Enable HTTP request logging for debugging
"""

import argparse
import errno
import http.server
import os
import socketserver
import sys


def serve_docs(verbose=False):
    """Start HTTP server to serve docs/visual_architecture directory.

    Args:
        verbose: If True, enable HTTP request logging.
    """

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

    # Create custom handler with optional logging
    class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format_, *args):
            """Log HTTP requests if verbose mode is enabled."""
            if verbose:
                # Use sys.stderr.write for HTTP server logging (standard practice)
                sys.stderr.write(
                    "%s - - [%s] %s\n"
                    % (self.client_address[0], self.log_date_time_string(), format_ % args)
                )

    # Create server with proper error handling
    try:
        # Bind to 127.0.0.1 (localhost only) for security
        # This prevents exposure on all network interfaces (0.0.0.0)
        httpd = socketserver.TCPServer(("127.0.0.1", PORT), MyHTTPRequestHandler)
    except OSError as e:
        # Handle port conflict specifically
        if e.errno in (errno.EADDRINUSE, errno.EADDRNOTAVAIL):
            print(f"ERROR: Port {PORT} is already in use.")
            print("\nTo find and stop the conflicting process:")
            print("  On Linux/macOS: lsof -i :8001")
            print("  On Linux:        sudo netstat -tulpn | grep 8001")
            print("  On Windows:      netstat -ano | findstr 8001")
            print("\nThen kill the process or use a different port.")
            sys.exit(1)
        else:
            # Other errors (permission denied, etc.)
            print(f"ERROR: Failed to start server: {e}")
            sys.exit(1)

    # Server is now running
    print(f"Serving Architecture Map at http://localhost:{PORT}")
    print(f"Serving directory: {os.path.abspath(serve_dir)}")
    if verbose:
        print("Verbose mode enabled - logging HTTP requests to stderr.")
    print("Press Ctrl+C to stop the server.")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple HTTP server for architecture maps")
    parser.add_argument(
        "--verbose", action="store_true", help="Enable HTTP request logging for debugging"
    )
    args = parser.parse_args()
    serve_docs(verbose=args.verbose)
