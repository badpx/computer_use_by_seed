# Android ADB Device Plugin Design

## Summary

Add a new built-in device plugin named `android_adb` so `ComputerUseAgent` can control an Android phone over `adb`.

The plugin will:

- capture screenshots with `adb exec-out screencap -p`
- execute supported phone actions with `adb shell input ...`
- expose Android environment info to the agent
- select a phone-specific prompt profile so the model sees the correct action space

This design assumes:

- `adb` is already available in `PATH`
- a default Android device is already connected before the agent starts
- v1 does not support device serial selection or Android display selection

## Goals

- Reuse the existing device plugin architecture instead of adding a special Android mode
- Keep coordinate normalization global so the Android plugin only consumes normalized pixel commands
- Use the existing phone prompt template instead of reusing the desktop action space
- Keep the first version small, explicit, and testable

## Non-Goals

- `adb -s <serial>` support
- switching between multiple Android devices
- Android display ID selection
- app-name-to-package-name lookup
- advanced IME integration
- gesture synthesis beyond `adb shell input`

## Architecture

### Plugin Layout

Create a new built-in plugin under:

- `computer_use/devices/plugins/android_adb/plugin.json`
- `computer_use/devices/plugins/android_adb/plugin.py`
- `computer_use/devices/plugins/android_adb/adapter.py`

The plugin uses the existing `DeviceAdapter` interface and remains discoverable through the current device registry.

### Prompt Profile

Extend `DeviceAdapter` with a new method:

```python
def get_prompt_profile(self) -> str:
    return "computer"
```

Prompt profiles:

- `computer` -> `COMPUTER_USE_DOUBAO`
- `cellphone` -> `PHONE_USE_DOUBAO`

The built-in adapters should report:

- `local` -> `computer`
- `lumi_cua_sandbox` -> `computer`
- `android_adb` -> `cellphone`

`ComputerUseAgent` should select the system prompt by prompt profile, not by device name.

## Android ADB Adapter

### Device Identity

`android_adb` reports:

- `device_name`: `android_adb`
- `operating_system`: `Android`
- `prompt_profile`: `cellphone`

It does not support target selection in v1:

- `supports_target_selection()` returns `False`
- `list_targets()` returns `[]`
- `set_target()` raises `NotImplementedError`

### Screenshot Capture

The adapter captures screenshots with:

```bash
adb exec-out screencap -p
```

Implementation requirements:

- Use `subprocess.run(...)` without shell redirection
- Read PNG bytes from `stdout`
- Convert the bytes into `DeviceFrame.image_data_url` as `data:image/png;base64,...`
- Compute width and height from the PNG bytes

### Handling Warning Prefixes Before PNG Bytes

Some devices may prepend warning text before the real PNG payload, for example foldable devices where `screencap` warns about multiple displays.

The adapter must not assume `stdout` starts with PNG bytes.

Instead it must:

1. capture the full `stdout` as bytes
2. search for the PNG signature `\x89PNG\r\n\x1a\n`
3. discard any bytes before that signature
4. treat the remaining bytes as the screenshot payload

Behavior:

- if warning text exists before the PNG signature, ignore the prefix and continue
- if no PNG signature exists, fail the capture and include a safe preview of the leading output in the error

The frame metadata should include enough debugging context, for example:

- `device_name: "android_adb"`
- `capture_method: "adb_exec_out_screencap"`
- `png_prefix_stripped: true|false`

### Command Execution Model

All commands should be executed through `subprocess.run(...)` with argument arrays, not shell strings.

Any non-zero exit code should raise an exception that includes:

- the adb command
- the exit code
- `stderr` text when present

If `adb` is missing from `PATH`, the adapter should raise a clear error explaining that `adb` must be installed and available before starting the agent.

## Supported Action Mapping

The Android plugin should align with `PHONE_USE_DOUBAO`.

The shared command mapping layer should support these phone actions:

- `click`
- `long_press`
- `type`
- `scroll`
- `open_app`
- `drag`
- `press_home`
- `press_back`

### Mappings

`click(point)`:

```bash
adb shell input tap <x> <y>
```

`long_press(point)`:

```bash
adb shell input swipe <x> <y> <x> <y> <duration_ms>
```

Use a fixed default duration in v1, for example `600ms`.

`drag(start_point, end_point)`:

Preferred:

```bash
adb shell input draganddrop <x1> <y1> <x2> <y2> <duration_ms>
```

Fallback when needed:

```bash
adb shell input swipe <x1> <y1> <x2> <y2> <duration_ms>
```

Use a fixed default duration in v1, for example `400ms`.

`type(content)`:

```bash
adb shell input text <escaped_text>
```

If the content ends with `\n`, strip the trailing newline from the text payload and then send:

