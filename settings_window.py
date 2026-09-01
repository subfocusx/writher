"""Settings window — Recording, Microphone, Autostart only."""

import json
import os
import threading

import tkinter as tk
import sounddevice as sd
import customtkinter as ctk
from PIL import ImageTk

from logger import log
import config
import database as db
import locales
from brand import make_title_bar_image
import theme as T
from recorder import _sd_lock  # shared with recorder._resolve_device
from models_registry import discover_models

_WIN_W, _WIN_H = 460, 500
_TITLE_H = 40


class SettingsWindow:
    def __init__(self, root: tk.Tk, engine=None):
        self._root = root
        self._engine = engine
        self._win = None
        self._drag_x = 0
        self._drag_y = 0
        self._title_eye_tk = None
        # Recording mode
        self._hold_btn = None
        self._toggle_btn = None
        self._slider = None
        self._slider_val_label = None
        self._slider_section = None
        # VAD
        self._vad_slider = None
        self._vad_slider_val_label = None
        self._vad_section = None
        # Microphone
        self._mic_dropdown = None
        self._mic_devices = []
        self._refresh_btn = None
        # ASR model
        self._model_dropdown = None
        self._model_rescan_btn = None
        self._model_folder_btn = None
        self._model_status_label = None
        self._model_specs = []
        self._models_dir = db.get_setting("asr_models_dir", "") or None
        # Autostart
        self._autostart_switch = None
        # Recognition accuracy (audio pre-processing toggles)
        self._pp_switches = {}

    def show(self):
        if self._win is not None:
            try:
                if self._win.winfo_exists():
                    self._win.attributes("-topmost", True)
                    self._win.lift()
                    self._win.focus_force()
                    # Drop the always-on-top flag after 100ms (otherwise the
                    # window stays above all others forever and steals focus
                    # from the active app — bug reported in audit). Matches
                    # NotesWindow.show() behaviour.
                    self._win.after(100, lambda: self._win.attributes("-topmost", False)
                                    if self._win and self._win.winfo_exists() else None)
                    self._sync_ui()
                    return
            except Exception:
                pass
        self._build()
        self._sync_ui()

    def _build(self):
        win = ctk.CTkToplevel(self._root)
        win.overrideredirect(True)
        win.configure(fg_color=T.BG_DEEP)
        win.attributes("-topmost", True)

        saved = db.get_setting("settings_window_geometry")
        if saved:
            win.geometry(saved)
        else:
            sx = win.winfo_screenwidth()
            sy = win.winfo_screenheight()
            x = (sx - _WIN_W) // 2
            y = (sy - _WIN_H) // 2
            win.geometry(f"{_WIN_W}x{_WIN_H}+{x}+{y}")
        self._win = win

        outer = ctk.CTkFrame(win, fg_color=T.BG_DEEP, border_color=T.BORDER,
                             border_width=1, corner_radius=0)
        outer.pack(fill="both", expand=True)

        # ── Title bar ────────────────────────────────────────────────
        title_bar = ctk.CTkFrame(outer, fg_color=T.TITLE_BG, height=_TITLE_H,
                                 corner_radius=0)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        eye_img = make_title_bar_image(size=20)
        self._title_eye_tk = ImageTk.PhotoImage(eye_img)
        eye_lbl = tk.Label(title_bar, image=self._title_eye_tk, bg=T.TITLE_BG)
        eye_lbl.pack(side="left", padx=(14, 8))

        title_lbl = ctk.CTkLabel(title_bar, text=locales.get("settings_title"),
                                 font=T.FONT_TITLE, text_color=T.FG)
        title_lbl.pack(side="left")

        close_btn = ctk.CTkButton(
            title_bar, text="✕", width=44, height=_TITLE_H,
            fg_color="transparent", hover_color=T.CLOSE_HOVER,
            text_color=T.FG_DIM, font=(T.FONT_FAMILY, 15),
            corner_radius=0, command=self._close,
        )
        close_btn.pack(side="right")

        for w in (title_bar, title_lbl):
            w.bind("<Button-1>", self._start_drag)
            w.bind("<B1-Motion>", self._on_drag)

        # ── Scrollable content ────────────────────────────────────────
        scroll = ctk.CTkScrollableFrame(
            outer, fg_color=T.BG, corner_radius=0,
            scrollbar_button_color=T.BORDER,
            scrollbar_button_hover_color=T.BORDER_GLOW,
        )
        scroll.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        pad = ctk.CTkFrame(scroll, fg_color="transparent")
        pad.pack(fill="both", expand=True, padx=T.PAD_L, pady=T.PAD_L)

        # ── 1. Recording mode ────────────────────────────────────────
        self._build_section_label(pad, locales.get("setting_record_mode"))

        btn_row = ctk.CTkFrame(pad, fg_color="transparent")
        btn_row.pack(fill="x", pady=(0, T.PAD_M))

        self._hold_btn = ctk.CTkButton(
            btn_row, text=locales.get("setting_hold"),
            font=T.FONT_SMALL, height=36, corner_radius=6,
            fg_color=T.BG_CARD, hover_color=T.BG_HOVER,
            border_color=T.BORDER, border_width=1,
            text_color=T.FG, command=lambda: self._set_mode(True),
        )
        self._hold_btn.pack(side="left", padx=(0, T.PAD_M))

        self._toggle_btn = ctk.CTkButton(
            btn_row, text=locales.get("setting_toggle"),
            font=T.FONT_SMALL, height=36, corner_radius=6,
            fg_color=T.BG_CARD, hover_color=T.BG_HOVER,
            border_color=T.BORDER, border_width=1,
            text_color=T.FG, command=lambda: self._set_mode(False),
        )
        self._toggle_btn.pack(side="left")

        # Max duration (toggle only)
        self._slider_section = ctk.CTkFrame(pad, fg_color="transparent")
        self._slider_section.pack(fill="x")

        lbl_row = ctk.CTkFrame(self._slider_section, fg_color="transparent")
        lbl_row.pack(fill="x", pady=(0, T.PAD_S))

        ctk.CTkLabel(lbl_row, text=locales.get("setting_max_duration"),
                     font=T.FONT_SMALL, text_color=T.FG_DIM,
                     anchor="w").pack(side="left")

        self._slider_val_label = ctk.CTkLabel(
            lbl_row, text="120s", font=T.FONT_SMALL,
            text_color=T.ACCENT, anchor="e",
        )
        self._slider_val_label.pack(side="right")

        self._slider = ctk.CTkSlider(
            self._slider_section, from_=30, to=300,
            fg_color=T.BG_INPUT, progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
            height=16, corner_radius=8,
            command=self._on_slider_change,
        )
        self._slider.pack(fill="x")

        # VAD auto-stop (toggle only)
        self._vad_section = ctk.CTkFrame(pad, fg_color="transparent")
        self._vad_section.pack(fill="x")

        vad_lbl_row = ctk.CTkFrame(self._vad_section, fg_color="transparent")
        vad_lbl_row.pack(fill="x", pady=(0, T.PAD_S))

        ctk.CTkLabel(vad_lbl_row, text=locales.get("setting_vad_auto_stop"),
                     font=T.FONT_SMALL, text_color=T.FG_DIM,
                     anchor="w").pack(side="left")

        self._vad_slider_val_label = ctk.CTkLabel(
            vad_lbl_row, text="2.0s", font=T.FONT_SMALL,
            text_color=T.ACCENT, anchor="e",
        )
        self._vad_slider_val_label.pack(side="right")

        self._vad_slider = ctk.CTkSlider(
            self._vad_section, from_=0.5, to=5.0, number_of_steps=45,
            fg_color=T.BG_INPUT, progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
            height=16, corner_radius=8,
            command=self._on_vad_slider_change,
        )
        self._vad_slider.pack(fill="x")

        self._build_separator(pad)

        # ── 2. Microphone ────────────────────────────────────────────
        self._build_section_label(pad, locales.get("setting_microphone"))

        mic_row = ctk.CTkFrame(pad, fg_color="transparent")
        mic_row.pack(fill="x", pady=(0, T.PAD_M))

        self._mic_devices = self._get_input_devices()
        mic_names = [name for _, name in self._mic_devices]

        self._mic_dropdown = ctk.CTkComboBox(
            mic_row, values=mic_names, font=T.FONT_SMALL,
            dropdown_font=T.FONT_SMALL,
            fg_color=T.BG_CARD, border_color=T.BORDER,
            button_color=T.BORDER_GLOW, button_hover_color=T.FG_DIM,
            dropdown_fg_color=T.BG_CARD, dropdown_hover_color=T.BG_HOVER,
            dropdown_text_color=T.FG, text_color=T.FG,
            height=36, corner_radius=6,
            command=self._on_mic_change, state="readonly",
        )
        self._mic_dropdown.pack(side="left", fill="x", expand=True)

        self._refresh_btn = ctk.CTkButton(
            mic_row, text="⟳", width=36, height=36,
            fg_color=T.BG_CARD, hover_color=T.BG_HOVER,
            border_color=T.BORDER, border_width=1,
            text_color=T.FG, font=(T.FONT_FAMILY, 16),
            corner_radius=6, command=self._on_refresh_mic,
        )
        self._refresh_btn.pack(side="right", padx=(T.PAD_M, 0))

        self._build_separator(pad)

        # ── 3. ASR model ─────────────────────────────────────────────
        self._build_section_label(pad, locales.get("setting_asr_model"))

        model_row = ctk.CTkFrame(pad, fg_color="transparent")
        model_row.pack(fill="x", pady=(0, T.PAD_M))

        self._model_dropdown = ctk.CTkComboBox(
            model_row, values=[], font=T.FONT_SMALL,
            dropdown_font=T.FONT_SMALL,
            fg_color=T.BG_CARD, border_color=T.BORDER,
            button_color=T.BORDER_GLOW, button_hover_color=T.FG_DIM,
            dropdown_fg_color=T.BG_CARD, dropdown_hover_color=T.BG_HOVER,
            dropdown_text_color=T.FG, text_color=T.FG,
            height=36, corner_radius=6,
            command=self._on_model_change, state="readonly",
        )
        self._model_dropdown.pack(side="left", fill="x", expand=True)

        self._model_rescan_btn = ctk.CTkButton(
            model_row, text=locales.get("setting_asr_model_rescan"),
            width=72, height=36,
            fg_color=T.BG_CARD, hover_color=T.BG_HOVER,
            border_color=T.BORDER, border_width=1,
            text_color=T.FG, font=(T.FONT_FAMILY, 13),
            corner_radius=6, command=self._on_refresh_model,
        )
        self._model_rescan_btn.pack(side="right", padx=(T.PAD_M, 0))

        model_row2 = ctk.CTkFrame(pad, fg_color="transparent")
        model_row2.pack(fill="x", pady=(0, T.PAD_M))

        self._model_folder_btn = ctk.CTkButton(
            model_row2, text=locales.get("setting_asr_model_choose"),
            height=32,
            fg_color=T.BG_CARD, hover_color=T.BG_HOVER,
            border_color=T.BORDER, border_width=1,
            text_color=T.FG, font=T.FONT_SMALL,
            corner_radius=6, command=self._on_choose_folder,
        )
        self._model_folder_btn.pack(side="left")

        self._model_status_label = ctk.CTkLabel(
            model_row2, text="", font=T.FONT_SMALL,
            text_color=T.FG_DIM, anchor="w",
        )
        self._model_status_label.pack(side="left", padx=(T.PAD_M, 0))

        self._build_separator(pad)

        # ── 4. Recognition accuracy ──────────────────────────────────
        self._build_section_label(pad, locales.get("setting_accuracy"))

        hint = ctk.CTkLabel(
            pad, text=locales.get("setting_pp_hint"),
            font=T.FONT_SMALL, text_color=T.FG_DIM, anchor="w", wraplength=390,
        )
        hint.pack(fill="x", pady=(0, T.PAD_S))

        for flag, key, text in (
            ("PP_NORMALIZE", "pp_normalize", locales.get("setting_pp_normalize")),
            ("PP_HIGHPASS", "pp_highpass", locales.get("setting_pp_highpass")),
            ("PP_DENOISE", "pp_denoise", locales.get("setting_pp_denoise")),
            ("PP_PREEMPHASIS", "pp_preemphasis", locales.get("setting_pp_preemphasis")),
        ):
            row = ctk.CTkFrame(pad, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=text, font=T.FONT_SMALL,
                         text_color=T.FG, anchor="w").pack(side="left")
            sw = ctk.CTkSwitch(
                row, text="",
                fg_color=T.BG_INPUT, progress_color=T.ACCENT,
                button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
                command=lambda f=flag, k=key: self._on_pp_toggle(f, k),
            )
            sw.pack(side="right")
            self._pp_switches[key] = sw

        self._build_separator(pad)

        # ── 5. Autostart ─────────────────────────────────────────────
        self._build_section_label(pad, locales.get("setting_autostart"))

        self._autostart_switch = ctk.CTkSwitch(
            pad, text="", font=T.FONT_SMALL,
            fg_color=T.BG_INPUT, progress_color=T.ACCENT,
            button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER,
            command=self._on_autostart_toggle,
        )
        self._autostart_switch.pack(anchor="w")

    # ── Helpers ───────────────────────────────────────────────────────────

    def _build_section_label(self, parent, text: str):
        ctk.CTkLabel(parent, text=text, font=T.FONT_TITLE, text_color=T.FG,
                     anchor="w").pack(fill="x", pady=(0, T.PAD_S))

    def _build_separator(self, parent):
        ctk.CTkFrame(parent, fg_color=T.BORDER, height=1,
                     corner_radius=0).pack(fill="x", pady=T.PAD_M)

    # ── Drag ──────────────────────────────────────────────────────────────

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _on_drag(self, event):
        if self._win:
            x = self._win.winfo_x() + (event.x - self._drag_x)
            y = self._win.winfo_y() + (event.y - self._drag_y)
            self._win.geometry(f"+{x}+{y}")

    def _close(self):
        if self._win:
            try:
                db.save_setting("settings_window_geometry", self._win.geometry())
            except Exception:
                pass
            try:
                self._win.destroy()
            except Exception:
                pass
            self._win = None

    # ── UI sync ───────────────────────────────────────────────────────────

    def _sync_ui(self):
        hold = getattr(config, "HOLD_TO_RECORD", True)
        self._update_mode_buttons(hold)
        max_sec = getattr(config, "MAX_RECORD_SECONDS", 120)
        if self._slider:
            self._slider.set(max_sec)
        if self._slider_val_label:
            self._slider_val_label.configure(text=f"{max_sec}s")
        vad_sec = getattr(config, "VAD_AUTO_STOP_SECONDS", 2.0)
        if self._vad_slider:
            self._vad_slider.set(vad_sec)
        if self._vad_slider_val_label:
            self._vad_slider_val_label.configure(text=f"{vad_sec}s")
        self._update_slider_visibility(hold)

        self._refresh_mic_list()
        self._sync_mic_dropdown()

        self._refresh_model_list()
        self._sync_model_dropdown()

        if self._autostart_switch:
            import autostart
            self._autostart_switch.select() if autostart.is_autostart_enabled() \
                else self._autostart_switch.deselect()

        for flag, key in (
            ("PP_NORMALIZE", "pp_normalize"),
            ("PP_HIGHPASS", "pp_highpass"),
            ("PP_DENOISE", "pp_denoise"),
            ("PP_PREEMPHASIS", "pp_preemphasis"),
        ):
            sw = self._pp_switches.get(key)
            if sw is None:
                continue
            on = bool(getattr(config, flag, False))
            if on:
                sw.select()
            else:
                sw.deselect()

    def _update_mode_buttons(self, hold: bool):
        if self._hold_btn:
            if hold:
                self._hold_btn.configure(
                    fg_color=T.FG, text_color="#000000",
                    border_color=T.FG, hover_color=T.ACCENT_HOVER,
                )
            else:
                self._hold_btn.configure(
                    fg_color=T.BG_CARD, text_color=T.FG,
                    border_color=T.BORDER, hover_color=T.BG_HOVER,
                )
        if self._toggle_btn:
            if not hold:
                self._toggle_btn.configure(
                    fg_color=T.FG, text_color="#000000",
                    border_color=T.FG, hover_color=T.ACCENT_HOVER,
                )
            else:
                self._toggle_btn.configure(
                    fg_color=T.BG_CARD, text_color=T.FG,
                    border_color=T.BORDER, hover_color=T.BG_HOVER,
                )

    def _update_slider_visibility(self, hold: bool):
        if self._slider_section:
            if hold:
                self._slider_section.pack_forget()
            else:
                self._slider_section.pack(fill="x")
        if self._vad_section:
            if hold:
                self._vad_section.pack_forget()
            else:
                self._vad_section.pack(fill="x")

    # ── Callbacks ─────────────────────────────────────────────────────────

    def _set_mode(self, hold: bool):
        config.HOLD_TO_RECORD = hold
        db.save_setting("hold_to_record", "1" if hold else "0")
        self._update_mode_buttons(hold)
        self._update_slider_visibility(hold)
        log.info("Recording mode set to %s", "hold" if hold else "toggle")

    def _on_slider_change(self, value):
        seconds = int(float(value))
        config.MAX_RECORD_SECONDS = seconds
        db.save_setting("max_record_seconds", str(seconds))
        if self._slider_val_label:
            self._slider_val_label.configure(text=f"{seconds}s")

    def _on_vad_slider_change(self, value):
        seconds = round(float(value), 1)
        config.VAD_AUTO_STOP_SECONDS = seconds
        db.save_setting("vad_auto_stop_seconds", str(seconds))
        if self._vad_slider_val_label:
            self._vad_slider_val_label.configure(text=f"{seconds}s")

    def _on_autostart_toggle(self):
        enabled = bool(self._autostart_switch.get())
        import autostart
        ok = autostart.set_autostart(enabled)
        if ok:
            config.AUTOSTART = enabled
            db.save_setting("autostart", "1" if enabled else "0")
        else:
            log.warning("Autostart not supported on this platform.")
            self._autostart_switch.select() if autostart.is_autostart_enabled() \
                else self._autostart_switch.deselect()

    def _on_pp_toggle(self, flag: str, key: str):
        """Audio pre-processing switch — live effect on the next dictation."""
        sw = self._pp_switches.get(key)
        enabled = bool(sw.get()) if sw is not None else bool(getattr(config, flag, False))
        setattr(config, flag, enabled)
        db.save_setting(key, "1" if enabled else "0")
        log.info("Pre-processing %s -> %s", flag, enabled)

    # ── Microphone helpers ────────────────────────────────────────────────

    @staticmethod
    def _get_input_devices() -> list[tuple[int | None, str]]:
        default_label = locales.get("setting_mic_default")
        devices = [(None, default_label)]
        try:
            # Shared lock with recorder._resolve_device() — see recorder.py.
            with _sd_lock:
                sd._terminate()
                sd._initialize()
            all_devs = sd.query_devices()
            host_apis = sd.query_hostapis()
            wasapi_idx = None
            for i, api in enumerate(host_apis):
                if "WASAPI" in api.get("name", ""):
                    wasapi_idx = i
                    break
            seen_names = set()
            for i, dev in enumerate(all_devs):
                if dev["max_input_channels"] <= 0:
                    continue
                if wasapi_idx is not None and dev.get("hostapi") != wasapi_idx:
                    continue
                name = dev["name"]
                if name in seen_names:
                    continue
                seen_names.add(name)
                devices.append((i, name))
            if len(devices) == 1:
                seen_names.clear()
                for i, dev in enumerate(all_devs):
                    if dev["max_input_channels"] > 0:
                        name = dev["name"]
                        if name not in seen_names:
                            seen_names.add(name)
                            devices.append((i, name))
        except Exception as exc:
            log.warning("Could not enumerate audio devices: %s", exc)
        return devices

    def _sync_mic_dropdown(self):
        if not self._mic_dropdown:
            return
        current_name = getattr(config, "MIC_DEVICE_NAME", None)
        if current_name:
            for idx, name in self._mic_devices:
                if name == current_name:
                    self._mic_dropdown.set(name)
                    return
        if self._mic_devices:
            self._mic_dropdown.set(self._mic_devices[0][1])

    def _refresh_mic_list(self):
        self._mic_devices = self._get_input_devices()
        if self._mic_dropdown:
            mic_names = [name for _, name in self._mic_devices]
            self._mic_dropdown.configure(values=mic_names)

    def _on_mic_change(self, selected_name: str):
        for idx, name in self._mic_devices:
            if name == selected_name:
                if idx is None:
                    config.MIC_DEVICE_NAME = None
                    db.save_setting("mic_device_name", "none")
                else:
                    config.MIC_DEVICE_NAME = name
                    db.save_setting("mic_device_name", name)
                log.info("Microphone set to: %s", name)
                return

    def _on_refresh_mic(self):
        self._refresh_mic_list()
        self._sync_mic_dropdown()
        log.info("Microphone list refreshed.")
        if self._refresh_btn:
            self._refresh_btn.configure(fg_color=T.GREEN, text_color="#000000")
            self._refresh_btn.after(
                500, lambda: self._refresh_btn.configure(
                    fg_color=T.BG_CARD, text_color=T.FG)
                if self._refresh_btn and self._win else None
            )

    # ── ASR model ─────────────────────────────────────────────────────────

    def _refresh_model_list(self):
        """Scan bundled + custom model dirs, keeping the active model present."""
        dirs = [self._models_dir] if self._models_dir else []
        specs = discover_models(dirs)
        if self._engine and self._engine.current_spec is not None:
            current = self._engine.current_spec
            if not any(s.id == current.id for s in specs):
                specs.insert(0, current)
        self._model_specs = specs
        if self._model_dropdown:
            self._model_dropdown.configure(values=[s.label for s in specs])
        return specs

    def _sync_model_dropdown(self):
        if not self._model_dropdown:
            return
        labels = [s.label for s in self._model_specs]
        if not labels:
            self._model_dropdown.set("")
            return
        target = ""
        if self._engine and self._engine.current_spec is not None:
            cur = self._engine.current_spec
            for s in self._model_specs:
                if s.label == cur.label:
                    target = s.label
                    break
            if not target:
                for s in self._model_specs:
                    if s.id == cur.id:
                        target = s.label
                        break
        if not target:
            target = labels[0]
        self._model_dropdown.set(target)

    def _set_model_status(self, text: str):
        if self._model_status_label and self._win and self._win.winfo_exists():
            self._model_status_label.configure(text=text)

    def _on_model_change(self, selected_label: str):
        spec = next((s for s in self._model_specs if s.label == selected_label), None)
        if spec is None:
            return
        db.save_setting("asr_model", json.dumps(spec.to_dict()))
        log.info("ASR model selected: %s", spec.label)
        if not self._engine:
            return
        self._set_model_status(locales.get("setting_asr_model_loading"))
        threading.Thread(target=self._do_model_switch, args=(spec,),
                         daemon=True).start()

    def _do_model_switch(self, spec):
        try:
            self._engine.switch(spec)
        except Exception as exc:
            log.error("ASR model switch failed: %s", exc)
        finally:
            if self._win and self._win.winfo_exists():
                self._win.after(0, lambda: self._set_model_status(""))

    def _on_choose_folder(self):
        if not self._win:
            return
        from tkinter import filedialog
        folder = filedialog.askdirectory(
            parent=self._win,
            title=locales.get("setting_asr_model_choose_title"),
            initialdir=self._models_dir or os.path.expanduser("~"),
        )
        if not folder:
            return
        self._models_dir = folder
        db.save_setting("asr_models_dir", folder)
        self._refresh_model_list()
        self._sync_model_dropdown()
        log.info("Models folder set to: %s", folder)

    def _on_refresh_model(self):
        self._refresh_model_list()
        self._sync_model_dropdown()
        log.info("ASR model list refreshed.")
        if self._model_rescan_btn:
            self._model_rescan_btn.configure(fg_color=T.GREEN, text_color="#000000")
            self._model_rescan_btn.after(
                500, lambda: self._model_rescan_btn.configure(
                    fg_color=T.BG_CARD, text_color=T.FG)
                if self._model_rescan_btn and self._win else None
            )
