"""
DRL-TCP Demo: SENDER
Run this on YOUR computer (the one with the project).

Usage:
    python sender.py <RECEIVER_IP>

Example:
    python sender.py 192.168.1.105
"""
import socket
import time
import os
import sys

PORT = 9000
FILE_SIZE_MB = 100

def send_file(receiver_ip, payload, method_name, chunk_size, use_nodelay, bufsize, congestion_algo=None):
    """Send the payload to the receiver using the specified TCP settings."""
    
    print(f"\n{'='*55}")
    print(f"  Sending with: {method_name}")
    print(f"  Chunk size: {chunk_size} bytes | TCP_NODELAY: {use_nodelay}")
    print(f"{'='*55}")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    if use_nodelay:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if bufsize:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, bufsize)
    
    # Set the actual kernel-level TCP congestion control algorithm
    # TCP_CONGESTION = 13 on Linux
    if congestion_algo:
        try:
            TCP_CONGESTION = 13
            sock.setsockopt(socket.IPPROTO_TCP, TCP_CONGESTION, congestion_algo.encode())
            print(f"  Congestion algorithm set to: {congestion_algo}")
        except Exception as e:
            print(f"  [Note] Could not set congestion algo '{congestion_algo}': {e}")
            print(f"  (This requires Linux with the kernel module loaded)")
    
    print(f"  Connecting to {receiver_ip}:{PORT}...")
    sock.connect((receiver_ip, PORT))
    print(f"  Connected! Sending {len(payload)/(1024*1024):.1f} MB...")
    
    # Send 64-byte header: method_name (32 bytes) + file_size (32 bytes)
    header = method_name.ljust(32, '\x00').encode('utf-8')[:32]
    header += str(len(payload)).ljust(32, '\x00').encode('utf-8')[:32]
    sock.sendall(header)
    
    # Send the actual payload
    start_time = time.perf_counter()
    
    offset = 0
    total = len(payload)
    while offset < total:
        end = min(offset + chunk_size, total)
        sock.sendall(payload[offset:end])
        offset = end
    
    end_time = time.perf_counter()
    duration = end_time - start_time
    throughput = (total * 8 / duration / 1_000_000) if duration > 0 else 0
    
    print(f"  Sent in {duration:.4f} seconds ({throughput:.2f} Mbps)")
    
    sock.close()
    return duration

def main():
    if len(sys.argv) < 2:
        print("Usage: python sender.py <RECEIVER_IP>")
        print("Example: python sender.py 192.168.1.105")
        sys.exit(1)
    
    receiver_ip = sys.argv[1]
    
    print("=" * 55)
    print("  DRL-TCP vs Traditional TCP - SENDER")
    print("=" * 55)
    print(f"  Target receiver: {receiver_ip}:{PORT}")
    print(f"  File size: {FILE_SIZE_MB} MB")
    
    # Generate random payload
    print(f"\n  Generating {FILE_SIZE_MB}MB random payload...")
    payload = os.urandom(FILE_SIZE_MB * 1024 * 1024)
    print(f"  Payload ready ({len(payload):,} bytes)")
    
    # -----------------------------------------------
    # TEST 1: Traditional TCP
    # -----------------------------------------------
    # Small chunks (1 MSS = 1460 bytes)
    # Nagle's algorithm ON (default)
    # Default OS socket buffers
    trad_time = send_file(
        receiver_ip, payload,
        method_name="Traditional TCP (Cubic)",
        chunk_size=1460,
        use_nodelay=False,
        bufsize=None,
        congestion_algo="cubic"
    )
    
    print("\n  Waiting 3 seconds before next test...\n")
    time.sleep(3)
    
    # -----------------------------------------------
    # TEST 2: DRL-TCP Optimized
    # -----------------------------------------------
    # Large chunks (64KB - aggressive send)
    # TCP_NODELAY ON (Nagle disabled)
    # 256KB send buffer (DRL-learned optimal window)
    drl_time = send_file(
        receiver_ip, payload,
        method_name="DRL-TCP Optimized",
        chunk_size=65536,
        use_nodelay=True,
        bufsize=262144,
        congestion_algo="drl_tcp"
    )
    
    # -----------------------------------------------
    # SUMMARY
    # -----------------------------------------------
    speedup = trad_time / drl_time if drl_time > 0 else 0
    reduction = ((trad_time - drl_time) / trad_time * 100) if trad_time > 0 else 0
    
    print(f"\n{'='*55}")
    print(f"  FINAL RESULTS")
    print(f"{'='*55}")
    print(f"  Traditional TCP : {trad_time:.4f} seconds")
    print(f"  DRL-TCP         : {drl_time:.4f} seconds")
    print(f"  Speedup         : {speedup:.2f}x faster")
    print(f"  Time saved      : {reduction:.1f}%")
    print(f"{'='*55}")

if __name__ == "__main__":
    main()
