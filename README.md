# HumanType — Realistic Human Typing Simulator

A realistic keystroke simulator for Windows that types, replaces text, or intercepts physical keystrokes with human-like rhythm, speed, variation, and natural pauses.

## Features

1. **Type Tab**: Paste text, and it types it out into any active window with realistic typing speeds, dynamic variations, typos, and natural "thinking" pauses.
2. **Replace Tab**: Diffs CURRENT text and DESIRED text, then navigates and replaces text in-place (deleting and typing only the changed parts). Position your cursor at the start and go!
3. **Fake Typing Tab**: Intercepts all physical keypresses (except Escape and Backspace) and replaces them character-by-character with the text you pasted.
   - **Letters per Keystroke**: Set how many characters of your text print per keypress (1 to 5).
   - **Retype Support**: Backspace actually deletes text on screen and decrements the index, allowing you to "retype" over deleted sections.
   - **Navigation & Control Keys**: Enter, Tab, arrow keys, Shift, Ctrl, Alt, Caps Lock, etc., pass straight through to the system without getting intercepted.
4. **Smart Resume**: Pausing or stopping types/replaces and clicking **Resume** immediately Alt-Tabs back to your active editor, selects the last few typed characters, copies them, and corrects the cursor index so you never miss or duplicate characters due to interruption.
5. **Global Safety Shortcuts**:
   - `ESC` (once): Instantly stops typing, saves progress, and minimizes the app.
   - `ESC` (3x fast): Restores/de-minimizes the app, Alt-Tabs back, and immediately resumes.

---

## Setup & Installation

### 1. Prerequisites
- **OS**: Windows (requires Windows APIs for low-level keyboard hooks)
- **Python**: Python 3.8 or higher installed and added to your system `PATH`.

### 2. Install Dependencies
Open Command Prompt or PowerShell and install the required library:
```bash
pip install pynput
```

### 3. Running the App
- Double-click **`HumanType.bat`** to launch the application in the background (using `pythonw`).
- Alternatively, run from console:
  ```bash
  python humantype.pyw
  ```

---

## How to Replicate on Another Computer

1. **Download/Copy the Folder**: Copy the entire `human-typer` directory containing:
   - `humantype.pyw` (main application code)
   - `HumanType.bat` (launcher script)
   - `README.md`
2. **Install Python & pynput**: On the target computer, install Python 3, run `pip install pynput` in the terminal.
3. **Run**: Run `HumanType.bat` or `python humantype.pyw`.

---

## Creating a GitHub Repository & Pushing

Since GitHub CLI (`gh`) is not currently authenticated on this machine, follow these steps to push this code to your own GitHub account:

1. Go to [GitHub](https://github.com/) and create a new repository (e.g., named `human-typer`). Do not initialize it with a README or .gitignore.
2. Initialize git and commit your files locally in the `human-typer` folder:
   ```bash
   cd C:\Users\john\Documents\ClaudeUSEpc\human-typer
   git init
   git add .
   git commit -m "Initial commit of HumanType with Fake Typing and Smart Resume"
   ```
3. Link and push to your new GitHub repository:
   ```bash
   git branch -M main
   git remote add origin https://github.com/YOUR_GITHUB_USERNAME/human-typer.git
   git push -u origin main
   ```
