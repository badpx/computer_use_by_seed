# Global Natural Scroll Design

## Summary

Make `NATURAL_SCROLL` a true device-agnostic scroll semantic instead of a local-device-only behavior.

After this change:

- `NATURAL_SCROLL` only affects the `scroll` action
- scroll direction flipping happens once in the shared command normalization pipeline
- all device plugins receive the already-normalized direction
- `local` no longer performs its own natural-scroll inversion
- `android_adb` automatically inherits the same behavior without device-specific logic

This change does not affect `swipe`, `drag`, or any non-scroll action.

## Current Problem

`ComputerUseAgent` already reads `NATURAL_SCROLL` and injects it into every device configuration, but only the `local` device actually consumes it.

Current behavior:

- `local` flips scroll amount inside the local executor
- `android_adb` ignores `natural_scroll`
- other future devices would also ignore it unless they each reimplement the same logic

This means `NATURAL_SCROLL` is currently a partially global configuration with a local-only implementation.

## Goals

- Make scroll direction semantics consistent across devices
- Keep device plugins focused on device execution, not user preference interpretation
- Preserve current local behavior after the refactor
- Make `android_adb` respect `NATURAL_SCROLL` without adding Android-specific inversion logic

## Non-Goals

- Do not apply `NATURAL_SCROLL` to `swipe`
- Do not apply `NATURAL_SCROLL` to `drag`
- Do not change coordinate normalization
- Do not add new config keys or CLI flags

## Design

### Canonical Scroll Semantics

The shared device-command pipeline will treat `scroll.direction` as user-intent direction.

When `natural_scroll` is enabled:

- `up` becomes `down`
- `down` becomes `up`
- `left` becomes `right`
- `right` becomes `left`

When `natural_scroll` is disabled:

- `direction` stays unchanged

This flip happens exactly once before dispatching the command to any device adapter.

### Shared Normalization Layer

Add a small shared helper in the device layer, alongside coordinate normalization, to normalize scroll direction:

- input: `DeviceCommand`, `natural_scroll`
- output: `DeviceCommand`

Behavior:

- if `command_type != "scroll"`, return unchanged
- if `natural_scroll` is false, return unchanged
- if payload has a supported `direction`, replace it with the opposite direction
- if `direction` is missing, keep the existing downstream default behavior

This keeps the change narrow and avoids mixing scroll preference logic into every adapter.

### Agent Integration

`ComputerUseAgent` should apply scroll-direction normalization in the same command-building pipeline that already performs shared command mapping and coordinate normalization.

The order should be:

1. map parsed action to `DeviceCommand`
2. normalize coordinates
3. normalize scroll direction using `natural_scroll`
4. dispatch to the selected device

This ensures every device sees the same already-normalized scroll intent.

### Local Device Changes

The `local` executor should stop inverting scroll amount based on its own `natural_scroll` field.

After the refactor, local scroll execution should simply:

- interpret `direction` literally
- compute the scroll amount from that direction
- execute it

The local adapter may still accept `natural_scroll` in config for backward compatibility, but it should no longer affect execution inside the local plugin.

### Android ADB Changes

`android_adb` should not gain any special-case natural-scroll code.

Its existing `scroll.direction -> input touchscreen scroll --axis ...` mapping should remain unchanged.

It will respect `NATURAL_SCROLL` automatically because the command reaches it with already-flipped direction when needed.

## Testing

Add or update tests for:

- shared normalization flips `scroll.direction` when `natural_scroll=True`
- shared normalization leaves non-scroll commands unchanged
- shared normalization leaves `scroll.direction` unchanged when `natural_scroll=False`
- local execution no longer performs its own inversion
- local behavior remains the same end-to-end after shared normalization
- `android_adb` receives the flipped direction when `natural_scroll=True`

Regression intent:

- local users should observe no behavior change
- Android users should start observing the same natural-scroll semantics

## Risks and Mitigations

### Risk: Double inversion on local

If the local executor keeps its old inversion logic after shared normalization is introduced, local scroll direction will be flipped twice.

Mitigation:

- remove the local inversion logic in the same change
- add an explicit regression test for local end-to-end behavior

### Risk: Scope accidentally expands to swipe

`swipe` is also direction-like from a user perspective, but it is a coordinate-driven gesture and should not be affected.

Mitigation:

- keep the shared helper strictly scoped to `command_type == "scroll"`
- add a test proving non-scroll commands are unchanged
