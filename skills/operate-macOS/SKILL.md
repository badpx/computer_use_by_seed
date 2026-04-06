---
name: operate-macOS
description: This skill provides the Agent with the necessary command mappings and logic to navigate the macOS environment. It focuses on system-level interactions, window management, and file operations via Finder, including advanced Unix-style text navigation.
---

## Instructions

### Global System Shortcuts

1. Navigation & Search
| Intent | Shortcut | Notes |
| :--- | :--- | :--- |
| **Open Spotlight Search** | `Cmd + Space` | The primary way to launch apps or find files. |
| **Switch Applications** | `Cmd + Tab` | Hold Cmd to cycle through active apps. |
| **Switch Windows (Same App)** | `Cmd + ~` | Cycles through windows of the current active app. |
| **Force Quit Menu** | `Cmd + Opt + Esc` | Use if an application becomes unresponsive. |
| **Screen Capture (Utility)** | `Cmd + Shift + 5` | Opens the screenshot and screen recording interface. |

2. Window Management
| Intent | Shortcut | Notes |
| :--- | :--- | :--- |
| **Minimize Window** | `Cmd + M` | Sends window to the Dock. |
| **Hide Current App** | `Cmd + H` | Instantly hides the active application. |
| **Mission Control** | `Ctrl + ↑` | Shows all open windows and desktops. |
| **Show Desktop** | `Cmd + F3` | Scatters windows to reveal the desktop. |

---

### Finder & File Operations
| Intent | Shortcut | Notes |
| :--- | :--- | :--- |
| **Go to Folder** | `Cmd + Shift + G` | Crucial for Agents to navigate to specific paths. |
| **Quick Look** | `Spacebar` | Preview a file without opening it. |
| **Move to Trash** | `Cmd + Delete` | Deletes the selected item. |
| **Get Info** | `Cmd + I` | Shows file permissions and metadata. |
| **New Folder** | `Cmd + Shift + N` | Creates a folder in the current directory. |

---

### Universal Editing & Clipboard (Essential)
These commands are standard across almost all macOS applications (Finder, Safari, Notes, etc.).

| Intent | Shortcut | Notes |
| :--- | :--- | :--- |
| **Select All** | `Cmd + A` | Selects all items in a folder or all text in a field. |
| **Copy** | `Cmd + C` | Copies selected items/text to the clipboard. |
| **Paste** | `Cmd + V` | Pastes content from the clipboard. |
| **Cut** | `Cmd + X` | Removes selection and copies to clipboard (Text only). |
| **Move Files** | `Cmd + Opt + V` | In Finder: Pastes files as "Move" (equivalent to Cut/Paste). |
| **Undo** | `Cmd + Z` | Reverses the last action. |
| **Redo** | `Cmd + Shift + Z`| Reverses the Undo command. |
| **Save** | `Cmd + S` | Saves the current document/file. |

---

### Text Editing & Advanced Navigation
macOS supports standard shortcuts and **Emacs-style** bindings globally. These are highly efficient for Agent text manipulation.

1. Standard Navigation
* **Start of Line:** `Cmd + ←`
* **End of Line:** `Cmd + →`
* **Start/End of Document:** `Cmd + ↑` / `Cmd + ↓`
* **Delete Word to the Left:** `Opt + Delete`

2. Emacs-Style Navigation (Global `Control` Bindings)
| Intent | Shortcut | Action |
| :--- | :--- | :--- |
| **Beginning of Line** | `Ctrl + A` | Moves cursor to the start of the paragraph/line. |
| **End of Line** | `Ctrl + E` | Moves cursor to the end of the paragraph/line. |
| **Forward One Char** | `Ctrl + F` | Moves cursor forward (Alternative to Right Arrow). |
| **Backward One Char**| `Ctrl + B` | Moves cursor backward (Alternative to Left Arrow). |
| **Next Line** | `Ctrl + N` | Moves cursor to the next line. |
| **Previous Line** | `Ctrl + P` | Moves cursor to the previous line. |
| **Delete Forward** | `Ctrl + D` | Deletes the character in front of the cursor. |
| **Kill to End of Line**| `Ctrl + K` | Deletes all text from cursor to the end of the line. |

---

### Agent Execution Strategy

a. Launching Applications
Instead of searching for icons, the Agent should:
1. Trigger `Cmd + Space`.
2. Type the application name (e.g., "Terminal").
3. Press `Enter`.

b. Permission Handling
* **Accessibility:** Simulating keystrokes requires specific OS-level permissions.
* **TCC Alerts:** If a command fails, the Agent should check for "App wants to control this computer" dialogs.

c. Best Practices
* **The "Escape" Key:** Use `Esc` to cancel out of stuck UI states (Spotlight, Menus).
* **UI Lag:** Add a ~300ms pause after Mission Control (`Ctrl + ↑`) before interacting with windows.
* **Focus Check:** Before sending text-editing commands (like `Ctrl + K`), ensure the target text field has an active blinking cursor.

### Error Recovery
* **Stuck Modifier:** If keys act strangely, "release" all modifier keys (`Cmd`, `Opt`, `Ctrl`) to reset.
* **Text Selection:** If the Agent needs to overwrite text, use `Ctrl + A` (Beginning) then `Shift + Ctrl + E` (Select to End) then `Delete`.
