#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DRL TCP Congestion Control Agent  —  PPO version
Replaces DQN with Proximal Policy Optimisation (Actor-Critic).

FIXES APPLIED (v2):
  1. Reward normalization  — reward now clipped to [-10, +10] per step
  2. Lower learning rates  — Actor 1e-4, Critic 3e-4 (was 3e-4 / 1e-3)
  3. Critic gradient clipping — clipnorm tightened to 0.3
  4. Observation running normalizer — RunningNormalizer replaces fixed STATE_SCALE
  5. Max cWnd tightened to 50_000 bytes, MAX_DELTA reduced to 720 bytes
  6. RTT penalty in reward uses ratio vs min_rtt (not absolute) — no unit blowup
  7. Critic loss clipping — returns clipped to [-50, +50] before MSE
  8. Entropy coefficient reduced to 0.005 (was 0.01) after warm-up
  9. PPO epochs reduced to 4 (was 5) to avoid over-fitting short rollouts
 10. Added per-step reward debug print (first 3 steps of ep 1) for sanity check
"""

import sys
import argparse
import os
import subprocess
import time
import platform
import threading

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
drl_tcp_dir  = project_root / 'DRL-TCP-PPO'
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
parser.add_argument('--episodes',    type=int, default=30)
parser.add_argument('--steps',       type=int, default=200)
parser.add_argument('--mode',        type=str, default='train',
                    choices=['train', 'test'])
parser.add_argument('--export-steps', type=str, default='',
                    help='Path to write per-step CSV for comparison plots')
args = parser.parse_args()

EPISODES     = args.episodes
STEPS        = args.steps
MODE         = args.mode
EXPORT_STEPS = args.export_steps
ACTOR_FILE   = str(drl_tcp_dir / 'ppo_actor.h5')
CRITIC_FILE  = str(drl_tcp_dir / 'ppo_critic.h5')
NORM_FILE    = str(drl_tcp_dir / 'obs_normalizer.npz')

# ── Simulation parameters ─────────────────────────────────────────────────────
PORT           = 5555
SEED           = 12
TIME_STEP      = 0.1
TOTAL_DURATION = (EPISODES * STEPS * TIME_STEP) + 30.0

# ── PPO Hyperparameters (tuned) ───────────────────────────────────────────────
GAMMA        = 0.99
LAM          = 0.95
CLIP_EPS     = 0.2
ENTROPY_COEF = 0.005   # FIX #8: halved — less re-randomisation
VF_COEF      = 0.5
ACTOR_LR     = 1e-4    # FIX #2: 3× lower than before
CRITIC_LR    = 3e-4    # FIX #2: 3× lower than before
PPO_EPOCHS   = 4       # FIX #9: reduced from 5
MINI_BATCH   = 64

# ── Network / action parameters (tuned) ──────────────────────────────────────
STATE_SIZE = 12
MAX_DELTA  = 720       # FIX #5: halved — finer cWnd steps
MIN_CWND   = 4 * 360   # bytes
MAX_CWND   = 50_000    # FIX #5: tightened from 75 000

# ── FIX #4: Running observation normalizer ────────────────────────────────────
class RunningNormalizer:
    """
    Online mean/variance normalization (Welford's algorithm).
    Replaces the fixed STATE_SCALE array so the agent auto-adapts
    to whatever units the environment produces.
    """
    def __init__(self, size: int, clip: float = 10.0):
        self.n    = np.zeros(size, dtype=np.float64)
        self.mean = np.zeros(size, dtype=np.float64)
        self.M2   = np.ones(size,  dtype=np.float64)   # var * n
        self.clip = clip

    def update(self, x: np.ndarray):
        self.n   += 1
        delta     = x - self.mean
        self.mean += delta / self.n
        self.M2  += delta * (x - self.mean)

    @property
    def std(self) -> np.ndarray:
        var = np.where(self.n > 1, self.M2 / self.n, 1.0)
        return np.sqrt(np.maximum(var, 1e-8))

    def normalize(self, x: np.ndarray) -> np.ndarray:
        normed = (x - self.mean) / (self.std + 1e-8)
        return np.clip(normed, -self.clip, self.clip).astype(np.float32)

    def save(self, path: str):
        np.savez(path, n=self.n, mean=self.mean, M2=self.M2)

    def load(self, path: str):
        d        = np.load(path)
        self.n   = d['n']
        self.mean = d['mean']
        self.M2  = d['M2']


obs_norm = RunningNormalizer(STATE_SIZE)
if MODE == 'test' and os.path.exists(NORM_FILE):
    obs_norm.load(NORM_FILE)
    print(f"[INFO] Obs normalizer loaded from {NORM_FILE}")

def normalise(raw: np.ndarray) -> np.ndarray:
    """Update running stats (train only) then normalize."""
    if MODE == 'train':
        obs_norm.update(raw)
    return obs_norm.normalize(raw)

# ── FIX #1 & #6: Reward shaping ──────────────────────────────────────────────
# We re-shape the raw env reward to keep it in a bounded range.
# The env reward is used directly but clipped; additionally we compute
# a shaped bonus based on normalized RTT improvement.
_min_rtt_seen = 1e9   # track minimum RTT seen so far (μs)

def shape_reward(raw_reward: float, rtt_us: float,
                 tp_bps: float, pkts_lost: int) -> float:
    """
    FIX #1: clip raw env reward
    FIX #6: add RTT-ratio penalty (dimensionless, bounded) instead of raw μs
    """
    global _min_rtt_seen
    if rtt_us > 0:
        _min_rtt_seen = min(_min_rtt_seen, rtt_us)

    # Log-normalized throughput score [0, ~1]
    import math
    tp_score = math.log1p(tp_bps) / math.log1p(1.25e6)

    # Base: env reward + throughput bonus
    r = float(np.clip(raw_reward, -5.0, 5.0)) + tp_score

    # Normalized RTT penalty: 0 at min RTT, grows gently above it
    if rtt_us > 0 and _min_rtt_seen < 1e9:
        rtt_ratio = rtt_us / _min_rtt_seen          # ≥ 1.0
        r -= 0.2 * max(0.0, rtt_ratio - 1.0)   # ≤ 0, bounded

    # Loss penalty — 0.5 per packet, floor -5
    if pkts_lost > 0:
        r -= min(5.0, 0.5 * pkts_lost)

    return float(np.clip(r, -10.0, 10.0))

# ── Background stdout drain ───────────────────────────────────────────────────
def _drain(proc):
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
    print(f"       Command: {cmd}\n")

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

    threading.Thread(target=_drain, args=(proc,), daemon=True).start()
    print("[INFO] NS-3 ready.\n")
    return proc

# ── Actor-Critic Networks ─────────────────────────────────────────────────────
def build_actor():
    inp     = tf.keras.layers.Input(shape=(STATE_SIZE,))
    x       = tf.keras.layers.Dense(128, activation='relu')(inp)
    x       = tf.keras.layers.Dense(128, activation='relu')(x)
    x       = tf.keras.layers.Dense(64,  activation='relu')(x)
    mean    = tf.keras.layers.Dense(1, activation='tanh')(x)
    log_std = tf.keras.layers.Dense(
        1, activation=None,
        kernel_initializer='zeros',
        bias_initializer=tf.keras.initializers.Constant(-0.5)
    )(x)
    return tf.keras.Model(inp, [mean, log_std], name='actor')

def build_critic():
    inp = tf.keras.layers.Input(shape=(STATE_SIZE,))
    x   = tf.keras.layers.Dense(128, activation='relu')(inp)
    x   = tf.keras.layers.Dense(128, activation='relu')(x)
    x   = tf.keras.layers.Dense(64,  activation='relu')(x)
    val = tf.keras.layers.Dense(1,   activation=None)(x)
    return tf.keras.Model(inp, val, name='critic')

# FIX #2 & #3: lower LR + tighter clipnorm
actor_opt  = tf.keras.optimizers.Adam(learning_rate=ACTOR_LR,  clipnorm=0.3)
critic_opt = tf.keras.optimizers.Adam(learning_rate=CRITIC_LR, clipnorm=0.3)

# ── Load or create models ─────────────────────────────────────────────────────
if MODE == 'test':
    if os.path.exists(ACTOR_FILE) and os.path.exists(CRITIC_FILE):
        print(f"[INFO] Loading models: {ACTOR_FILE}")
        actor  = tf.keras.models.load_model(ACTOR_FILE)
        critic = tf.keras.models.load_model(CRITIC_FILE)
    else:
        print("[ERROR] No saved model found. Train first.")
        sys.exit(1)
else:
    actor  = build_actor()
    critic = build_critic()
    actor.summary()
    critic.summary()

# ── Policy helpers ────────────────────────────────────────────────────────────
LOG_2PI = tf.cast(tf.math.log(2.0 * np.pi), tf.float32)

def get_action(state_norm: np.ndarray):
    s = tf.convert_to_tensor(state_norm, dtype=tf.float32)
    mean, log_std = actor(s, training=False)
    std    = tf.exp(tf.clip_by_value(log_std, -2.0, 0.5))
    eps    = tf.random.normal(shape=mean.shape)
    sample = mean + std * eps
    action_raw = float(tf.tanh(sample).numpy()[0, 0])

    log_prob = (
        -0.5 * ((sample - mean) / (std + 1e-8)) ** 2
        - tf.math.log(std + 1e-8)
        - 0.5 * LOG_2PI
        - tf.math.log(1.0 - tf.tanh(sample) ** 2 + 1e-6)
    )
    log_prob = float(tf.reduce_sum(log_prob).numpy())
    return action_raw * MAX_DELTA, action_raw, log_prob

def get_action_deterministic(state_norm: np.ndarray):
    s = tf.convert_to_tensor(state_norm, dtype=tf.float32)
    mean, _ = actor(s, training=False)
    action_raw = float(tf.tanh(mean).numpy()[0, 0])
    return action_raw * MAX_DELTA, action_raw, 0.0

# ── GAE computation ───────────────────────────────────────────────────────────
def compute_gae(rewards, values, dones, last_value):
    T          = len(rewards)
    advantages = np.zeros(T, dtype=np.float32)
    gae        = 0.0
    for t in reversed(range(T)):
        next_val  = last_value if t == T - 1 else values[t + 1]
        next_done = dones[t]
        delta     = rewards[t] + GAMMA * next_val * (1 - next_done) - values[t]
        gae       = delta + GAMMA * LAM * (1 - next_done) * gae
        advantages[t] = gae
    returns = advantages + np.array(values, dtype=np.float32)
    return advantages, returns

# ── PPO Update ────────────────────────────────────────────────────────────────
@tf.function
def ppo_update_step(states_b, actions_b, old_log_probs_b,
                    advantages_b, returns_b):
    with tf.GradientTape() as actor_tape, tf.GradientTape() as critic_tape:

        mean, log_std = actor(states_b, training=True)
        std    = tf.exp(tf.clip_by_value(log_std, -2.0, 0.5))

        pre_tanh = tf.atanh(tf.clip_by_value(actions_b, -0.999, 0.999))
        log_prob = (
            -0.5 * ((pre_tanh - mean) / (std + 1e-8)) ** 2
            - tf.math.log(std + 1e-8)
            - 0.5 * LOG_2PI
            - tf.math.log(1.0 - actions_b ** 2 + 1e-6)
        )
        log_prob = tf.reduce_sum(log_prob, axis=-1, keepdims=True)

        ratio      = tf.exp(log_prob - old_log_probs_b)
        surr1      = ratio * advantages_b
        surr2      = tf.clip_by_value(ratio, 1 - CLIP_EPS, 1 + CLIP_EPS) * advantages_b
        actor_loss = -tf.reduce_mean(tf.minimum(surr1, surr2))

        entropy     = tf.reduce_mean(
            0.5 * tf.math.log(2 * np.pi * np.e * (std ** 2 + 1e-8))
        )
        actor_loss -= ENTROPY_COEF * entropy

        # FIX #7: clip returns before MSE to prevent critic loss explosion
        returns_clipped = tf.clip_by_value(returns_b, -50.0, 50.0)
        values_pred     = critic(states_b, training=True)
        critic_loss     = VF_COEF * tf.reduce_mean(
            tf.square(returns_clipped - values_pred)
        )

    actor_grads  = actor_tape.gradient(actor_loss,  actor.trainable_variables)
    critic_grads = critic_tape.gradient(critic_loss, critic.trainable_variables)
    actor_opt.apply_gradients(zip(actor_grads,  actor.trainable_variables))
    critic_opt.apply_gradients(zip(critic_grads, critic.trainable_variables))

    return actor_loss, critic_loss, entropy

def ppo_update(rollout):
    states     = np.array(rollout['states'],      dtype=np.float32)
    actions    = np.array(rollout['actions_raw'], dtype=np.float32).reshape(-1, 1)
    log_probs  = np.array(rollout['log_probs'],   dtype=np.float32).reshape(-1, 1)
    advantages = np.array(rollout['advantages'],  dtype=np.float32).reshape(-1, 1)
    returns    = np.array(rollout['returns'],     dtype=np.float32).reshape(-1, 1)

    # Normalize advantages
    advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    T = len(states)
    a_losses, c_losses, entropies = [], [], []

    for _ in range(PPO_EPOCHS):
        indices = np.random.permutation(T)
        for start in range(0, T, MINI_BATCH):
            idx = indices[start:start + MINI_BATCH]
            if len(idx) < 2:
                continue
            al, cl, ent = ppo_update_step(
                tf.constant(states[idx]),
                tf.constant(actions[idx]),
                tf.constant(log_probs[idx]),
                tf.constant(advantages[idx]),
                tf.constant(returns[idx]),
            )
            a_losses.append(float(al))
            c_losses.append(float(cl))
            entropies.append(float(ent))

    return (float(np.mean(a_losses)),
            float(np.mean(c_losses)),
            float(np.mean(entropies)))

# ── History ───────────────────────────────────────────────────────────────────
ep_rewards, ep_actor_losses, ep_critic_losses = [], [], []
ep_entropies, ep_rtt, ep_cWnd, ep_tp = [], [], [], []

# ── Banner ────────────────────────────────────────────────────────────────────
def banner(msg):
    w = 60
    print("\n" + "─" * w)
    print(f"  {msg}")
    print("─" * w)

banner(f"PPO v2  |  Mode: {MODE.upper()}  |  Episodes: {EPISODES}  |  Steps/ep: {STEPS}")
print(f"  Actor LR  : {ACTOR_LR}   |  Critic LR : {CRITIC_LR}")
print(f"  Clip ε    : {CLIP_EPS}    |  GAE λ     : {LAM}")
print(f"  PPO epochs: {PPO_EPOCHS}        |  Minibatch : {MINI_BATCH}")
print(f"  MAX_DELTA : ±{MAX_DELTA} bytes  |  cWnd range: [{MIN_CWND}, {MAX_CWND}] bytes")
print(f"  Entropy β : {ENTROPY_COEF}   |  Sim duration: {TOTAL_DURATION:.1f}s\n")

# ── Launch NS-3 & connect ─────────────────────────────────────────────────────
ns3_proc = launch_ns3()
print("[INFO] Connecting to NS-3 environment…")
env = ns3env.Ns3Env(port=PORT, startSim=False, simSeed=SEED)
print("[INFO] Connected!\n")

# ── MAIN LOOP ─────────────────────────────────────────────────────────────────
global_step      = 0
train_start_time = time.time()
_step_rows: list = []

for ep in range(EPISODES):
    ep_start = time.time()

    obs       = env.ns3ZmqBridge.get_obs()
    obs       = np.array(obs, dtype=np.float32)
    raw_state = obs[4:]
    init_cWnd = float(raw_state[1])
    cWnd      = init_cWnd
    state     = normalise(raw_state).reshape(1, STATE_SIZE)

    rollout = {
        'states':      [],
        'actions_raw': [],
        'log_probs':   [],
        'rewards':     [],
        'values':      [],
        'dones':       [],
    }

    ep_reward    = 0.0
    rtt_samples  = []
    tp_samples   = []
    cwnd_samples = []
    last_rtt     = 0.0
    last_tp      = 0.0
    step_done    = False
    ep_pkt_loss  = 0

    # FIX #10: debug flag for first episode sanity check
    debug_reward = (ep == 0)

    for step in range(STEPS):
        global_step += 1

        if MODE == 'test':
            delta, action_raw, log_prob = get_action_deterministic(state)
        else:
            delta, action_raw, log_prob = get_action(state)

        value = float(critic(
            tf.convert_to_tensor(state, dtype=tf.float32), training=False
        ).numpy()[0, 0])

        calc_cWnd    = cWnd + delta
        new_cWnd     = float(np.clip(calc_cWnd, MIN_CWND, MAX_CWND))
        new_ssThresh = int(cWnd / 2)
        actions_env  = [new_ssThresh, int(new_cWnd)]

        next_obs, raw_reward, done, info = env.step(actions_env)

        if next_obs is None:
            step_done = True
            break

        next_obs  = np.array(next_obs, dtype=np.float32)
        next_raw  = next_obs[4:]

        # Skip corrupt zero-RTT steps
        if float(next_raw[5]) == 0.0 and float(next_raw[7]) == 0.0:
            raw_state = next_raw
            state     = normalise(next_raw).reshape(1, STATE_SIZE)
            continue

        cWnd      = float(next_raw[1])
        last_rtt  = float(next_raw[7])
        last_tp   = float(next_raw[11])
        step_loss_delta = int(next_raw[9])
        ep_pkt_loss += step_loss_delta

        # FIX #1 & #6: shaped, clipped reward
        reward = shape_reward(raw_reward, last_rtt, last_tp, step_loss_delta)

        # FIX #10: print first 3 steps of ep 1 to verify reward scale
        if debug_reward and step < 3:
            print(f"  [DEBUG ep1 step{step}] raw_reward={raw_reward:.4f}  "
                  f"rtt={last_rtt:.0f}μs  tp={last_tp:.0f}B/s  "
                  f"shaped_reward={reward:.4f}")

        ep_reward += reward

        rtt_samples.append(last_rtt)
        tp_samples.append(last_tp)
        cwnd_samples.append(cWnd)

        if EXPORT_STEPS:
            _step_rows.append((global_step, last_tp, last_rtt, ep_pkt_loss))

        if MODE == 'train':
            rollout['states'].append(state[0])
            rollout['actions_raw'].append(action_raw)
            rollout['log_probs'].append(log_prob)
            rollout['rewards'].append(reward)
            rollout['values'].append(value)
            rollout['dones'].append(float(done))

        raw_state = next_raw
        state     = normalise(next_raw).reshape(1, STATE_SIZE)

        if done:
            step_done = True
            break

    # ── PPO Update ────────────────────────────────────────────────────────
    actor_loss = critic_loss = entropy = 0.0

    if MODE == 'train' and len(rollout['states']) >= MINI_BATCH:
        last_value = float(critic(
            tf.convert_to_tensor(state, dtype=tf.float32), training=False
        ).numpy()[0, 0]) if not step_done else 0.0

        advantages, returns = compute_gae(
            rollout['rewards'],
            rollout['values'],
            rollout['dones'],
            last_value
        )
        rollout['advantages'] = advantages.tolist()
        rollout['returns']    = returns.tolist()

        actor_loss, critic_loss, entropy = ppo_update(rollout)

    # ── Bookkeeping ───────────────────────────────────────────────────────
    ep_elapsed = time.time() - ep_start
    ep_rewards.append(ep_reward)
    ep_actor_losses.append(actor_loss)
    ep_critic_losses.append(critic_loss)
    ep_entropies.append(entropy)
    ep_rtt.append(last_rtt)
    ep_cWnd.append(cWnd)
    ep_tp.append(last_tp)

    filled = int(20 * (ep + 1) / EPISODES)
    bar    = '█' * filled + '░' * (20 - filled)

    print(f"\n{'─'*60}")
    print(f"  Episode {ep+1}/{EPISODES}  [{bar}] {100*(ep+1)/EPISODES:.1f}%  ({ep_elapsed:.1f}s)")
    print(f"{'─'*60}")
    print(f"  Steps completed  : {min(step+1, STEPS)}/{STEPS}")
    print(f"  Total reward     : {ep_reward:+.4f}")
    print(f"  Actor  loss      : {actor_loss:.6f}")
    print(f"  Critic loss      : {critic_loss:.6f}")
    print(f"  Policy entropy   : {entropy:.4f}")
    print(f"  Rollout size     : {len(rollout['states'])} transitions")
    print(f"  Final cWnd       : {cWnd:.0f} bytes")
    print(f"  Final RTT        : {last_rtt:.1f} μs")
    print(f"  Final Throughput : {last_tp:.0f} bytes/s")
    if rtt_samples:
        print(f"  Avg RTT (ep)     : {np.mean(rtt_samples):.1f} μs")
        print(f"  Min RTT (ep)     : {np.min(rtt_samples):.1f} μs")
    if tp_samples:
        print(f"  Avg TP  (ep)     : {np.mean(tp_samples):.0f} bytes/s")
        print(f"  Max TP  (ep)     : {np.max(tp_samples):.0f} bytes/s")
    if cwnd_samples:
        print(f"  Avg cWnd (ep)    : {np.mean(cwnd_samples):.0f} bytes")
    print(f"  Wall time total  : {time.time()-train_start_time:.1f}s")

    if step_done and ep < EPISODES - 1:
        print(f"\n[WARN] Simulation ended at episode {ep+1}. "
              f"Increase --steps or --episodes.")
        break

# ── Done ──────────────────────────────────────────────────────────────────────
print("\n")
banner("PPO Training complete" if MODE == 'train' else "PPO Test complete")
total_time = time.time() - train_start_time
print(f"  Total wall time : {total_time:.1f}s")
print(f"  Episodes done   : {len(ep_rewards)}/{EPISODES}")
print(f"  Total steps     : {global_step:,}")

# ── Save models + normalizer ──────────────────────────────────────────────────
if MODE == 'train':
    actor.save(ACTOR_FILE)
    critic.save(CRITIC_FILE)
    obs_norm.save(NORM_FILE)
    print(f"[INFO] Actor  saved → {ACTOR_FILE}")
    print(f"[INFO] Critic saved → {CRITIC_FILE}")
    print(f"[INFO] Normalizer saved → {NORM_FILE}")

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
fig = plt.figure(figsize=(16, 9))
fig.suptitle(f'PPO v2 TCP Training — {EPISODES} eps × {STEPS} steps', fontsize=13)
gs  = gridspec.GridSpec(2, 4, figure=fig, hspace=0.45, wspace=0.35)

axes  = [fig.add_subplot(gs[r, c]) for r in range(2) for c in range(4)]
plots = [
    (ep_rewards,       'Episode Reward',   'Reward'),
    (ep_actor_losses,  'Actor Loss',       'Loss'),
    (ep_critic_losses, 'Critic Loss',      'Loss'),
    (ep_entropies,     'Policy Entropy',   'Entropy'),
    (ep_cWnd,          'Final cWnd',       'Bytes'),
    (ep_rtt,           'Final RTT',        'μs'),
    (ep_tp,            'Final Throughput', 'Bytes/s'),
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

axes[-1].axis('off')

plot_path = str(drl_tcp_dir / 'ppo_training_results.png')
plt.savefig(plot_path, dpi=120, bbox_inches='tight')
print(f"[INFO] Plots saved → {plot_path}")

# ── CSV log ───────────────────────────────────────────────────────────────────
csv_path = str(drl_tcp_dir / 'ppo_training_log.csv')
with open(csv_path, 'w') as f:
    f.write("episode,reward,actor_loss,critic_loss,entropy,cWnd,rtt_us,throughput\n")
    for i in range(len(ep_rewards)):
        f.write(f"{i+1},{ep_rewards[i]:.4f},"
                f"{ep_actor_losses[i]:.6f},{ep_critic_losses[i]:.6f},"
                f"{ep_entropies[i]:.4f},"
                f"{ep_cWnd[i]:.0f},{ep_rtt[i]:.2f},{ep_tp[i]:.2f}\n")
print(f"[INFO] Log saved   → {csv_path}")

# ── Per-step export ───────────────────────────────────────────────────────────
if EXPORT_STEPS and _step_rows:
    with open(EXPORT_STEPS, 'w') as f:
        f.write("step,throughput_bps,rtt_us,cum_packet_loss\n")
        for row in _step_rows:
            f.write(f"{row[0]},{row[1]:.2f},{row[2]:.2f},{row[3]}\n")
    print(f"[INFO] Step log saved → {EXPORT_STEPS}")