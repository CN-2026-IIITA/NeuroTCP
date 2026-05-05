#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRL TCP Congestion Control Agent  (v5 — fixed)

FIXES over v4:
  A. shape_reward() no longer double-counts RTT/loss penalties:
     C++ computes tp_score + rtt_penalty + loss_penalty as raw_reward.
     Python now ONLY clips — no additional penalties on top.
  B. State index mapping corrected to match C++ GetObservation():
     C++ sends segmentSize at index 2, segmentsAcked at index 3 (was swapped).
  C. STATE_SCALE updated to match corrected index order.
  D. ns3 minRtt (next_raw[6]) passed directly to shape_reward()
     instead of tracking _min_rtt_seen in Python from avgRtt samples.
  E. ssThresh: only halved on packet loss, else set to max (0x7FFFFFFF)
     to avoid triggering unnecessary slow-start every step.
"""

import sys
import argparse
import os
import subprocess
import time
import platform
import threading
import random
import math
from collections import deque

import numpy as np
import pathlib

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import tensorflow as tf

# ── Environment Detection ─────────────────────────────────────────────────────
IS_WINDOWS = (platform.system() == 'Windows')

def win_to_wsl_path(win_path):
    p = str(win_path).replace('\\', '/')
    if len(p) >= 2 and p[1] == ':':
        drive = p[0].lower()
        p = f'/mnt/{drive}{p[2:]}'
    return p

# ── Paths ─────────────────────────────────────────────────────────────────────
project_root = pathlib.Path(__file__).resolve().parent.parent
drl_tcp_dir  = project_root / 'Drl-Tcp-DQN'
ns3_dir      = project_root / 'ns-allinone-3.35' / 'ns-3.35'
ns3gym_path  = ns3_dir / 'contrib' / 'opengym' / 'model' / 'ns3gym'

if str(ns3gym_path) not in sys.path:
    sys.path.insert(0, str(ns3gym_path))

try:
    from ns3gym import ns3env
except ImportError as e:
    print(f"[ERROR] Cannot import ns3gym from {ns3gym_path}: {e}")
    sys.exit(1)

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
tf.get_logger().setLevel('ERROR')

# ── Arguments ─────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument('--episodes',     type=int, default=30)
parser.add_argument('--steps',        type=int, default=200)
parser.add_argument('--mode',         type=str, default='train',
                    choices=['train', 'test'])
parser.add_argument('--export-steps', type=str, default='',
                    help='Path to write per-step CSV for comparison plots')
args = parser.parse_args()

EPISODES     = args.episodes
STEPS        = args.steps
MODE         = args.mode
EXPORT_STEPS = args.export_steps
MODEL_FILE   = str(drl_tcp_dir / 'tcp_rl_model.h5')

# ── Simulation parameters ─────────────────────────────────────────────────────
PORT           = 5555
SEED           = 12
TIME_STEP      = 0.1
TOTAL_DURATION = (EPISODES * STEPS * TIME_STEP) + 30.0

# ── DQN hyper-parameters ──────────────────────────────────────────────────────
BATCH_SIZE         = 64
BUFFER_SIZE        = 20_000
TARGET_UPDATE_FREQ = 100
GAMMA              = 0.99
LEARNING_RATE      = 3e-4
WARMUP_STEPS       = 500

EPSILON_START = 1.0
EPSILON_MIN   = 0.05
EPSILON_DECAY = 0.9997   # per step

# ── Action map ────────────────────────────────────────────────────────────────
STATE_SIZE  = 12
ACTION_SIZE = 4

ACTION_MAP = {
    0: -1440,   # decrease 4 segments
    1:  -360,   # decrease 1 segment
    2:  +360,   # increase 1 segment
    3: +1440,   # increase 4 segments
}

MIN_CWND = 1440    # 1 segment minimum
MAX_CWND = 50_000  # hard ceiling

# ── FIX A: shape_reward — no double penalties ─────────────────────────────────
#
# C++ GetObservation() already computes:
#   reward = tp_score + rtt_penalty + loss_penalty
# and clips it to [-5, +5] before sending as raw_reward.
#
# Python must NOT add its own RTT or loss penalties on top.
# Just clip and return.
#
# FIX D: ns3_min_rtt_us is now passed in (next_raw[6]) but not used here
# since C++ already handles the rtt_ratio internally.  Parameter kept for
# potential future diagnostics / logging.
def shape_reward(raw_reward: float,
                 avg_rtt_us: float,
                 ns3_min_rtt_us: float,
                 tp_bps: float,
                 pkts_lost: int) -> float:
    # C++ already did the heavy lifting — just clip.
    return float(np.clip(raw_reward, -5.0, 5.0))

# ── FIX B+C: State layout corrected to match C++ GetObservation() ────────────
#
# C++ obs[4:] order:
#   [0]  ssThresh          → scale 1e5
#   [1]  cWnd              → scale 1e5
#   [2]  segmentSize       → scale 1e3   ← FIX: was labeled segmentsAcked
#   [3]  segmentsAckedSum  → scale 1e3   ← FIX: was labeled segmentSize (wrong scale too)
#   [4]  bytesInFlightAvg  → scale 1e5
#   [5]  lastRtt (avgRtt)  → scale 1e5
#   [6]  minRtt            → scale 1e5
#   [7]  avgRtt            → scale 1e5
#   [8]  rttVariance (0)   → scale 1e4
#   [9]  packetLostInStep  → scale 1.0
#   [10] retransmissions   → scale 1.0
#   [11] throughput        → scale 1.25e6
STATE_SCALE = np.array([
    1e5,    # [0]  ssThresh
    1e5,    # [1]  cWnd
    1e3,    # [2]  segmentSize       ← FIX C: was 1e2 under wrong label
    1e3,    # [3]  segmentsAckedSum  ← FIX C: was 1e3 under wrong label (scale ok, label fixed)
    1e5,    # [4]  bytesInFlightAvg
    1e5,    # [5]  lastRtt (avgRtt)
    1e5,    # [6]  minRtt
    1e5,    # [7]  avgRtt
    1e4,    # [8]  rttVariance (always 0 from C++)
    1.0,    # [9]  packetLostInStep
    1.0,    # [10] retransmissions (always 0 from C++)
    1.25e6, # [11] throughput (bytes/s)
], dtype=np.float32)

def normalise(state_raw: np.ndarray) -> np.ndarray:
    return np.clip(state_raw / STATE_SCALE, -10.0, 10.0)

# ── Background stdout drain ───────────────────────────────────────────────────
def _drain_ns3_stdout(proc):
    try:
        for _ in proc.stdout:
            pass
    except Exception:
        pass

# ── Launch NS-3 ───────────────────────────────────────────────────────────────
def launch_ns3():
    sim_args = (f"sim --transport_prot=TcpRlTimeBased "
                f"--duration={TOTAL_DURATION:.1f}")
    if IS_WINDOWS:
        wsl_ns3 = win_to_wsl_path(ns3_dir)
        cmd = f'wsl bash -c "cd \'{wsl_ns3}\' && ./waf --run \\"{sim_args}\\""'
        cwd = None
    else:
        cmd = f'{ns3_dir / "waf"} --run "{sim_args}"'
        cwd = str(ns3_dir)

    print(f"[INFO] Launching NS-3…  duration={TOTAL_DURATION:.1f}s")
    print(f"       Command: {cmd}")

    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    start_wait, ready = time.time(), False
    for line in proc.stdout:
        print(f"  [ns3] {line}", end='')
        if 'Waiting for Python process' in line or 'Please start proper' in line:
            ready = True
            break
        if proc.poll() is not None:
            print(proc.stdout.read())
            print(f"\n[ERROR] NS-3 exited early (code {proc.returncode}).")
            sys.exit(1)
        if time.time() - start_wait > 180:
            proc.kill()
            print("\n[ERROR] Timeout waiting for NS-3.")
            sys.exit(1)

    if not ready:
        print("[ERROR] NS-3 ready message never arrived.")
        sys.exit(1)

    threading.Thread(target=_drain_ns3_stdout, args=(proc,), daemon=True).start()
    print("[INFO] NS-3 ready.\n")
    return proc

# ── Build model ───────────────────────────────────────────────────────────────
def build_model():
    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(STATE_SIZE,)),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dense(128, activation='relu'),
        tf.keras.layers.Dense(64,  activation='relu'),
        tf.keras.layers.Dense(ACTION_SIZE, activation='linear')
    ])
    model.compile(
        optimizer=tf.keras.optimizers.Adam(
            learning_rate=LEARNING_RATE, clipnorm=0.5),
        loss='huber'
    )
    return model

# ── Load / create model ───────────────────────────────────────────────────────
if MODE == 'test':
    if os.path.exists(MODEL_FILE):
        print(f"[INFO] Loading model: {MODEL_FILE}")
        model   = tf.keras.models.load_model(MODEL_FILE)
        epsilon = 0.0
    else:
        print("[ERROR] No model file found. Train first.")
        sys.exit(1)
    target_model = model
else:
    model        = build_model()
    target_model = build_model()
    target_model.set_weights(model.get_weights())
    model.summary()
    epsilon = EPSILON_START

# ── Replay buffer ─────────────────────────────────────────────────────────────
replay_buffer = deque(maxlen=BUFFER_SIZE)

def store(state, action, reward, next_state, done):
    replay_buffer.append((state.copy(), action, reward,
                          next_state.copy(), done))

def sample_batch():
    batch       = random.sample(replay_buffer, BATCH_SIZE)
    states      = np.vstack([b[0] for b in batch])
    actions     = np.array([b[1] for b in batch], dtype=np.int32)
    rewards     = np.array([b[2] for b in batch], dtype=np.float32)
    next_states = np.vstack([b[3] for b in batch])
    dones       = np.array([b[4] for b in batch], dtype=np.float32)
    return states, actions, rewards, next_states, dones

def train_step():
    """Double-DQN: online net selects action, target net evaluates it."""
    states, actions, rewards, next_states, dones = sample_batch()

    q_online_next    = model.predict(next_states, verbose=0)
    best_actions     = np.argmax(q_online_next, axis=1)
    q_target_next    = target_model.predict(next_states, verbose=0)
    q_next_selected  = q_target_next[np.arange(BATCH_SIZE), best_actions]

    td_targets = rewards + GAMMA * q_next_selected * (1 - dones)
    td_targets = np.clip(td_targets, -5.0, 5.0)

    q_curr = model.predict(states, verbose=0)
    for i in range(BATCH_SIZE):
        q_curr[i][actions[i]] = td_targets[i]

    h = model.fit(states, q_curr, epochs=1, verbose=0,
                  batch_size=BATCH_SIZE)
    return h.history['loss'][0]

# ── History ───────────────────────────────────────────────────────────────────
ep_rewards, ep_losses, ep_rtt, ep_cWnd, ep_tp = [], [], [], [], []
ep_pkt_losses = []

# ── Banner ────────────────────────────────────────────────────────────────────
def banner(msg):
    w = 60
    print("\n" + "─" * w)
    print(f"  {msg}")
    print("─" * w)

eps_target_step = int(math.log(EPSILON_MIN / EPSILON_START) / math.log(EPSILON_DECAY))
eps_target_ep   = eps_target_step // STEPS

banner(f"DQN v5  |  Mode: {MODE.upper()}  |  Episodes: {EPISODES}  |  Steps: {STEPS}")
print(f"  Buffer    : {BUFFER_SIZE:,}  |  Batch: {BATCH_SIZE}  |  Warmup: {WARMUP_STEPS}")
print(f"  ε decay   : per-step {EPSILON_DECAY} → reaches {EPSILON_MIN} ~ep{eps_target_ep}")
print(f"  Actions   : {ACTION_MAP}")
print(f"  cWnd      : [{MIN_CWND}, {MAX_CWND}] bytes")
print(f"  Sim dur   : {TOTAL_DURATION:.1f}s\n")

# ── Launch NS-3 & connect ─────────────────────────────────────────────────────
ns3_proc = launch_ns3()
print("[INFO] Connecting to NS-3 environment…")
env = ns3env.Ns3Env(port=PORT, startSim=False, simSeed=SEED)
print("[INFO] Connected!\n")

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
global_step        = 0
train_start_time   = time.time()
_step_rows: list   = []
zero_reward_streak = 0

for ep in range(EPISODES):
    ep_start = time.time()

    obs       = env.ns3ZmqBridge.get_obs()
    obs       = np.array(obs, dtype=np.float32)
    raw_state = obs[4:]                        # strip 4-element header
    init_cWnd = float(raw_state[1])            # raw_state[1] = cWnd
    cWnd      = init_cWnd
    state     = normalise(raw_state).reshape(1, STATE_SIZE)

    ep_reward    = 0.0
    losses       = []
    rtt_samples  = []
    tp_samples   = []
    cwnd_samples = []
    last_rtt     = 0.0
    last_tp      = 0.0
    step_done    = False
    ep_pkt_loss  = 0

    for step in range(STEPS):
        global_step += 1

        # ε-greedy
        if np.random.rand() < epsilon:
            action_idx = np.random.randint(ACTION_SIZE)
        else:
            q_vals     = model.predict(state, verbose=0)
            action_idx = int(np.argmax(q_vals[0]))

        # Apply action — symmetric cWnd bounds
        calc_cWnd = cWnd + ACTION_MAP[action_idx]
        new_cWnd  = float(np.clip(calc_cWnd, MIN_CWND, MAX_CWND))

        # FIX E: only halve ssThresh on packet loss, else leave at max
        # to avoid triggering unnecessary slow-start every single step.
        # We don't know yet if this step has loss, so we read it from the
        # previous step's loss count as a proxy signal.
        if ep_pkt_loss > 0:
            new_ssThresh = int(cWnd / 2)
        else:
            new_ssThresh = 0x7FFFFFFF   # "infinity" → NS-3 stays in CA_OPEN

        actions_env = [new_ssThresh, int(new_cWnd)]

        next_obs, raw_reward, done, info = env.step(actions_env)

        if next_obs is None:
            step_done = True
            break

        next_obs = np.array(next_obs, dtype=np.float32)
        next_raw = next_obs[4:]   # strip 4-element header

        # ── FIX B: correct state field indices ───────────────────────────────
        # next_raw[0]  = ssThresh
        # next_raw[1]  = cWnd
        # next_raw[2]  = segmentSize    ← C++ index [6]
        # next_raw[3]  = segmentsAcked  ← C++ index [7]
        # next_raw[4]  = bytesInFlight
        # next_raw[5]  = lastRtt (avgRtt)
        # next_raw[6]  = minRtt         ← NS-3 native m_minRtt
        # next_raw[7]  = avgRtt
        # next_raw[8]  = rttVariance (0)
        # next_raw[9]  = packetLostInStep
        # next_raw[10] = retransmissions (0)
        # next_raw[11] = throughput (bytes/s)
        cWnd            = float(next_raw[1])
        last_avg_rtt    = float(next_raw[7])   # avgRtt
        ns3_min_rtt     = float(next_raw[6])   # minRtt from NS-3  ← FIX D
        last_tp         = float(next_raw[11])

        step_loss_delta  = int(next_raw[9])
        ep_pkt_loss     += step_loss_delta

        # FIX A: no double penalties — C++ already computed full reward signal
        reward = shape_reward(raw_reward, last_avg_rtt, ns3_min_rtt,
                              last_tp, step_loss_delta)
        ep_reward += reward

        last_rtt = last_avg_rtt

        next_state_norm = normalise(next_raw).reshape(1, STATE_SIZE)

        rtt_samples.append(last_avg_rtt)
        tp_samples.append(last_tp)
        cwnd_samples.append(cWnd)

        if EXPORT_STEPS:
            _step_rows.append((global_step, last_tp, last_avg_rtt, ep_pkt_loss))

        if MODE == 'train':
            store(state, action_idx, reward, next_state_norm, float(done))

            if len(replay_buffer) >= WARMUP_STEPS:
                loss = train_step()
                losses.append(loss)

            if epsilon > EPSILON_MIN:
                epsilon *= EPSILON_DECAY

            if global_step % TARGET_UPDATE_FREQ == 0:
                target_model.set_weights(model.get_weights())

        raw_state = next_raw
        state     = next_state_norm

        if done:
            step_done = True
            break

    # ── Episode bookkeeping ───────────────────────────────────────────────────
    ep_elapsed = time.time() - ep_start
    avg_loss   = float(np.mean(losses)) if losses else 0.0

    ep_rewards.append(ep_reward)
    ep_losses.append(avg_loss)
    ep_rtt.append(last_rtt)
    ep_cWnd.append(cWnd)
    ep_tp.append(last_tp)
    ep_pkt_losses.append(ep_pkt_loss)

    if ep_reward == 0.0:
        zero_reward_streak += 1
    else:
        zero_reward_streak = 0
    if zero_reward_streak >= 3:
        print(f"\n[WARN] Reward 0.0 for {zero_reward_streak} consecutive "
              f"episodes — check NS-3 GetReward().")

    # ── Progress report ───────────────────────────────────────────────────────
    filled = int(20 * (ep + 1) / EPISODES)
    bar    = '█' * filled + '░' * (20 - filled)

    print(f"\n{'─'*60}")
    print(f"  Episode {ep+1}/{EPISODES}  [{bar}] "
          f"{100*(ep+1)/EPISODES:.1f}%  ({ep_elapsed:.1f}s)")
    print(f"{'─'*60}")
    print(f"  Steps completed : {min(step+1, STEPS)}/{STEPS}")
    print(f"  Total reward    : {ep_reward:+.4f}")
    print(f"  Avg Huber loss  : {avg_loss:.6f}")
    print(f"  Epsilon         : {epsilon:.4f}")
    print(f"  Replay buffer   : {len(replay_buffer):,}/{BUFFER_SIZE:,}")
    print(f"  Ep packet loss  : {ep_pkt_loss:,}")
    print(f"  Final cWnd      : {cWnd:.0f} bytes")
    print(f"  Final RTT       : {last_rtt:.1f} μs")
    print(f"  Final Throughput: {last_tp:.0f} bytes/s")
    if rtt_samples:
        print(f"  Avg RTT (ep)    : {np.mean(rtt_samples):.1f} μs")
        print(f"  Min RTT (ep)    : {np.min(rtt_samples):.1f} μs")
    if tp_samples:
        print(f"  Avg TP (ep)     : {np.mean(tp_samples):.0f} bytes/s")
        print(f"  Max TP (ep)     : {np.max(tp_samples):.0f} bytes/s")
    if cwnd_samples:
        print(f"  Avg cWnd (ep)   : {np.mean(cwnd_samples):.0f} bytes")

    link_capacity = 250_000   # 2Mbps in bytes/s
    utilisation   = 100.0 * np.mean(tp_samples) / link_capacity if tp_samples else 0
    print(f"  Link utilisation: {utilisation:.1f}%  (2Mbps = 250KB/s)")
    print(f"  Wall time total : {time.time()-train_start_time:.1f}s")

    if step_done and ep < EPISODES - 1:
        print(f"\n[WARN] Simulation ended at episode {ep+1}. "
              f"Increase --steps or --episodes.")
        break

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n")
banner("Training complete" if MODE == 'train' else "Test complete")
total_time = time.time() - train_start_time
print(f"  Total wall time : {total_time:.1f}s")
print(f"  Episodes done   : {len(ep_rewards)}/{EPISODES}")
print(f"  Total steps     : {global_step:,}")
print(f"  Final epsilon   : {epsilon:.4f}")
print(f"  Total pkt loss  : {sum(ep_pkt_losses):,}")

# ── Save model ────────────────────────────────────────────────────────────────
if MODE == 'train':
    model.save(MODEL_FILE)
    print(f"[INFO] Model saved → {MODEL_FILE}")

# ── Cleanup ───────────────────────────────────────────────────────────────────
try:
    env.close()
except Exception:
    pass
try:
    ns3_proc.terminate()
except Exception:
    pass

# ── Plots ─────────────────────────────────────────────────────────────────────
if MODE == 'train':
    fig = plt.figure(figsize=(16, 9))
    fig.suptitle(
        f'DQN v5 TCP Training — {EPISODES} eps × {STEPS} steps',
        fontsize=13)
    gs   = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.35)
    axes = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(3)]

    plots = [
        (ep_rewards,    'Episode Reward',   'Reward'),
        (ep_losses,     'Training Loss',    'Huber Loss'),
        (ep_cWnd,       'Final cWnd',       'Bytes'),
        (ep_rtt,        'Final RTT',        'μs'),
        (ep_tp,         'Final Throughput', 'Bytes/s'),
        (ep_pkt_losses, 'Ep Packet Loss',   'Packets'),
    ]

    for i, (data, title, ylabel) in enumerate(plots):
        xs = range(1, len(data) + 1)
        axes[i].plot(xs, data, linewidth=1.5)
        if len(data) >= 5:
            rm = np.convolve(data, np.ones(5) / 5, mode='valid')
            axes[i].plot(range(5, len(data) + 1), rm, linewidth=2,
                         linestyle='--', label='5-ep avg')
            axes[i].legend(fontsize=7)
        axes[i].set_title(title, fontsize=10)
        axes[i].set_xlabel('Episode')
        axes[i].set_ylabel(ylabel)
        axes[i].grid(True, alpha=0.3)

    plot_path = str(drl_tcp_dir / 'training_results.png')
    plt.savefig(plot_path, dpi=120, bbox_inches='tight')
    print(f"[INFO] Plots saved → {plot_path}")

    csv_path = str(drl_tcp_dir / 'training_log.csv')
    with open(csv_path, 'w') as f:
        f.write("episode,reward,loss,cWnd,rtt_us,throughput,packet_loss\n")
        for i in range(len(ep_rewards)):
            f.write(f"{i+1},{ep_rewards[i]:.4f},{ep_losses[i]:.6f},"
                    f"{ep_cWnd[i]:.0f},{ep_rtt[i]:.2f},{ep_tp[i]:.2f},"
                    f"{ep_pkt_losses[i]}\n")
    print(f"[INFO] Log saved   → {csv_path}")

# ── Per-step export ───────────────────────────────────────────────────────────
if EXPORT_STEPS and _step_rows:
    with open(EXPORT_STEPS, 'w') as f:
        f.write("step,throughput_bps,rtt_us,cum_packet_loss\n")
        for row in _step_rows:
            f.write(f"{row[0]},{row[1]:.2f},{row[2]:.2f},{row[3]}\n")
    print(f"[INFO] Step log saved → {EXPORT_STEPS}")