```bash
adb shell input keyevent KEYCODE_ENTER
```

`open_app(app_name)`:

Treat `app_name` as an Android package name in v1 and launch it with:

```bash
adb shell monkey -p <package_name> -c android.intent.category.LAUNCHER 1
```

`press_home()`:

```bash
adb shell input keyevent KEYCODE_HOME
```

`press_back()`:

```bash
adb shell input keyevent KEYCODE_BACK
```

`scroll(point, direction, steps)`:

Use the native `input scroll` command rather than synthesizing a swipe.

Example shape:

```bash
adb shell input touchscreen scroll <x> <y> --axis VSCROLL,<value>
```

Rules:

- vertical directions map to `VSCROLL`
- horizontal directions map to `HSCROLL`
- the sign depends on `direction`
- `steps` controls magnitude
- omit unsupported axes

Recommended v1 conversion:

- clamp `steps` to `1..50`
- convert steps into a small signed float multiplier
- use `touchscreen scroll <x> <y>` so the event is associated with a concrete location

### Unsupported Actions

The Android plugin should reject unsupported actions with a clear error.

Out of scope in v1:

- `hover`
- `right_single`
- `left_double`
- `hotkey`

These are not part of `PHONE_USE_DOUBAO`, and the plugin should not silently guess an Android equivalent.

## Shared-Core Changes

### DeviceAdapter Interface

Add:

```python
def get_prompt_profile(self) -> str:
    return "computer"
```

This keeps prompt selection stable and reusable across devices.

### Agent Prompt Selection

`ComputerUseAgent` should:

- ask the connected device for its prompt profile
- select the matching prompt template
- continue injecting runtime context, history, and screenshots exactly as before

No Android-specific prompt logic should be hardcoded by device name if prompt profiles already cover the choice.

### Command Mapper

Extend the shared command mapper so parsed phone actions become normalized `DeviceCommand` objects before they reach the plugin.

This includes:

- `long_press`
- `open_app`
- `press_home`
- `press_back`

The Android plugin should consume the normalized command object, not parse raw model actions.

## Text Input Escaping

`adb shell input text` is sensitive to spaces and some special characters.

For v1:

- implement a small explicit escaping layer for spaces and common special characters
- keep newline handling separate through `KEYCODE_ENTER`
- if a string cannot be safely encoded for `input text`, raise a clear error instead of silently corrupting it

The design intentionally avoids IME-based text injection in this iteration.

## Logging

The existing task and model logs should continue to work without special changes.

The Android plugin should contribute device metadata through normal device status and frame metadata, including:

- `device_name`
- `connected_via: "adb"`
- `capture_method`
- whether a non-PNG prefix was stripped before screenshot decoding

## Testing

Add regression coverage for:

### Plugin Discovery and Loading

- `android_adb` can be discovered as a built-in plugin
- the plugin factory returns an adapter instance

### Prompt Selection

- `android_adb.get_prompt_profile()` returns `cellphone`
- `ComputerUseAgent` chooses `PHONE_USE_DOUBAO` when the active device profile is `cellphone`

### Screenshot Capture

- valid PNG stdout becomes a `DeviceFrame`
- warning text before PNG bytes is stripped correctly
- missing PNG signature raises a clear capture error
- frame dimensions are read from the PNG payload

### Command Mapping

- `click` maps to `adb shell input tap`
- `long_press` maps to same-point `swipe`
- `drag` maps to `draganddrop`
- `type("abc\\n")` maps to `text abc` plus `KEYCODE_ENTER`
- `open_app` maps to `monkey -p <package>`
- `press_home` maps to `KEYCODE_HOME`
- `press_back` maps to `KEYCODE_BACK`
- `scroll` maps to `input touchscreen scroll` with the expected axis and sign

### Error Handling

- missing `adb` raises a clear dependency error
- non-zero adb exit codes surface stderr
- unsupported actions raise a clear plugin error

## Open Decisions Resolved

- Prompt profile name: `cellphone`
- Android plugin name: `android_adb`
- `open_app(app_name)` treats `app_name` as package name in v1
- screenshot capture uses in-memory stdout, not temporary files
- prefixed warning text before PNG bytes is supported by scanning for the PNG signature

## Implementation Sequence

1. Add `get_prompt_profile()` to `DeviceAdapter`
2. Update existing adapters to report their prompt profile
3. Update `ComputerUseAgent` to choose prompts by profile
4. Extend shared command mapping for phone actions
5. Add the `android_adb` plugin files
6. Implement screenshot capture and PNG-prefix stripping
7. Implement adb command execution and action mappings
8. Add tests for prompt selection, screenshot handling, command mapping, and failures
9. Update documentation for the new built-in plugin
