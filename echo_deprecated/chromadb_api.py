#!/usr/bin/env python3
"""
ChromaDB API Server

This script provides a simple API server to access ChromaDB data for the Obsidian Narrative View plugin.
It exposes endpoints for retrieving and searching narrative chunks.

Usage:
    python chromadb_api.py
"""

import os
import json
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import chromadb

# Default settings
DEFAULT_PORT = 3000
DEFAULT_CHROMA_PATH = "/Users/pythagor/nexus/chroma_db"
DEFAULT_COLLECTION = "transcripts"

class ChromaDBAPI(BaseHTTPRequestHandler):
    """
    HTTP request handler for the ChromaDB API server
    """
    
    def __init__(self, *args, chroma_path=DEFAULT_CHROMA_PATH, collection_name=DEFAULT_COLLECTION, **kwargs):
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        
        # Initialize the ChromaDB client
        try:
            self.client = chromadb.PersistentClient(self.chroma_path)
            self.collection = self.client.get_collection(self.collection_name)
        except Exception as e:
            print(f"Error initializing ChromaDB: {e}")
        
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            parsed_url = urlparse(self.path)
            path = parsed_url.path
            query_params = parse_qs(parsed_url.query)
            
            # Add CORS headers
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
            self.end_headers()
            
            # Route requests
            if path == '/api/narrative-chunks':
                limit = int(query_params.get('limit', [50])[0])
                result = self.get_recent_chunks(limit)
                self.wfile.write(json.dumps(result).encode())
            
            elif path == '/api/search-chunks':
                query = query_params.get('query', [''])[0]
                limit = int(query_params.get('limit', [10])[0])
                result = self.search_chunks(query, limit)
                self.wfile.write(json.dumps(result).encode())
            
            else:
                # Default route
                response = {
                    'status': 'ok',
                    'message': 'ChromaDB API server running',
                    'endpoints': [
                        '/api/narrative-chunks?limit=50',
                        '/api/search-chunks?query=example&limit=10'
                    ]
                }
                self.wfile.write(json.dumps(response).encode())
        
        except Exception as e:
            # Handle errors
            error_response = {
                'status': 'error',
                'message': str(e)
            }
            self.wfile.write(json.dumps(error_response).encode())
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests for CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def get_recent_chunks(self, limit=50):
        """Get recent chunks from ChromaDB"""
        if not self.collection:
            return {'error': 'ChromaDB collection not initialized'}
        
        try:
            # Get recent chunks sorted by ID (assuming IDs are sequential or chronological)
            result = self.collection.get(limit=limit)
            return result
        except Exception as e:
            return {'error': f'Error fetching chunks: {str(e)}'}
    
    def search_chunks(self, query, limit=10):
        """Search chunks in ChromaDB"""
        if not self.collection:
            return {'error': 'ChromaDB collection not initialized'}
        
        try:
            # Perform a semantic search
            result = self.collection.query(
                query_texts=[query],
                n_results=limit,
                include=["documents", "metadatas", "distances"]
            )
            
            # Format the result to match the get() method format
            formatted_result = {
                'ids': result['ids'][0],
                'documents': result['documents'][0],
                'metadatas': result['metadatas'][0],
                'distances': result['distances'][0]
            }
            
            return formatted_result
        except Exception as e:
            return {'error': f'Error searching chunks: {str(e)}'}

def run_server(port=DEFAULT_PORT, chroma_path=DEFAULT_CHROMA_PATH, collection_name=DEFAULT_COLLECTION):
    """Run the API server"""
    
    # Create a server with the handler
    def handler_factory(*args, **kwargs):
        return ChromaDBAPI(*args, chroma_path=chroma_path, collection_name=collection_name, **kwargs)
    
    server = HTTPServer(('localhost', port), handler_factory)
    print(f"Starting ChromaDB API server on port {port}")
    print(f"ChromaDB path: {chroma_path}")
    print(f"Collection name: {collection_name}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='ChromaDB API Server')
    parser.add_argument('--port', type=int, default=DEFAULT_PORT, help='Port to run the server on')
    parser.add_argument('--chroma-path', type=str, default=DEFAULT_CHROMA_PATH, help='Path to ChromaDB')
    parser.add_argument('--collection', type=str, default=DEFAULT_COLLECTION, help='ChromaDB collection name')
    
    args = parser.parse_args()
    
    run_server(port=args.port, chroma_path=args.chroma_path, collection_name=args.collection) 