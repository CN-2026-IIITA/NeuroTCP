"""
DRL-TCP Demo: RECEIVER
Run this on your FRIEND'S computer.

Usage:
    python receiver.py
    
It will listen on port 9000 and wait for the sender to connect.
"""
import socket
import time
import sys

PORT = 9000
RECV_CHUNK = 65536

def main():
    print("=" * 60)
    print("  DRL-TCP RECEIVER - Waiting for incoming file transfer")
    print("=" * 60)
    
    # Get this machine's IP to display
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"\n  This machine's IP: {local_ip}")
    print(f"  Listening on port: {PORT}")
    print(f"\n  Tell the SENDER to use this IP address!")
    print("-" * 60)
    
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', PORT))  # Listen on all interfaces
    server.listen(5)
    
    test_number = 0
    
    while True:
        test_number += 1
        print(f"\n[Test #{test_number}] Waiting for sender to connect...")
        
        conn, addr = server.accept()
        print(f"[Test #{test_number}] Connection from {addr[0]}:{addr[1]}")
        
        # First, receive the 64-byte header containing test metadata
        header = b""
        while len(header) < 64:
            chunk = conn.recv(64 - len(header))
            if not chunk:
                break
            header += chunk
        
        # Parse header: method_name (32 bytes) + file_size (32 bytes)
        method_name = header[:32].decode('utf-8').strip('\x00')
        file_size = int(header[32:64].decode('utf-8').strip('\x00'))
        
        print(f"[Test #{test_number}] Method: {method_name}")
        print(f"[Test #{test_number}] Expected size: {file_size / (1024*1024):.1f} MB")
        print(f"[Test #{test_number}] Receiving data...")
        
        received = 0
        start_time = time.perf_counter()
        
        while received < file_size:
            data = conn.recv(RECV_CHUNK)
            if not data:
                break
            received += len(data)
        
        end_time = time.perf_counter()
        duration = end_time - start_time
        throughput = (received * 8 / duration / 1_000_000) if duration > 0 else 0
        
        print(f"")
        print(f"  ===================================================")
        print(f"  [{method_name}] RESULT:")
        print(f"  ---------------------------------------------------")
        print(f"  Bytes received : {received:,} / {file_size:,}")
        print(f"  Transfer time  : {duration:.4f} seconds")
        print(f"  Throughput     : {throughput:.2f} Mbps")
        print(f"  ===================================================")
        print(f"")
        
        conn.close()

if __name__ == "__main__":
    main()
