# HumanType — Realistic Human Typing Simulator

A realistic keystroke simulator for Windows that types, replaces text, or intercepts physical keystrokes with human-like rhythm, speed, variation, and natural pauses.

---

## Quick Start (Easiest Way to Run)

### Option 1: Standalone Executable (Recommended — No Python Needed)
- Double-click **`HumanType.exe`**.
- Everything (Python runtime, UI, low-level keyboard hooks) is self-contained. No setup, installation, or configuration required.

### Option 2: Smart Launcher Script
- Double-click **`HumanType.bat`**.
- It automatically detects your Python environment and installs any missing dependencies (like `pynput`) automatically before launching.

### Option 3: Run from Source via Terminal
```bash
pip install pynput
python humantype.pyw
```

---

## Features

1. **Type Tab**: Paste text, and it types it out into any active window with realistic typing speeds, dynamic variations, typos, and natural "thinking" pauses.
2. **Replace Tab**: Diffs CURRENT text and DESIRED text, then navigates and replaces text in-place (deleting and typing only the changed parts). Position your cursor at the start and go!
3. **Fake Typing Tab**: Intercepts physical keypresses and replaces them character-by-character with the text you pasted.
   - **Letters per Keystroke**: Configure 1 to 5 characters per keypress.
   - **Retype Support**: Backspace deletes text on screen and decrements the index, allowing you to "retype" over deleted sections.
   - **Control Keys Pass-Through**: Navigation and modifier keys (Enter, Tab, arrows, Shift, Ctrl, Alt, Caps Lock) pass straight through.
4. **Smart Resume**: Pausing or stopping types/replaces and clicking **Resume** immediately Alt-Tabs back to your active editor, selects the last few typed characters, copies them, and corrects the cursor index so you never miss or duplicate characters.
5. **Global Safety Shortcuts**:
   - `ESC` (once): Instantly stops typing, saves progress, and minimizes the app.
   - `ESC` (3x fast): Restores the app, Alt-Tabs back, and immediately resumes.

---

## Running on Another Computer

If you are transferring this app to another Windows PC:

1. **Copy the Folder or ZIP**:
   - Copy `HumanType.exe` and `config.json` (or the entire `HumanType` folder / `HumanType-Portable.zip`).
2. **Launch**:
   - Double-click **`HumanType.exe`**.
   - No Python installation, PATH configuration, or terminal commands are required on the other machine.
