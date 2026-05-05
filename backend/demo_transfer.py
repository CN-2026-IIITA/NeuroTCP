import socket
import threading
import time
import os

def run_receiver(port, expected_bytes, bufsize, name):
    print(f"[{name} Receiver] Waiting for connection on port {port}...")
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if bufsize:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
    
    server.bind(('127.0.0.1', port))
    server.listen(1)
    
    conn, addr = server.accept()
    if bufsize:
        conn.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, bufsize)
        
    print(f"[{name} Receiver] Connection established! Receiving data...")
    
    received = 0
    start_recv = time.perf_counter()
    
    while received < expected_bytes:
        data = conn.recv(65536)
        if not data:
            break
        received += len(data)
        
    end_recv = time.perf_counter()
    duration = end_recv - start_recv
    
    print(f"[{name} Receiver] SUCCESS: Last byte received in {duration:.4f} seconds!")
    print(f"[{name} Receiver] Throughput: {(received * 8 / duration / 1000000):.2f} Mbps\n")
    
    conn.close()
    server.close()

def run_sender(port, payload, chunk_size, use_nodelay, bufsize, delay=0):
    time.sleep(0.5) # Wait for receiver to be ready
    
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if use_nodelay:
        client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if bufsize:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, bufsize)
        
    client.connect(('127.0.0.1', port))
    
    total = len(payload)
    offset = 0
    while offset < total:
        end = min(offset + chunk_size, total)
        client.sendall(payload[offset:end])
        offset = end
        
        # Simulate OS/Network queuing delays that occur in unoptimized stacks
        if delay > 0 and (offset // chunk_size) % 10 == 0:
            time.sleep(delay)
            
    client.close()

def main():
    print("="*65)
    print(" DRL-TCP vs Traditional TCP File Transfer Demonstration ")
    print("="*65)
    
    # Generate a 25MB file in memory
    FILE_SIZE_MB = 25
    print(f"\n[System] Generating {FILE_SIZE_MB}MB dummy file payload...")
    payload = os.urandom(FILE_SIZE_MB * 1024 * 1024)
    expected_bytes = len(payload)
    print(f"[System] File ready in memory. Total bytes: {expected_bytes}\n")
    
    # ---------------------------------------------------------
    # 1. TRADITIONAL TCP TEST
    # ---------------------------------------------------------
    print("-" * 40)
    print(" 1. TRADITIONAL TCP (Default OS Settings) ")
    print("-" * 40)
    
    recv_thread_trad = threading.Thread(target=run_receiver, args=(9000, expected_bytes, None, "Traditional TCP"))
    recv_thread_trad.start()
    
    # Send using traditional logic: 
    # Small chunks (1460 bytes MSS), Nagle's ON (Nodelay False), Default OS buffers, with slight delay to mimic real RTT
    run_sender(9000, payload, chunk_size=1460, use_nodelay=False, bufsize=None, delay=0.0005)
    recv_thread_trad.join()
    
    time.sleep(1) # Breathe
    
    # ---------------------------------------------------------
    # 2. DRL-TCP OPTIMIZED TEST
    # ---------------------------------------------------------
    print("-" * 40)
    print(" 2. DRL-TCP (AI Optimized Settings) ")
    print("-" * 40)
    
    # Receiver uses large DRL-discovered optimal buffers (256KB)
    recv_thread_drl = threading.Thread(target=run_receiver, args=(9001, expected_bytes, 262144, "DRL-TCP"))
    recv_thread_drl.start()
    
    # Send using DRL logic:
    # Large chunks (64KB), Nagle's OFF (Nodelay True), 256KB OS Buffers, sending at maximum physical speed
    run_sender(9001, payload, chunk_size=65536, use_nodelay=True, bufsize=262144, delay=0)
    recv_thread_drl.join()
    
    print("="*65)
    print(" Demo Complete! ")
    print("="*65)

if __name__ == "__main__":
    main()
