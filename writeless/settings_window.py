"""Native macOS Settings window built with PyObjC."""

import AppKit
import objc
from Foundation import NSObject, NSMakeRect

from writeless.constants import WHISPER_MODELS
from writeless.hotkey_utils import (
    ns_event_to_pynput,
    pynput_to_display,
)

_WINDOW_WIDTH = 420
_ROW_HEIGHT = 36
_PADDING = 20
_LABEL_WIDTH = 180
_FIELD_HEIGHT = 28

# ── Hotkey capture field ─────────────────────────────────────────────────────


class HotkeyField(AppKit.NSTextField):
    """A text field that captures key combinations when focused."""

    @objc.python_method
    def initWithFrame_callback_(self, frame, callback):
        self = objc.super(HotkeyField, self).initWithFrame_(frame)
        if self is None:
            return None
        self._hotkey_callback = callback
        self._captured_pynput = None
        self.setEditable_(False)
        self.setSelectable_(False)
        self.setBezeled_(True)
        self.setBezelStyle_(1)  # NSTextFieldRoundedRect
        self.setAlignment_(AppKit.NSTextAlignmentCenter)
        self.setFocusRingType_(AppKit.NSFocusRingTypeExterior)
        font = AppKit.NSFont.systemFontOfSize_weight_(13, AppKit.NSFontWeightMedium)
        self.setFont_(font)
        return self

    def acceptsFirstResponder(self):
        return True

    def mouseDown_(self, event):
        self.window().makeFirstResponder_(self)

    def becomeFirstResponder(self):
        result = objc.super(HotkeyField, self).becomeFirstResponder()
        if result:
            self.setStringValue_("Press shortcut…")
            self.setTextColor_(AppKit.NSColor.placeholderTextColor())
        return result

    def resignFirstResponder(self):
        result = objc.super(HotkeyField, self).resignFirstResponder()
        if self._captured_pynput:
            display = pynput_to_display(self._captured_pynput)
            self.setStringValue_(display)
            self.setTextColor_(AppKit.NSColor.labelColor())
        else:
            self.setStringValue_("")
        return result

    def keyDown_(self, event):
        key_code = event.keyCode()
        modifier_flags = event.modifierFlags()
        pynput_str = ns_event_to_pynput(key_code, modifier_flags)
        if pynput_str:
            self._captured_pynput = pynput_str
            display = pynput_to_display(pynput_str)
            self.setStringValue_(display)
            self.setTextColor_(AppKit.NSColor.labelColor())
            self.window().makeFirstResponder_(None)
            if self._hotkey_callback:
                self._hotkey_callback(pynput_str)

    def flagsChanged_(self, event):
        # Show live modifier preview while pressing
        modifier_flags = event.modifierFlags()
        symbols = []
        for flag, sym in [
            (AppKit.NSEventModifierFlagControl, "⌃"),
            (AppKit.NSEventModifierFlagOption, "⌥"),
            (AppKit.NSEventModifierFlagShift, "⇧"),
            (AppKit.NSEventModifierFlagCommand, "⌘"),
        ]:
            if modifier_flags & flag:
                symbols.append(sym)
        if symbols:
            self.setStringValue_("".join(symbols) + "…")
            self.setTextColor_(AppKit.NSColor.placeholderTextColor())
        else:
            if not self._captured_pynput:
                self.setStringValue_("Press shortcut…")

    @objc.python_method
    def set_hotkey(self, pynput_str):
        """Set the displayed hotkey programmatically."""
        self._captured_pynput = pynput_str
        if pynput_str:
            self.setStringValue_(pynput_to_display(pynput_str))
            self.setTextColor_(AppKit.NSColor.labelColor())
        else:
            self.setStringValue_("")


# ── Action target (NSObject subclass for setTarget_/setAction_) ──────────────


class _ActionTarget(NSObject):
    """Bridges ObjC target/action to Python callbacks."""

    @objc.python_method
    def initWithCallbacks_(self, callbacks):
        self = objc.super(_ActionTarget, self).init()
        if self is None:
            return None
        self._callbacks = callbacks
        return self

    @objc.IBAction
    def notifToggled_(self, sender):
        if "notif_toggled" in self._callbacks:
            enabled = sender.state() == AppKit.NSControlStateValueOn
            self._callbacks["notif_toggled"](enabled)

    @objc.IBAction
    def sslToggled_(self, sender):
        if "ssl_toggled" in self._callbacks:
            enabled = sender.state() == AppKit.NSControlStateValueOn
            self._callbacks["ssl_toggled"](enabled)

    @objc.IBAction
    def modelChanged_(self, sender):
        if "model_changed" in self._callbacks:
            index = sender.indexOfSelectedItem()
            model_id = WHISPER_MODELS[index][0]
            self._callbacks["model_changed"](model_id)


# ── Window delegate ──────────────────────────────────────────────────────────


class _WindowDelegate(NSObject):
    """Handle window close — hide instead of destroy so we can reuse it."""

    def windowShouldClose_(self, sender):
        sender.orderOut_(None)
        return False


# ── Settings window ──────────────────────────────────────────────────────────


