---
name: operate-Cellphone
description: This skill enables a Vision-based Agent to accurately control mobile devices (Android/iOS). It addresses mobile-specific UX patterns like placeholder text, full-screen app management, and gesture-based navigation, using a standardized coordinate system.
---

# SKILL: Visual-Based Mobile Automation

## Multi-Method "Back" Navigation
Unlike desktop apps with explicit "Close" buttons, mobile apps use multiple "Back" paradigms. The Agent should try these in order:

1.  **Visual UI Button:** Look for symbols like `<` or `<-` in the top-left area . 
    - **Action:** `click(point='<point>x y</point>')`
2.  **Edge Swipe (Back Gesture):** Swipe from the left edge toward the center.
    - **Action:** `swipe(start_point='<point>0 500</point>', end_point='<point>300 500</point>')`
3.  **Physical Key Command:** Use the built-in system back action.
    - **Action:** `press_back()`

---

## Global Gesture Mapping
Since mobile devices lack visible taskbars, use these specific `swipe` actions to trigger system overlays:

| Target UI | Start Point | End Point | Instruction Example |
| :--- | :--- | :--- | :--- |
| **Notification Panel** | Top-Left `<point>250 0</point>` | Down `<point>250 800</point>` | `swipe(start_point='<point>250 0</point>', end_point='<point>250 800</point>')` |
| **Control Center** | Top-Right `<point>750 0</point>` | Down `<point>750 800</point>` | `swipe(start_point='<point>750 0</point>', end_point='<point>750 800</point>')` |
| **Recents (App List)** | Bottom-Center `<point>500 1000</point>`| Up `<point>500 400</point>` | `swipe(start_point='<point>500 1000</point>', end_point='<point>500 400</point>')` |

---

## Window Management: "Home" as Exit
**Crucial Concept:** Mobile apps do not have "Close (X)" buttons on the window frame.
- **To Exit/Close an App:** Use `press_home()`. This is the primary way to "quit" the current context and return to the desktop (Launcher).
- **To Switch Apps:** Use the **Recents Gesture** (defined above) or `open_app(app_name='...')`.

---

## App Discovery & Launcher Navigation
If the target application icon is not visible on the current Home Screen (Launcher):
- **Horizontal Navigation:** Use `swipe` to move between pages (e.g., swipe from right to left to see the next page).
    - *Example:* `swipe(start_point='<point>900 500</point>', end_point='<point>100 500</point>', duration=500)`
- **Exhaustive Search:** The Agent must check all available launcher pages before concluding that an application is not installed.
## Visual Trap: Placeholder vs. Actual Input
Mobile search bars often display "Suggested Terms" or "Trending Topics" that look like entered text.

---

## Visual Trap: Placeholder vs. Actual Input
Mobile search bars often look "full" even when they are empty.

- **Placeholder (Empty State): ** No `X` (Clear) icon is visible on the right side of the bar. 
- **Actual Text (Occupied State): ** A small `X` or "Clear" icon appears at the end of the input field.
- **CJK Constraint:** The `type()` action is strictly limited to **ASCII characters**. Direct input of CJK (Chinese, Japanese, Korean) or other non-ASCII characters is not supported.
    - **Workaround:** To input CJK text, the Agent must use `click()` to interact with the on-screen soft keyboard or predictive text suggestions.

---

## Operational Guidelines (Drag vs. Scroll vs. Swipe)

- **`drag`**: Used for precise "press-and-hold" movement, such as moving an app icon or a slider. Use `drag(start_point='...', end_point='...')`.
- **`scroll`**: Used for navigating lists or long pages. 
    - *Caution:* `direction='down'` moves the view down.
- **`swipe`**: Used for rapid movement or triggering system gestures. 
    - *Speed Rule:* Smaller `duration` = Slower; Larger `duration` = Faster.

---

## Handling the Keyboard
- When `type()` is called, the keyboard will likely cover the bottom half of the screen.
- If a "Confirm" or "Next" button is hidden by the keyboard, use `press_back()` once to dismiss the keyboard and reveal the full UI.
