"""
HumanType — Realistic Human Typing Simulator

Features:
  - Type tab: paste text, it types it out with human-like rhythm
  - Replace tab: paste CURRENT text + DESIRED text, position cursor at
    the start, and it diffs + edits in-place like a human would.
    No clipboard gymnastics — just paste both boxes and go.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import time
import random
import math
import difflib
import json
import os

from pynput.keyboard import Controller, Key

keyboard = Controller()

import sys

if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, 'config.json')


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(data):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception:
        pass


# QWERTY neighbour map for realistic typos
NEIGHBORS = {
    'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'serfcx',
    'e': 'wrds34', 'f': 'drtgvc', 'g': 'ftyh bv', 'h': 'gyujnb',
    'i': 'uokj89', 'j': 'huiknm', 'k': 'jiolm', 'l': 'kop;',
    'm': 'njk,', 'n': 'bhjm', 'o': 'iplk90', 'p': 'ol[0',
    'q': 'wa12', 'r': 'etfd45', 's': 'awedxz', 't': 'rygf56',
    'u': 'yijh78', 'v': 'cfgb', 'w': 'qesa23', 'x': 'zsdc',
    'y': 'tuhg67', 'z': 'asx',
}


def gaussian(mean, stddev):
    u1 = max(1e-10, random.random())
    u2 = random.random()
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    return mean + z * stddev


def get_typo_char(ch):
    lower = ch.lower()
    neighbors = NEIGHBORS.get(lower)
    if neighbors:
        pick = random.choice([c for c in neighbors if c.strip()])
        return pick.upper() if ch.isupper() else pick
    pick = random.choice('abcdefghijklmnopqrstuvwxyz')
    return pick.upper() if ch.isupper() else pick


def get_typo_percent(typo_var):
    v = typo_var.get()
    if v < -3.0:
        return 0.0
    return 10 ** v


class LenientChar:
    """Character wrapper that supports case-insensitive / newline-normalised diffing."""
    def __init__(self, char, case_sensitive, norm_newlines):
        self.char = char
        self.case_sensitive = case_sensitive
        self.norm_newlines = norm_newlines

    def __eq__(self, other):
        if not isinstance(other, LenientChar):
            return False
        c1, c2 = self.char, other.char
        if self.norm_newlines and c1 == '\n' and c2 == '\n':
            return True
        if not self.case_sensitive:
            return c1.lower() == c2.lower()
        return c1 == c2

    def __hash__(self):
        if self.norm_newlines and self.char == '\n':
            return hash('\n')
        if not self.case_sensitive:
            return hash(self.char.lower())
        return hash(self.char)


# Colour palette
BG         = '#0d0d14'
BG_PANEL   = '#14141f'
BG_INPUT   = '#0a0a12'
FG         = '#d8d8e8'
FG_DIM     = '#6e6e88'
ACCENT     = '#a78bfa'
ACCENT_DIM = '#7c6bc4'
RED        = '#f87171'
GREEN      = '#34d399'
YELLOW     = '#fbbf24'
BORDER     = '#22223a'
CYAN       = '#22d3ee'


class HumanTypeApp:
    def __init__(self, root):
        self.root = root
        self.root.title('HumanType')
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.root.minsize(980, 640)
        self.root.geometry('980x720')

        try:
            self.root.iconbitmap(default='')
        except Exception:
            pass

        # --- shared state ---
        self.typing   = False
        self.paused   = False
        self.stop_flag = False
        self.stats    = {'chars': 0, 'typos': 0, 'corrections': 0}

        # resume pointers
        self.resume_type_idx            = 0
        self.resume_replace_opcode_idx  = 0
        self.resume_replace_opcodes     = None
        self.resume_replace_target_clean  = None
        self.resume_replace_original_clean = None

        self.esc_times      = []
        self._in_countdown  = False
        self._active_mode   = 'type'

        # listeners
        from pynput.keyboard import Listener
        self.esc_listener = Listener(on_press=self._on_global_press)
        self.esc_listener.start()

        from pynput.mouse import Listener as MouseListener
        self.mouse_listener = MouseListener(on_click=self._on_global_click)
        self.mouse_listener.start()

        self.type_widgets    = {}
        self.replace_widgets = {}
        self.fake_widgets    = {}

        self._build_styles()
        self._build_ui()
        self._load_state()

    # ------------------------------------------------------------------ styles
    def _build_styles(self):
        s = ttk.Style()
        s.theme_use('clam')
        s.configure('.', background=BG, foreground=FG, font=('Segoe UI', 10))
        s.configure('TFrame',    background=BG)
        s.configure('TLabel',    background=BG, foreground=FG, font=('Segoe UI', 10))
        s.configure('Dim.TLabel',    foreground=FG_DIM,  font=('Segoe UI', 9))
        s.configure('Hint.TLabel',   foreground='#6e6e9b', font=('Segoe UI', 8, 'italic'))
        s.configure('Title.TLabel',  foreground=FG,      font=('Segoe UI', 16, 'bold'))
        s.configure('Accent.TLabel', foreground=ACCENT,  font=('Segoe UI', 10, 'bold'))
        s.configure('Cyan.TLabel',   foreground=CYAN,    font=('Segoe UI', 10, 'bold'))
        s.configure('Status.TLabel', foreground=FG_DIM,  font=('Consolas', 9), background=BG_PANEL)
        s.configure('TScale', background=BG, troughcolor=BORDER, sliderthickness=16)
        s.configure('TNotebook',     background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=BG_PANEL, foreground=FG_DIM,
                    font=('Segoe UI', 10, 'bold'), padding=(16, 6))
        s.map('TNotebook.Tab', background=[('selected', BG)], foreground=[('selected', FG)])
        s.configure('Accent.TButton',  background=ACCENT,    foreground='white',
                    font=('Segoe UI', 11, 'bold'), padding=(16, 8))
        s.map('Accent.TButton',
              background=[('active', ACCENT_DIM), ('disabled', '#3a3a55')])
        s.configure('Cyan.TButton',    background='#0e7490', foreground='white',
                    font=('Segoe UI', 11, 'bold'), padding=(16, 8))
        s.map('Cyan.TButton',
              background=[('active', '#155e75'), ('disabled', '#3a3a55')])
        s.configure('Secondary.TButton', background=BG_PANEL, foreground=FG_DIM,
                    font=('Segoe UI', 10), padding=(12, 6), relief='flat')
        s.map('Secondary.TButton', background=[('active', BORDER)])
        s.configure('Danger.TButton',  background='#2a1515', foreground=RED,
                    font=('Segoe UI', 10), padding=(12, 6), relief='flat')
        s.map('Danger.TButton', background=[('active', '#3a2020')])
        s.configure('Cyan.TCheckbutton', foreground=FG, background=BG, font=('Segoe UI', 9))
        s.map('Cyan.TCheckbutton', foreground=[('active', CYAN)], background=[('active', BG)])

    # ------------------------------------------------------------------ settings panel (shared)
    def _create_settings_panel(self, parent, defaults=None):
        d = defaults or {}
        defaults_full = {
            'speed':     d.get('speed', 55),
            'variation': d.get('variation', 40),
            'typo_log':  d.get('typo_log', 0.77815),
            'pause':     d.get('pause', 12),
            'pause_dur': d.get('pause_dur', 1200),
            'countdown': d.get('countdown', 5),
        }

        wrap = ttk.Frame(parent)
        wrap.pack(fill='both', expand=True, pady=(0, 8))

        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        canvas.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(wrap, orient='vertical', command=canvas.yview)
        sb.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=sb.set)

        inner = ttk.Frame(canvas)
        win   = canvas.create_window((0, 0), window=inner, anchor='nw')

        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win, width=e.width))

        def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _mw))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        refs = {}

        def slider_row(label, from_, to, var_cls, default, fmt_fn, hint=''):
            row = ttk.Frame(inner, padding=(0, 4))
            row.pack(fill='x', pady=2)
            hdr = ttk.Frame(row); hdr.pack(fill='x')
            ttk.Label(hdr, text=label, style='Accent.TLabel').pack(side='left')
            lbl = ttk.Label(hdr, text=fmt_fn(default), style='Dim.TLabel')
            lbl.pack(side='right')
            var = var_cls(value=default)
            def cb(_, v=var, l=lbl, fn=fmt_fn): l.config(text=fn(v.get()))
            sc = ttk.Scale(row, from_=from_, to=to, variable=var,
                           orient='horizontal', command=cb)
            sc.pack(fill='x', pady=(2, 2))
            sc.bind('<ButtonRelease-1>', lambda e: self.root.after(50, self._save_state))
            if hint:
                ttk.Label(row, text=hint, style='Hint.TLabel').pack(anchor='w')
            return var, lbl

        v, l = slider_row('Typing Speed', 10, 180, tk.IntVar,
                          defaults_full['speed'],
                          lambda x: f'{int(x)} WPM',
                          'Base target speed. Delay varies dynamically per character.')
        refs['speed_var'] = v; refs['speed_label'] = l

        v, l = slider_row('Speed Variation', 0, 100, tk.IntVar,
                          defaults_full['variation'],
                          lambda x: f'{int(x)}%',
                          'Random timing variation. Higher = more human-like erratic flow.')
        refs['variation_var'] = v; refs['variation_label'] = l

        v, l = slider_row('Error Rate (Typos)', -3.05, 1.477, tk.DoubleVar,
                          defaults_full['typo_log'],
                          lambda x: ('Off (0%)' if x < -3.0 else
                                     f'{10**x:.3f}%' if 10**x < 0.1 else
                                     f'{10**x:.2f}%' if 10**x < 1.0 else
                                     f'{10**x:.1f}%'),
                          'Logarithmic: 0% to 30%. Drag left for extreme precision.')
        refs['typo_var'] = v; refs['typo_label'] = l

        v, l = slider_row('Natural Think Pauses', 0, 50, tk.IntVar,
                          defaults_full['pause'],
                          lambda x: f'{int(x)}%',
                          'Chance to pause at punctuation, word boundaries, or newlines.')
        refs['pause_var'] = v; refs['pause_label'] = l

        v, l = slider_row('Think Pause Length', 300, 5000, tk.IntVar,
                          defaults_full['pause_dur'],
                          lambda x: f'{int(x)/1000:.1f}s',
                          'Average duration of each thinking pause. Responsive — won\'t freeze.')
        refs['pause_dur_var'] = v; refs['pause_dur_label'] = l

        v, l = slider_row('Start Countdown Delay', 2, 15, tk.IntVar,
                          defaults_full['countdown'],
                          lambda x: f'{int(x)}s',
                          'Time to click your target field before action starts.')
        refs['countdown_var'] = v; refs['countdown_label'] = l

        return refs

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        container = ttk.Frame(self.root, padding=(20, 12, 20, 12))
        container.pack(fill='both', expand=True)

        hdr = ttk.Frame(container)
        hdr.pack(fill='x', pady=(0, 8))
        ttk.Label(hdr, text='HumanType', style='Title.TLabel').pack(side='left')
        ttk.Label(hdr, text='Realistic keystroke simulator',
                  style='Dim.TLabel').pack(side='left', padx=(12, 0))

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill='both', expand=True, pady=(0, 4))

        type_tab    = ttk.Frame(self.notebook)
        replace_tab = ttk.Frame(self.notebook)
        fake_tab    = ttk.Frame(self.notebook)
        help_tab    = ttk.Frame(self.notebook)
        self.notebook.add(type_tab,    text='  Type  ')
        self.notebook.add(replace_tab, text='  Replace  ')
        self.notebook.add(fake_tab,    text='  Fake Typing  ')
        self.notebook.add(help_tab,    text='  Help  ')

        self._build_type_tab(type_tab)
        self._build_replace_tab(replace_tab)
        self._build_fake_tab(fake_tab)
        self._build_help_tab(help_tab)

        bar = tk.Frame(container, bg=BG_PANEL, highlightthickness=1,
                       highlightbackground=BORDER, padx=12, pady=8)
        bar.pack(fill='x', pady=(4, 0))
        self.status_label = ttk.Label(bar, text='Ready — paste text and hit Start',
                                      style='Status.TLabel')
        self.status_label.pack(side='left')
        self.stats_label = ttk.Label(bar, text='Chars: 0  |  Typos: 0  |  Fixes: 0',
                                     style='Status.TLabel')
        self.stats_label.pack(side='right')

    # ------------------------------------------------------------------ Type tab
    def _build_type_tab(self, parent):
        w = self.type_widgets
        split = ttk.Frame(parent)
        split.pack(fill='both', expand=True, pady=8, padx=4)

        left = ttk.Frame(split)
        left.pack(side='left', fill='both', expand=True, padx=(0, 10))
        ttk.Label(left, text='Text to type:', style='Accent.TLabel').pack(anchor='w', pady=(0, 4))
        w['text_input'] = scrolledtext.ScrolledText(
            left, wrap='word', bg=BG_INPUT, fg=FG, insertbackground=ACCENT,
            font=('Consolas', 10), relief='flat', bd=0,
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER,
            padx=10, pady=8, selectbackground=ACCENT_DIM, selectforeground='white')
        w['text_input'].pack(fill='both', expand=True)
        w['text_input'].bind('<KeyRelease>', self._on_text_change)

        right = ttk.Frame(split, width=340)
        right.pack(side='right', fill='both', padx=(10, 0))
        right.pack_propagate(False)
        w['settings'] = self._create_settings_panel(right)

        btns = ttk.Frame(right)
        btns.pack(fill='x', pady=(8, 0))
        w['start_btn'] = ttk.Button(btns, text='Start Typing', style='Accent.TButton',
                                    command=self._start_type)
        w['start_btn'].pack(side='left', fill='x', expand=True, padx=(0, 4))
        w['pause_btn'] = ttk.Button(btns, text='Pause', style='Secondary.TButton',
                                    command=lambda: self._toggle_pause('type'), state='disabled')
        w['pause_btn'].pack(side='left', padx=4)
        w['stop_btn'] = ttk.Button(btns, text='Stop', style='Danger.TButton',
                                   command=self._stop, state='disabled')
        w['stop_btn'].pack(side='left', padx=(4, 0))

    # ------------------------------------------------------------------ Replace tab
    def _build_replace_tab(self, parent):
        w = self.replace_widgets
        split = ttk.Frame(parent)
        split.pack(fill='both', expand=True, pady=8, padx=4)

        # Left: two stacked text boxes
        left = ttk.Frame(split)
        left.pack(side='left', fill='both', expand=True, padx=(0, 10))

        ttk.Label(left, text='Current text  (paste exactly what the editor has right now):',
                  style='Dim.TLabel').pack(anchor='w', pady=(0, 4))
        w['original_input'] = scrolledtext.ScrolledText(
            left, wrap='word', bg=BG_INPUT, fg=FG, insertbackground=FG_DIM,
            font=('Consolas', 10), relief='flat', bd=0,
            highlightthickness=1, highlightcolor=BORDER, highlightbackground=BORDER,
            padx=10, pady=8, selectbackground=ACCENT_DIM, selectforeground='white',
            height=9)
        w['original_input'].pack(fill='both', expand=True, pady=(0, 8))
        w['original_input'].bind('<KeyRelease>', self._on_text_change)

        ttk.Label(left, text='Desired text  (what you want it to say):',
                  style='Cyan.TLabel').pack(anchor='w', pady=(0, 4))
        w['text_input'] = scrolledtext.ScrolledText(
            left, wrap='word', bg=BG_INPUT, fg=FG, insertbackground=CYAN,
            font=('Consolas', 10), relief='flat', bd=0,
            highlightthickness=1, highlightcolor=CYAN, highlightbackground=BORDER,
            padx=10, pady=8, selectbackground='#155e75', selectforeground='white',
            height=9)
        w['text_input'].pack(fill='both', expand=True)
        w['text_input'].bind('<KeyRelease>', self._on_text_change)

        # Right: options + settings + buttons
        right = ttk.Frame(split, width=340)
        right.pack(side='right', fill='both', padx=(10, 0))
        right.pack_propagate(False)

        opts = ttk.Frame(right)
        opts.pack(fill='x', pady=(0, 8))
        ttk.Label(opts, text='Leniency & Formatting:', style='Cyan.TLabel').pack(anchor='w', pady=(0, 4))

        w['case_sensitive_var']         = tk.BooleanVar(value=True)
        w['norm_newlines_var']          = tk.BooleanVar(value=True)
        w['double_enter_var']           = tk.BooleanVar(value=True)
        w['double_enter_threshold_var'] = tk.IntVar(value=15)
        w['fast_nav_var']               = tk.BooleanVar(value=False)

        chks = ttk.Frame(opts); chks.pack(fill='x')
        for text, var in [
            ('Case Sensitive',               'case_sensitive_var'),
            ('Consider all \\n the same',    'norm_newlines_var'),
            ('Double Enter on large inserts','double_enter_var'),
            ('Fast word nav (Ctrl+Arrow)',   'fast_nav_var'),
        ]:
            ttk.Checkbutton(chks, text=text, variable=w[var],
                            style='Cyan.TCheckbutton',
                            command=self._save_state).pack(anchor='w', pady=1)

        sf = ttk.Frame(opts); sf.pack(fill='x', pady=(6, 0))
        ttk.Label(sf, text='Spacer Threshold:', style='Dim.TLabel').pack(side='left', padx=(0, 6))
        tlbl = ttk.Label(sf, text='15 chars', style='Dim.TLabel')
        w['double_enter_threshold_label'] = tlbl
        def _thresh(_, v=w['double_enter_threshold_var'], l=tlbl):
            l.config(text=f'{v.get()} chars')
        tsc = ttk.Scale(sf, from_=1, to=100,
                        variable=w['double_enter_threshold_var'],
                        orient='horizontal', command=_thresh)
        tsc.pack(side='left', fill='x', expand=True, padx=(4, 6))
        tsc.bind('<ButtonRelease-1>', lambda e: self.root.after(50, self._save_state))
        tlbl.pack(side='right')

        w['settings'] = self._create_settings_panel(right, defaults={
            'speed': 45, 'variation': 35, 'typo_log': -0.22185,
            'pause': 18, 'pause_dur': 1500, 'countdown': 6,
        })

        # Hint above buttons
        ttk.Label(right,
                  text='Position cursor at the START of the current text before clicking Start.',
                  style='Hint.TLabel').pack(anchor='w', pady=(2, 4))

        btns = ttk.Frame(right)
        btns.pack(fill='x')
        w['start_btn'] = ttk.Button(btns, text='Start Replace', style='Cyan.TButton',
                                    command=self._start_replace)
        w['start_btn'].pack(side='left', fill='x', expand=True, padx=(0, 4))
        w['pause_btn'] = ttk.Button(btns, text='Pause', style='Secondary.TButton',
                                    command=lambda: self._toggle_pause('replace'), state='disabled')
        w['pause_btn'].pack(side='left', padx=4)
        w['stop_btn'] = ttk.Button(btns, text='Stop', style='Danger.TButton',
                                   command=self._stop, state='disabled')
        w['stop_btn'].pack(side='left', padx=(4, 0))

    # ------------------------------------------------------------------ Help tab
    def _build_help_tab(self, parent):
        wrap = ttk.Frame(parent)
        wrap.pack(fill='both', expand=True, pady=8, padx=4)
        canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        canvas.pack(side='left', fill='both', expand=True)
        sb = ttk.Scrollbar(wrap, orient='vertical', command=canvas.yview)
        sb.pack(side='right', fill='y')
        canvas.configure(yscrollcommand=sb.set)
        inner = ttk.Frame(canvas)
        win = canvas.create_window((0, 0), window=inner, anchor='nw')
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(win, width=e.width))
        def _mw(e): canvas.yview_scroll(int(-1*(e.delta/120)), 'units')
        canvas.bind('<Enter>', lambda e: canvas.bind_all('<MouseWheel>', _mw))
        canvas.bind('<Leave>', lambda e: canvas.unbind_all('<MouseWheel>'))

        def H(t, c=CYAN):
            ttk.Label(inner, text=t, font=('Segoe UI', 11, 'bold'),
                      foreground=c).pack(anchor='w', pady=(12, 4))
        def B(t):
            ttk.Label(inner, text=t, font=('Segoe UI', 9),
                      wraplength=500, justify='left').pack(anchor='w', pady=(0, 8))

        H('Type Tab:', ACCENT)
        B('1. Paste or write your text in the box.\n'
          '2. Click "Start Typing".\n'
          '3. Switch to your target app during the countdown.\n'
          '4. The app types character-by-character with realistic speed, variation and pauses.\n'
          '   Think pauses are fully responsive — pressing Stop during a pause stops immediately.')

        H('Replace Tab:', CYAN)
        B('1. Paste the CURRENT text (what is in your editor right now) into the top box.\n'
          '2. Paste the DESIRED text (what you want it to say) into the bottom box.\n'
          '3. In your editor, position your cursor at the very START of the current text.\n'
          '4. Click "Start Replace" — the app Alt-Tabs to your editor and starts the countdown.\n'
          '5. The app diffs the two texts and makes only the necessary edits in-place.\n\n'
          'No clipboard selection needed — just paste both boxes and position your cursor.')

        H('Keyboard Shortcuts & Safety:', YELLOW)
        B('ESC (once)    — instantly stops, saves progress, minimises the app.\n'
          'ESC (3x fast) — de-minimises, switches focus back, resumes from where it stopped.\n'
          'Accidental click guard — clicking outside HumanType while typing immediately pauses.\n'
          '                         Hit Resume (or ESC ×3) to continue.')

        H('Sliders:')
        B('Typing Speed      — baseline WPM target.\n'
          'Speed Variation   — how erratic/human the rhythm feels.\n'
          'Error Rate        — logarithmic typo probability (0% – 30%).\n'
          'Natural Pauses    — chance of pausing at punctuation or word boundaries.\n'
          'Think Pause Length — average pause duration. Interruption-safe: stops/pauses\n'
          '                     respond within ~80ms even during a long pause.\n'
          'Start Countdown   — seconds to switch to your target field before typing begins.')

    # ------------------------------------------------------------------ state
    def _on_text_change(self, event=None):
        self.resume_type_idx              = 0
        self.resume_replace_opcode_idx    = 0
        self.resume_replace_opcodes       = None
        self.resume_replace_target_clean  = None
        self.resume_replace_original_clean = None
        self.type_widgets['start_btn'].config(text='Start Typing')
        self.replace_widgets['start_btn'].config(text='Start Replace')
        try: self.fake_widgets['start_btn'].config(text='Start Fake Typing')
        except Exception: pass
        self._save_state()

    def _save_state(self):
        cfg = {}
        try: cfg['type_text']        = self.type_widgets['text_input'].get('1.0', 'end').strip()
        except Exception: pass
        try: cfg['replace_original'] = self.replace_widgets['original_input'].get('1.0', 'end').strip()
        except Exception: pass
        try: cfg['replace_text']     = self.replace_widgets['text_input'].get('1.0', 'end').strip()
        except Exception: pass
        try: cfg['fake_text']        = self.fake_widgets['text_input'].get('1.0', 'end').strip()
        except Exception: pass
        try: cfg['fake_chars_per_keystroke'] = self.fake_widgets['chars_per_keystroke_var'].get()
        except Exception: pass

        def get_s(refs):
            return {k: refs[f'{k}_var'].get()
                    for k in ('speed','variation','typo_log','pause','pause_dur','countdown')
                    if f'{k}_var' in refs}
        try: cfg['type_settings']    = get_s(self.type_widgets['settings'])
        except Exception: pass
        try: cfg['replace_settings'] = get_s(self.replace_widgets['settings'])
        except Exception: pass

        try:
            rw = self.replace_widgets
            cfg.update({
                'case_sensitive':         rw['case_sensitive_var'].get(),
                'norm_newlines':          rw['norm_newlines_var'].get(),
                'double_enter':           rw['double_enter_var'].get(),
                'double_enter_threshold': rw['double_enter_threshold_var'].get(),
                'fast_nav':               rw['fast_nav_var'].get(),
            })
        except Exception: pass
        save_config(cfg)

    def _load_state(self):
        cfg = load_config()
        if not cfg:
            return

        def ins(widget, key):
            if key in cfg and cfg[key]:
                widget.delete('1.0', 'end')
                widget.insert('1.0', cfg[key])

        ins(self.type_widgets['text_input'],       'type_text')
        ins(self.replace_widgets['original_input'], 'replace_original')
        ins(self.replace_widgets['text_input'],    'replace_text')
        ins(self.fake_widgets['text_input'],       'fake_text')

        try:
            if 'fake_chars_per_keystroke' in cfg:
                self.fake_widgets['chars_per_keystroke_var'].set(cfg['fake_chars_per_keystroke'])
                self.fake_widgets['chars_per_keystroke_label'].config(text=str(int(cfg['fake_chars_per_keystroke'])))
                self.fake_chars_per_keystroke = int(cfg['fake_chars_per_keystroke'])
        except Exception: pass

        def set_s(refs, d):
            if not d: return
            mapping = {'speed':'speed_var','variation':'variation_var','typo_log':'typo_var',
                       'pause':'pause_var','pause_dur':'pause_dur_var','countdown':'countdown_var'}
            for k, vn in mapping.items():
                if k in d: refs[vn].set(d[k])
            # Refresh labels
            refs['speed_label'].config(text=f"{int(refs['speed_var'].get())} WPM")
            refs['variation_label'].config(text=f"{int(refs['variation_var'].get())}%")
            pct = get_typo_percent(refs['typo_var'])
            refs['typo_label'].config(text='Off (0%)' if pct==0 else
                                      f'{pct:.3f}%' if pct<0.1 else
                                      f'{pct:.2f}%' if pct<1.0 else f'{pct:.1f}%')
            refs['pause_label'].config(text=f"{int(refs['pause_var'].get())}%")
            refs['pause_dur_label'].config(text=f"{int(refs['pause_dur_var'].get())/1000:.1f}s")
            refs['countdown_label'].config(text=f"{int(refs['countdown_var'].get())}s")

        try: set_s(self.type_widgets['settings'],    cfg.get('type_settings'))
        except Exception: pass
        try: set_s(self.replace_widgets['settings'], cfg.get('replace_settings'))
        except Exception: pass

        try:
            rw = self.replace_widgets
            for k, vk in [('case_sensitive','case_sensitive_var'),
                           ('norm_newlines','norm_newlines_var'),
                           ('double_enter','double_enter_var'),
                           ('fast_nav','fast_nav_var')]:
                if k in cfg: rw[vk].set(cfg[k])
            if 'double_enter_threshold' in cfg:
                rw['double_enter_threshold_var'].set(cfg['double_enter_threshold'])
                rw['double_enter_threshold_label'].config(text=f"{cfg['double_enter_threshold']} chars")
        except Exception: pass

    # ------------------------------------------------------------------ global listeners
    def _on_global_press(self, key):
        if self._active_mode == 'fake':
            return
        if key != Key.esc:
            return
        now = time.time()
        self.esc_times = (self.esc_times + [now])[-3:]
        if len(self.esc_times) == 3 and self.esc_times[2] - self.esc_times[0] < 0.8:
            self.esc_times = []
            self.root.after(0, self._quick_resume)
            return
        if self.typing:
            self.root.after(0, self._handle_esc_stop)

    def _handle_esc_stop(self):
        if self.typing:
            self.stop_flag = True
            self.root.iconify()
            self._set_status('Stopped (Esc — progress saved)', RED)

    def _on_global_click(self, x, y, button, pressed):
        if self._active_mode == 'fake':
            return
        if not (pressed and self.typing and not self.paused):
            return
        try:
            wx, wy = self.root.winfo_rootx(), self.root.winfo_rooty()
            ww, wh = self.root.winfo_width(), self.root.winfo_height()
            if wx <= x <= wx + ww and wy <= y <= wy + wh:
                return
        except Exception:
            pass
        if self._in_countdown:
            return
        self.root.after(0, self._handle_click_pause)

    def _handle_click_pause(self):
        if self.typing and not self.paused:
            self.paused = True
            w = self._get_active_widgets()
            w['pause_btn'].config(text='Resume')
            self._set_status('Accidental click! Click back at your cursor and hit Resume.', YELLOW)

    def _quick_resume(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        if self.typing and self.paused:
            self._toggle_pause()
            return
        if not self.typing:
            tab = self.notebook.index(self.notebook.select())
            if tab == 0 and self.resume_type_idx > 0:
                self._start_type()
            elif tab == 1 and self.resume_replace_opcodes and self.resume_replace_opcode_idx > 0:
                self._start_replace()

    # ------------------------------------------------------------------ start / pause / stop
    def _get_active_widgets(self):
        idx = self.notebook.index(self.notebook.select())
        if idx == 0: return self.type_widgets
        elif idx == 1: return self.replace_widgets
        elif idx == 2: return self.fake_widgets
        else: return None

    def _set_status(self, text, color=FG_DIM):
        self.status_label.config(text=text, foreground=color)

    def _update_stats(self):
        s = self.stats
        self.stats_label.config(
            text=f"Chars: {s['chars']}  |  Typos: {s['typos']}  |  Fixes: {s['corrections']}")

    def _start_type(self):
        w = self.type_widgets
        text = w['text_input'].get('1.0', 'end').strip()
        if not text:
            self._set_status('No text entered!', RED)
            return
        self.typing    = True
        self.paused    = False
        self.stop_flag = False
        self.stats     = {'chars': 0, 'typos': 0, 'corrections': 0}
        self._update_stats()
        self._active_mode = 'type'
        w['start_btn'].config(state='disabled')
        w['pause_btn'].config(state='normal')
        w['stop_btn'].config(state='normal')
        w['text_input'].config(state='disabled')
        threading.Thread(target=self._typing_thread,
                         args=(text, w['settings']), daemon=True).start()

    def _start_replace(self):
        w = self.replace_widgets
        original_text = w['original_input'].get('1.0', 'end').strip()
        target_text   = w['text_input'].get('1.0', 'end').strip()
        if not original_text:
            self._set_status('Paste the CURRENT text (top box) first!', RED)
            return
        if not target_text:
            self._set_status('Paste the DESIRED text (bottom box) first!', RED)
            return
        self.typing    = True
        self.paused    = False
        self.stop_flag = False
        self.stats     = {'chars': 0, 'typos': 0, 'corrections': 0}
        self._update_stats()
        self._active_mode = 'replace'
        w['start_btn'].config(state='disabled')
        w['pause_btn'].config(state='normal')
        w['stop_btn'].config(state='normal')
        w['text_input'].config(state='disabled')
        w['original_input'].config(state='disabled')
        threading.Thread(target=self._replace_thread,
                         args=(original_text, target_text, w['settings']), daemon=True).start()

    def _toggle_pause(self, mode=None):
        self.paused = not self.paused
        w = self._get_active_widgets()
        if self.paused:
            w['pause_btn'].config(text='Resume')
            self._set_status('Paused', YELLOW)
        else:
            w['pause_btn'].config(text='Pause')
            self._set_status('Replacing...' if self._active_mode == 'replace' else 'Typing...',
                             CYAN if self._active_mode == 'replace' else ACCENT)

    def _stop(self):
        self.stop_flag = True

    def _finish(self, completed=True):
        if not self.typing:
            return                          # guard against double-call
        self.typing = False
        w = self.type_widgets if self._active_mode == 'type' else self.replace_widgets
        self.root.after(0, lambda: w['start_btn'].config(state='normal'))
        self.root.after(0, lambda: w['pause_btn'].config(state='disabled', text='Pause'))
        self.root.after(0, lambda: w['stop_btn'].config(state='disabled'))
        self.root.after(0, lambda: w['text_input'].config(state='normal'))
        if self._active_mode == 'replace':
            self.root.after(0, lambda: w['original_input'].config(state='normal'))
        self.root.after(0, lambda: self._set_status('Done!' if completed else 'Stopped',
                                                     GREEN if completed else RED))

    # ------------------------------------------------------------------ thread helpers
    def _check_stop(self):
        """Returns True (and calls _finish) if stop was requested."""
        if self.stop_flag:
            self._finish(False)
            return True
        return False

    def _wait_pause(self):
        """Block in 50ms ticks while paused. Returns True if stopped during wait."""
        was_paused = False
        while self.paused and not self.stop_flag:
            was_paused = True
            time.sleep(0.05)
        if was_paused and not self.stop_flag:
            self._perform_alt_tab()
            if self._active_mode == 'type':
                text = self.type_widgets['text_input'].get('1.0', 'end').strip()
                self.resume_type_idx = self._sync_typing_index(text, self.resume_type_idx)
        return self.stop_flag

    def _read_settings(self, settings):
        wpm        = settings['speed_var'].get()
        base_delay = 60 / (wpm * 5)
        variation  = settings['variation_var'].get() / 100
        typo_rate  = get_typo_percent(settings['typo_var']) / 100
        pause_rate = settings['pause_var'].get() / 100
        pause_dur  = settings['pause_dur_var'].get() / 1000
        return base_delay, variation, typo_rate, pause_rate, pause_dur

    def _do_countdown(self, settings, msg='Click your target field!'):
        n = settings['countdown_var'].get()
        self._in_countdown = True
        for i in range(n, 0, -1):
            if self.stop_flag:
                self._in_countdown = False
                return True
            self.root.after(0, lambda s=i: self._set_status(f'{msg}  Starting in {s}...', YELLOW))
            time.sleep(1)
        self._in_countdown = False
        return False

    def _do_think_pause(self, ch, i, text, pause_rate, pause_dur):
        """
        Optionally sleep to simulate a 'thinking' pause.
        Sleeps in 80ms chunks — stops and pauses respond immediately.
        Returns True if the thread should abort (stop was requested).
        Returns False if typing can continue normally.
        Returns "resumed" if it was paused and then resumed.
        """
        at_word_boundary = (ch == ' ' or i == 0)
        after_punct      = (i > 0 and text[i - 1] in '.!?,;:')
        at_newline       = (ch == '\n')

        should_pause = False
        if at_newline:
            should_pause = random.random() < 0.55
        elif after_punct:
            should_pause = random.random() < min(pause_rate * 2.5, 0.7)
        elif at_word_boundary:
            should_pause = random.random() < pause_rate

        if not should_pause:
            return False

        pause_time = max(0.15, gaussian(pause_dur, pause_dur * 0.4))
        pause_time = min(pause_time, pause_dur * 3)

        self.root.after(0, lambda: self._set_status('Thinking...', FG_DIM))

        # Chunked sleep — fully responsive to stop/pause
        elapsed = 0.0
        chunk   = 0.08
        was_paused = False
        while elapsed < pause_time:
            time.sleep(min(chunk, pause_time - elapsed))
            elapsed += chunk

            if self.stop_flag:
                return True          # caller must call _finish

            if self.paused:
                was_paused = True
                self.root.after(0, lambda: self._set_status('Paused', YELLOW))
                while self.paused and not self.stop_flag:
                    time.sleep(0.05)
                if self.stop_flag:
                    return True      # caller must call _finish
                # resumed — break out of think pause and continue typing immediately
                break

        if was_paused and not self.stop_flag:
            self._perform_alt_tab()
            if self._active_mode == 'type':
                self.resume_type_idx = self._sync_typing_index(text, self.resume_type_idx)
            return "resumed"

        mode = self._active_mode
        self.root.after(0, lambda: self._set_status(
            'Replacing...' if mode == 'replace' else 'Typing...',
            CYAN if mode == 'replace' else ACCENT))
        return False

    def _type_char_human(self, ch, base_delay, variation, typo_rate, i, text, settings):
        """
        Type one character with human-like behaviour.
        Returns 1 (advance index), or -1 if stopped.
        """
        should_typo = ch.isalpha() and random.random() < typo_rate

        if should_typo:
            self._press_key(get_typo_char(ch))
            self.stats['typos'] += 1
            self.root.after(0, self._update_stats)

            extra = random.randint(0, 3)
            extra_typed = 0
            for j in range(extra):
                if i + 1 + j >= len(text): break
                time.sleep(max(0.02, gaussian(base_delay * 0.7, base_delay * variation * 0.5)))
                if self.stop_flag: self._finish(False); return -1
                self._press_key(text[i + 1 + j])
                extra_typed += 1

            time.sleep(random.uniform(0.18, 0.55))
            if self.stop_flag: self._finish(False); return -1

            for _ in range(1 + extra_typed):
                time.sleep(random.uniform(0.035, 0.08))
                if self.stop_flag: self._finish(False); return -1
                keyboard.press(Key.backspace); keyboard.release(Key.backspace)

            self.stats['corrections'] += 1
            self.root.after(0, self._update_stats)
            time.sleep(random.uniform(0.06, 0.18))

        delay = max(0.02, gaussian(base_delay, base_delay * variation))
        if   ch == ' ':             delay *= 0.7
        elif ch.isupper():          delay *= 1.3
        elif ch in '.,!?;:\'"()-': delay *= 1.4
        elif ch.isdigit():          delay *= 1.2

        time.sleep(delay)
        if self.stop_flag: self._finish(False); return -1

        self._press_key(ch)
        self.stats['chars'] += 1
        self.root.after(0, self._update_stats)
        return 1

    # ------------------------------------------------------------------ typing thread
    def _typing_thread(self, text, settings):
        is_resume = (self.resume_type_idx > 0)
        self._perform_alt_tab()

        if is_resume:
            self.resume_type_idx = self._sync_typing_index(text, self.resume_type_idx)
            time.sleep(0.1)
        else:
            if self._do_countdown(settings, 'Click your target field!'):
                self._finish(False); return

        self.root.after(0, lambda: self._set_status('Typing...', ACCENT))

        i = self.resume_type_idx
        while i < len(text):
            self.resume_type_idx = i
            if self._check_stop():
                self.resume_type_idx = i
                self.root.after(0, lambda: self.type_widgets['start_btn'].config(text='Resume Typing'))
                return
            if self._wait_pause():
                self.resume_type_idx = i
                self.root.after(0, lambda: self.type_widgets['start_btn'].config(text='Resume Typing'))
                self._finish(False); return

            i = self.resume_type_idx
            if i >= len(text):
                break

            ch = text[i]
            base_delay, variation, typo_rate, pause_rate, pause_dur = self._read_settings(settings)

            pause_result = self._do_think_pause(ch, i, text, pause_rate, pause_dur)
            if pause_result is True:
                self.resume_type_idx = i
                self.root.after(0, lambda: self.type_widgets['start_btn'].config(text='Resume Typing'))
                self._finish(False); return
            elif pause_result == "resumed":
                i = self.resume_type_idx
                continue

            advance = self._type_char_human(ch, base_delay, variation, typo_rate, i, text, settings)
            if advance == -1:
                self.resume_type_idx = i
                self.root.after(0, lambda: self.type_widgets['start_btn'].config(text='Resume Typing'))
                return
            i += advance

        self.resume_type_idx = 0
        self.root.after(0, lambda: self.type_widgets['start_btn'].config(text='Start Typing'))
        self._finish(True)

    # ------------------------------------------------------------------ replace thread
    def _replace_thread(self, original_text, target_text, settings):
        is_resume = (self.resume_replace_opcodes is not None
                     and self.resume_replace_opcode_idx > 0)

        if not is_resume:
            # Alt-Tab back to editor, then countdown (user should have cursor positioned)
            self._perform_alt_tab()

            if self._do_countdown(settings, 'Position cursor at START of current text!'):
                self._finish(False); return

            original_clean = original_text.replace('\r\n', '\n').replace('\r', '\n')
            target_clean   = target_text.replace('\r\n', '\n').replace('\r', '\n')

            self.root.after(0, lambda: self._set_status(
                f'Diffing {len(original_clean)} → {len(target_clean)} chars...', CYAN))
            time.sleep(0.2)

            w = self.replace_widgets
            cs = w['case_sensitive_var'].get()
            nn = w['norm_newlines_var'].get()

            seq_o = [LenientChar(c, cs, nn) for c in original_clean]
            seq_t = [LenientChar(c, cs, nn) for c in target_clean]
            sm      = difflib.SequenceMatcher(None, seq_o, seq_t, autojunk=False)
            opcodes = sm.get_opcodes()

            self.resume_replace_opcodes        = opcodes
            self.resume_replace_target_clean   = target_clean
            self.resume_replace_original_clean = original_clean
            self.resume_replace_opcode_idx     = 0
        else:
            opcodes      = self.resume_replace_opcodes
            target_clean = self.resume_replace_target_clean
            self._perform_alt_tab()
            time.sleep(0.1)

        self.root.after(0, lambda: self._set_status('Replacing...', CYAN))
        w = self.replace_widgets

        def _abort(idx):
            self.resume_replace_opcode_idx = idx
            self.root.after(0, lambda: self.replace_widgets['start_btn'].config(text='Resume Replace'))

        for idx in range(self.resume_replace_opcode_idx, len(opcodes)):
            if self._check_stop(): _abort(idx); return
            if self._wait_pause(): _abort(idx); self._finish(False); return

            tag, i1, i2, j1, j2 = opcodes[idx]
            base_delay, variation, typo_rate, pause_rate, pause_dur = self._read_settings(settings)

            if tag == 'equal':
                self._navigate_right(i2 - i1, base_delay, target_clean[j1:j2])
                if self._check_stop(): _abort(idx); return

            elif tag == 'delete':
                time.sleep(random.uniform(0.2, 0.5))
                self._delete_chars(i2 - i1, base_delay)
                if self._check_stop(): _abort(idx); return

            elif tag in ('insert', 'replace'):
                if tag == 'replace':
                    time.sleep(random.uniform(0.25, 0.6))
                    self._delete_chars(i2 - i1, base_delay)
                    if self._check_stop(): _abort(idx); return
                    time.sleep(random.uniform(0.1, 0.35))

                insert_text = target_clean[j1:j2]
                threshold   = w['double_enter_threshold_var'].get()
                do_space    = (w['double_enter_var'].get()
                               and len(insert_text) >= threshold
                               and insert_text.strip())

                if do_space:
                    for _ in range(2):
                        keyboard.press(Key.enter); keyboard.release(Key.enter)
                        time.sleep(random.uniform(0.08, 0.15))
                    for _ in range(2):
                        keyboard.press(Key.left); keyboard.release(Key.left)
                        time.sleep(random.uniform(0.08, 0.15))

                time.sleep(random.uniform(0.15, 0.4))

                for ci, ch in enumerate(insert_text):
                    if self._check_stop(): _abort(idx); return
                    if self._wait_pause(): _abort(idx); self._finish(False); return

                    base_delay, variation, typo_rate, pause_rate, pause_dur = self._read_settings(settings)

                    pause_result = self._do_think_pause(ch, ci, insert_text, pause_rate, pause_dur)
                    if pause_result is True:
                        _abort(idx); self._finish(False); return
                    elif pause_result == "resumed":
                        continue

                    adv = self._type_char_human(ch, base_delay, variation, typo_rate,
                                                ci, insert_text, settings)
                    if adv == -1: _abort(idx); return

                if do_space:
                    for _ in range(2):
                        keyboard.press(Key.delete); keyboard.release(Key.delete)
                        time.sleep(random.uniform(0.08, 0.15))

        self.resume_replace_opcodes        = None
        self.resume_replace_target_clean   = None
        self.resume_replace_original_clean = None
        self.resume_replace_opcode_idx     = 0
        self.root.after(0, lambda: self.replace_widgets['start_btn'].config(text='Start Replace'))
        self._finish(True)

    def _build_fake_tab(self, parent):
        w = self.fake_widgets
        split = ttk.Frame(parent)
        split.pack(fill='both', expand=True, pady=8, padx=4)

        left = ttk.Frame(split)
        left.pack(side='left', fill='both', expand=True, padx=(0, 10))
        ttk.Label(left, text='Text to type (each keystroke prints letters from here):', style='Accent.TLabel').pack(anchor='w', pady=(0, 4))
        w['text_input'] = scrolledtext.ScrolledText(
            left, wrap='word', bg=BG_INPUT, fg=FG, insertbackground=ACCENT,
            font=('Consolas', 10), relief='flat', bd=0,
            highlightthickness=1, highlightcolor=ACCENT, highlightbackground=BORDER,
            padx=10, pady=8, selectbackground=ACCENT_DIM, selectforeground='white')
        w['text_input'].pack(fill='both', expand=True)
        w['text_input'].bind('<KeyRelease>', self._on_text_change)

        right = ttk.Frame(split, width=340)
        right.pack(side='right', fill='both', padx=(10, 0))
        right.pack_propagate(False)

        # Settings
        wrap = ttk.Frame(right)
        wrap.pack(fill='x', pady=(0, 8))
        
        ttk.Label(wrap, text='Letters per Keystroke', style='Accent.TLabel').pack(side='left')
        lbl = ttk.Label(wrap, text='1', style='Dim.TLabel')
        lbl.pack(side='right')
        
        w['chars_per_keystroke_var'] = tk.IntVar(value=1)
        self.fake_chars_per_keystroke = 1
        def cb(v):
            val = int(float(v))
            lbl.config(text=str(val))
            self.fake_chars_per_keystroke = val
            self._save_state()
            
        sc = ttk.Scale(wrap, from_=1, to=5, variable=w['chars_per_keystroke_var'],
                       orient='horizontal', command=cb)
        sc.pack(fill='x', pady=(2, 2))
        sc.bind('<ButtonRelease-1>', lambda e: self.root.after(50, self._save_state))
        w['chars_per_keystroke_label'] = lbl
        
        ttk.Label(right, text='Every keystroke will print characters from the text.\nPress Backspace to delete and retype.\nPress ESC to stop fake typing & minimize.', style='Hint.TLabel', justify='left').pack(anchor='w', pady=(10, 10))

        btns = ttk.Frame(right)
        btns.pack(fill='x', pady=(8, 0))
        w['start_btn'] = ttk.Button(btns, text='Start Fake Typing', style='Accent.TButton',
                                    command=self._start_fake_typing)
        w['start_btn'].pack(side='left', fill='x', expand=True, padx=(0, 4))
        w['stop_btn'] = ttk.Button(btns, text='Stop', style='Danger.TButton',
                                   command=self._stop_fake_typing, state='disabled')
        w['stop_btn'].pack(side='left', padx=(4, 0))

    def _start_fake_typing(self):
        w = self.fake_widgets
        text = w['text_input'].get('1.0', 'end').strip()
        if not text:
            self._set_status('No text entered!', RED)
            return

        self.typing = True
        self.paused = False
        self.stop_flag = False
        self._active_mode = 'fake'

        self.fake_text_to_type = text
        self.fake_index = 0

        w['start_btn'].config(state='disabled')
        w['stop_btn'].config(state='normal')
        w['text_input'].config(state='disabled')

        self._set_status('Fake typing active — start pressing keys!', ACCENT)

        # Alt-Tab first, then install the raw Windows keyboard hook
        self._perform_alt_tab()
        self._install_fake_hook()

    def _install_fake_hook(self):
        """Install a raw WH_KEYBOARD_LL hook via ctypes.
        Only real (non-injected) keystrokes are intercepted and replaced.
        Injected characters (from pynput keyboard.type) are flagged LLKHF_INJECTED
        by Windows and pass straight through without being intercepted."""
        import ctypes
        import ctypes.wintypes
        import threading

        VK_ESCAPE      = 0x1B
        VK_BACK        = 0x08
        WH_KEYBOARD_LL = 13
        WM_KEYDOWN     = 0x0100
        WM_SYSKEYDOWN  = 0x0104
        LLKHF_INJECTED = 0x00000010
        LLKHF_LOWER_IL = 0x00000002
        WM_QUIT        = 0x0012
        PASS_THROUGH_VKS = {
            0x0D,  # Enter
            0x09,  # Tab
            0x25, 0x26, 0x27, 0x28,  # Left, Up, Right, Down arrows
            0x21, 0x22,  # Page Up, Page Down
            0x23, 0x24,  # End, Home
            0x2D, 0x2E,  # Insert, Delete
            0x10, 0x11, 0x12,  # Shift, Ctrl, Alt
            0x5B, 0x5C,  # Left/Right Win keys
            0x14, 0x90, 0x91,  # Caps, Num, Scroll Lock
        }

        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [
                ('vkCode',      ctypes.wintypes.DWORD),
                ('scanCode',    ctypes.wintypes.DWORD),
                ('flags',       ctypes.wintypes.DWORD),
                ('time',        ctypes.wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_ulong),
            ]

        # MUST use c_size_t for lParam — it's a pointer (64-bit on 64-bit Windows).
        # ctypes.wintypes.LPARAM is c_long (32-bit) and will truncate the address.
        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_long,    # return
            ctypes.c_int,     # nCode
            ctypes.c_uint,    # wParam (WPARAM — message ID, fits in 32-bit)
            ctypes.c_size_t,  # lParam (LPARAM — pointer to KBDLLHOOKSTRUCT, MUST be pointer-sized)
        )

        # Set correct argtypes so ctypes doesn't truncate arguments
        user32.SetWindowsHookExW.restype  = ctypes.c_void_p
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p,
                                              ctypes.c_void_p, ctypes.wintypes.DWORD]
        user32.CallNextHookEx.restype     = ctypes.c_long
        user32.CallNextHookEx.argtypes    = [ctypes.c_void_p, ctypes.c_int,
                                              ctypes.c_uint, ctypes.c_size_t]
        user32.UnhookWindowsHookEx.restype  = ctypes.wintypes.BOOL
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        user32.PostThreadMessageW.argtypes  = [ctypes.wintypes.DWORD, ctypes.c_uint,
                                                ctypes.c_size_t, ctypes.c_size_t]

        # Use c_void_p so HHOOK (pointer-sized on 64-bit) isn't truncated
        hook_id   = ctypes.c_void_p(0)
        thread_id = [0]

        def low_level_handler(nCode, wParam, lParam):
            try:
                if nCode >= 0 and wParam in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    struct   = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                    injected = bool(struct.flags & (LLKHF_INJECTED | LLKHF_LOWER_IL))

                    if not injected:
                        vk = struct.vkCode

                        if vk == VK_ESCAPE:
                            self.root.after(0, self._stop_fake_typing)
                            self.root.after(0, self.root.iconify)
                            return 1  # suppress Esc

                        elif vk == VK_BACK:
                            # Real backspace: step index back so char can be retyped,
                            # then let the physical backspace through to delete it
                            if self.fake_index > 0:
                                self.fake_index -= 1
                            # Fall through to CallNextHookEx (don't suppress)

                        elif vk in PASS_THROUGH_VKS:
                            # Let navigation/control/enter keys pass through normally
                            return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

                        else:
                            # Any other real key: suppress it and inject our text
                            txt = self.fake_text_to_type
                            if self.fake_index < len(txt):
                                n     = self.fake_chars_per_keystroke
                                chunk = txt[self.fake_index: self.fake_index + n]
                                for ch in chunk:
                                    self._press_key(ch)
                                self.fake_index += len(chunk)
                                if self.fake_index >= len(txt):
                                    self.root.after(0, self._stop_fake_typing)
                            return 1  # suppress physical key
            except Exception:
                pass  # never let exceptions escape a ctypes callback

            return user32.CallNextHookEx(hook_id, nCode, wParam, lParam)

        self._fake_hook_proc = HOOKPROC(low_level_handler)  # keep reference alive

        def hook_thread():
            thread_id[0] = kernel32.GetCurrentThreadId()
            hook_id.value = user32.SetWindowsHookExW(
                WH_KEYBOARD_LL, self._fake_hook_proc, None, 0
            )
            msg = ctypes.wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            if hook_id.value:
                user32.UnhookWindowsHookEx(hook_id.value)

        def stop_hook():
            if thread_id[0]:
                user32.PostThreadMessageW(thread_id[0], WM_QUIT, 0, 0)

        self._stop_fake_hook_fn = stop_hook
        threading.Thread(target=hook_thread, daemon=True).start()


    def _stop_fake_typing(self):
        if hasattr(self, '_stop_fake_hook_fn') and self._stop_fake_hook_fn:
            try:
                self._stop_fake_hook_fn()
            except Exception:
                pass
            self._stop_fake_hook_fn = None

        self.typing = False
        self._active_mode = 'type'
        w = self.fake_widgets
        done = self.fake_index >= len(getattr(self, 'fake_text_to_type', ''))
        self.root.after(0, lambda: w['start_btn'].config(state='normal'))
        self.root.after(0, lambda: w['stop_btn'].config(state='disabled'))
        self.root.after(0, lambda: w['text_input'].config(state='normal'))
        self.root.after(0, lambda: self._set_status(
            'Done!' if done else 'Stopped',
            GREEN if done else RED))

    def _perform_alt_tab(self):
        old_injecting = getattr(self, '_injecting', False)
        self._injecting = True
        from pynput.keyboard import Key as PKey
        keyboard.press(PKey.alt); keyboard.press(PKey.tab)
        keyboard.release(PKey.tab); keyboard.release(PKey.alt)
        time.sleep(0.4)
        self._injecting = old_injecting

    def _sync_typing_index(self, text, current_idx):
        if current_idx <= 0:
            return current_idx

        old_injecting = getattr(self, '_injecting', False)
        self._injecting = True

        try:
            self.root.clipboard_clear()
        except Exception:
            pass

        num_chars_to_select = min(15, current_idx)
        if num_chars_to_select <= 0:
            self._injecting = old_injecting
            return current_idx

        # Select text to the left
        keyboard.press(Key.shift)
        for _ in range(num_chars_to_select):
            keyboard.press(Key.left)
            keyboard.release(Key.left)
            time.sleep(0.01)
        keyboard.release(Key.shift)
        time.sleep(0.05)

        # Copy to clipboard
        keyboard.press(Key.ctrl)
        keyboard.press('c')
        keyboard.release('c')
        keyboard.release(Key.ctrl)
        time.sleep(0.15)

        copied_text = ""
        try:
            copied_text = self.root.clipboard_get()
        except Exception:
            pass

        # Deselect (Right Arrow once cancels selection and keeps cursor at the right edge)
        keyboard.press(Key.right)
        keyboard.release(Key.right)
        time.sleep(0.05)

        self._injecting = old_injecting

        if not copied_text:
            return current_idx

        copied_clean = copied_text.replace('\r\n', '\n').replace('\r', '\n')
        copied_len = len(copied_clean)
        if copied_len == 0:
            return current_idx

        start_search = max(0, current_idx - 40)
        end_search = min(len(text), current_idx + 40)

        best_idx = current_idx
        best_score = 0

        for i in range(start_search, end_search - copied_len + 1):
            candidate = text[i:i+copied_len]
            score = sum(1 for c1, c2 in zip(candidate, copied_clean) if c1 == c2)
            if score > best_score:
                best_score = score
                best_idx = i + copied_len

        if best_score / copied_len >= 0.6:
            return best_idx

        return current_idx

    # ------------------------------------------------------------------ navigation / input
    def _navigate_right(self, count, base_delay, text_segment=''):
        use_fast = self.replace_widgets.get('fast_nav_var')
        use_fast = use_fast.get() if use_fast else False

        if not use_fast or not text_segment or count < 8:
            for _ in range(count):
                if self._check_stop(): return
                time.sleep(random.uniform(0.015, 0.04) if count > 10 else random.uniform(0.04, 0.09))
                keyboard.press(Key.right); keyboard.release(Key.right)
            return

        import re
        idx = 0
        while idx < count:
            if self._check_stop(): return
            remaining = text_segment[idx:count]
            m = re.match(r'^([a-zA-Z0-9]+)(\s*)', remaining)
            if m and len(m.group(0)) > 2 and idx + len(m.group(0)) <= count:
                time.sleep(random.uniform(0.07, 0.15))
                keyboard.press(Key.ctrl); keyboard.press(Key.right)
                keyboard.release(Key.right); keyboard.release(Key.ctrl)
                idx += len(m.group(0))
                continue
            time.sleep(random.uniform(0.02, 0.05))
            keyboard.press(Key.right); keyboard.release(Key.right)
            idx += 1

    def _delete_chars(self, count, base_delay):
        for n in range(count):
            if self._check_stop(): return
            delay = (random.uniform(0.025, 0.055) if count > 5 and 0 < n < count - 1
                     else random.uniform(0.05, 0.1))
            time.sleep(delay)
            keyboard.press(Key.delete); keyboard.release(Key.delete)
            self.stats['chars'] += 1
            self.root.after(0, self._update_stats)

    def _press_key(self, ch):
        if ch == '\n':
            keyboard.press(Key.enter); keyboard.release(Key.enter)
        elif ch == '\t':
            keyboard.press(Key.tab); keyboard.release(Key.tab)
        else:
            keyboard.type(ch)


# ------------------------------------------------------------------ entry point
if __name__ == '__main__':
    root = tk.Tk()
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    HumanTypeApp(root)
    root.mainloop()
