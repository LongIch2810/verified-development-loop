"""VDL Control Center - Real-Time Workflow Tracking Server & Passive Monitoring UI (Python 3.11+).

Provides:
- HTTP REST API (/api/state, /api/events, /api/projects)
- Server-Sent Events (SSE) stream (/api/stream) with reconnection replay via Last-Event-ID
- Modern Dark-Themed Single-Page Vertical Stepper UI for real-time passive monitoring
"""

import argparse
import json
import os
import queue
import re
import socket
import sys
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Local scripts imports
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

try:
    from vdl_events import (
        EventStore,
        VDLEvent,
        WorkflowStateReducer,
        detect_project_id,
        emit_event,
    )
except ImportError:
    from .vdl_events import (  # type: ignore
        EventStore,
        VDLEvent,
        WorkflowStateReducer,
        detect_project_id,
        emit_event,
    )

HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VDL Control Center - Real-Time Workflow Loop Graph</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg-base: #121212;
      --bg-surface: #1E1E1E;
      --bg-card: #1E1E1E;
      --bg-card-hover: #252525;
      --border-subtle: #2C2C2E;
      --border-bright: #3A3A3C;
      --border-active: #00E5FF;
      --text-main: #FFFFFF;
      --text-muted: #98989D;
      --text-dim: #68686D;
      --accent-cyan: #00E5FF;
      --accent-blue: #0A84FF;
      --accent-indigo: #5E5CE6;
      --accent-emerald: #32D74B;
      --accent-amber: #FF9F0A;
      --accent-rose: #FF453A;
      --accent-purple: #BF5AF2;
      --glow-cyan: 0 0 25px rgba(0, 229, 255, 0.45);
      --glow-emerald: 0 0 25px rgba(50, 215, 75, 0.45);
      --glow-amber: 0 0 25px rgba(255, 159, 10, 0.45);
      --glow-rose: 0 0 25px rgba(255, 69, 58, 0.5);
    }

    html, body, * { 
      box-sizing: border-box; 
      margin: 0; 
      padding: 0; 
      scrollbar-width: thin;
      scrollbar-color: #2C2C2E #121212;
    }

    /* Ultra-Sleek Minimalist Cyber Scrollbar */
    ::-webkit-scrollbar {
      width: 5px !important;
      height: 5px !important;
    }
    ::-webkit-scrollbar-track {
      background: #121212 !important;
    }
    ::-webkit-scrollbar-thumb {
      background: #2C2C2E !important;
      border-radius: 9999px !important;
      border: 1px solid #3A3A3C !important;
      transition: background 0.2s ease, box-shadow 0.2s ease;
    }
    ::-webkit-scrollbar-thumb:hover {
      background: #00E5FF !important;
      box-shadow: 0 0 10px rgba(0, 229, 255, 0.6) !important;
    }
    ::-webkit-scrollbar-thumb:active {
      background: var(--accent-cyan) !important;
    }
    ::-webkit-scrollbar-button {
      display: none !important;
      width: 0 !important;
      height: 0 !important;
    }
    ::-webkit-scrollbar-corner {
      background: transparent !important;
    }

    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 14px;
      background-color: var(--bg-base);
      background-image: 
        radial-gradient(circle at 15% 15%, rgba(0, 229, 255, 0.05) 0%, transparent 40%),
        radial-gradient(circle at 85% 85%, rgba(50, 215, 75, 0.04) 0%, transparent 40%),
        linear-gradient(rgba(44, 44, 46, 0.35) 1px, transparent 1px),
        linear-gradient(90deg, rgba(44, 44, 46, 0.35) 1px, transparent 1px);
      background-size: 100% 100%, 100% 100%, 32px 32px, 32px 32px;
      color: var(--text-main);
      line-height: 1.5;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Header Bar */
    header {
      background: rgba(18, 18, 18, 0.95);
      backdrop-filter: blur(16px);
      border-bottom: 1px solid var(--border-subtle);
      padding: 0.65rem 1.5rem;
      position: sticky;
      top: 0;
      z-index: 50;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem 1rem;
      flex-wrap: wrap !important;
      overflow: visible !important;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-shrink: 0;
      white-space: nowrap !important;
    }
    .brand-icon {
      width: 34px;
      height: 34px;
      border-radius: 9px;
      background: linear-gradient(135deg, var(--accent-cyan), #0077b6);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      color: #121212;
      font-size: 0.875rem;
      box-shadow: 0 0 16px rgba(0, 229, 255, 0.4);
      border: 1px solid rgba(255, 255, 255, 0.2);
    }
    .brand-title {
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: -0.02em;
      color: #FFFFFF;
      white-space: nowrap !important;
    }
    .brand-tag {
      font-size: 0.625rem;
      color: var(--accent-cyan);
      margin-left: 0.45rem;
      padding: 0.15rem 0.55rem;
      background: rgba(0, 229, 255, 0.1);
      border: 1px solid rgba(0, 229, 255, 0.3);
      border-radius: 9999px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      white-space: nowrap !important;
      flex-shrink: 0 !important;
    }

    /* View Switcher */
    .view-switcher {
      display: flex;
      background: #181818;
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 0.2rem;
      gap: 0.25rem;
      flex-shrink: 0 !important;
      white-space: nowrap !important;
    }
    .view-btn {
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-size: 0.8125rem;
      font-weight: 600;
      padding: 0.35rem 0.85rem;
      border-radius: 6px;
      cursor: pointer;
      display: flex;
      align-items: center;
      gap: 0.4rem;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      white-space: nowrap !important;
      flex-shrink: 0 !important;
    }
    .view-btn:hover {
      color: #FFFFFF;
      background: #252525;
    }
    .view-btn.active {
      background: var(--accent-cyan);
      color: #121212;
      font-weight: 700;
      box-shadow: 0 0 14px rgba(0, 229, 255, 0.4);
    }

    .header-controls {
      display: flex;
      align-items: center;
      gap: 0.65rem 0.85rem;
      flex-wrap: wrap !important;
      white-space: nowrap !important;
    }
    .control-group {
      display: flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.8125rem;
      color: var(--text-muted);
      flex-shrink: 0 !important;
      white-space: nowrap !important;
    }
    select {
      background: #1E1E1E;
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      padding: 0.35rem 0.7rem;
      border-radius: 6px;
      font-size: 0.8125rem;
      outline: none;
      cursor: pointer;
      transition: border-color 0.2s;
      white-space: nowrap !important;
      flex-shrink: 0 !important;
    }
    select:focus { border-color: var(--accent-cyan); }
    #projectSelect {
      max-width: 170px;
      text-overflow: ellipsis;
    }
    #sessionSelect {
      max-width: 130px;
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.35rem 0.85rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      white-space: nowrap !important;
      flex-shrink: 0 !important;
      min-width: max-content !important;
    }
    #connText {
      white-space: nowrap !important;
      word-break: keep-all !important;
      display: inline-block;
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
    }
    .status-CONNECTED { background: rgba(50, 215, 75, 0.15); color: #32D74B; border: 1px solid rgba(50, 215, 75, 0.4); }
    .status-CONNECTED .status-dot { background: #32D74B; box-shadow: 0 0 10px #32D74B; animation: pulse 2s infinite; }
    .status-CONNECTING { background: rgba(255, 159, 10, 0.15); color: #FF9F0A; border: 1px solid rgba(255, 159, 10, 0.4); }
    .status-CONNECTING .status-dot { background: #FF9F0A; }
    .status-DISCONNECTED { background: rgba(255, 69, 58, 0.15); color: #FF453A; border: 1px solid rgba(255, 69, 58, 0.4); }
    .status-DISCONNECTED .status-dot { background: #FF453A; }

    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.3; transform: scale(0.85); }
    }

    /* Metrics Bar */
    .metrics-bar {
      background: #181818;
      backdrop-filter: blur(12px);
      border-bottom: 1px solid var(--border-subtle);
      padding: 0.5rem 1.75rem;
      display: flex;
      align-items: center;
      gap: 2rem;
      font-size: 0.8125rem;
      color: var(--text-muted);
      overflow-x: auto;
    }
    .metric-item {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      white-space: nowrap;
    }
    .metric-label {
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
      font-size: 0.6875rem;
      letter-spacing: 0.05em;
    }
    .metric-value {
      color: var(--text-main);
      font-weight: 600;
      font-family: 'Inter', sans-serif;
    }
    .metric-mono {
      font-family: 'JetBrains Mono', monospace !important;
      font-weight: 700;
    }
    .metric-badge {
      padding: 0.1rem 0.45rem;
      border-radius: 4px;
      font-size: 0.6875rem;
      font-weight: 700;
    }

    /* Main Workspace Grid */
    .container {
      max-width: 1680px;
      margin: 1.25rem auto;
      padding: 0 1.5rem;
      display: grid;
      grid-template-columns: 1fr 440px;
      gap: 1.5rem;
      flex: 1;
      width: 100%;
    }

    /* Left Side: Graph / Stepper Workspace */
    .workspace-pane {
      background: var(--bg-surface);
      backdrop-filter: blur(16px);
      border: 1px solid var(--border-subtle);
      border-radius: 16px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      box-shadow: 0 10px 40px rgba(0, 0, 0, 0.5);
      min-height: 620px;
    }

    .pane-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--border-subtle);
    }
    .pane-title {
      font-size: 1.05rem;
      font-weight: 600;
      letter-spacing: -0.01em;
      color: #FFFFFF;
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }
    .loop-indicator-pill {
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-weight: 700;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      white-space: nowrap !important;
      flex-shrink: 0 !important;
    }
    .loop-active {
      background: rgba(0, 229, 255, 0.15);
      border: 1px solid var(--accent-cyan);
      color: var(--accent-cyan);
      box-shadow: 0 0 12px rgba(0, 229, 255, 0.3);
      animation: pulse 1.8s infinite;
    }
    .loop-idle {
      background: #252525;
      border: 1px solid #2C2C2E;
      color: var(--text-muted);
    }

    /* Arrow Color & Node Status Legend Ribbon */
    .arrow-legend-ribbon {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1.25rem;
      background: #181818;
      padding: 0.4rem 0.85rem;
      border-radius: 8px;
      border: 1px solid var(--border-subtle);
      font-size: 0.6875rem;
      color: var(--text-muted);
      margin-bottom: 0.85rem;
      flex-wrap: wrap;
    }
    .mode-explainer {
      margin: 0 0 0.85rem;
      color: var(--text-muted);
      font-size: 0.8125rem;
      line-height: 1.5;
    }
    .mode-explainer strong { color: var(--accent-cyan); }
    .legend-group {
      display: flex;
      align-items: center;
      gap: 0.85rem;
      flex-wrap: nowrap;
    }
    .legend-group-title {
      font-weight: 800;
      color: var(--text-dim);
      font-size: 0.625rem;
      letter-spacing: 0.06em;
      white-space: nowrap !important;
    }
    .legend-item {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      white-space: nowrap !important;
      font-weight: 600;
      flex-shrink: 0 !important;
    }
    .legend-color-dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      flex-shrink: 0;
    }
    .dot-cyan { background: #00E5FF; box-shadow: 0 0 6px #00E5FF; }
    .dot-emerald { background: #32D74B; box-shadow: 0 0 6px #32D74B; }
    .dot-orange, .dot-amber { background: #FF9F0A; box-shadow: 0 0 6px #FF9F0A; }
    .dot-red, .dot-rose { background: #FF453A; box-shadow: 0 0 6px #FF453A; }
    .dot-purple { background: #BF5AF2; box-shadow: 0 0 6px #BF5AF2; }
    .dot-slate { background: #68686D; }
    .dot-cyan-active { background: #00E5FF; box-shadow: 0 0 8px #00E5FF; }
    .dot-magenta-upcoming, .dot-cyan-upcoming { background: transparent; border: 1.8px dashed #ec4899; box-shadow: 0 0 8px rgba(236, 72, 153, 0.8); animation: pulse 1.8s infinite; }
    .dot-sapphire, .dot-indigo { background: #0A84FF; box-shadow: 0 0 6px #0A84FF; }

    .demo-btn {
      background: rgba(0, 229, 255, 0.12);
      border: 1px solid rgba(0, 229, 255, 0.4);
      color: var(--accent-cyan);
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0.38rem 0.85rem;
      border-radius: 6px;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      white-space: nowrap !important;
      word-break: keep-all !important;
      min-width: max-content !important;
      flex-shrink: 0 !important;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .demo-btn:hover {
      background: rgba(0, 229, 255, 0.25);
      border-color: var(--accent-cyan);
      box-shadow: 0 0 12px rgba(0, 229, 255, 0.5);
      color: #FFFFFF;
    }
    .demo-btn.demo-active {
      background: var(--accent-cyan);
      color: #121212;
      box-shadow: 0 0 16px rgba(0, 229, 255, 0.6);
    }

    /* Graph Canvas Container */
    #graphContainer {
      flex: 1;
      position: relative;
      width: 100%;
      min-height: 650px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      border-radius: 12px;
      background: #161616;
      border: 1px solid #2C2C2E;
    }

    svg#workflowSvg {
      width: 100%;
      height: 100%;
      max-height: 700px;
    }
    .graph-scroll-hint { display: none; }

    /* SVG Graph Element Styling */
    .svg-phase-bg {
      fill: #191919;
      stroke: #2C2C2E;
      stroke-width: 1;
      rx: 16;
      ry: 16;
    }
    .svg-phase-title {
      font-size: 10px;
      font-family: 'Inter', sans-serif;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      fill: #98989D;
    }

    /* Graph Nodes */
    .graph-node {
      cursor: pointer;
      transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .graph-node:hover {
      transform: translateY(-2px);
    }

    /* Circular Node Styles */
    .node-circle {
      fill: #1E1E1E;
      stroke: #2C2C2E;
      stroke-width: 2.2;
      transition: all 0.3s;
    }
    .node-glow-ring {
      fill: none;
      stroke: transparent;
      stroke-width: 2;
      opacity: 0.6;
      transition: all 0.3s;
    }
    .node-icon {
      font-size: 16px;
      font-weight: 700;
      fill: #ffffff !important;
      text-anchor: middle;
      dominant-baseline: central;
      pointer-events: none;
      user-select: none;
      filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.9));
    }
    .node-icon-fix {
      font-size: 21px !important;
      font-weight: 900 !important;
      fill: #00E5FF !important;
      filter: drop-shadow(0 0 6px rgba(0, 229, 255, 0.9)) !important;
    }
    .node-title {
      font-size: 11px;
      font-weight: 600;
      font-family: 'Inter', sans-serif;
      fill: #FFFFFF;
      text-anchor: middle;
      pointer-events: none;
    }
    .node-sub {
      font-size: 8.5px;
      font-family: 'JetBrains Mono', monospace;
      fill: #98989D;
      text-anchor: middle;
      pointer-events: none;
    }
    .node-badge-rect {
      rx: 3;
      ry: 3;
      fill: #252525;
      stroke: #2C2C2E;
      stroke-width: 1;
      pointer-events: none;
    }
    .node-badge-text {
      font-size: 7.5px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      text-anchor: middle;
      fill: #98989D;
      pointer-events: none;
    }

    /* 3-Tier Node Luminosity System */
    /* Tier 1: PENDING - Chưa chạy qua và chưa đến (Standby, dịu mắt nhưng rõ nét 100%) */
    .node-PENDING {
      opacity: 0.72;
      transition: opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    }
    .node-PENDING:hover {
      opacity: 0.95;
      transform: translateY(-2px);
    }
    .node-PENDING .node-circle {
      fill: #1E1E1E;
      stroke: #2C2C2E;
      stroke-width: 1.8;
      filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.5));
    }
    .node-PENDING .node-title {
      fill: #FFFFFF;
      font-weight: 600;
    }
    .node-PENDING .node-sub {
      fill: #98989D;
    }
    .node-PENDING .node-icon {
      fill: #e2e8f0 !important;
      opacity: 1 !important;
    }
    .node-PENDING .node-icon-fix {
      fill: #00E5FF !important;
      opacity: 0.85 !important;
    }
    .node-PENDING .node-glow-ring {
      display: none;
    }
    .node-PENDING .node-badge-rect {
      fill: #252525;
      stroke: #2C2C2E;
    }
    .node-PENDING .node-badge-text {
      fill: #98989D;
      font-weight: 600;
    }

    /* Tier 2: ACTIVE-LUMINOUS - Khi tới node nào (Sáng dần dần lên, blooming & breathing aura) */
    .node-ACTIVE-LUMINOUS {
      opacity: 1 !important;
      filter: none !important;
      transition: all 0.8s cubic-bezier(0.16, 1, 0.3, 1);
      animation: nodeArriveBloom 0.8s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
    .node-ACTIVE-LUMINOUS .node-circle {
      stroke: var(--accent-cyan) !important;
      stroke-width: 3.5 !important;
      animation: breatheGlow 1.8s ease-in-out infinite !important;
    }
    .node-ACTIVE-LUMINOUS .node-title {
      fill: #ffffff !important;
      font-weight: 700;
      text-shadow: 0 0 10px rgba(0, 229, 255, 0.9), 0 0 20px rgba(0, 229, 255, 0.5);
    }
    .node-ACTIVE-LUMINOUS .node-sub {
      fill: #80F2FF !important;
      font-weight: 600;
    }
    .node-ACTIVE-LUMINOUS .node-icon {
      fill: #ffffff !important;
      opacity: 1 !important;
      filter: drop-shadow(0 0 6px rgba(0, 229, 255, 0.95));
    }
    .node-ACTIVE-LUMINOUS .node-icon-fix {
      fill: #ffffff !important;
      filter: drop-shadow(0 0 8px rgba(0, 229, 255, 1)) !important;
    }
    .node-ACTIVE-LUMINOUS .node-glow-ring {
      display: block !important;
      stroke: var(--accent-cyan);
      animation: sonicWaveRing 1.8s cubic-bezier(0.2, 0.8, 0.4, 1) infinite !important;
    }
    .node-ACTIVE-LUMINOUS .node-badge-rect {
      fill: rgba(0, 229, 255, 0.25) !important;
      stroke: #00E5FF !important;
    }
    .node-ACTIVE-LUMINOUS .node-badge-text {
      fill: #E0FCFF !important;
      font-weight: 800;
    }

    /* Active Glowing Variants for Gates & Alerts */
    .node-ACTIVE-LUMINOUS.node-WAITING_HUMAN .node-circle {
      stroke: var(--accent-amber) !important;
      animation: breatheGlowAmber 1.8s ease-in-out infinite !important;
    }
    .node-ACTIVE-LUMINOUS.node-WAITING_HUMAN .node-glow-ring {
      stroke: var(--accent-amber) !important;
      animation: sonicWaveRingAmber 1.8s cubic-bezier(0.2, 0.8, 0.4, 1) infinite !important;
    }
    .node-ACTIVE-LUMINOUS.node-WAITING_HUMAN .node-title {
      text-shadow: 0 0 10px rgba(255, 159, 10, 0.9), 0 0 20px rgba(255, 159, 10, 0.5) !important;
    }
    .node-ACTIVE-LUMINOUS.node-WAITING_HUMAN .node-badge-rect {
      fill: rgba(255, 159, 10, 0.25) !important;
      stroke: #FF9F0A !important;
    }
    .node-ACTIVE-LUMINOUS.node-WAITING_HUMAN .node-badge-text {
      fill: #FFF3D6 !important;
    }

    .node-ACTIVE-LUMINOUS.node-FAILED .node-circle,
    .node-ACTIVE-LUMINOUS.node-BLOCKED .node-circle {
      stroke: var(--accent-rose) !important;
      animation: breatheGlowRose 1.8s ease-in-out infinite !important;
    }
    .node-ACTIVE-LUMINOUS.node-FAILED .node-glow-ring,
    .node-ACTIVE-LUMINOUS.node-BLOCKED .node-glow-ring {
      stroke: var(--accent-rose) !important;
      animation: sonicWaveRingRose 1.8s cubic-bezier(0.2, 0.8, 0.4, 1) infinite !important;
    }
    .node-ACTIVE-LUMINOUS.node-FAILED .node-title,
    .node-ACTIVE-LUMINOUS.node-BLOCKED .node-title {
      text-shadow: 0 0 10px rgba(255, 69, 58, 0.9), 0 0 20px rgba(255, 69, 58, 0.5) !important;
    }

    /* Tier 2: UPCOMING - Chuẩn bị đến (Hiệu ứng viền Neon Magenta/Hồng Điện Tử) */
    .node-UPCOMING {
      opacity: 0.98;
    }
    .node-UPCOMING .node-circle {
      fill: #1E121C;
      stroke: #ec4899 !important;
      stroke-width: 2.8px !important;
      stroke-dasharray: 6 3;
      animation: upcomingPulseMagenta 1.8s ease-in-out infinite, rotateDashes 10s linear infinite !important;
      filter: drop-shadow(0 0 16px rgba(236, 72, 153, 0.85)) !important;
    }
    .node-UPCOMING .node-glow-ring {
      display: block !important;
      stroke: #ec4899 !important;
      stroke-dasharray: 4 4;
      animation: upcomingRingPulseMagenta 2s ease-in-out infinite !important;
    }
    .node-UPCOMING .node-title {
      fill: #fdf2f8 !important;
      font-weight: 600;
      text-shadow: 0 0 10px rgba(236, 72, 153, 0.8);
    }
    .node-UPCOMING .node-sub {
      fill: #fbcfe8 !important;
    }
    .node-UPCOMING .node-icon {
      fill: #ffffff !important;
      opacity: 0.98 !important;
      filter: drop-shadow(0 0 6px rgba(236, 72, 153, 0.85));
    }
    .node-UPCOMING .node-badge-rect {
      fill: rgba(236, 72, 153, 0.28) !important;
      stroke: #ec4899 !important;
    }
    .node-UPCOMING .node-badge-text {
      fill: #f472b6 !important;
      font-weight: 700;
    }

    /* Tier 3: COMPLETED - Đã chạy qua (Xanh Sapphire Công Nghệ vững chãi, không trùng với tím/chàm) */
    .node-COMPLETED {
      opacity: 1;
      transition: opacity 0.6s ease;
    }
    .node-COMPLETED .node-circle {
      fill: #141c2c;
      stroke: #0A84FF;
      stroke-width: 2.4;
      filter: drop-shadow(0 0 12px rgba(10, 132, 255, 0.65));
    }
    .node-COMPLETED .node-title {
      fill: #FFFFFF;
      font-weight: 600;
    }
    .node-COMPLETED .node-sub {
      fill: #bfdbfe;
    }
    .node-COMPLETED .node-icon {
      fill: #ffffff !important;
      opacity: 1 !important;
    }
    .node-COMPLETED .node-icon-fix {
      fill: #93c5fd !important;
      filter: drop-shadow(0 0 6px rgba(10, 132, 255, 0.9)) !important;
    }
    .node-COMPLETED .node-badge-rect {
      fill: rgba(10, 132, 255, 0.2);
      stroke: #0A84FF;
    }
    .node-COMPLETED .node-badge-text {
      fill: #bfdbfe;
      font-weight: 700;
    }
    .node-COMPLETED .node-glow-ring {
      display: none;
    }

    /* Standalone Alert Nodes */
    .node-FAILED .node-circle, .node-BLOCKED .node-circle {
      stroke: var(--accent-rose);
      stroke-width: 2.8;
      filter: drop-shadow(0 0 12px rgba(255, 69, 58, 0.85));
    }
    .node-BLOCKED .node-glow-ring, .node-FAILED .node-glow-ring {
      stroke: var(--accent-rose);
      animation: sonicWaveRingRose 1.6s infinite;
    }
    .node-FAILED .node-badge-rect, .node-BLOCKED .node-badge-rect { fill: #3A1C1C; stroke: var(--accent-rose); }
    .node-FAILED .node-badge-text, .node-BLOCKED .node-badge-text { fill: #FF453A; }

    .node-WAITING_HUMAN .node-circle {
      stroke: var(--accent-amber);
      stroke-width: 2.5;
      filter: drop-shadow(0 0 10px rgba(255, 159, 10, 0.65));
    }
    .node-WAITING_HUMAN .node-glow-ring {
      stroke: var(--accent-amber);
      animation: sonicWaveRingAmber 2s infinite;
    }
    .node-WAITING_HUMAN .node-badge-rect { fill: rgba(255, 159, 10, 0.2); stroke: var(--accent-amber); }
    .node-WAITING_HUMAN .node-badge-text { fill: #FF9F0A; }

    /* Selected node focus ring */
    .node-selected .node-circle {
      stroke: #00E5FF !important;
      stroke-width: 3.5 !important;
      filter: drop-shadow(0 0 16px rgba(0, 229, 255, 0.95)) !important;
    }

    /* Luminosity Keyframes */
    @keyframes nodeArriveBloom {
      0% { opacity: 0.38; }
      100% { opacity: 1; }
    }

    @keyframes breatheGlow {
      0%, 100% {
        stroke-width: 3px;
        filter: drop-shadow(0 0 10px rgba(0, 229, 255, 0.75));
      }
      50% {
        stroke-width: 4.2px;
        filter: drop-shadow(0 0 22px rgba(0, 229, 255, 1)) drop-shadow(0 0 36px rgba(0, 229, 255, 0.6));
      }
    }

    @keyframes sonicWaveRing {
      0% { r: 28px; opacity: 0.9; stroke-width: 2.5px; }
      100% { r: 44px; opacity: 0; stroke-width: 0.6px; }
    }

    @keyframes breatheGlowAmber {
      0%, 100% {
        stroke-width: 3px;
        filter: drop-shadow(0 0 10px rgba(255, 159, 10, 0.75));
      }
      50% {
        stroke-width: 4.2px;
        filter: drop-shadow(0 0 22px rgba(255, 159, 10, 1)) drop-shadow(0 0 36px rgba(255, 159, 10, 0.6));
      }
    }

    @keyframes sonicWaveRingAmber {
      0% { r: 28px; opacity: 0.9; stroke-width: 2.5px; }
      100% { r: 44px; opacity: 0; stroke-width: 0.6px; }
    }

    @keyframes breatheGlowRose {
      0%, 100% {
        stroke-width: 3px;
        filter: drop-shadow(0 0 10px rgba(255, 69, 58, 0.75));
      }
      50% {
        stroke-width: 4.2px;
        filter: drop-shadow(0 0 22px rgba(255, 69, 58, 1)) drop-shadow(0 0 36px rgba(255, 69, 58, 0.6));
      }
    }

    @keyframes sonicWaveRingRose {
      0% { r: 28px; opacity: 0.9; stroke-width: 2.5px; }
      100% { r: 44px; opacity: 0; stroke-width: 0.6px; }
    }

    @keyframes upcomingPulseMagenta {
      0%, 100% {
        stroke-width: 2.6px;
        filter: drop-shadow(0 0 10px rgba(236, 72, 153, 0.7));
      }
      50% {
        stroke-width: 3.8px;
        filter: drop-shadow(0 0 22px rgba(236, 72, 153, 1)) drop-shadow(0 0 34px rgba(236, 72, 153, 0.6));
      }
    }

    @keyframes upcomingRingPulseMagenta {
      0% { r: 30px; opacity: 0.85; stroke-width: 2.2px; }
      100% { r: 44px; opacity: 0; stroke-width: 0.5px; }
    }

    @keyframes rotateDashes {
      from { stroke-dashoffset: 0; }
      to { stroke-dashoffset: 72; }
    }

    /* Node Connection Ports (Anchor Dots) */
    .node-port {
      fill: #1E1E1E;
      stroke: var(--border-subtle);
      stroke-width: 1.5px;
      transition: all 0.3s ease;
    }
    .node-ACTIVE-LUMINOUS .node-port {
      fill: #00E5FF;
      stroke: #ffffff;
      filter: drop-shadow(0 0 6px #00E5FF);
    }
    .node-UPCOMING .node-port {
      fill: #be185d;
      stroke: #ec4899;
      filter: drop-shadow(0 0 6px rgba(236, 72, 153, 0.85));
    }
    .node-COMPLETED .node-port {
      fill: #0A84FF;
      stroke: #93c5fd;
    }

    /* Edges and Feedback Loops with Semantic Color Coding */
    .graph-edge {
      fill: none !important;
      stroke-width: 2.4;
      transition: stroke 0.3s, stroke-width 0.3s;
    }
    /* Semantic Colors for Inactive Edges */
    .edge-cyan { stroke: #00E5FF; opacity: 0.85; }
    .edge-emerald { stroke: #32D74B; opacity: 0.85; }
    .edge-amber { stroke: #FF9F0A; opacity: 0.85; }
    .edge-rose { stroke: #FF453A; opacity: 0.9; }
    .edge-purple { stroke: #BF5AF2; opacity: 0.85; }

    /* Turbo Wind Speed Boost Stream & Racing Photon FX */
    @keyframes windSpeedBoost {
      from { stroke-dashoffset: 48; }
      to { stroke-dashoffset: 0; }
    }

    .edge-speed-boost {
      stroke-linecap: round !important;
      stroke-dasharray: 8 14 !important;
      animation: windSpeedBoost 0.3s linear infinite !important;
    }

    /* Edge Wind Aura (Thick glowing background stream) */
    .edge-wind-aura {
      fill: none !important;
      stroke-width: 7;
      stroke-linecap: round;
      opacity: 0.45;
      filter: blur(4px);
      pointer-events: none;
    }
    .aura-cyan { stroke: #00E5FF; }
    .aura-emerald { stroke: #32D74B; }
    .aura-amber { stroke: #FF9F0A; }
    .aura-rose { stroke: #FF453A; }
    .aura-purple { stroke: #BF5AF2; }

    /* Boost Edge Strokes */
    .boost-cyan { stroke: #00E5FF !important; stroke-width: 3.4 !important; filter: drop-shadow(0 0 12px rgba(0, 229, 255, 0.95)) !important; }
    .boost-emerald { stroke: #32D74B !important; stroke-width: 3.4 !important; filter: drop-shadow(0 0 12px rgba(50, 215, 75, 0.95)) !important; }
    .boost-amber { stroke: #FF9F0A !important; stroke-width: 3.6 !important; filter: drop-shadow(0 0 14px rgba(255, 159, 10, 0.95)) !important; }
    .boost-rose { stroke: #FF453A !important; stroke-width: 3.5 !important; filter: drop-shadow(0 0 12px rgba(255, 69, 58, 0.95)) !important; }
    .boost-purple { stroke: #BF5AF2 !important; stroke-width: 3.4 !important; filter: drop-shadow(0 0 12px rgba(191, 90, 242, 0.95)) !important; }

    /* Racing Photon Comet Bead */
    .wind-comet {
      pointer-events: none;
      filter: drop-shadow(0 0 6px rgba(255, 255, 255, 0.95)) drop-shadow(0 0 12px currentColor);
    }
    .comet-cyan { fill: #ffffff; stroke: #00E5FF; stroke-width: 2; color: #00E5FF; }
    .comet-emerald { fill: #ffffff; stroke: #32D74B; stroke-width: 2; color: #32D74B; }
    .comet-amber { fill: #ffffff; stroke: #FF9F0A; stroke-width: 2; color: #FF9F0A; }
    .comet-rose { fill: #ffffff; stroke: #FF453A; stroke-width: 2; color: #FF453A; }
    .comet-purple { fill: #ffffff; stroke: #BF5AF2; stroke-width: 2; color: #BF5AF2; }

    /* Edge Label Pill (Semi-transparent Cyber Glass Badge) */
    .edge-label-group {
      pointer-events: none;
      user-select: none;
    }
    .edge-pill-rect {
      rx: 6;
      ry: 6;
      stroke-width: 1.2;
      filter: drop-shadow(0 2px 6px rgba(0, 0, 0, 0.6));
    }
    .edge-pill-text {
      font-size: 8.5px;
      font-family: 'JetBrains Mono', monospace;
      font-weight: 700;
      text-anchor: middle;
      dominant-baseline: central;
      white-space: nowrap !important;
    }
    .pill-cyan rect { stroke: rgba(0, 229, 255, 0.7); fill: #1E1E1E; }
    .pill-cyan text { fill: #00E5FF; }
    .pill-emerald rect { stroke: rgba(50, 215, 75, 0.7); fill: #1E1E1E; }
    .pill-emerald text { fill: #32D74B; }
    .pill-amber rect { stroke: rgba(255, 159, 10, 0.8); fill: #1E1E1E; }
    .pill-amber text { fill: #FF9F0A; }
    .pill-rose rect { stroke: rgba(255, 69, 58, 0.8); fill: #3A1C1C; }
    .pill-rose text { fill: #FF453A; }
    .pill-purple rect { stroke: rgba(191, 90, 242, 0.7); fill: #1E1E1E; }
    .pill-purple text { fill: #BF5AF2; }

    /* Stepper View Container (Alternative mode) */
    #stepperViewContainer {
      display: none;
      flex-direction: column;
      gap: 0.75rem;
      max-height: 560px;
      overflow-y: auto;
      padding-right: 0.5rem;
    }

    .step-item {
      display: flex;
      gap: 1rem;
      padding: 0.75rem 0.875rem;
      border-radius: 8px;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      transition: all 0.25s;
    }
    .step-item.active-step {
      border-color: var(--accent-cyan);
      background: rgba(0, 229, 255, 0.08);
      box-shadow: 0 0 16px rgba(0, 229, 255, 0.2);
    }
    .step-indicator {
      width: 24px;
      height: 24px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.6875rem;
      font-weight: 700;
      flex-shrink: 0;
      background: var(--bg-base);
      border: 2px solid var(--border-subtle);
      color: var(--text-dim);
    }
    .step-COMPLETED .step-indicator { background: #0A84FF; border-color: #0A84FF; color: #FFFFFF; }
    .step-RUNNING .step-indicator { background: var(--accent-cyan); border-color: var(--accent-cyan); color: #121212; animation: pulse 1.6s infinite; }
    .step-FAILED .step-indicator, .step-BLOCKED .step-indicator { background: var(--accent-rose); border-color: var(--accent-rose); color: #fff; }
    .step-WAITING_HUMAN .step-indicator { background: var(--accent-amber); border-color: var(--accent-amber); color: #121212; }

    /* Right Column: Telemetry & Evidence Inspector */
    .details-pane {
      display: flex;
      flex-direction: column;
      gap: 1.25rem;
      padding-right: 0.4rem;
    }

    .card {
      background: #1E1E1E;
      backdrop-filter: blur(16px);
      border: 1px solid #2C2C2E;
      border-radius: 16px;
      padding: 20px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
      transition: border-color 0.3s;
    }
    .card.highlighted-card {
      border-color: var(--accent-cyan);
      box-shadow: 0 0 20px rgba(0, 229, 255, 0.25);
    }

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 0.875rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid #2C2C2E;
    }
    .card-title {
      font-size: 0.875rem;
      font-weight: 600;
      color: #FFFFFF;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .step-badge {
      font-size: 0.6875rem;
      font-weight: 700;
      padding: 0.15rem 0.55rem;
      border-radius: 4px;
      letter-spacing: 0.03em;
      text-transform: uppercase;
      white-space: nowrap !important;
      flex-shrink: 0 !important;
      display: inline-block;
    }
    .badge-PENDING { background: #252525; border: 1px solid #2C2C2E; color: #98989D; }
    .badge-RUNNING { background: rgba(0, 229, 255, 0.18); border: 1px solid var(--accent-cyan); color: #00E5FF; }
    .badge-PASS { background: rgba(50, 215, 75, 0.2); border: 1px solid var(--accent-emerald); color: #32D74B; }
    .badge-COMPLETED { background: rgba(10, 132, 255, 0.2); border: 1px solid #0A84FF; color: #93C5FD; }
    .badge-FAILED { background: rgba(255, 69, 58, 0.18); border: 1px solid var(--accent-rose); color: #FF453A; }
    .badge-BLOCKED { background: #3A1C1C; border: 1px solid #FF453A; color: #FF453A; }
    .badge-WAITING_HUMAN { background: rgba(255, 159, 10, 0.18); border: 1px solid var(--accent-amber); color: #FF9F0A; }
    .badge-UNKNOWN { background: #252525; border: 1px solid #2C2C2E; color: #98989D; }

    .alert-banner {
      background: #3A1C1C;
      border: 1px solid rgba(255, 69, 58, 0.3);
      border-left: 4px solid #FF453A;
      border-radius: 8px;
      padding: 1rem 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .alert-title {
      color: #FF453A;
      font-weight: 800;
      font-size: 0.9375rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .alert-desc {
      color: #FFB3AE;
      font-size: 0.8125rem;
    }

    .fix-counter-bar {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      margin-top: 0.5rem;
    }
    .fix-pill {
      flex: 1;
      text-align: center;
      padding: 0.5rem;
      border-radius: 6px;
      background: #181818;
      border: 1px solid #2C2C2E;
      font-size: 0.75rem;
      font-weight: 700;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }
    .fix-pill.current {
      border-color: var(--accent-cyan);
      color: var(--accent-cyan);
      background: rgba(0, 229, 255, 0.15);
      box-shadow: 0 0 12px rgba(0, 229, 255, 0.3);
    }
    .fix-pill.done {
      border-color: var(--accent-emerald);
      color: var(--accent-emerald);
      background: rgba(50, 215, 75, 0.15);
    }
    .fix-pill.failed {
      border-color: var(--accent-rose);
      color: var(--accent-rose);
      background: #3A1C1C;
    }

    .code-box {
      background: #121212;
      border: 1px solid #2C2C2E;
      border-radius: 8px;
      padding: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
      font-size: 0.75rem;
      color: #cbd5e1;
      overflow-x: auto;
      max-height: 200px;
      overflow-y: auto;
      white-space: pre-wrap;
    }

    .event-log-table {
      width: 100%;
      border-collapse: collapse;
      table-layout: fixed;
      font-size: 0.75rem;
      font-family: 'JetBrains Mono', monospace;
    }
    .event-log-scroll {
      height: clamp(600px, 75vh, 1000px);
      overflow-y: auto;
      resize: vertical;
    }
    .event-log-section {
      width: 100%;
      max-width: 1680px;
      margin: 1.25rem auto 2rem;
      padding: 0 1.5rem;
    }
    .event-log-table th {
      text-align: left;
      padding: 0.6rem 0.5rem;
      color: var(--text-muted);
      border-bottom: 1px solid #2C2C2E;
      font-weight: 600;
      position: sticky;
      top: 0;
      background: #1E1E1E;
      z-index: 1;
    }
    .event-log-table td {
      padding: 0.5rem 0.5rem;
      border-bottom: 1px solid #2C2C2E;
      color: var(--text-muted);
      vertical-align: top;
      overflow-wrap: anywhere;
    }
    .event-log-table tr:hover td {
      background: #252525;
      color: var(--text-main);
    }
    .badge-source {
      background: rgba(191, 90, 242, 0.15);
      border: 1px solid #BF5AF2;
      color: #E7B8FF;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      font-size: 0.6875rem;
      font-weight: 600;
    }

    footer {
      border-top: 1px solid #2C2C2E;
      padding: 0.65rem 1.75rem;
      font-size: 0.75rem;
      color: var(--text-muted);
      display: flex;
      justify-content: space-between;
      align-items: center;
      background: #181818;
    }
    @media (max-width: 900px) {
      header { padding: 0.65rem 0.75rem; }
      .brand-tag { display: none; }
      .container { grid-template-columns: minmax(0, 1fr); padding: 0 0.75rem; }
      .workspace-pane { min-width: 0; padding: 14px; }
      .pane-header, .legend-group { flex-wrap: wrap; gap: 0.5rem; }
      .graph-scroll-hint { display: block; margin-bottom: 0.5rem; color: var(--text-muted); font-size: 0.75rem; }
      #graphContainer { overflow-x: auto; justify-content: flex-start; min-height: 560px; }
      svg#workflowSvg { flex: 0 0 850px; height: auto; }
    }
  </style>
</head>
<body>

  <!-- Top Navigation Bar -->
  <header>
    <div class="brand">
      <div class="brand-icon">VDL</div>
      <div>
        <span class="brand-title">Trung tâm Điều khiển VDL</span>
        <span class="brand-tag">GIÁM SÁT THỜI GIAN THỰC</span>
      </div>
    </div>

    <!-- View Mode Switcher -->
    <div class="view-switcher">
      <button id="btnGraphView" class="view-btn active" onclick="switchView('graph')">
        <span>&#9737;</span> Sơ đồ Chu trình
      </button>
      <button id="btnStepperView" class="view-btn" onclick="switchView('stepper')">
        <span>&#9776;</span> Nhật ký Tuần tự
      </button>
    </div>

    <div class="header-controls">
      <div class="control-group">
        <label for="projectSelect">Dự án:</label>
        <select id="projectSelect" onchange="switchProject(this.value)">
          <option value="">Đang tải...</option>
        </select>
      </div>

      <div class="control-group">
        <label for="sessionSelect">Phiên:</label>
        <select id="sessionSelect" onchange="switchSession(this.value)">
          <option value="all">Tất cả phiên</option>
        </select>
      </div>

      <div class="control-group">
        <label for="demoModeSelect">Mô phỏng UI:</label>
        <select id="demoModeSelect">
          <option value="feature">Feature</option>
          <option value="bug">Bug</option>
        </select>
      </div>

      <button id="btnDemoMode" class="demo-btn" onclick="toggleDemoMode()" title="Chạy mô phỏng để kiểm tra hiệu ứng sáng node và boots tốc độ">
        <span id="demoBtnIcon">▶</span> <span id="demoBtnText">Thử Nghiệm FX · Mô phỏng UI</span>
      </button>

      <div id="connPill" class="status-pill status-CONNECTING">
        <div class="status-dot"></div>
        <span id="connText">Đang kết nối...</span>
      </div>
    </div>
  </header>

  <!-- Live Telemetry Quick Metrics Ribbon -->
  <div class="metrics-bar">
    <div class="metric-item">
      <span class="metric-label">Mode:</span>
      <span id="metricMode" class="metric-value">Chưa chọn mode</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Giai đoạn:</span>
      <span id="metricStage" class="metric-value">Yêu cầu Gốc</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Nhiệm vụ:</span>
      <span id="metricTask" class="metric-value">chưa có</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Vòng sửa lỗi:</span>
      <span id="metricFix" class="metric-value metric-mono">Vòng 0/3</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Kiểm thử:</span>
      <span id="metricVerify" class="metric-badge badge-PENDING">CHỜ</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Review:</span>
      <span id="metricReview" class="metric-badge badge-PENDING">CHỜ</span>
    </div>
    <div class="metric-item">
      <span class="metric-label">Fingerprint:</span>
      <span id="metricFingerprint" class="metric-value metric-mono">--------</span>
    </div>
  </div>

  <div class="container">
    <!-- Left Column: Graph View / Stepper View -->
    <section class="workspace-pane">
      <div class="pane-header">
        <div class="pane-title">
          <span id="paneTitleText">Sơ đồ Chu trình Workflow</span>
        </div>
        <div id="loopStatusBadge" class="loop-indicator-pill loop-idle">
          <span>&#8634;</span> <span id="loopStatusText">Chu trình phản hồi: NGHỈ (IDLE)</span>
        </div>
      </div>

      <!-- Arrow Color & Node Status Legend Ribbon (Dedicated Row) -->
      <div class="arrow-legend-ribbon">
        <div class="legend-group">
          <span class="legend-group-title">MŨI TÊN:</span>
          <span class="legend-item"><span class="legend-color-dot dot-cyan"></span>Tuần tự</span>
          <span class="legend-item"><span class="legend-color-dot dot-emerald"></span>Phê duyệt / ĐẠT</span>
          <span class="legend-item"><span class="legend-color-dot dot-orange"></span>Vòng sửa lỗi ↺</span>
          <span class="legend-item"><span class="legend-color-dot dot-red"></span>Thất bại / Bị chặn</span>
          <span class="legend-item"><span class="legend-color-dot dot-purple"></span>Kế tiếp / Nghiệm thu</span>
        </div>
        <div class="legend-group">
          <span class="legend-group-title">NODE:</span>
          <span class="legend-item"><span class="legend-color-dot dot-slate"></span>Chưa đến</span>
          <span class="legend-item"><span class="legend-color-dot dot-cyan-active"></span>Sáng dần (Đang chạy)</span>
          <span class="legend-item"><span class="legend-color-dot dot-magenta-upcoming"></span>Chuẩn bị đến (Upcoming)</span>
          <span class="legend-item"><span class="legend-color-dot dot-sapphire"></span>Đã chạy qua</span>
        </div>
      </div>

      <div class="mode-explainer"><p><strong>Feature Mode:</strong> Interview làm rõ yêu cầu trước Spec/Plan.</p><p><strong>Bug Mode:</strong> Diagnosis thay Interview để tái hiện lỗi và xác định nguyên nhân trước Spec/Plan. Các bước sau đó giống Feature Mode.</p><p>“Thử Nghiệm FX” chỉ mô phỏng giao diện, không khởi chạy workflow.</p></div>
      <p id="emptyWorkflowNote" class="mode-explainer">Chưa có workflow. Chưa chọn mode; hãy xem mô tả Feature Mode và Bug Mode ở trên.</p>
      <p class="graph-scroll-hint">Vuốt ngang trong khung sơ đồ để xem các node còn lại.</p>

      <!-- VIEW 1: Dynamic SVG Workflow Loop Graph -->
      <div id="graphContainer">
        <svg id="workflowSvg" viewBox="0 0 1100 700">
          <defs>
            <!-- Glowing filters -->
            <filter id="glowCyan" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glowEmerald" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glowRose" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="glowAmber" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>

            <!-- Modern Cyber Stealth Arrow Markers -->
            <marker id="arrowDefault" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#00E5FF" />
            </marker>
            <marker id="arrowCyan" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#00E5FF" />
            </marker>
            <marker id="arrowEmerald" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#32D74B" />
            </marker>
            <marker id="arrowAmber" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#FF9F0A" />
            </marker>
            <marker id="arrowRose" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#FF453A" />
            </marker>
            <marker id="arrowPurple" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="7.5" markerHeight="7.5" orient="auto-start-reverse">
              <path d="M 1 2 L 10 6 L 1 10 L 3.5 6 Z" fill="#BF5AF2" />
            </marker>
          </defs>

          <!-- Phase Group Backgrounds -->
          <g id="svgPhaseBgs">
            <!-- Phase 1: Inception -->
            <rect class="svg-phase-bg" x="20" y="15" width="1060" height="245" rx="16" />
            <text class="svg-phase-title" x="60" y="34">TẦNG 1: THIẾT LẬP &amp; DUYỆT KẾ HOẠCH (INCEPTION)</text>

            <!-- Phase 2: Governed Core Execution -->
            <rect class="svg-phase-bg" x="20" y="280" width="1060" height="160" rx="16" />
            <text class="svg-phase-title" x="135" y="299">TẦNG 2: TDD, VERIFICATION, REVIEW &amp; QA (CORE EXECUTION)</text>

            <!-- Phase 3: Bounded Feedback Loops & Escape Branch -->
            <rect class="svg-phase-bg" x="20" y="480" width="1060" height="155" rx="16" />
            <text class="svg-phase-title" x="60" y="499">TẦNG 3: VÒNG LẶP SỬA LỖI &amp; PHÒNG VỆ AN TOÀN (BOUNDED FIX &amp; SAFETY)</text>
          </g>

          <!-- SVG Edges Layer -->
          <g id="svgEdgesLayer"></g>

          <!-- SVG Nodes Layer -->
          <g id="svgNodesLayer"></g>
        </svg>
      </div>

      <!-- VIEW 2: Stepper Timeline (Alternative View) -->
      <div id="stepperViewContainer">
        <!-- Rendered dynamically -->
      </div>
    </section>

    <!-- Right Side: Deep Telemetry & Evidence Inspector -->
    <section class="details-pane">

      <!-- BLOCKED Warning Banner (if blocked) -->
      <div id="blockedBanner" class="alert-banner" style="display: none;">
        <div class="alert-title">
          <span>&#9888; TIẾN TRÌNH BỊ CHẶN (BLOCKED)</span>
        </div>
        <div id="blockedReason" class="alert-desc">Tiến trình bị chặn, chờ quyết định từ con người.</div>
        <div id="blockedEvidence" style="font-size: 0.75rem; color: #FFB3AE; font-family: 'JetBrains Mono', monospace;"></div>
      </div>

      <!-- Verification Inspector Card -->
      <div id="verCard" class="card">
        <div class="card-header">
          <div class="card-title">
            <span>&#9881; Bằng chứng Kiểm thử Độc lập</span>
          </div>
          <span id="verStatusBadge" class="step-badge badge-PENDING">CHỜ</span>
        </div>
        <div id="verInfo" style="font-size: 0.8125rem; color: var(--text-muted); margin-bottom: 0.75rem;">
          Chưa thực hiện lệnh kiểm thử nào.
        </div>
        <div id="verLogs" class="code-box" style="display: none;"></div>
      </div>

      <!-- Code Review Inspector Card -->
      <div id="revCard" class="card">
        <div class="card-header">
          <div class="card-title">
            <span>&#128065; Kết quả Review Độc lập</span>
          </div>
          <span id="revStatusBadge" class="step-badge badge-PENDING">CHỜ</span>
        </div>
        <div id="revInfo" style="font-size: 0.8125rem; color: var(--text-muted); margin-bottom: 0.5rem;">
          Reviewer độc lập chưa kiểm tra nhiệm vụ.
        </div>
        <div id="revFindings" class="code-box" style="display: none;"></div>
      </div>

      <!-- Bounded Fix Loop Tracker Card -->
      <div id="fixCard" class="card">
        <div class="card-header">
          <div class="card-title">
            <span>&#8634; Vòng lặp Sửa lỗi Có giới hạn (Tối đa 3 lượt)</span>
          </div>
          <span id="fixStatusBadge" class="step-badge badge-PENDING">0 / 3</span>
        </div>
        <div class="fix-counter-bar">
          <div id="fixPill1" class="fix-pill">Lượt 1 / 3</div>
          <div id="fixPill2" class="fix-pill">Lượt 2 / 3</div>
          <div id="fixPill3" class="fix-pill">Lượt 3 / 3</div>
        </div>
        <div id="fixApproach" style="font-size: 0.8125rem; color: var(--text-muted); margin-top: 0.75rem;">
          Chưa kích hoạt vòng sửa lỗi nào.
        </div>
      </div>

      <!-- Main Agent Report Card -->
      <div id="repCard" class="card">
        <div class="card-header">
          <div class="card-title">
            <span>&#10003; Báo cáo Tổng kết &amp; Nghiệm thu</span>
          </div>
          <span id="repStatusBadge" class="step-badge badge-PENDING">CHỜ</span>
        </div>
        <div id="repSummary" style="font-size: 0.8125rem; color: var(--text-muted);">
          Đang chờ hoàn tất tất cả các nhiệm vụ.
        </div>
        <ul id="repCriteriaList" style="margin-top: 0.5rem; margin-left: 1.25rem; font-size: 0.8125rem; color: #cbd5e1;"></ul>
      </div>

    </section>
  </div>

  <footer>
    <div>Trung tâm Điều khiển VDL &bull; Governed Verified Development Loop &bull; Giám sát Thụ động Thời gian thực</div>
    <div id="footerMeta">Tự động đồng bộ lại qua Last-Event-ID</div>
  </footer>

  <section class="event-log-section" aria-label="Nhật ký sự kiện">
    <!-- Live Event Log -->
    <div id="eventCard" class="card">
      <div class="card-header">
        <div class="card-title">
          <span>Nhật ký Sự kiện Thời gian thực</span>
        </div>
        <span id="eventCountBadge" class="step-badge badge-PENDING">0 Sự kiện</span>
      </div>
      <div class="event-log-scroll">
        <table class="event-log-table">
          <thead>
            <tr>
              <th style="width: 110px;">Thời gian</th>
              <th style="width: 90px;">Nguồn</th>
              <th style="width: 180px;">Sự kiện</th>
              <th>Trạng thái / Tóm tắt</th>
            </tr>
          </thead>
          <tbody id="eventTableBody">
            <tr><td colspan="4" style="text-align: center; color: var(--text-dim);">Đang lắng nghe sự kiện từ Agent...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </section>

  <script>
    let currentProjectId = "";
    let currentSessionId = "all";
    let eventSource = null;
    let lastEventId = "";
    let eventsList = [];
    let currentViewMode = "graph";
    let selectedNodeId = null;

    // Node Spatial Coordinates on the 1100x700 SVG Canvas (Circular Nodes)
    const NODE_COORDS = {
      // Tầng 1: hai nhánh mode cùng cột, cách nhau theo hàng.
      prompt:      { cx: 95,  cy: 80,  r: 26, icon: "💬", label: "Yêu cầu Gốc", sub: "User Prompt" },
      read_errors: { cx: 275, cy: 80,  r: 26, icon: "📖", label: "Đọc Lỗi Cũ", sub: "Ký ức lỗi" },
      interview:   { cx: 430, cy: 80,  r: 26, icon: "❓", label: "Phỏng Vấn", sub: "Feature Mode" },
      diagnosis:   { cx: 430, cy: 180, r: 26, icon: "🔬", label: "Chẩn Đoán", sub: "Bug Mode" },
      proposal:    { cx: 665, cy: 80,  r: 26, icon: "📋", label: "Đặc Tả & Plan", sub: "Kế hoạch chi tiết" },
      approval:    { cx: 890, cy: 80,  r: 28, icon: "🛡️", label: "Cổng Duyệt", sub: "Chờ người duyệt", isGate: true },

       // Tầng 2: TDD, Verification, Review & QA (cy = 350)
      active:      { cx: 95,  cy: 350, r: 26, icon: "🎯", label: "Nhiệm Vụ", sub: "Phạm vi Task" },
      tdd:         { cx: 275, cy: 350, r: 26, icon: "⚡", label: "Lập Trình TDD", sub: "Red-Green-Refactor" },
      verify:      { cx: 505, cy: 350, r: 28, icon: "🧪", label: "Cổng Kiểm Thử", sub: "Test argv độc lập", isGate: true },
       review:      { cx: 705, cy: 350, r: 28, icon: "🔍", label: "Review Độc Lập", sub: "Agent phản biện", isGate: true },
       qa:          { cx: 845, cy: 350, r: 28, icon: "🧭", label: "QA Sản Phẩm", sub: "Thử nghiệm thực tế", isGate: true },
       complete:    { cx: 1000, cy: 350, r: 26, icon: "🏆", label: "Nhiệm Vụ Xong", sub: "Hoàn tất task" },

      // Tầng 3: Vòng lặp sửa lỗi & Phòng vệ an toàn (cy = 535)
      blocked:     { cx: 95,  cy: 535, r: 28, icon: "⛔", label: "BỊ CHẶN", sub: "Dừng an toàn", isBlocked: true },
      fix_loop:    { cx: 275, cy: 535, r: 28, icon: "↺", label: "Vòng Sửa Lỗi", sub: "Tối đa 3 lượt", isLoop: true },
      error_rec:   { cx: 505, cy: 535, r: 26, icon: "📝", label: "Ghi Nhận Lỗi", sub: "Mã hóa lỗi ID" },
       report:      { cx: 1000, cy: 535, r: 26, icon: "📢", label: "Báo Cáo", sub: "Nghiệm thu cuối" }
    };

    // Edge Path Definitions with Semantic Color Coding (Không che lấn, chuẩn hành lang, vuông góc chuẩn xác, kéo dài đoạn thẳng)
    const EDGE_PATHS = [
      // Tầng 1: Tuần tự ngang (Cyan)
      { id: "prompt->read_errors", from: "prompt", to: "read_errors", color: "cyan", marker: "arrowCyan", d: "M 121 80 L 247 80" },
      { id: "read_errors->interview", from: "read_errors", to: "interview", color: "cyan", marker: "arrowCyan", d: "M 301 80 L 402 80" },
      { id: "read_errors->diagnosis", from: "read_errors", to: "diagnosis", color: "cyan", marker: "arrowCyan", d: "M 301 80 L 320 80 L 320 180 L 402 180" },
      { id: "interview->proposal", from: "interview", to: "proposal", color: "cyan", marker: "arrowCyan", d: "M 458 80 L 637 80" },
      { id: "diagnosis->proposal", from: "diagnosis", to: "proposal", color: "cyan", marker: "arrowCyan", d: "M 456 180 L 540 180 L 540 95 L 644 95" },
      { id: "proposal->approval", from: "proposal", to: "approval", color: "cyan", marker: "arrowCyan", d: "M 691 80 L 860 80" },

      { id: "approval->proposal", from: "approval", to: "proposal", color: "amber", marker: "arrowAmber", d: "M 890 52 L 890 30 L 665 30 L 665 52", label: "Yêu cầu sửa ↺", labelX: 778, labelY: 30 },

      // Hành lang dưới hai nhánh mode, phía trên hàng Task.
      { id: "approval->active", from: "approval", to: "active", color: "emerald", marker: "arrowEmerald", d: "M 890 153 L 890 265 L 95 265 L 95 324", label: "Đã phê duyệt", labelX: 480, labelY: 265 },

      // Chu trình 2: Task kế tiếp ở đầu tầng TDD.
       { id: "complete->active", from: "complete", to: "active", color: "purple", marker: "arrowPurple", d: "M 1000 324 L 1000 310 L 35 310 L 35 350 L 67 350", label: "Task kế tiếp ↺", labelX: 680, labelY: 310 },

      // Tầng 2: Cốt lõi ngang (Cyan)
      { id: "active->tdd", from: "active", to: "tdd", color: "cyan", marker: "arrowCyan", d: "M 121 350 L 247 350" },
      { id: "tdd->verify", from: "tdd", to: "verify", color: "cyan", marker: "arrowCyan", d: "M 301 350 L 475 350" },

      // Hai cổng Đạt chuẩn (Emerald)
       { id: "verify->review", from: "verify", to: "review", color: "emerald", marker: "arrowEmerald", d: "M 533 350 L 675 350", label: "ĐẠT (PASS)", labelX: 604, labelY: 334 },
       { id: "review->qa", from: "review", to: "qa", color: "emerald", marker: "arrowEmerald", d: "M 733 350 L 815 350" },
       { id: "qa->complete", from: "qa", to: "complete", color: "emerald", marker: "arrowEmerald", d: "M 873 350 L 972 350", label: "ĐẠT (PASS)", labelX: 923, labelY: 334 },

      // THẲNG ĐỨNG 90°: Cổng Kiểm thử Thất bại rơi thẳng xuống Ghi nhận lỗi (Rose / Đỏ)
      // Xuất phát dưới Kiểm thử, đến đỉnh Ghi nhận lỗi.
      { id: "verify->error_rec", from: "verify", to: "error_rec", color: "rose", marker: "arrowRose", d: "M 505 422 L 505 507", label: "THẤT BẠI (FAIL)", labelX: 505, labelY: 462 },

      // Review có điểm sửa lỗi (Hành lang Giữa 3: y = 445 - Rose / Đỏ)
       { id: "review->error_rec", from: "review", to: "error_rec", color: "rose", marker: "arrowRose", d: "M 705 422 L 705 435 Q 705 445 695 445 L 595 445 Q 585 445 585 455 L 585 525 Q 585 535 575 535 L 533 535", label: "Có điểm cần sửa", labelX: 645, labelY: 445 },
       { id: "qa->error_rec", from: "qa", to: "error_rec", color: "rose", marker: "arrowRose", d: "M 845 422 L 845 465 Q 845 475 835 475 L 635 475 Q 625 475 625 485 L 625 525 Q 625 535 615 535 L 533 535", label: "QA FAIL", labelX: 745, labelY: 475 },

      // Tầng 3: Chuyển sang Vòng sửa lỗi (Cyan)
      { id: "error_rec->fix_loop", from: "error_rec", to: "fix_loop", color: "cyan", marker: "arrowCyan", d: "M 479 535 L 305 535" },

      // CHU TRÌNH SỬA LỖI CỐT LÕI: VUÔNG GÓC KHÉP KÍN (Amber / Cam)
      { id: "fix_loop->tdd", from: "fix_loop", to: "tdd", color: "amber", marker: "arrowAmber", d: "M 247 535 L 195 535 Q 185 535 185 525 L 185 360 Q 185 350 195 350 L 247 350", label: "Sửa lỗi ↺", labelX: 185, labelY: 452 },

      // Khi cạn kiệt 3 lượt: fix_loop rẽ sang BỊ CHẶN (Rose / Đỏ)
      { id: "fix_loop->blocked", from: "fix_loop", to: "blocked", color: "rose", marker: "arrowRose", d: "M 247 535 L 125 535", label: "Vượt quá 3 lượt", labelX: 186, labelY: 520 },

      // Khi thiếu tool / lỗi nghiêm trọng: Rẽ sang Hành lang y = 468 lượn vào đỉnh BỊ CHẶN (Rose / Đỏ)
      { id: "verify->blocked", from: "verify", to: "blocked", color: "rose", marker: "arrowRose", d: "M 480 422 L 480 458 Q 480 468 470 468 L 105 468 Q 95 468 95 478 L 95 505", label: "Lỗi sâu / Thiếu tool", labelX: 290, labelY: 468 },

      // THẲNG ĐỨNG 90°: Hoàn thành xuống Báo cáo Nghiệm thu (Purple / Tím)
       { id: "complete->report", from: "complete", to: "report", color: "purple", marker: "arrowPurple", d: "M 1000 422 L 1000 507", label: "Nghiệm thu", labelX: 1000, labelY: 462 }
    ];

    function switchView(mode) {
      currentViewMode = mode;
      const btnGraph = document.getElementById("btnGraphView");
      const btnStepper = document.getElementById("btnStepperView");
      const graphContainer = document.getElementById("graphContainer");
      const stepperContainer = document.getElementById("stepperViewContainer");
      const title = document.getElementById("paneTitleText");

      if (mode === "graph") {
        btnGraph.classList.add("active");
        btnStepper.classList.remove("active");
        graphContainer.style.display = "flex";
        stepperContainer.style.display = "none";
        title.textContent = "Sơ đồ Chu trình Workflow";
      } else {
        btnStepper.classList.add("active");
        btnGraph.classList.remove("active");
        graphContainer.style.display = "none";
        stepperContainer.style.display = "flex";
        title.textContent = "Nhật ký Thực thi Tuần tự (Audit Trail)";
      }
    }

    function updateConnStatus(status, text) {
      const pill = document.getElementById("connPill");
      const textElem = document.getElementById("connText");
      pill.className = "status-pill status-" + status;
      textElem.textContent = text;
    }

    async function loadProjects() {
      try {
        const res = await fetch("/api/projects");
        const data = await res.json();
        const sel = document.getElementById("projectSelect");
        sel.innerHTML = "";
        data.projects.forEach(p => {
          const opt = document.createElement("option");
          opt.value = p.id;
          opt.textContent = p.id;
          if (p.is_default) {
            opt.selected = true;
            currentProjectId = p.id;
          }
          sel.appendChild(opt);
        });
        if (!currentProjectId && data.projects.length > 0) {
          currentProjectId = data.projects[0].id;
        }
        await refreshState();
        connectSSE();
      } catch (err) {
        console.error("Failed to load projects", err);
      }
    }

    function switchProject(pid) {
      currentProjectId = pid;
      refreshState();
      connectSSE();
    }

    function switchSession(sid) {
      currentSessionId = sid;
      refreshState();
    }

    // Render SVG Graph Nodes and Directed Edges
    function renderSvgGraph(graphData) {
      const nodesLayer = document.getElementById("svgNodesLayer");
      const edgesLayer = document.getElementById("svgEdgesLayer");
      if (!nodesLayer || !edgesLayer) return;

      nodesLayer.innerHTML = "";
      edgesLayer.innerHTML = "";

      const activeEdges = new Set(graphData.active_edges || []);
      const nodeStatusMap = {};
      (graphData.nodes || []).forEach(n => {
        nodeStatusMap[n.id] = n;
      });
      if (!graphData.mode) {
        for (const id of ["interview", "diagnosis"]) {
          if (!nodeStatusMap[id]) nodeStatusMap[id] = { id, status: "PENDING" };
        }
      }

      // 1. Render Edges with Semantic Colors, Speed Boost FX & Label Pills
      EDGE_PATHS.forEach(edge => {
         if (!nodeStatusMap[edge.from] || !nodeStatusMap[edge.to]) return;
        const isActive = activeEdges.has(edge.id);
        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");

        if (isActive) {
          // A. Wind Aura Track (thick glowing background)
          const aura = document.createElementNS("http://www.w3.org/2000/svg", "path");
          aura.setAttribute("d", edge.d);
          aura.setAttribute("fill", "none");
          aura.setAttribute("class", `edge-wind-aura aura-${edge.color}`);
          g.appendChild(aura);

          // B. Main Speed Boost Path (fast streaming capsules)
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("d", edge.d);
          path.setAttribute("fill", "none");
          path.setAttribute("class", `graph-edge edge-speed-boost boost-${edge.color}`);
          path.setAttribute("marker-end", `url(#${edge.marker})`);
          g.appendChild(path);

          // C. Racing Photon Comet 1 (high speed energy bead along curve)
          const comet1 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          comet1.setAttribute("r", "4.5");
          comet1.setAttribute("cx", "0");
          comet1.setAttribute("cy", "0");
          comet1.setAttribute("class", `wind-comet comet-${edge.color}`);

          const anim1 = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
          anim1.setAttribute("path", edge.d);
          anim1.setAttribute("dur", "0.65s");
          anim1.setAttribute("repeatCount", "indefinite");
          comet1.appendChild(anim1);
          g.appendChild(comet1);

          // D. Racing Photon Comet 2 (staggered trail bead for continuous speed stream)
          const comet2 = document.createElementNS("http://www.w3.org/2000/svg", "circle");
          comet2.setAttribute("r", "3.2");
          comet2.setAttribute("cx", "0");
          comet2.setAttribute("cy", "0");
          comet2.setAttribute("class", `wind-comet comet-${edge.color}`);
          comet2.setAttribute("opacity", "0.75");

          const anim2 = document.createElementNS("http://www.w3.org/2000/svg", "animateMotion");
          anim2.setAttribute("path", edge.d);
          anim2.setAttribute("dur", "0.65s");
          anim2.setAttribute("begin", "0.32s");
          anim2.setAttribute("repeatCount", "indefinite");
          comet2.appendChild(anim2);
          g.appendChild(comet2);
        } else {
          // Standard Inactive Semantic Edge
          const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("d", edge.d);
          path.setAttribute("fill", "none");
          path.setAttribute("class", `graph-edge edge-${edge.color}`);
          path.setAttribute("marker-end", `url(#${edge.marker})`);
          g.appendChild(path);
        }

        if (edge.label) {
          const lx = (edge.labelX !== undefined) ? edge.labelX : 500;
          const ly = (edge.labelY !== undefined) ? edge.labelY : 200;

          const labelG = document.createElementNS("http://www.w3.org/2000/svg", "g");
          labelG.setAttribute("class", `edge-label-group pill-${edge.color}`);

          const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
          text.setAttribute("class", "edge-pill-text");
          text.setAttribute("x", lx);
          text.setAttribute("y", ly);
          text.textContent = edge.label;

          // Estimate pill card dimensions
          const padX = 14;
          const charW = 6.8;
          const pillW = edge.label.length * charW + padX * 2;
          const pillH = 18;

          const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
          rect.setAttribute("class", "edge-pill-rect");
          rect.setAttribute("x", lx - pillW / 2);
          rect.setAttribute("y", ly - pillH / 2);
          rect.setAttribute("width", pillW);
          rect.setAttribute("height", pillH);

          labelG.appendChild(rect);
          labelG.appendChild(text);
          g.appendChild(labelG);
        }

        edgesLayer.appendChild(g);
      });

      // Map status codes to Vietnamese
      const VN_STATUS_MAP = {
        "PENDING": "CHỜ",
        "RUNNING": "ĐANG CHẠY",
        "COMPLETED": "HOÀN THÀNH",
        "FAILED": "THẤT BẠI",
        "BLOCKED": "BỊ CHẶN",
        "WAITING_HUMAN": "CHỜ DUYỆT",
        "UNKNOWN": "CHƯA RÕ"
      };

      // 2. Render Circular Nodes with Multi-Tier Luminosity & Upcoming State
      Object.keys(NODE_COORDS).forEach(nodeId => {
         if (!nodeStatusMap[nodeId]) return;
        const cfg = NODE_COORDS[nodeId];
        const stateNode = nodeStatusMap[nodeId] || { status: "PENDING", is_active: false };
        const status = stateNode.status || "PENDING";
        const isSelected = (selectedNodeId === nodeId);
        const isActiveNode = !!(stateNode.is_active || status === "RUNNING") && !["COMPLETED", "FAILED", "BLOCKED"].includes(status);
        const isUpcoming = !!(stateNode.is_next);

        let tierClass = "node-PENDING";
        if (isActiveNode) {
          tierClass = "node-ACTIVE-LUMINOUS";
        } else if (isUpcoming) {
          tierClass = "node-UPCOMING";
        } else if (status === "COMPLETED") {
          tierClass = "node-COMPLETED";
        } else if (status === "FAILED" || status === "BLOCKED") {
          tierClass = `node-${status}`;
        } else if (status === "WAITING_HUMAN") {
          tierClass = "node-WAITING_HUMAN";
        }

        const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
        g.setAttribute("class", `graph-node ${tierClass} node-${status} ${isActiveNode ? 'node-RUNNING' : ''} ${isUpcoming ? 'node-is-next' : ''} ${isSelected ? 'node-selected' : ''}`);
        g.setAttribute("onclick", `inspectNode('${nodeId}')`);

        // 1. Outer Glow / Pulse Ring
        const glowRing = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        glowRing.setAttribute("class", "node-glow-ring");
        glowRing.setAttribute("cx", cfg.cx);
        glowRing.setAttribute("cy", cfg.cy);
        glowRing.setAttribute("r", cfg.r + 6);
        g.appendChild(glowRing);

        // 2. Main Circle Body
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("class", "node-circle");
        circle.setAttribute("cx", cfg.cx);
        circle.setAttribute("cy", cfg.cy);
        circle.setAttribute("r", cfg.r);
        g.appendChild(circle);

        // 3. Node Icon Glyph inside the circle
        const iconText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        iconText.setAttribute("class", `node-icon ${nodeId === 'fix_loop' ? 'node-icon-fix' : ''}`);
        iconText.setAttribute("x", cfg.cx);
        iconText.setAttribute("y", cfg.cy + 1);
        iconText.textContent = cfg.icon;
        g.appendChild(iconText);

        // 4. Centered Title (Tiếng Việt) below circle
        const title = document.createElementNS("http://www.w3.org/2000/svg", "text");
        title.setAttribute("class", "node-title");
        title.setAttribute("x", cfg.cx);
        title.setAttribute("y", cfg.cy + 37);
        title.textContent = (nodeId === "fix_loop" && graphData.loop_round) ? `Vòng Sửa (${graphData.loop_round}/3)` : cfg.label;
        g.appendChild(title);

        // 5. Centered Subtitle (Tiếng Việt)
        const sub = document.createElementNS("http://www.w3.org/2000/svg", "text");
        sub.setAttribute("class", "node-sub");
        sub.setAttribute("x", cfg.cx);
        sub.setAttribute("y", cfg.cy + 49);
        sub.textContent = cfg.sub;
        g.appendChild(sub);

        // 6. Centered Status Badge Pill
        const badgeW = (isUpcoming && !isActiveNode) ? 62 : 54;
        const badgeH = 14;
        const badgeX = cfg.cx - badgeW / 2;
        const badgeY = cfg.cy + 57;

        const badgeRect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        badgeRect.setAttribute("class", "node-badge-rect");
        badgeRect.setAttribute("x", badgeX);
        badgeRect.setAttribute("y", badgeY);
        badgeRect.setAttribute("width", badgeW);
        badgeRect.setAttribute("height", badgeH);
        g.appendChild(badgeRect);

        const badgeText = document.createElementNS("http://www.w3.org/2000/svg", "text");
        badgeText.setAttribute("class", "node-badge-text");
        badgeText.setAttribute("x", cfg.cx);
        badgeText.setAttribute("y", badgeY + 10.5);

        let badgeDisplay = VN_STATUS_MAP[status] || status;
        if (isActiveNode) {
          badgeDisplay = (status === "WAITING_HUMAN") ? "CHỜ DUYỆT" : "ĐANG CHẠY";
        } else if (isUpcoming && status === "PENDING") {
          badgeDisplay = "CHUẨN BỊ";
        }
        badgeText.textContent = badgeDisplay;
        g.appendChild(badgeText);

        // 7. Node Anchor Ports for visual connection continuity
        const portBottom = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        portBottom.setAttribute("class", "node-port node-port-bottom");
        portBottom.setAttribute("cx", cfg.cx);
        portBottom.setAttribute("cy", cfg.cy + 71);
        portBottom.setAttribute("r", 3.2);
        g.appendChild(portBottom);

        const portTop = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        portTop.setAttribute("class", "node-port node-port-top");
        portTop.setAttribute("cx", cfg.cx);
        portTop.setAttribute("cy", cfg.cy - cfg.r);
        portTop.setAttribute("r", 3.2);
        g.appendChild(portTop);

        nodesLayer.appendChild(g);
      });

      // Update Loop Status Badge in pane header
      const loopBadge = document.getElementById("loopStatusBadge");
      const loopText = document.getElementById("loopStatusText");
      if (graphData.is_blocked) {
        loopBadge.className = "loop-indicator-pill";
        loopBadge.style.background = "#3A1C1C";
        loopBadge.style.border = "1px solid #FF453A";
        loopBadge.style.color = "#FF453A";
        loopText.textContent = "Chu trình phản hồi: BỊ CHẶN";
      } else if (graphData.is_looping) {
        loopBadge.className = "loop-indicator-pill loop-active";
        loopBadge.style.background = "";
        loopBadge.style.border = "";
        loopBadge.style.color = "";
        loopText.textContent = `Chu trình phản hồi: ĐANG CHẠY (Vòng ${graphData.loop_round}/3)`;
      } else {
        loopBadge.className = "loop-indicator-pill loop-idle";
        loopBadge.style.background = "";
        loopBadge.style.border = "";
        loopBadge.style.color = "";
        loopText.textContent = "Chu trình phản hồi: NGHỈ (IDLE)";
      }
    }

    // Interactive Click-to-Inspect handler
    function inspectNode(nodeId) {
      selectedNodeId = nodeId;
      // Re-render graph to show focus ring
      if (window.latestGraphData) {
        renderSvgGraph(window.latestGraphData);
      }

      // Highlight corresponding card and scroll smoothly
      const allCards = document.querySelectorAll(".card");
      allCards.forEach(c => c.classList.remove("highlighted-card"));

      let targetCardId = null;
      if (nodeId === "verify") targetCardId = "verCard";
      else if (nodeId === "review") targetCardId = "revCard";
      else if (nodeId === "fix_loop" || nodeId === "error_rec") targetCardId = "fixCard";
      else if (nodeId === "report" || nodeId === "complete") targetCardId = "repCard";
      else if (nodeId === "blocked") targetCardId = "blockedBanner";

      if (targetCardId) {
        const card = document.getElementById(targetCardId);
        if (card) {
          card.classList.add("highlighted-card");
          card.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      }
    }

    function renderStepper(steps, currentStepId) {
      const container = document.getElementById("stepperViewContainer");
      if (!container) return;
      container.innerHTML = "";
      if (!steps.length) {
        container.textContent = "Chưa có workflow. Chưa chọn mode.";
        return;
      }

      const VN_STATUS_MAP = {
        "PENDING": "CHỜ",
        "RUNNING": "ĐANG CHẠY",
        "COMPLETED": "HOÀN THÀNH",
        "FAILED": "THẤT BẠI",
        "BLOCKED": "BỊ CHẶN",
        "WAITING_HUMAN": "CHỜ DUYỆT",
        "UNKNOWN": "CHƯA RÕ"
      };

      steps.forEach((step, idx) => {
        const item = document.createElement("div");
        const isActive = (step.id === currentStepId);
        item.className = `step-item step-${step.status} ${isActive ? 'active-step' : ''}`;

        const isCheck = (step.status === "COMPLETED");
        const icon = isCheck ? "&#10003;" : (idx + 1);
        const displayName = step.name_vn || step.name;

        item.innerHTML = `
          <div class="step-indicator">${icon}</div>
          <div style="flex: 1; min-width: 0;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.2rem;">
              <span style="font-size: 0.875rem; font-weight: 700; color: #fff;">${displayName}</span>
              <span class="step-badge badge-${step.status}">${VN_STATUS_MAP[step.status] || step.status}</span>
            </div>
            <div style="font-size: 0.78125rem; color: var(--text-muted); word-break: break-word;">${escapeHtml(step.summary || "")}</div>
            ${step.timestamp ? `<div style="font-size: 0.6875rem; color: var(--text-dim); font-family: 'JetBrains Mono', monospace; margin-top: 0.25rem;">${formatTime(step.timestamp)}</div>` : ''}
          </div>
        `;
        container.appendChild(item);
      });
    }

    function renderVerification(ver) {
      const badge = document.getElementById("verStatusBadge");
      const info = document.getElementById("verInfo");
      const logs = document.getElementById("verLogs");
      const metricVerify = document.getElementById("metricVerify");

      if (!ver || !ver.status) {
        badge.className = "step-badge badge-PENDING";
        badge.textContent = "CHỜ";
        metricVerify.className = "metric-badge badge-PENDING";
        metricVerify.textContent = "CHỜ";
        info.textContent = "Chưa thực hiện lệnh kiểm thử nào.";
        logs.style.display = "none";
        return;
      }

      const st = ver.status;
      badge.className = "step-badge badge-" + (st === "PASS" ? "PASS" : "FAILED");
      badge.textContent = st === "PASS" ? "ĐẠT" : "HỎNG";
      metricVerify.className = "metric-badge badge-" + (st === "PASS" ? "PASS" : "FAILED");
      metricVerify.textContent = st === "PASS" ? "ĐẠT (PASS)" : "HỎNG (FAIL)";
      info.textContent = `Bằng chứng: ${ver.evidence || "chưa có"} (Mã: ${(ver.revision || "").slice(0, 8)})`;

      if (ver.commands && ver.commands.length > 0) {
        logs.style.display = "block";
        logs.innerHTML = ver.commands.map(c => {
          const cmdStr = Array.isArray(c.command) ? c.command.join(" ") : c.command;
          const exitStr = c.exit_code !== null ? ("mã thoát: " + c.exit_code) : ("lỗi: " + c.error);
          const stderrPart = c.stderr ? ("\\nSTDERR:\\n" + escapeHtml(c.stderr)) : "";
          return "<strong>$ " + escapeHtml(cmdStr) + "</strong> [" + exitStr + "]\\n" + escapeHtml(c.stdout || "") + stderrPart;
        }).join("\\n---\\n");
      } else {
        logs.style.display = "none";
      }
    }

    function renderReview(rev) {
      const badge = document.getElementById("revStatusBadge");
      const info = document.getElementById("revInfo");
      const box = document.getElementById("revFindings");
      const metricReview = document.getElementById("metricReview");

      if (!rev || !rev.status) {
        badge.className = "step-badge badge-PENDING";
        badge.textContent = "CHỜ";
        metricReview.className = "metric-badge badge-PENDING";
        metricReview.textContent = "CHỜ";
        info.textContent = "Reviewer độc lập chưa kiểm tra nhiệm vụ.";
        box.style.display = "none";
        return;
      }

      const isPass = (rev.status === "PASS");
      badge.className = "step-badge badge-" + (isPass ? "PASS" : "FAILED");
      badge.textContent = isPass ? "ĐẠT" : "CẦN SỬA";
      metricReview.className = "metric-badge badge-" + (isPass ? "PASS" : "FAILED");
      metricReview.textContent = isPass ? "ĐẠT (PASS)" : "CẦN SỬA";
      info.textContent = `Reviewer: ${rev.reviewer || "code_reviewer"} (Bằng chứng: ${rev.evidence || "chưa có"})`;

      if (rev.findings && rev.findings.length > 0) {
        box.style.display = "block";
        box.textContent = rev.findings.join("\\n");
      } else if (isPass) {
        box.style.display = "block";
        box.textContent = "Nghiệm thu: ĐẠT không phát hiện lỗi. Bản đặc tả và tiêu chí chấp nhận đã được thỏa mãn.";
      } else {
        box.style.display = "none";
      }
    }

    function renderFixLoop(fix) {
      const badge = document.getElementById("fixStatusBadge");
      const desc = document.getElementById("fixApproach");
      const p1 = document.getElementById("fixPill1");
      const p2 = document.getElementById("fixPill2");
      const p3 = document.getElementById("fixPill3");
      const metricFix = document.getElementById("metricFix");

      const attempts = fix.attempts || 0;
      badge.textContent = `${attempts} / 3`;
      badge.className = "step-badge badge-" + (fix.status || "PENDING");
      metricFix.textContent = `Vòng ${attempts}/3`;

      [p1, p2, p3].forEach((p, idx) => {
        p.className = "fix-pill";
        const roundNum = idx + 1;
        p.textContent = `Lượt ${roundNum} / 3`;
        if (roundNum < attempts) {
          p.classList.add("done");
        } else if (roundNum === attempts) {
          p.classList.add(fix.status === "BLOCKED" ? "failed" : "current");
        }
      });

      if (fix.current_approach) {
        desc.innerHTML = `<strong>Hướng tiếp cận hiện tại:</strong> ${escapeHtml(fix.current_approach)}`;
      } else if (attempts > 0) {
        desc.textContent = `Đã ghi nhận vòng sửa lỗi ${attempts}/3.`;
      } else {
        desc.textContent = "Chưa kích hoạt vòng sửa lỗi nào.";
      }
    }

    function renderBlocked(blocked) {
      const banner = document.getElementById("blockedBanner");
      if (blocked && blocked.is_blocked) {
        banner.style.display = "flex";
        document.getElementById("blockedReason").textContent = blocked.reason ? `Lý do: ${blocked.reason}` : "Tiến trình bị chặn, chờ quyết định từ con người.";
        document.getElementById("blockedEvidence").textContent = blocked.evidence ? `Tham chiếu: ${blocked.evidence}` : "";
      } else {
        banner.style.display = "none";
      }
    }

    function renderReport(rep) {
      const badge = document.getElementById("repStatusBadge");
      const summary = document.getElementById("repSummary");
      const list = document.getElementById("repCriteriaList");

      if (!rep || (!rep.summary && (!rep.criteria || rep.criteria.length === 0))) {
        badge.className = "step-badge badge-PENDING";
        badge.textContent = "CHỜ";
        summary.textContent = "Đang chờ hoàn tất tất cả các nhiệm vụ.";
        list.innerHTML = "";
        return;
      }

      badge.className = "step-badge badge-COMPLETED";
      badge.textContent = "HOÀN THÀNH";
      summary.textContent = rep.summary || "Toàn bộ nhiệm vụ đã được nghiệm thu và kiểm thử thành công.";
      list.innerHTML = (rep.criteria || []).map(c => `<li>&#10003; ${escapeHtml(c)}</li>`).join("");
    }

    function renderEventTable(events) {
      const tbody = document.getElementById("eventTableBody");
      const badge = document.getElementById("eventCountBadge");
      badge.textContent = `${events.length} Sự kiện`;

      const VN_STATUS_MAP = {
        "PENDING": "CHỜ",
        "RUNNING": "ĐANG CHẠY",
        "COMPLETED": "HOÀN THÀNH",
        "FAILED": "THẤT BẠI",
        "BLOCKED": "BỊ CHẶN",
        "WAITING_HUMAN": "CHỜ DUYỆT",
        "UNKNOWN": "CHƯA RÕ"
      };

      if (!events || events.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" style="text-align: center; color: var(--text-dim);">Chưa có sự kiện nào được ghi nhận.</td></tr>`;
        return;
      }

      const rows = events.slice().reverse().map(ev => {
        const timeStr = formatTime(ev.timestamp);
        const dataSnippet = ev.data && Object.keys(ev.data).length ? JSON.stringify(ev.data).slice(0, 80) : "";
        const vnSt = VN_STATUS_MAP[ev.status] || ev.status;
        return `
          <tr>
            <td>${timeStr}</td>
            <td><span class="badge-source">${ev.source || 'script'}</span></td>
            <td><strong style="color: #fff;">${escapeHtml(ev.event_type)}</strong></td>
            <td>
              <span class="step-badge badge-${ev.status}">${vnSt}</span>
              ${dataSnippet ? `<span style="display: block; color: var(--text-dim); margin-top: 0.25rem;">${escapeHtml(dataSnippet)}</span>` : ''}
            </td>
          </tr>
        `;
      }).join("");
      tbody.innerHTML = rows;
    }

    async function refreshState() {
      try {
        const res = await fetch(`/api/state?project_id=${encodeURIComponent(currentProjectId)}`);
        if (!res.ok) return;
        const state = await res.json();

        // Map stage to Vietnamese for quick metrics bar
        const STAGE_VN_MAP = {
          "raw_prompt": "YÊU CẦU GỐC",
          "read_errors": "ĐỌC LỖI CŨ",
          "interview": "PHỎNG VẤN",
          "diagnosis": "CHẨN ĐOÁN",
          "spec": "ĐẶC TẢ (SPEC)",
          "plan": "KẾ HOẠCH (PLAN)",
          "human_approval": "CHỜ DUYỆT CON NGƯỜI",
          "active": "THỰC THI NHIỆM VỤ",
          "tdd": "LẬP TRÌNH TDD",
          "verification": "KIỂM THỬ ARGV",
          "code_review": "REVIEW ĐỘC LẬP",
          "qa": "QA SẢN PHẨM",
          "fix_loop": "VÒNG SỬA LỖI",
          "main_agent_report": "BÁO CÁO NGHIỆM THU"
        };
        const stageKey = state.current_step_id || "";
        const displayedMode = isDemoRunning ? document.getElementById("demoModeSelect").value : state.mode;
        document.getElementById("metricMode").textContent = displayedMode ? (displayedMode === "bug" ? "Bug Mode" : "Feature Mode") + (isDemoRunning ? " (mô phỏng)" : "") : "Chưa chọn mode";
        document.getElementById("emptyWorkflowNote").style.display = displayedMode ? "none" : "block";
        document.getElementById("metricStage").textContent = stageKey ? (STAGE_VN_MAP[stageKey] || stageKey.replace(/_/g, " ").toUpperCase()) : "CHỜ BẮT ĐẦU";
        document.getElementById("metricTask").textContent = state.active_task_id || "chưa có";
        document.getElementById("metricFingerprint").textContent = (state.verification && state.verification.revision) ? state.verification.revision.slice(0, 8) : "--------";

        // Store latest graph and render SVG Loop Graph
        const graphData = state.graph || {};
        window.latestGraphData = state.mode ? { ...graphData, mode: state.mode } : {
            ...graphData,
            nodes: (graphData.nodes || []).map(node => ({ ...node, is_next: false })),
            active_edges: [],
            mode: null
          };
        if (!isDemoRunning) {
          renderSvgGraph(window.latestGraphData);
        }

        // Also render Stepper view
        renderStepper(state.mode ? (state.steps || []) : [], state.current_step_id);

        renderVerification(state.verification);
        renderReview(state.review);
        renderFixLoop(state.fix_loop || {});
        renderBlocked(state.blocked);
        renderReport(state.report || {});

        const evRes = await fetch(`/api/events?project_id=${encodeURIComponent(currentProjectId)}`);
        if (evRes.ok) {
          const evData = await evRes.json();
          eventsList = evData.events || [];
          if (eventsList.length > 0) {
            lastEventId = eventsList[eventsList.length - 1].event_id;
          }
          renderEventTable(eventsList);
        }
      } catch (err) {
        console.error("refreshState error", err);
      }
    }

    function connectSSE() {
      if (eventSource) {
        eventSource.close();
      }

      updateConnStatus("CONNECTING", "Đang kết nối...");
      const url = `/api/stream?project_id=${encodeURIComponent(currentProjectId)}&last_event_id=${encodeURIComponent(lastEventId)}`;
      eventSource = new EventSource(url);

      eventSource.onopen = () => {
        updateConnStatus("CONNECTED", "Giám sát trực tiếp");
      };

      eventSource.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === "event") {
            const ev = data.event;
            lastEventId = ev.event_id;
            eventsList.push(ev);
            renderEventTable(eventsList);
            refreshState();
          } else if (data.type === "connected" || data.type === "ping") {
            // Heartbeat
          }
        } catch (e) {
          console.error("SSE parse error", e);
        }
      };

      eventSource.onerror = () => {
        updateConnStatus("DISCONNECTED", "Đang kết nối lại...");
      };
    }

    function escapeHtml(str) {
      if (!str) return "";
      return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
    }

    function formatTime(isoStr) {
      if (!isoStr) return "";
      try {
        const d = new Date(isoStr);
        return d.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
      } catch (e) {
        return isoStr;
      }
    }

    let demoTimer = null;
    let isDemoRunning = false;
    const DEMO_STEPS = [
      { step: "raw_prompt", active: "prompt", next: "read_errors", edge: ["prompt->read_errors"], title: "Yêu Cầu Gốc (Prompt)" },
      { step: "read_errors", active: "read_errors", next: "interview", edge: ["read_errors->interview"], title: "Đọc Ký Ức Lỗi Cũ" },
      { step: "interview", active: "interview", next: "proposal", edge: ["interview->proposal"], title: "Phỏng Vấn Làm Rõ" },
      { step: "proposal", active: "proposal", next: "approval", edge: ["proposal->approval"], title: "Lập Đặc Tả & Kế Hoạch" },
      { step: "human_approval", active: "approval", next: "active", edge: ["approval->active"], title: "Cổng Duyệt Con Người" },
      { step: "active", active: "active", next: "tdd", edge: ["active->tdd"], title: "Nhận Nhiệm Vụ (Task Active)" },
      { step: "tdd", active: "tdd", next: "verify", edge: ["tdd->verify"], title: "Lập Trình TDD (Red-Green)" },
      { step: "verify_fail", active: "verify", next: "error_rec", edge: ["verify->error_rec"], title: "Cổng Kiểm Thử (FAIL)" },
      { step: "fix_loop", active: "fix_loop", next: "tdd", edge: ["fix_loop->tdd"], title: "Vòng Sửa Lỗi ↺ (Round 1/3)" },
      { step: "tdd_retry", active: "tdd", next: "verify", edge: ["tdd->verify"], title: "Lập Trình TDD Sửa Lỗi" },
      { step: "verify_pass", active: "verify", next: "review", edge: ["verify->review"], title: "Cổng Kiểm Thử (PASS ĐẠT)" },
       { step: "review", active: "review", next: "qa", edge: ["review->qa"], title: "Review Độc Lập (PASS ĐẠT)" },
       { step: "qa", active: "qa", next: "complete", edge: ["qa->complete"], title: "QA Sản Phẩm (PASS ĐẠT)" },
      { step: "complete", active: "complete", next: "report", edge: ["complete->report"], title: "Nhiệm Vụ Hoàn Tất" },
      { step: "report", active: "report", next: "", edge: [], title: "Báo Cáo Nghiệm Thu Cuối" }
    ];

    function toggleDemoMode() {
      const btn = document.getElementById("btnDemoMode");
      const icon = document.getElementById("demoBtnIcon");
      const txt = document.getElementById("demoBtnText");
      const modeSelect = document.getElementById("demoModeSelect");

      if (isDemoRunning) {
        clearInterval(demoTimer);
        isDemoRunning = false;
        btn.classList.remove("demo-active");
        icon.textContent = "▶";
        txt.textContent = "Thử Nghiệm FX · Mô phỏng UI";
        modeSelect.disabled = false;
        refreshState();
        return;
      }

      isDemoRunning = true;
      btn.classList.add("demo-active");
      icon.textContent = "⏹";
      txt.textContent = "Dừng Mô phỏng UI";
      modeSelect.disabled = true;

      const demoMode = modeSelect.value;
      document.getElementById("metricMode").textContent = (demoMode === "bug" ? "Bug Mode" : "Feature Mode") + " (mô phỏng)";
      document.getElementById("emptyWorkflowNote").style.display = "none";
      const demoSteps = demoMode === "bug" ? DEMO_STEPS.map(item => ({
        ...item,
        step: item.step === "interview" ? "diagnosis" : item.step,
        active: item.active === "interview" ? "diagnosis" : item.active,
        next: item.next === "interview" ? "diagnosis" : item.next,
        edge: item.edge.map(id => id.replace("interview", "diagnosis")),
        title: item.step === "interview" ? "Chẩn Đoán Nguyên Nhân Gốc" : item.title
      })) : DEMO_STEPS;
      let idx = 0;
      function playStep() {
        const item = demoSteps[idx];
        const fakeNodes = Object.keys(NODE_COORDS).filter(id =>
          id !== (demoMode === "bug" ? "interview" : "diagnosis")
        ).map(id => {
          let st = "PENDING";
          if (id === item.active) {
            st = (id === "approval") ? "WAITING_HUMAN" : ((id === "verify" && item.step === "verify_fail") ? "FAILED" : "RUNNING");
          } else if (demoSteps.slice(0, idx).some(s => s.active === id && s.active !== item.active)) {
            st = "COMPLETED";
          }
          return {
            id: id,
            status: st,
            is_active: (id === item.active),
            is_next: (id === item.next)
          };
        });

        renderSvgGraph({
          mode: demoMode,
          nodes: fakeNodes,
          active_edges: item.edge,
          active_node_id: item.active,
          next_node_id: item.next,
          loop_round: (item.step === "fix_loop" ? 1 : 0),
          is_blocked: false
        });

        document.getElementById("metricStage").textContent = item.title;
        idx = (idx + 1) % demoSteps.length;
      }

      playStep();
      demoTimer = setInterval(playStep, 2200);
    }

    window.addEventListener("DOMContentLoaded", loadProjects);
  </script>
</body>
</html>
"""


class ControlCenterHub:
    """Manages active project stores, SSE subscribers, and event broadcasts."""

    def __init__(self, default_root: Path):
        self.default_root = default_root.resolve()
        self.projects: Dict[str, Path] = {}
        self.subscribers: Set[queue.Queue] = set()
        self._lock = threading.Lock()
        self.register_project(self.default_root)

    def register_project(self, root: Path) -> str:
        root = root.resolve()
        pid = detect_project_id(root)
        with self._lock:
            self.projects[pid] = root
        return pid

    def get_root_for_project(self, project_id: Optional[str]) -> Path:
        with self._lock:
            if project_id and project_id in self.projects:
                return self.projects[project_id]
            return self.default_root

    def add_subscriber(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=100)
        with self._lock:
            self.subscribers.add(q)
        return q

    def remove_subscriber(self, q: queue.Queue):
        with self._lock:
            self.subscribers.discard(q)

    def broadcast_event(self, event: VDLEvent):
        with self._lock:
            dead = []
            for q in self.subscribers:
                try:
                    q.put_nowait(event)
                except queue.Full:
                    dead.append(q)
            for d in dead:
                self.subscribers.discard(d)


class ControlCenterHandler(BaseHTTPRequestHandler):
    hub: ControlCenterHub

    def reject_foreign_origin(self):
        origin = self.headers.get("Origin")
        if origin and origin != f"http://127.0.0.1:{self.server.server_port}":
            self.send_error(HTTPStatus.FORBIDDEN, "Foreign origin")
            return True
        return False

    def log_message(self, format, *args):
        # Silence routine access logs; keep stderr clean
        pass

    def send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        if self.reject_foreign_origin():
            return
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        if self.reject_foreign_origin():
            return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/" or path == "/index.html":
            body = HTML_PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/projects":
            with self.hub._lock:
                projs = [{"id": pid, "root": str(root), "is_default": (root == self.hub.default_root)} for pid, root in self.hub.projects.items()]
            self.send_json({"projects": projs})
            return

        if path == "/api/state":
            pid = query.get("project_id", [None])[0]
            root = self.hub.get_root_for_project(pid)
            store = EventStore(root)
            events = store.read_all()
            state = WorkflowStateReducer.reduce(root, events)
            self.send_json(state)
            return

        if path == "/api/events":
            pid = query.get("project_id", [None])[0]
            root = self.hub.get_root_for_project(pid)
            since_id = query.get("since", [None])[0]
            store = EventStore(root)
            events = store.get_events_since(since_id)
            current_pid = detect_project_id(root)
            filtered = [e for e in events if e.project_id in (current_pid, "default", "") or not e.project_id]
            self.send_json({"events": [e.to_dict() for e in filtered]})
            return

        if path == "/api/stream":
            self.handle_sse_stream(query)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def handle_sse_stream(self, query: Dict[str, List[str]]):
        pid = query.get("project_id", [None])[0]
        root = self.hub.get_root_for_project(pid)
        store = EventStore(root)

        last_id = self.headers.get("Last-Event-ID") or query.get("last_event_id", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        # Send immediate initial handshake frame so browser establishes open state instantly
        conn_msg = f":connected\ndata: {json.dumps({'type': 'connected', 'project_id': str(root.name)})}\n\n".encode("utf-8")
        try:
            self.wfile.write(conn_msg)
            self.wfile.flush()
        except Exception:
            return

        # Catch up with missed events if last_id specified
        if last_id:
            missed = store.get_events_since(last_id)
            current_pid = detect_project_id(root)
            for ev in missed:
                if ev.project_id and ev.project_id not in (current_pid, "default"):
                    continue
                payload = json.dumps({"type": "event", "event": ev.to_dict()})
                msg = f"id: {ev.event_id}\ndata: {payload}\n\n".encode("utf-8")
                try:
                    self.wfile.write(msg)
                    self.wfile.flush()
                except Exception:
                    return

        q = self.hub.add_subscriber()
        try:
            while True:
                try:
                    event: VDLEvent = q.get(timeout=15.0)
                    payload = json.dumps({"type": "event", "event": event.to_dict()})
                    msg = f"id: {event.event_id}\ndata: {payload}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
                except queue.Empty:
                    # Heartbeat ping
                    ping = json.dumps({"type": "ping", "time": time.time()})
                    msg = f":ping\ndata: {ping}\n\n".encode("utf-8")
                    self.wfile.write(msg)
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.hub.remove_subscriber(q)

    def do_POST(self):
        if self.reject_foreign_origin():
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/events":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8")
                d = json.loads(body)
                event = VDLEvent.from_dict(d)

                default_pid = detect_project_id(self.hub.default_root)
                # Only write to local file store if event belongs to a registered project or the default project
                if event.project_id in self.hub.projects or event.project_id in (default_pid, "default"):
                    root = self.hub.get_root_for_project(event.project_id)
                    store = EventStore(root)
                    saved_event = store.append(event)
                    self.hub.broadcast_event(saved_event)
                    self.send_json({"ok": True, "event_id": saved_event.event_id}, status=201)
                else:
                    # Ephemeral test event from unregistered temp directory: broadcast without polluting default_root
                    self.hub.broadcast_event(event)
                    self.send_json({"ok": True, "event_id": event.event_id, "ephemeral": True}, status=201)
            except Exception as e:
                self.send_json({"error": str(e)}, status=400)
            return

        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")


def run_server(root: Path, port: int = 4040, host: str = "127.0.0.1", monitor_dirs: Optional[List[Path]] = None):
    hub = ControlCenterHub(default_root=root)
    if monitor_dirs:
        for md in monitor_dirs:
            if md.exists():
                hub.register_project(md)

    class CustomServer(ThreadingHTTPServer):
        daemon_threads = True

    ControlCenterHandler.hub = hub
    server = CustomServer((host, port), ControlCenterHandler)
    print(f"VDL Control Center running on http://{host}:{port}")
    print(f"Monitoring default project: {root.name} ({root})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main():
    parser = argparse.ArgumentParser(description="VDL Control Center Real-Time Monitoring Server")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Default repository root to monitor")
    parser.add_argument("--port", type=int, default=4040, help="Port to run HTTP & SSE server on (default: 4040)")
    parser.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--monitor", type=Path, action="append", default=[], help="Additional repository roots to monitor")
    args = parser.parse_args()

    run_server(args.root.resolve(), port=args.port, host=args.host, monitor_dirs=args.monitor)


if __name__ == "__main__":
    main()
