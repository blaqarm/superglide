# Superglide

A small Windows tool that performs the **input package** for an Apex Legends
superglide: jump, then crouch exactly one game frame later.

## How a superglide works

1. Sprint into a ledge and mantle.
2. During the **last ~150 ms** of the mantle, press **Jump**.
3. Press **Crouch exactly one frame later**.
4. Keep a movement direction held.

The tool does not know when your mantle starts. You still time the mantle
yourself; the tool only guarantees the Jump -> Crouch gap.

| In-game FPS | One frame |
|---|---|
| 60 | 16.67 ms |
| 120 | 8.33 ms |
| 144 | 6.94 ms |
| 165 | 6.06 ms |
| 180 | 5.56 ms |
| 240 | 4.17 ms |
| 300 | 3.33 ms |

Use the same FPS cap that is set in your game. If the timing feels slightly
off on your hardware, adjust the **Fine-tune (ms)** value by a few tenths.

## Installation & Run

**Prerequisites:** Python 3.10+ on Windows.

### PowerShell
```powershell
git clone https://github.com/blaqarm/superglide
cd superglide
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python superglide.py
```

### Command Prompt (cmd)
```bat
git clone https://github.com/blaqarm/superglide
cd superglide
py -m venv .venv
.\.venv\Scripts\activate.bat
pip install -r requirements.txt
python superglide.py
```

*Note:* If PowerShell blocks script execution, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once in a PowerShell window.

## Usage

1. Select your in-game FPS (or choose **Custom...**).
2. Optionally adjust **Fine-tune (ms)**.
3. Change **Activation**, **Jump**, and **Crouch** under **Keybinds** if needed.
   The next key you press becomes the new bind.
4. Press **Start**.
5. In game, press the activation key during the last part of a mantle.

Default binds:

- Activation: `Caps Lock`
- Jump: `Space`
- Crouch: `Left Ctrl`

Settings are saved to `config.json` next to the script and restored on the
next launch. Delete that file to reset everything to defaults.

## Notes

- If Apex is running as administrator, run this tool as administrator too,
  otherwise Windows may block the injected inputs.
- The activation key is still sent to the game. Rebinding it to a key that is
  also used in game can cause that action to fire.
- Keyboard polling rate and system input latency affect superglide consistency.
  At 240+ FPS the window is only a few milliseconds.
- Macros may violate the game's terms of service. Use at your own risk.

![Pic](superglide.jpg)
