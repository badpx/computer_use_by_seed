---
name: open-browser
description: Open a web browser and navigate to a specific URL using keyboard shortcuts and the address bar on desktop operating systems. Use this skill for macOS, Windows, or Linux browser tasks, not for cellphone systems.
---

## Instructions

Follow these steps to open a browser and navigate to a URL:

1. **Open a new browser window or tab**
   - Use `hotkey(key='ctrl n')` to open a new browser window (Windows/Linux)
   - Or use `hotkey(key='cmd n')` on macOS
   - If the browser is not already open, it may need to be launched first via `hotkey(key='cmd space')` then type the browser name

2. **Focus the address bar**
   - Use `hotkey(key='ctrl l')` (Windows/Linux) or `hotkey(key='cmd l')` (macOS) to focus the address bar
   - Alternatively, click directly on the address bar at the top of the browser

3. **Type the URL**
   - Use `type(content='https://example.com\n')` to type the URL and press Enter to navigate
   - Always include the protocol (`https://`) for external URLs

4. **Verify navigation**
   - After pressing Enter, wait briefly for the page to load
   - Take a screenshot to confirm the page has loaded correctly

5. **Tab & Window Management**

| Intent | macOS (All Browsers) | Windows/Linux (Chromium) |
| :--- | :--- | :--- |
| **New Tab** | `Cmd + T` | `Ctrl + T` |
| **Close Current Tab** | `Cmd + W` | `Ctrl + W` |
| **Reopen Closed Tab** | `Cmd + Shift + T` | `Ctrl + Shift + T` |
| **Focus Address Bar** | `Cmd + L` | `Ctrl + L` or `F6` |
| **Next Tab** | `Ctrl + Tab` | `Ctrl + Tab` |
| **Previous Tab** | `Ctrl + Shift + Tab` | `Ctrl + Shift + Tab` |

5. **Navigation & Interaction**

| Intent | macOS | Windows/Linux |
| :--- | :--- | :--- |
| **Hard Reload (Clear Cache)** | `Cmd + Shift + R` | `Ctrl + F5` |
| **Find on Page** | `Cmd + F` | `Ctrl + F` |
| **Zoom In / Out** | `Cmd + (+/-)` | `Ctrl + (+/-)` |
| **Reset Zoom (100%)** | `Cmd + 0` | `Ctrl + 0` |
| **Save Page As** | `Cmd + S` | `Ctrl + S` |

## Notes

- If the browser address bar is already focused, skip step 2
- For URLs without a protocol, add `https://` prefix
- If the page takes time to load, use `wait()` to pause before checking
