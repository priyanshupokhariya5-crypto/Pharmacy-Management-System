"""
Main Entry Point for Pharmacy Management System Desktop Application.
Initializes database schema and launches the CustomTkinter GUI application.

Login flow: a single CTk root window shows the login panel first, then
swaps to the main application content in-place (no second window opened).
"""
import sys
import os

# Add project root directory to sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import customtkinter as ctk

from database.schema import init_db
from models.user import User
from ui.theme import Theme
from services.auth_service import AuthService
from services.medicine_service import MedicineService
from utils.benchmark import SearchBenchmark
from utils.logger import get_app_logger

ctk.set_appearance_mode(Theme.APPEARANCE_MODE)
ctk.set_default_color_theme(Theme.COLOR_THEME)

# Deactivate CustomTkinter's Windows header manipulation which repeatedly withdraws
# and unmaps the window during startup, causing Windows to revoke foreground permission.
if sys.platform.startswith("win"):
    ctk.CTk._deactivate_windows_window_header_manipulation = True


class PharmacyApp(ctk.CTk):
    """
    Single root-window application.

    Shows the login panel on startup.
    On successful authentication the login panel is destroyed and the
    MainWindow content is built inside the same root window so the OS
    window is never destroyed or replaced.
    On logout the main content is destroyed and the login panel is
    rebuilt inside the same window.
    """

    def __init__(self):
        super().__init__()
        self.logger = get_app_logger()
        self.title("Pharmacy Management System – Login")
        self.configure(fg_color=Theme.BG_DARK)
        self._setup_window_geometry()
        self._apply_global_scroll_patch()
        self._login_frame = None
        self._signup_frame = None
        self._main_content = None
        self._show_login()
        self._bring_to_foreground()

    def _setup_window_geometry(self) -> None:
        """
        Configures responsive initial window sizing:
        - Sets minimum dimensions for smaller displays (980x640).
        - Allows standard resizing and maximize controls.
        - Computes large centered fallback dimensions (e.g. 1200x760).
        - Maximizes on Windows using state('zoomed').
        """
        self.minsize(980, 640)
        self.resizable(True, True)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = min(1280, max(980, int(screen_w * 0.88)))
        target_h = min(820, max(640, int(screen_h * 0.88)))
        self._center(target_w, target_h)

        try:
            self.state('zoomed')
        except Exception:
            try:
                self.attributes('-zoomed', True)
            except Exception:
                pass

    def _apply_global_scroll_patch(self) -> None:
        """
        Creates ONE reliable centralized scrolling mechanism for the entire app.
        Replaces conflicting/buggy CustomTkinter and Tkinter default handlers.
        """
        import tkinter as tk
        from tkinter import ttk

        # 1. Unbind native class handlers that steal and trap events
        self.unbind_class('Treeview', '<MouseWheel>')
        self.unbind_class('Text', '<MouseWheel>')
        self.unbind_class('Canvas', '<MouseWheel>')

        # 2. Bind at the Window level (runs after instance/class, but BEFORE bind_all)
        self.bind('<MouseWheel>', self._on_global_mousewheel)

        # Patch CustomTkinter Dropdowns for readability
        import customtkinter as ctk
        ctk.ThemeManager.theme["CTkOptionMenu"]["fg_color"] = ["#FFFFFF", "#FFFFFF"]
        ctk.ThemeManager.theme["CTkOptionMenu"]["button_color"] = [Theme.PRIMARY, Theme.PRIMARY]
        ctk.ThemeManager.theme["CTkOptionMenu"]["button_hover_color"] = [Theme.PRIMARY_HOVER, Theme.PRIMARY_HOVER]
        ctk.ThemeManager.theme["CTkOptionMenu"]["text_color"] = [Theme.TEXT_MAIN, Theme.TEXT_MAIN]
        ctk.ThemeManager.theme["DropdownMenu"]["fg_color"] = ["#FFFFFF", "#FFFFFF"]
        ctk.ThemeManager.theme["DropdownMenu"]["hover_color"] = [Theme.INPUT_BG, Theme.INPUT_BG]
        ctk.ThemeManager.theme["DropdownMenu"]["text_color"] = [Theme.TEXT_MAIN, Theme.TEXT_MAIN]

    def _on_global_mousewheel(self, event):
        import tkinter as tk
        from tkinter import ttk

        delta = event.delta
        if not delta:
            return 'break'
            
        scroll_dir = -1 if delta > 0 else 1
        
        # Find the actual widget under the pointer
        x, y = self.winfo_pointerxy()
        try:
            target = self.winfo_containing(x, y)
        except Exception:
            target = event.widget

        curr = target
        while curr:
            scrolled = False
            
            # Check Treeview
            if isinstance(curr, ttk.Treeview) and curr.cget('yscrollcommand'):
                yview = curr.yview()
                if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                    curr.yview_scroll(int(-1 * (delta / 120)), 'units')
                    scrolled = True

            # Check Text / CTkTextbox
            elif isinstance(curr, tk.Text):
                yview = curr.yview()
                if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                    curr.yview_scroll(int(-1 * (delta / 120)), 'units')
                    scrolled = True

            # Check Canvas (CTkScrollableFrame uses a Canvas internally)
            elif isinstance(curr, tk.Canvas):
                scrollregion = curr.cget("scrollregion")
                if scrollregion:
                    yview = curr.yview()
                    if not ((scroll_dir < 0 and yview[0] <= 0.001) or (scroll_dir > 0 and yview[1] >= 0.999)):
                        # CustomTkinter Canvas uses yscrollincrement=1 (1 unit = 1 px).
                        # Multiply by 60 to scroll a standard 60 pixels per notch.
                        scroll_amount = int(-1 * (delta / 120) * 60)
                        curr.yview_scroll(scroll_amount, 'units')
                        scrolled = True

            if scrolled:
                break
                
            curr = curr.master
            
        # Always break to prevent CTk bind_all from firing and causing jumps
        return 'break'

    def _center(self, width: int = None, height: int = None) -> None:
        """Centers the window on the primary screen at the given dimensions."""
        self.update_idletasks()
        w = width or self.winfo_width()
        h = height or self.winfo_height()
        if w <= 1 or w == 200:
            w = width or 450
        if h <= 1 or h == 200:
            h = height or 620
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        x = max(0, (screen_w - w) // 2)
        y = max(0, (screen_h - h) // 2)
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _bring_to_foreground(self) -> None:
        """
        Ensures the application window appears cleanly in the foreground
        on initial launch without aggressive focus stealing or repetitive timers.
        """
        self.deiconify()
        self.lift()
        self.attributes('-topmost', True)
        self.after_idle(lambda: self.attributes('-topmost', False))
        if sys.platform.startswith("win"):
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
                if not hwnd:
                    hwnd = self.winfo_id()
                ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        self.focus_force()

    # ------------------------------------------------------------------
    # Login panel
    # ------------------------------------------------------------------

    def _show_login(self, prefill_username: str = "", message: str = "", is_success: bool = False) -> None:
        """Build the login card inside the root window without changing window geometry."""
        self.title("Pharmacy Management System – Login")
        if hasattr(self, '_signup_frame') and self._signup_frame:
            self._signup_frame.destroy()
            self._signup_frame = None
        if hasattr(self, '_login_frame') and self._login_frame:
            self._login_frame.destroy()
            self._login_frame = None

        self._login_frame = _LoginPanel(
            self,
            on_success=self._on_login_success,
            on_signup_click=self._show_signup,
            prefill_username=prefill_username,
            initial_message=message,
            is_success=is_success
        )
        self._login_frame.pack(fill="both", expand=True)

    def _show_signup(self) -> None:
        """Build the signup card inside the root window without changing window geometry."""
        self.title("Pharmacy Management System – Register Store")
        if hasattr(self, '_login_frame') and self._login_frame:
            self._login_frame.destroy()
            self._login_frame = None
        if hasattr(self, '_signup_frame') and self._signup_frame:
            self._signup_frame.destroy()
            self._signup_frame = None

        self._signup_frame = _SignupPanel(
            self,
            on_login_click=lambda: self._show_login(),
            on_signup_success=self._on_signup_success
        )
        self._signup_frame.pack(fill="both", expand=True)

    def _on_signup_success(self, created_user: User, message: str) -> None:
        """Redirect to login screen upon successful store registration."""
        self._show_login(prefill_username=created_user.username, message=message, is_success=True)

    def _on_login_success(self, user: User) -> None:
        """Swap login panel → main content in the same window smoothly without flicker."""
        self.logger.log_event("AUTH",
                              f"User '{user.username}' (Store: {user.store_name}) logged in successfully.")
        # Destroy login panel
        if hasattr(self, '_login_frame') and self._login_frame:
            self._login_frame.destroy()
            self._login_frame = None
        if hasattr(self, '_signup_frame') and self._signup_frame:
            self._signup_frame.destroy()
            self._signup_frame = None

        self.title(f"Pharmacy Management System – {user.store_name}")

        # Build main window content inside the same root
        from ui.main_window import MainWindowContent
        self._main_content = MainWindowContent(
            self, user, on_logout_callback=self._on_logout
        )
        self._main_content.pack(fill="both", expand=True)
        self.update_idletasks()

    def _on_logout(self) -> None:
        """Swap main content → login panel in the same window cleanly without resizing."""
        if hasattr(self, '_main_content') and self._main_content:
            self._main_content.destroy()
            self._main_content = None
        self._show_login()


# ---------------------------------------------------------------------------
# Embedded login & signup panels (Frames, not CTk roots)
# ---------------------------------------------------------------------------

class _LoginPanel(ctk.CTkFrame):
    """Login form as a Frame so it can live inside the PharmacyApp root."""

    def __init__(self, parent, on_success, on_signup_click, prefill_username="", initial_message="", is_success=False):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        self._on_success = on_success
        self._on_signup_click = on_signup_click
        self._prefill_username = prefill_username
        self._initial_message = initial_message
        self._is_success = is_success
        self._auth = AuthService()
        self._logger = get_app_logger()
        self._build()

    def _build(self) -> None:
        import tkinter as tk

        # Centering responsive grid configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=480)

        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.grid(row=1, column=1, padx=20, pady=20, sticky="n")

        # Pharmacy Icon & Title
        ctk.CTkLabel(
            card,
            text="🏥  Pharmacy Management System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(pady=(28, 4), padx=32)

        ctk.CTkLabel(
            card,
            text="Q13: Faster Search & Retrieval  |  Multi-Store Edition",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 16), padx=32)

        self._msg = ctk.CTkLabel(
            card,
            text=self._initial_message,
            font=Theme.FONT_SMALL,
            text_color=Theme.SUCCESS if self._is_success else Theme.DANGER,
            wraplength=400
        )
        self._msg.pack(pady=(0, 12), padx=32)

        # Username / Email
        ctk.CTkLabel(
            card,
            text="Username or Email",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=32, fill="x", pady=(0, 4))
        self._user_e = ctk.CTkEntry(
            card,
            placeholder_text="Enter username or email address",
            height=42,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self._user_e.pack(padx=32, fill="x", pady=(0, 14))
        if self._prefill_username:
            self._user_e.insert(0, self._prefill_username)
        self._user_e.focus()

        # Password
        ctk.CTkLabel(
            card,
            text="Password",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=32, fill="x", pady=(0, 4))
        self._pwd_e = ctk.CTkEntry(
            card,
            placeholder_text="Enter password",
            show="*",
            height=42,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self._pwd_e.pack(padx=32, fill="x", pady=(0, 8))
        self._pwd_e.bind("<Return>", lambda e: self._login())

        # Show/hide password
        self._show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            card,
            text="Show Password",
            variable=self._show_var,
            command=self._toggle_pwd,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            checkbox_width=18,
            checkbox_height=18,
            border_color=Theme.BORDER_COLOR,
            hover_color=Theme.PRIMARY_HOVER,
            fg_color=Theme.PRIMARY
        ).pack(padx=32, anchor="w", pady=(0, 18))

        # Login button
        ctk.CTkButton(
            card,
            text="LOGIN TO STORE",
            font=Theme.FONT_HEADING,
            height=44,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._login
        ).pack(padx=32, fill="x", pady=(0, 18))

        # Signup switch footer
        footer_frame = ctk.CTkFrame(card, fg_color="transparent")
        footer_frame.pack(padx=32, fill="x", pady=(0, 24))

        ctk.CTkLabel(
            footer_frame,
            text="New pharmacy owner? Register your store to get started.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 8))

        ctk.CTkButton(
            footer_frame,
            text="Register New Pharmacy Store",
            font=Theme.FONT_SUBHEADING,
            height=38,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.PRIMARY,
            border_width=1,
            border_color=Theme.PRIMARY,
            corner_radius=8,
            command=self._on_signup_click
        ).pack(fill="x")

    def _toggle_pwd(self) -> None:
        self._pwd_e.configure(show="" if self._show_var.get() else "*")

    def _login(self) -> None:
        identity = self._user_e.get().strip()
        password = self._pwd_e.get()
        user, message = self._auth.authenticate(identity, password)
        if user:
            self._msg.configure(text="Login successful! Loading…",
                                text_color=Theme.SUCCESS)
            self.update_idletasks()
            self._on_success(user)
        else:
            self._logger.log_event("AUTH",
                                   f"Failed login for '{identity}'",
                                   level="WARNING")
            self._msg.configure(text=message, text_color=Theme.DANGER)


class _SignupPanel(ctk.CTkFrame):
    """Store Registration form as a Frame inside PharmacyApp root."""

    def __init__(self, parent, on_login_click, on_signup_success):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        self._on_login_click = on_login_click
        self._on_signup_success = on_signup_success
        self._auth = AuthService()
        self._logger = get_app_logger()
        self._build()

    def _build(self) -> None:
        import tkinter as tk

        # Centering responsive grid configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=520)

        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.grid(row=1, column=1, padx=20, pady=20, sticky="n")

        # Header Section
        ctk.CTkLabel(
            card,
            text="🏥  Pharmacy Registration",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(pady=(22, 3), padx=25)

        ctk.CTkLabel(
            card,
            text="Register your independent store & owner account",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 8), padx=25)

        self._msg = ctk.CTkLabel(
            card,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            wraplength=440
        )
        self._msg.pack(pady=(0, 6), padx=25)

        # Scrollable form container
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", height=380)
        scroll.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # 1. Store Name
        ctk.CTkLabel(scroll, text="Pharmacy / Store Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._store_e = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Medical Store",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._store_e.pack(fill="x", pady=(0, 8))

        # 2. Owner Name
        ctk.CTkLabel(scroll, text="Owner's Full Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._owner_e = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Sharma",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._owner_e.pack(fill="x", pady=(0, 8))

        # 3. Username
        ctk.CTkLabel(scroll, text="Username *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._user_e = ctk.CTkEntry(scroll, placeholder_text="Choose unique username (min 3 chars)",
                                    height=38, font=Theme.FONT_BODY,
                                    fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                    text_color=Theme.TEXT_MAIN)
        self._user_e.pack(fill="x", pady=(0, 8))

        # 4. Email
        ctk.CTkLabel(scroll, text="Email Address *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._email_e = ctk.CTkEntry(scroll, placeholder_text="e.g. store@example.com",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._email_e.pack(fill="x", pady=(0, 8))

        # 5. Password
        ctk.CTkLabel(scroll, text="Password * (min 6 characters)", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._pwd_e = ctk.CTkEntry(scroll, placeholder_text="Enter secure password",
                                   show="*", height=38, font=Theme.FONT_BODY,
                                   fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                   text_color=Theme.TEXT_MAIN)
        self._pwd_e.pack(fill="x", pady=(0, 8))

        # 6. Confirm Password
        ctk.CTkLabel(scroll, text="Confirm Password *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._cpwd_e = ctk.CTkEntry(scroll, placeholder_text="Re-enter password",
                                    show="*", height=38, font=Theme.FONT_BODY,
                                    fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                    text_color=Theme.TEXT_MAIN)
        self._cpwd_e.pack(fill="x", pady=(0, 8))

        # Show passwords toggle
        self._show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(scroll, text="Show Passwords",
                        variable=self._show_var,
                        command=self._toggle_pwd,
                        font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED,
                        checkbox_width=18, checkbox_height=18,
                        border_color=Theme.BORDER_COLOR,
                        hover_color=Theme.PRIMARY_HOVER,
                        fg_color=Theme.PRIMARY
                        ).pack(anchor="w", pady=(2, 6))

        # Action Buttons (Outside scrollable frame, always accessible)
        ctk.CTkButton(card, text="CREATE PHARMACY STORE",
                      font=Theme.FONT_HEADING, height=42,
                      fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
                      text_color=Theme.TEXT_DARK, corner_radius=8,
                      command=self._signup
                      ).pack(padx=25, fill="x", pady=(6, 8))

        # Back to login
        ctk.CTkButton(card, text="Already have a registered store? Back to Login",
                      font=Theme.FONT_SMALL, height=28,
                      fg_color="transparent", hover_color=Theme.INPUT_BG,
                      text_color=Theme.SECONDARY,
                      command=self._on_login_click
                      ).pack(pady=(0, 16))

    def _toggle_pwd(self) -> None:
        mask = "" if self._show_var.get() else "*"
        self._pwd_e.configure(show=mask)
        self._cpwd_e.configure(show=mask)

    def _signup(self) -> None:
        store_name = self._store_e.get().strip()
        owner_name = self._owner_e.get().strip()
        username = self._user_e.get().strip()
        email = self._email_e.get().strip()
        pwd = self._pwd_e.get()
        cpwd = self._cpwd_e.get()

        ok, msg, created_user = self._auth.register_store(
            store_name=store_name,
            owner_name=owner_name,
            username=username,
            email=email,
            password=pwd,
            confirm_password=cpwd
        )

        if ok and created_user:
            self._logger.log_event("AUTH", f"New store registered: '{store_name}' by '{username}' ({created_user.store_id})")
            self._on_signup_success(created_user, f"Store '{store_name}' registered successfully! Please log in.")
        else:
            self._msg.configure(text=msg, text_color=Theme.DANGER)


# ---------------------------------------------------------------------------
# Embedded login & signup panels (Frames, not CTk roots)
# ---------------------------------------------------------------------------

class _LoginPanel(ctk.CTkFrame):
    """Login form as a Frame so it can live inside the PharmacyApp root."""

    def __init__(self, parent, on_success, on_signup_click, prefill_username="", initial_message="", is_success=False):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        self._on_success = on_success
        self._on_signup_click = on_signup_click
        self._prefill_username = prefill_username
        self._initial_message = initial_message
        self._is_success = is_success
        self._auth = AuthService()
        self._logger = get_app_logger()
        self._build()

    def _build(self) -> None:
        import tkinter as tk

        # Centering responsive grid configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=480)

        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.grid(row=1, column=1, padx=20, pady=20, sticky="n")

        # Pharmacy Icon & Title
        ctk.CTkLabel(
            card,
            text="🏥  Pharmacy Management System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(pady=(28, 4), padx=32)

        ctk.CTkLabel(
            card,
            text="Q13: Faster Search & Retrieval  |  Multi-Store Edition",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 16), padx=32)

        self._msg = ctk.CTkLabel(
            card,
            text=self._initial_message,
            font=Theme.FONT_SMALL,
            text_color=Theme.SUCCESS if self._is_success else Theme.DANGER,
            wraplength=400
        )
        self._msg.pack(pady=(0, 12), padx=32)

        # Username / Email
        ctk.CTkLabel(
            card,
            text="Username or Email",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=32, fill="x", pady=(0, 4))
        self._user_e = ctk.CTkEntry(
            card,
            placeholder_text="Enter username or email address",
            height=42,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self._user_e.pack(padx=32, fill="x", pady=(0, 14))
        if self._prefill_username:
            self._user_e.insert(0, self._prefill_username)
        self._user_e.focus()

        # Password
        ctk.CTkLabel(
            card,
            text="Password",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=32, fill="x", pady=(0, 4))
        self._pwd_e = ctk.CTkEntry(
            card,
            placeholder_text="Enter password",
            show="*",
            height=42,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self._pwd_e.pack(padx=32, fill="x", pady=(0, 8))
        self._pwd_e.bind("<Return>", lambda e: self._login())

        # Show/hide password
        self._show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            card,
            text="Show Password",
            variable=self._show_var,
            command=self._toggle_pwd,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            checkbox_width=18,
            checkbox_height=18,
            border_color=Theme.BORDER_COLOR,
            hover_color=Theme.PRIMARY_HOVER,
            fg_color=Theme.PRIMARY
        ).pack(padx=32, anchor="w", pady=(0, 18))

        # Login button
        ctk.CTkButton(
            card,
            text="LOGIN TO STORE",
            font=Theme.FONT_HEADING,
            height=44,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._login
        ).pack(padx=32, fill="x", pady=(0, 18))

        # Signup switch footer
        footer_frame = ctk.CTkFrame(card, fg_color="transparent")
        footer_frame.pack(padx=32, fill="x", pady=(0, 24))

        ctk.CTkLabel(
            footer_frame,
            text="New pharmacy owner? Register your store to get started.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 8))

        ctk.CTkButton(
            footer_frame,
            text="Register New Pharmacy Store",
            font=Theme.FONT_SUBHEADING,
            height=38,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.PRIMARY,
            border_width=1,
            border_color=Theme.PRIMARY,
            corner_radius=8,
            command=self._on_signup_click
        ).pack(fill="x")

    def _toggle_pwd(self) -> None:
        self._pwd_e.configure(show="" if self._show_var.get() else "*")

    def _login(self) -> None:
        identity = self._user_e.get().strip()
        password = self._pwd_e.get()
        user, message = self._auth.authenticate(identity, password)
        if user:
            self._msg.configure(text="Login successful! Loading…",
                                text_color=Theme.SUCCESS)
            self.update_idletasks()
            self._on_success(user)
        else:
            self._logger.log_event("AUTH",
                                   f"Failed login for '{identity}'",
                                   level="WARNING")
            self._msg.configure(text=message, text_color=Theme.DANGER)


class _SignupPanel(ctk.CTkFrame):
    """Store Registration form as a Frame inside PharmacyApp root."""

    def __init__(self, parent, on_login_click, on_signup_success):
        super().__init__(parent, fg_color=Theme.BG_DARK)
        self._on_login_click = on_login_click
        self._on_signup_success = on_signup_success
        self._auth = AuthService()
        self._logger = get_app_logger()
        self._build()

    def _build(self) -> None:
        import tkinter as tk

        # Centering responsive grid configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=520)

        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.grid(row=1, column=1, padx=20, pady=20, sticky="n")

        # Header Section
        ctk.CTkLabel(
            card,
            text="🏥  Pharmacy Registration",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(pady=(22, 3), padx=25)

        ctk.CTkLabel(
            card,
            text="Register your independent store & owner account",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 8), padx=25)

        self._msg = ctk.CTkLabel(
            card,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            wraplength=440
        )
        self._msg.pack(pady=(0, 6), padx=25)

        # Scrollable form container
        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", height=380)
        scroll.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # 1. Store Name
        ctk.CTkLabel(scroll, text="Pharmacy / Store Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._store_e = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Medical Store",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._store_e.pack(fill="x", pady=(0, 8))

        # 2. Owner Name
        ctk.CTkLabel(scroll, text="Owner's Full Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._owner_e = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Sharma",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._owner_e.pack(fill="x", pady=(0, 8))

        # 3. Username
        ctk.CTkLabel(scroll, text="Username *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._user_e = ctk.CTkEntry(scroll, placeholder_text="Choose unique username (min 3 chars)",
                                    height=38, font=Theme.FONT_BODY,
                                    fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                    text_color=Theme.TEXT_MAIN)
        self._user_e.pack(fill="x", pady=(0, 8))

        # 4. Email
        ctk.CTkLabel(scroll, text="Email Address *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._email_e = ctk.CTkEntry(scroll, placeholder_text="e.g. store@example.com",
                                     height=38, font=Theme.FONT_BODY,
                                     fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                     text_color=Theme.TEXT_MAIN)
        self._email_e.pack(fill="x", pady=(0, 8))

        # 5. Password
        ctk.CTkLabel(scroll, text="Password * (min 6 characters)", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._pwd_e = ctk.CTkEntry(scroll, placeholder_text="Enter secure password",
                                   show="*", height=38, font=Theme.FONT_BODY,
                                   fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                   text_color=Theme.TEXT_MAIN)
        self._pwd_e.pack(fill="x", pady=(0, 8))

        # 6. Confirm Password
        ctk.CTkLabel(scroll, text="Confirm Password *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self._cpwd_e = ctk.CTkEntry(scroll, placeholder_text="Re-enter password",
                                    show="*", height=38, font=Theme.FONT_BODY,
                                    fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                    text_color=Theme.TEXT_MAIN)
        self._cpwd_e.pack(fill="x", pady=(0, 8))

        # Show passwords toggle
        self._show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(scroll, text="Show Passwords",
                        variable=self._show_var,
                        command=self._toggle_pwd,
                        font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED,
                        checkbox_width=18, checkbox_height=18,
                        border_color=Theme.BORDER_COLOR,
                        hover_color=Theme.PRIMARY_HOVER,
                        fg_color=Theme.PRIMARY
                        ).pack(anchor="w", pady=(2, 6))

        # Action Buttons (Outside scrollable frame, always accessible)
        ctk.CTkButton(card, text="CREATE PHARMACY STORE",
                      font=Theme.FONT_HEADING, height=42,
                      fg_color=Theme.PRIMARY, hover_color=Theme.PRIMARY_HOVER,
                      text_color=Theme.TEXT_DARK, corner_radius=8,
                      command=self._signup
                      ).pack(padx=25, fill="x", pady=(6, 8))

        # Back to login
        ctk.CTkButton(card, text="Already have a registered store? Back to Login",
                      font=Theme.FONT_SMALL, height=28,
                      fg_color="transparent", hover_color=Theme.INPUT_BG,
                      text_color=Theme.SECONDARY,
                      command=self._on_login_click
                      ).pack(pady=(0, 16))

    def _toggle_pwd(self) -> None:
        mask = "" if self._show_var.get() else "*"
        self._pwd_e.configure(show=mask)
        self._cpwd_e.configure(show=mask)

    def _signup(self) -> None:
        store_name = self._store_e.get().strip()
        owner_name = self._owner_e.get().strip()
        username = self._user_e.get().strip()
        email = self._email_e.get().strip()
        pwd = self._pwd_e.get()
        cpwd = self._cpwd_e.get()

        ok, msg, created_user = self._auth.register_store(
            store_name=store_name,
            owner_name=owner_name,
            username=username,
            email=email,
            password=pwd,
            confirm_password=cpwd
        )

        if ok and created_user:
            self._logger.log_event("AUTH", f"New store registered: '{store_name}' by '{username}' ({created_user.store_id})")
            self._on_signup_success(created_user, f"Store '{store_name}' registered successfully! Please log in.")
        else:
            self._msg.configure(text=msg, text_color=Theme.DANGER)


# ---------------------------------------------------------------------------
# CLI verification (unchanged)
# ---------------------------------------------------------------------------

def run_stage1_cli_verification():
    """Initializes database and prints Stage 1 foundation verification summary in CLI."""
    print("=" * 70)
    print("  PHARMACY MANAGEMENT SYSTEM PROJECT")
    print("  Pharmacy Management System - Faster Search & Retrieval")
    print("  Student: Priyanshu Pokhariya | Enrollment No: 2410303005")
    print("  Branch: CSE | Section: C | Session: 2026-27")
    print("=" * 70)

    logger = get_app_logger()
    logger.log_event("SYSTEM", "Initializing Stage 1 CLI Verification...")

    db = init_db()
    print("\n[OK] Database file initialized at: data/pharmacy.db")

    tables = db.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
    table_names = [t["name"] for t in tables if not t["name"].startswith("sqlite_")]
    print(f"[OK] Created Database Tables ({len(table_names)}): {', '.join(table_names)}")

    indexes = db.fetch_all("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%';")
    idx_names = [i["name"] for i in indexes]
    print(f"[OK] Created SQLite B-Tree Indexes ({len(idx_names)}): {', '.join(idx_names)}")

    auth_service = AuthService(db)
    admin_user, _ = auth_service.authenticate("admin", "admin123")
    pharma_user, _ = auth_service.authenticate("pharmacist", "pharma123")
    print(f"[OK] Seed User Accounts Verified:")
    print(f"    - Admin: '{admin_user.username if admin_user else 'FAIL'}' (Role: {admin_user.role if admin_user else 'N/A'})")
    print(f"    - Pharmacist: '{pharma_user.username if pharma_user else 'FAIL'}' (Role: {pharma_user.role if pharma_user else 'N/A'})")

    med_service = MedicineService(db)
    kpis = med_service.get_inventory_summary()
    print(f"[OK] Seed Inventory Loaded:")
    print(f"    - Total Medicines: {kpis['total_medicines']}")
    print(f"    - Total Stock Quantity: {kpis['total_stock_quantity']}")
    try:
        print(f"    - Total Inventory Value: ₹{kpis['total_inventory_value']:.2f}")
    except UnicodeEncodeError:
        print(f"    - Total Inventory Value: Rs. {kpis['total_inventory_value']:.2f}")
    print(f"    - Low Stock Items (<=10): {kpis['low_stock_count']}")
    print(f"    - Out of Stock Items: {kpis['out_of_stock_count']}")
    print(f"    - Expiring Soon Items: {kpis['expiring_soon_count']}")
    print(f"    - Expired Items: {kpis['expired_count']}")

    bm = SearchBenchmark(db)
    res = bm.benchmark_query(
        "SELECT medicine_id, medicine_name FROM medicines WHERE medicine_code = ?",
        ("MED1001",)
    )
    print(f"[OK] Search Performance Baseline:")
    print(f"    - Query: Exact Code Lookup ('MED1001')")
    print(f"    - Execution Time: {res['avg_time_ms']:.4f} ms")
    print(f"    - Query Plan: {res['query_plan']}")
    print(f"    - Index Used: {res['uses_index']}")

    print("\n[OK] STAGE 1 DATABASE FOUNDATION SUCCESSFULLY VERIFIED!")
    print("=" * 70)


def launch_app():
    """Launches the single-window pharmacy application."""
    logger = get_app_logger()
    logger.log_event("SYSTEM", "Starting Pharmacy Management System...")
    try:
        init_db()
    except Exception as e:
        logger.log_event("ERROR", f"Database initialization failed: {e}", level="ERROR")
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        from utils.paths import get_default_db_path
        db_path = get_default_db_path()
        messagebox.showerror(
            "Pharmacy Management System - Database Error",
            f"The application could not start because the database cannot be initialized:\n\n"
            f"{e}\n\n"
            f"Target database location:\n{db_path}\n\n"
            f"Please verify folder and file permissions."
        )
        root.destroy()
        sys.exit(1)
    app = PharmacyApp()
    app.mainloop()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        run_stage1_cli_verification()
    elif len(sys.argv) > 1 and sys.argv[1] == "--sync-db":
        from database.sync import get_source_db_candidate, sync_databases
        from utils.paths import get_default_db_path
        src = get_source_db_candidate()
        dst = get_default_db_path()
        if not src:
            print("[SYNC] No source database candidate found to synchronize from.")
            sys.exit(1)
        print(f"[SYNC] Synchronizing from '{src}' to '{dst}'...")
        res = sync_databases(src, dst)
        print("[SYNC] Synchronization complete:", res)
        sys.exit(0)
    else:
        launch_app()