class SettingsWindow:
    """macOS Settings panel."""

    def __init__(
        self,
        current_hotkey: str,
        notifications_enabled: bool,
        ssl_verification_enabled: bool,
        current_model: str = "small",
        on_hotkey_change=None,
        on_notifications_change=None,
        on_ssl_change=None,
        on_model_change=None,
    ):
        self._on_hotkey_change = on_hotkey_change

        # ObjC action target
        self._target = _ActionTarget.alloc().initWithCallbacks_({
            "notif_toggled": on_notifications_change,
            "ssl_toggled": on_ssl_change,
            "model_changed": on_model_change,
        })

        num_rows = 4
        content_height = _PADDING * 2 + num_rows * _ROW_HEIGHT + (num_rows - 1) * 8
        frame = NSMakeRect(0, 0, _WINDOW_WIDTH, content_height)

        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
        )
        self._window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style, AppKit.NSBackingStoreBuffered, False
        )
        self._window.setTitle_("Settings")
        self._window.center()
        self._window.setLevel_(AppKit.NSFloatingWindowLevel)

        self._win_delegate = _WindowDelegate.alloc().init()
        self._window.setDelegate_(self._win_delegate)

        content = self._window.contentView()
        content.setWantsLayer_(True)

        y = content_height - _PADDING - _ROW_HEIGHT

        # Row 1: Keyboard shortcut
        self._add_label(content, "Keyboard shortcut", y)
        field_x = _LABEL_WIDTH + _PADDING
        field_width = _WINDOW_WIDTH - field_x - _PADDING
        self._hotkey_field = HotkeyField.alloc().initWithFrame_callback_(
            NSMakeRect(field_x, y + 4, field_width, _FIELD_HEIGHT),
            self._hotkey_changed,
        )
        self._hotkey_field.set_hotkey(current_hotkey)
        content.addSubview_(self._hotkey_field)

        y -= _ROW_HEIGHT + 8

        # Row 2: Notifications
        self._add_label(content, "Notifications", y)
        self._notif_switch = self._add_switch(
            content, y, notifications_enabled, b"notifToggled:"
        )

        y -= _ROW_HEIGHT + 8

        # Row 3: SSL Verification
        self._add_label(content, "SSL Verification", y)
        self._ssl_switch = self._add_switch(
            content, y, ssl_verification_enabled, b"sslToggled:"
        )

        y -= _ROW_HEIGHT + 8

        # Row 4: Whisper Model
        self._add_label(content, "Whisper Model", y)
        field_x = _LABEL_WIDTH + _PADDING
        field_width = _WINDOW_WIDTH - field_x - _PADDING
        self._model_popup = AppKit.NSPopUpButton.alloc().initWithFrame_pullsDown_(
            NSMakeRect(field_x, y + 2, field_width, _FIELD_HEIGHT),
            False,
        )
        for _model_id, label in WHISPER_MODELS:
            self._model_popup.addItemWithTitle_(label)
        current_index = next(
            (i for i, (mid, _) in enumerate(WHISPER_MODELS) if mid == current_model),
            2,  # fallback to "small" index
        )
        self._model_popup.selectItemAtIndex_(current_index)
        self._model_popup.setTarget_(self._target)
        self._model_popup.setAction_(b"modelChanged:")
        font = AppKit.NSFont.systemFontOfSize_(13)
        self._model_popup.setFont_(font)
        content.addSubview_(self._model_popup)

    def _add_label(self, parent, text, y):
        label = AppKit.NSTextField.labelWithString_(text)
        label.setFrame_(NSMakeRect(_PADDING, y + 6, _LABEL_WIDTH, 20))
        font = AppKit.NSFont.systemFontOfSize_(13)
        label.setFont_(font)
        parent.addSubview_(label)

    def _add_switch(self, parent, y, state, action_sel):
        switch = AppKit.NSSwitch.alloc().initWithFrame_(
            NSMakeRect(_WINDOW_WIDTH - _PADDING - 40, y + 4, 40, 24)
        )
        switch.setState_(AppKit.NSControlStateValueOn if state else AppKit.NSControlStateValueOff)
        switch.setTarget_(self._target)
        switch.setAction_(action_sel)
        parent.addSubview_(switch)
        return switch

    def _hotkey_changed(self, pynput_str):
        if self._on_hotkey_change:
            self._on_hotkey_change(pynput_str)

    def show(self):
        self._window.makeKeyAndOrderFront_(None)
        AppKit.NSApp().activateIgnoringOtherApps_(True)

    def update_state(self, notifications_enabled, ssl_verification_enabled, current_hotkey, current_model):
        """Refresh UI to match current app state (called when re-showing)."""
        self._hotkey_field.set_hotkey(current_hotkey)
        self._notif_switch.setState_(
            AppKit.NSControlStateValueOn if notifications_enabled else AppKit.NSControlStateValueOff
        )
        self._ssl_switch.setState_(
            AppKit.NSControlStateValueOn if ssl_verification_enabled else AppKit.NSControlStateValueOff
        )
        current_index = next(
            (i for i, (mid, _) in enumerate(WHISPER_MODELS) if mid == current_model),
            2,
        )
        self._model_popup.selectItemAtIndex_(current_index)
