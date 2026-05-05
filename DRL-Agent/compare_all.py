#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_all.py
==============
Comprehensive comparison of four TCP congestion-control approaches:
  • TcpNewReno   (NS-3 baseline)
  • TcpCubic     (NS-3 baseline)
  • DQN agent    (trained model — test mode)
  • PPO agent    (trained model — test mode)

Metrics compared:
  1. Throughput (Mbps)          – time-series over simulation
  2. Latency / RTT (ms)         – time-series over simulation
  3. Cumulative Packet Loss      – monotonically increasing count

Generates comparison graphs and summary statistics.
"""

import argparse
import os
import subprocess
import sys
import pathlib
import shutil
import csv
import time
from datetime import datetime

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.ticker import MaxNLocator

# ── Paths ─────────────────────────────────────────────────────────────────────
project_root = pathlib.Path(__file__).resolve().parent
dqn_dir      = project_root / 'Drl-Tcp-DQN'
ppo_dir      = project_root / 'DRL-TCP-PPO'
ns3_dir      = project_root / 'ns-allinone-3.35' / 'ns-3.35'
out_dir      = project_root / 'comparison_results'
out_dir.mkdir(parents=True, exist_ok=True)

# Venv Python that has numpy / matplotlib / tensorflow
VENV_PY = project_root / 'DRL-TCP' / 'venv' / 'bin' / 'python3'

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description='Compare TCP algorithms: CUBIC, NewReno, DQN, PPO')
parser.add_argument('--episodes', type=int, default=3,
                    help='Test episodes for RL agents (default: 3)')
parser.add_argument('--steps',    type=int, default=200,
                    help='Steps per episode for RL agents (default: 200)')
parser.add_argument('--duration', type=float, default=30.0,
                    help='NS-3 simulation duration for baselines (default: 30 s)')
parser.add_argument('--skip-baselines', action='store_true',
                    help='Skip NS-3 baseline runs (use existing result.txt files)')
parser.add_argument('--skip-rl', action='store_true',
                    help='Skip RL agent runs (use existing metrics)')
args = parser.parse_args()


IS_WINDOWS = (sys.platform == 'win32')

# ── Helpers ───────────────────────────────────────────────────────────────────
def win_to_wsl(p: pathlib.Path) -> str:
    s = str(p).replace('\\', '/')
    if len(s) >= 2 and s[1] == ':':
        s = f'/mnt/{s[0].lower()}{s[2:]}'
    return s

def banner(msg: str):
    w = 72
    print('\n' + '═' * w)
    print(f'  {msg}')
    print('═' * w)

def run(cmd: str, cwd=None, label='') -> bool:
    """Run a shell command, return True on success."""
    if label:
        print(f'\n[RUN] {label}')
    print(f'  $ {cmd}\n')
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f'[ERROR] Command failed (exit {result.returncode})')
        if result.stderr:
            print(result.stderr[:500])
        return False
    return True

# ── NS-3 baseline runner ──────────────────────────────────────────────────────
def run_baseline(proto: str) -> pathlib.Path | None:
    """
    Run NS-3 for a baseline TCP variant.
    Returns path to the saved result.txt, or None on failure.
    """
    dst_dir = out_dir / 'baselines' / proto
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst_file = dst_dir / 'result.txt'

    sim_args = f'sim --transport_prot={proto} --duration={args.duration:.1f}'

    if IS_WINDOWS:
        wsl_ns3 = win_to_wsl(ns3_dir)
        cmd = f'wsl bash -c "cd \'{wsl_ns3}\' && ./waf --run \\"{sim_args}\\""'
        cwd = None
    else:
        cmd = f'{ns3_dir / "waf"} --run "{sim_args}"'
        cwd = str(ns3_dir)

    ok = run(cmd, cwd=cwd, label=f'NS-3 baseline: {proto}')
    if not ok:
        return None

    # NS-3 writes result.txt to the ns-3 working dir
    src = ns3_dir / 'result.txt'
    if not src.exists():
        print(f'[WARN] result.txt not found after running {proto}')
        return None

    shutil.copy(str(src), str(dst_file))
    print(f'[OK] Saved baseline results → {dst_file}')
    return dst_file


def parse_ns3_result(path: pathlib.Path):
    """
    Parse NS-3 result.txt:
      Time (s), Throughput (bps), Average RTT (s), Packet Loss (packets)
    Returns dict with lists: time, throughput_mbps, rtt_ms, cum_packet_loss
    """
    times, tp_mbps, rtt_ms, cum_loss = [], [], [], []
    cumulative = 0
    try:
        with open(path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    t   = float(row[0].strip())
                    tp  = float(row[1].strip()) / 1e6   # bps → Mbps
                    rtt = float(row[2].strip()) * 1000  # s  → ms
                    loss = int(float(row[3].strip()))
                    cumulative += loss
                    times.append(t)
                    tp_mbps.append(tp)
                    rtt_ms.append(rtt)
                    cum_loss.append(cumulative)
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f'[WARN] File not found: {path}')
    
    return {'time': times, 'throughput_mbps': tp_mbps,
            'rtt_ms': rtt_ms, 'cum_packet_loss': cum_loss}


# ── RL agent runner ───────────────────────────────────────────────────────────
def run_rl_agent(agent: str) -> pathlib.Path | None:
    """
    Run DQN or PPO agent in test mode with --export-steps so we get per-step
    throughput/RTT/packet-loss data collected directly from the RL environment
    observations (distinct from the NS-3 FlowMonitor result.txt).
    Returns path to the steps.csv file, or None on failure.
    """
    if agent == 'DQN':
        script = dqn_dir / 'TCP-RL-Agent.py'
    else:
        script = ppo_dir / 'TCP-PPO-Agent.py'

    if not script.exists():
        print(f'[ERROR] Script not found: {script}')
        return None

    dst_dir  = out_dir / 'agents' / agent
    dst_dir.mkdir(parents=True, exist_ok=True)
    step_csv = dst_dir / 'steps.csv'

    # Write a launcher script — avoids shell quoting issues with long paths
    launcher = out_dir / f'_run_{agent.lower()}.sh'
    launcher.write_text(
        f'#!/bin/bash\n'
        f'{VENV_PY} {script} '
        f'--episodes={args.episodes} --steps={args.steps} '
        f'--mode=test '
        f'--export-steps={step_csv}\n'
    )
    launcher.chmod(0o755)

    ok = run(f'bash {launcher}',
             label=f'{agent} agent (test mode, {args.episodes} ep x {args.steps} steps)')
    if not ok:
        return None

    if not step_csv.exists():
        print(f'[WARN] Step CSV not found for {agent} — agent may have 0 valid steps')
        return None

    print(f'[OK] {agent} step CSV → {step_csv}')
    return step_csv


def parse_rl_results(path: pathlib.Path):
    """
    Parse per-step CSV written by RL agents via --export-steps:
      step, throughput_bps, rtt_us, cum_packet_loss
    Returns same dict shape as parse_ns3_result for unified plotting.
    """
    steps, tp_mbps, rtt_ms, cum_loss = [], [], [], []
    try:
        with open(path, 'r') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            for row in reader:
                if len(row) < 4:
                    continue
                try:
                    steps.append(int(row[0].strip()))
                    tp_mbps.append(float(row[1].strip()) * 8 / 1e6)   # bytes/s → Mbps
                    rtt_ms.append(float(row[2].strip()) / 1000.0)      # μs → ms
                    cum_loss.append(int(float(row[3].strip())))
                except (ValueError, IndexError):
                    continue
    except FileNotFoundError:
        print(f'[WARN] File not found: {path}')

    return {'time': steps, 'throughput_mbps': tp_mbps,
            'rtt_ms': rtt_ms, 'cum_packet_loss': cum_loss}



# ── Plotting ──────────────────────────────────────────────────────────────────
COLORS = {
    'NewReno': '#2196F3',   # blue
    'Cubic':   '#FF9800',   # orange
    'DQN':     '#4CAF50',   # green
    'PPO':     '#E91E63',   # pink/magenta
}
LINE_STYLES = {
    'NewReno': '-',
    'Cubic':   '--',
    'DQN':     '-.',
    'PPO':     ':',
}


def smooth(data, w=5):
    """Simple moving average with window w."""
    if len(data) < w:
        return data
    kernel = np.ones(w) / w
    return np.convolve(data, kernel, mode='valid')


def draw_comparison(all_data: dict):
    """
    all_data = {
      'NewReno': {'x': [...], 'tp': [...], 'rtt': [...], 'loss': [...]},
      'Cubic':   {...},
      'DQN':     {...},
      'PPO':     {...},
    }
    Creates 3x2 grid of plots comparing all algorithms.
    """
    fig = plt.figure(figsize=(20, 12))
    fig.patch.set_facecolor('white')

    title = (f'TCP Algorithm Comparison: CUBIC vs NewReno vs DQN vs PPO  —  '
             f'{datetime.now().strftime("%Y-%m-%d %H:%M")}')
    fig.suptitle(title, fontsize=14, fontweight='bold', y=0.98)

    gs = gridspec.GridSpec(2, 3, figure=fig,
                           hspace=0.35, wspace=0.3,
                           left=0.08, right=0.96,
                           top=0.92, bottom=0.08)

    ax_tp_ts  = fig.add_subplot(gs[0, 0])   # Throughput time-series
    ax_rtt_ts = fig.add_subplot(gs[0, 1])   # RTT time-series
    ax_lp_ts  = fig.add_subplot(gs[0, 2])   # Cum. packet loss time-series

    ax_tp_bar  = fig.add_subplot(gs[1, 0])  # Mean throughput bar
    ax_rtt_bar = fig.add_subplot(gs[1, 1])  # Mean RTT bar
    ax_lp_bar  = fig.add_subplot(gs[1, 2])  # Total packet loss bar

    # ── Time-series panels ────────────────────────────────────────────────────
    SMOOTH_W = 5

    for name, d in all_data.items():
        if not d['x'] or not d['tp']:
            continue
        color = COLORS.get(name, '#666')
        ls    = LINE_STYLES.get(name, '-')
        x     = np.array(d['x'])

        # Throughput
        tp = np.array(d['tp'])
        tp_s = smooth(tp, SMOOTH_W)
        x_s  = x[SMOOTH_W - 1:]
        if len(x_s) == len(tp_s):
            ax_tp_ts.plot(x_s, tp_s, color=color, ls=ls,
                          linewidth=2.5, label=name, alpha=0.85)

        # RTT
        rtt = np.array(d['rtt'])
        rtt_s = smooth(rtt, SMOOTH_W)
        if len(x_s) == len(rtt_s):
            ax_rtt_ts.plot(x_s, rtt_s, color=color, ls=ls,
                           linewidth=2.5, label=name, alpha=0.85)

        # Cumulative loss
        loss = np.array(d['loss'])
        ax_lp_ts.plot(x, loss, color=color, ls=ls,
                      linewidth=2.5, label=name, alpha=0.85, marker='o', markersize=2)

    # Style time-series axes
    ax_tp_ts.set_title('Throughput over Time', fontsize=12, fontweight='bold')
    ax_tp_ts.set_xlabel('Time (s)', fontsize=10)
    ax_tp_ts.set_ylabel('Throughput (Mbps)', fontsize=10)
    ax_tp_ts.grid(True, alpha=0.3)
    ax_tp_ts.legend(fontsize=9, loc='best')

    ax_rtt_ts.set_title('RTT (Latency) over Time', fontsize=12, fontweight='bold')
    ax_rtt_ts.set_xlabel('Time (s)', fontsize=10)
    ax_rtt_ts.set_ylabel('RTT (ms)', fontsize=10)
    ax_rtt_ts.grid(True, alpha=0.3)
    ax_rtt_ts.legend(fontsize=9, loc='best')

    ax_lp_ts.set_title('Cumulative Packet Loss', fontsize=12, fontweight='bold')
    ax_lp_ts.set_xlabel('Time (s)', fontsize=10)
    ax_lp_ts.set_ylabel('Packets Lost (cumulative)', fontsize=10)
    ax_lp_ts.grid(True, alpha=0.3)
    ax_lp_ts.legend(fontsize=9, loc='best')

    # ── Bar / summary panels ──────────────────────────────────────────────────
    names      = [n for n in all_data if all_data[n]['tp']]
    bar_colors = [COLORS.get(n, '#aaa') for n in names]

    mean_tp  = [float(np.mean(all_data[n]['tp']))   for n in names]
    mean_rtt = [float(np.mean(all_data[n]['rtt']))  for n in names]
    tot_loss = [all_data[n]['loss'][-1] if all_data[n]['loss'] else 0 for n in names]

    x_pos = np.arange(len(names))
    bar_w = 0.5

    # Mean throughput
    bars = ax_tp_bar.bar(x_pos, mean_tp, width=bar_w, color=bar_colors,
                         edgecolor='black', linewidth=1.2, alpha=0.8)
    ax_tp_bar.set_xticks(x_pos)
    ax_tp_bar.set_xticklabels(names, fontsize=10)
    ax_tp_bar.set_ylabel('Throughput (Mbps)', fontsize=10)
    ax_tp_bar.set_title('Mean Throughput', fontsize=12, fontweight='bold')
    ax_tp_bar.grid(True, alpha=0.3, axis='y')
    
    # Add value labels on bars
    for bar, val in zip(bars, mean_tp):
        ax_tp_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(mean_tp) * 0.02,
                      f'{val:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Mean RTT
    bars = ax_rtt_bar.bar(x_pos, mean_rtt, width=bar_w, color=bar_colors,
                          edgecolor='black', linewidth=1.2, alpha=0.8)
    ax_rtt_bar.set_xticks(x_pos)
    ax_rtt_bar.set_xticklabels(names, fontsize=10)
    ax_rtt_bar.set_ylabel('RTT (ms)', fontsize=10)
    ax_rtt_bar.set_title('Mean RTT (Latency)', fontsize=12, fontweight='bold')
    ax_rtt_bar.grid(True, alpha=0.3, axis='y')
    
    for bar, val in zip(bars, mean_rtt):
        ax_rtt_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(mean_rtt) * 0.02,
                       f'{val:.2f}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    # Total packet loss
    bars = ax_lp_bar.bar(x_pos, tot_loss, width=bar_w, color=bar_colors,
                         edgecolor='black', linewidth=1.2, alpha=0.8)
    ax_lp_bar.set_xticks(x_pos)
    ax_lp_bar.set_xticklabels(names, fontsize=10)
    ax_lp_bar.set_ylabel('Packets Lost', fontsize=10)
    ax_lp_bar.set_title('Total Packet Loss', fontsize=12, fontweight='bold')
    ax_lp_bar.grid(True, alpha=0.3, axis='y')
    
    for bar, val in zip(bars, tot_loss):
        ax_lp_bar.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(tot_loss) * 0.02,
                      f'{int(val)}', ha='center', va='bottom', fontsize=9, fontweight='bold')

    # ── Save ──────────────────────────────────────────────────────────────────
    out_path = out_dir / 'comparison.png'
    plt.savefig(str(out_path), dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close(fig)
    print(f'\n[OK] Comparison chart saved → {out_path}')
    return out_path


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    banner(f'4-WAY TCP ALGORITHM COMPARISON')
    print(f'  CUBIC vs NewReno vs DQN vs PPO')
    print(f'  Output dir : {out_dir}')
    print(f'  NS-3 duration: {args.duration}s')
    print(f'  Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')

    all_data = {}

    # ── 1. NS-3 baselines ─────────────────────────────────────────────────────
    for proto, label in [('TcpCubic', 'Cubic'), ('TcpNewReno', 'NewReno')]:
        banner(f'Baseline TCP: {label}')

        if args.skip_baselines:
            result_file = out_dir / 'baselines' / proto / 'result.txt'
            print(f'[SKIP] Using existing: {result_file}')
        else:
            result_file = run_baseline(proto)

        if result_file and result_file.exists():
            d = parse_ns3_result(result_file)
            all_data[label] = {
                'x':    d['time'],
                'tp':   d['throughput_mbps'],
                'rtt':  d['rtt_ms'],
                'loss': d['cum_packet_loss'],
            }
            if d['throughput_mbps']:
                print(f'  ✓ Data points: {len(d["time"])}')
                print(f'  ✓ Avg throughput: {np.mean(d["throughput_mbps"]):.3f} Mbps')
                print(f'  ✓ Avg RTT: {np.mean(d["rtt_ms"]):.2f} ms')
                print(f'  ✓ Total packet loss: {d["cum_packet_loss"][-1] if d["cum_packet_loss"] else 0}')
        else:
            print(f'[WARN] No data for {label}, skipping.')

    # ── 2. RL agents ──────────────────────────────────────────────────────────
    for agent in ['DQN', 'PPO']:
        banner(f'RL Agent: {agent} (test mode)')

        if args.skip_rl:
            result_file = out_dir / 'agents' / agent / 'result.txt'
            print(f'[SKIP] Using existing: {result_file}')
        else:
            result_file = run_rl_agent(agent)

        if result_file and result_file.exists():
            d = parse_rl_results(result_file)
            all_data[agent] = {
                'x':    d['time'],
                'tp':   d['throughput_mbps'],
                'rtt':  d['rtt_ms'],
                'loss': d['cum_packet_loss'],
            }
            if d['throughput_mbps']:
                print(f'  ✓ Data points: {len(d["time"])}')
                print(f'  ✓ Avg throughput: {np.mean(d["throughput_mbps"]):.3f} Mbps')
                print(f'  ✓ Avg RTT: {np.mean(d["rtt_ms"]):.2f} ms')
                print(f'  ✓ Total packet loss: {d["cum_packet_loss"][-1] if d["cum_packet_loss"] else 0}')
        else:
            print(f'[WARN] No data for {agent}, skipping.')

    # ── 3. Plot ───────────────────────────────────────────────────────────────
    if not all_data:
        print('[ERROR] No data collected. Nothing to plot.')
        sys.exit(1)

    banner('Generating comparison graphs')
    chart = draw_comparison(all_data)

    # ── 4. Summary table ──────────────────────────────────────────────────────
    banner('SUMMARY STATISTICS')
    hdr = f'{"Algorithm":<12}  {"Mean TP (Mbps)":>16}  {"Mean RTT (ms)":>14}  {"Total Loss":>12}'
    print(hdr)
    print('-' * len(hdr))
    for name, d in sorted(all_data.items()):
        mtp  = np.mean(d['tp'])  if d['tp']   else 0
        mrtt = np.mean(d['rtt']) if d['rtt']  else 0
        loss = d['loss'][-1]     if d['loss'] else 0
        print(f'{name:<12}  {mtp:>16.3f}  {mrtt:>14.2f}  {loss:>12d}')

    print(f'\n[DONE] Comparison complete!')
    print(f'  Chart: {chart}')
    print(f'  Output dir: {out_dir}')


if __name__ == '__main__':
    main()
