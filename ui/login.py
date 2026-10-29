"""
Login Window UI for Pharmacy Management System.
Uses AuthService for authentication and opens MainWindow upon successful login.
"""
import tkinter as tk
from typing import Optional, Callable
import customtkinter as ctk

from ui.theme import Theme
from services.auth_service import AuthService
from models.user import User
from utils.logger import get_app_logger

ctk.set_appearance_mode(Theme.APPEARANCE_MODE)
ctk.set_default_color_theme(Theme.COLOR_THEME)


class LoginWindow(ctk.CTk):
    """Modern Desktop Login & Signup Window for Pharmacy Management System."""

    def __init__(self, on_login_success: Optional[Callable[[User], None]] = None):
        super().__init__()
        self.on_login_success = on_login_success
        self.auth_service = AuthService()
        self.logger = get_app_logger()

        self.title("Pharmacy Management System - Login")
        self._setup_window_geometry()
        self.configure(fg_color=Theme.BG_DARK)

        self._current_panel: Optional[ctk.CTkFrame] = None
        self._show_login_panel()

    def _setup_window_geometry(self) -> None:
        """Configures responsive window sizing: minsize, resizable, maximized with large fallback."""
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

    def _center(self, width: int, height: int) -> None:
        """Centers the window on the primary screen at the given dimensions."""
        self.update_idletasks()
        x = max(0, (self.winfo_screenwidth() // 2) - (width // 2))
        y = max(0, (self.winfo_screenheight() // 2) - (height // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _show_login_panel(self, message: str = "", is_success: bool = False, prefill_username: str = "") -> None:
        """Constructs and displays the login form."""
        if self._current_panel:
            self._current_panel.destroy()

        self.title("Pharmacy Management System - Login")

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
        self._current_panel = card

        # Header Section
        ctk.CTkLabel(
            card,
            text="🏥  Pharmacy Management System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(pady=(25, 4))

        ctk.CTkLabel(
            card,
            text="Q13: Faster Search & Retrieval  |  Multi-Store Edition",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 15))

        # Status / Error / Success Message Label
        self.msg_label = ctk.CTkLabel(
            card,
            text=message,
            font=Theme.FONT_SMALL,
            text_color=Theme.SUCCESS if is_success else Theme.DANGER,
            wraplength=380
        )
        self.msg_label.pack(pady=(0, 10))

        # Username / Email Input
        ctk.CTkLabel(
            card,
            text="Username or Email",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=30, fill="x", pady=(0, 2))

        self.username_entry = ctk.CTkEntry(
            card,
            placeholder_text="Enter username or email address",
            height=40,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self.username_entry.pack(padx=30, fill="x", pady=(0, 14))
        if prefill_username:
            self.username_entry.insert(0, prefill_username)
        self.username_entry.focus()

        # Password Input
        ctk.CTkLabel(
            card,
            text="Password",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(padx=30, fill="x", pady=(0, 2))

        self.password_entry = ctk.CTkEntry(
            card,
            placeholder_text="Enter password",
            show="*",
            height=40,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self.password_entry.pack(padx=30, fill="x", pady=(0, 6))
        self.password_entry.bind("<Return>", lambda event: self._handle_login())

        # Show/Hide Password Checkbox
        self.show_pwd_var = tk.BooleanVar(value=False)
        self.show_pwd_cb = ctk.CTkCheckBox(
            card,
            text="Show Password",
            variable=self.show_pwd_var,
            command=self._toggle_password_visibility,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            checkbox_width=18,
            checkbox_height=18,
            border_color=Theme.BORDER_COLOR,
            hover_color=Theme.PRIMARY_HOVER,
            fg_color=Theme.PRIMARY
        )
        self.show_pwd_cb.pack(padx=30, anchor="w", pady=(0, 20))

        # Login Button
        self.login_btn = ctk.CTkButton(
            card,
            text="LOGIN TO STORE",
            font=Theme.FONT_HEADING,
            height=42,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._handle_login
        )
        self.login_btn.pack(padx=30, fill="x", pady=(0, 18))

        # Register switch footer
        footer_frame = ctk.CTkFrame(card, fg_color="transparent")
        footer_frame.pack(padx=30, fill="x", pady=(5, 10))

        ctk.CTkLabel(
            footer_frame,
            text="New pharmacy owner? Register your store to get started.",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(pady=(0, 6))

        signup_btn = ctk.CTkButton(
            footer_frame,
            text="Register New Pharmacy Store",
            font=Theme.FONT_SUBHEADING,
            height=36,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.PRIMARY,
            border_width=1,
            border_color=Theme.PRIMARY,
            corner_radius=8,
            command=self._show_signup_panel
        )
        signup_btn.pack(fill="x")

    def _show_signup_panel(self) -> None:
        """Constructs and displays the multi-field store signup form."""
        if self._current_panel:
            self._current_panel.destroy()

        self.title("Pharmacy Management System - Register New Store")

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
        self._current_panel = card

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

        # Error / Success Message Label
        self.signup_msg_label = ctk.CTkLabel(
            card,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            wraplength=440
        )
        self.signup_msg_label.pack(pady=(0, 6), padx=25)

        scroll = ctk.CTkScrollableFrame(card, fg_color="transparent", height=380)
        scroll.pack(fill="both", expand=True, padx=25, pady=(0, 10))

        # 1. Pharmacy / Store Name
        ctk.CTkLabel(scroll, text="Pharmacy / Store Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.store_name_entry = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Medical Store",
                                            height=36, font=Theme.FONT_BODY,
                                            fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                            text_color=Theme.TEXT_MAIN)
        self.store_name_entry.pack(fill="x", pady=(0, 8))

        # 2. Owner's Full Name
        ctk.CTkLabel(scroll, text="Owner's Full Name *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.owner_name_entry = ctk.CTkEntry(scroll, placeholder_text="e.g. Ram Sharma",
                                            height=36, font=Theme.FONT_BODY,
                                            fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                            text_color=Theme.TEXT_MAIN)
        self.owner_name_entry.pack(fill="x", pady=(0, 8))

        # 3. Username
        ctk.CTkLabel(scroll, text="Username *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.signup_user_entry = ctk.CTkEntry(scroll, placeholder_text="Choose unique username (min 3 chars)",
                                              height=36, font=Theme.FONT_BODY,
                                              fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                              text_color=Theme.TEXT_MAIN)
        self.signup_user_entry.pack(fill="x", pady=(0, 8))

        # 4. Email Address
        ctk.CTkLabel(scroll, text="Email Address *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.signup_email_entry = ctk.CTkEntry(scroll, placeholder_text="e.g. store@example.com",
                                               height=36, font=Theme.FONT_BODY,
                                               fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                               text_color=Theme.TEXT_MAIN)
        self.signup_email_entry.pack(fill="x", pady=(0, 8))

        # 5. Password
        ctk.CTkLabel(scroll, text="Password * (min 6 characters)", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.signup_pwd_entry = ctk.CTkEntry(scroll, placeholder_text="Enter secure password",
                                             show="*", height=36, font=Theme.FONT_BODY,
                                             fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                             text_color=Theme.TEXT_MAIN)
        self.signup_pwd_entry.pack(fill="x", pady=(0, 8))

        # 6. Confirm Password
        ctk.CTkLabel(scroll, text="Confirm Password *", font=Theme.FONT_SUBHEADING,
                     text_color=Theme.TEXT_MAIN, anchor="w").pack(fill="x", pady=(0, 2))
        self.signup_cpwd_entry = ctk.CTkEntry(scroll, placeholder_text="Re-enter password",
                                              show="*", height=36, font=Theme.FONT_BODY,
                                              fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR,
                                              text_color=Theme.TEXT_MAIN)
        self.signup_cpwd_entry.pack(fill="x", pady=(0, 8))

        # Show passwords toggle
        self.signup_show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            scroll,
            text="Show Passwords",
            variable=self.signup_show_var,
            command=self._toggle_signup_pwd_visibility,
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            checkbox_width=18,
            checkbox_height=18,
            border_color=Theme.BORDER_COLOR,
            hover_color=Theme.PRIMARY_HOVER,
            fg_color=Theme.PRIMARY
        ).pack(anchor="w", pady=(2, 10))

        # Submit button
        submit_btn = ctk.CTkButton(
            card,
            text="CREATE PHARMACY STORE",
            font=Theme.FONT_HEADING,
            height=40,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._handle_signup
        )
        submit_btn.pack(padx=20, fill="x", pady=(4, 6))

        # Back to login
        back_btn = ctk.CTkButton(
            card,
            text="Already have a registered store? Back to Login",
            font=Theme.FONT_SMALL,
            height=28,
            fg_color="transparent",
            hover_color=Theme.INPUT_BG,
            text_color=Theme.SECONDARY,
            command=lambda: self._show_login_panel()
        )
        back_btn.pack(pady=(0, 8))

    def _toggle_password_visibility(self) -> None:
        """Toggles password entry show/hide mask."""
        if hasattr(self, 'password_entry'):
            self.password_entry.configure(show="" if self.show_pwd_var.get() else "*")

    def _toggle_signup_pwd_visibility(self) -> None:
        """Toggles password masks in signup panel."""
        show_char = "" if self.signup_show_var.get() else "*"
        if hasattr(self, 'signup_pwd_entry'):
            self.signup_pwd_entry.configure(show=show_char)
        if hasattr(self, 'signup_cpwd_entry'):
            self.signup_cpwd_entry.configure(show=show_char)

    def _handle_login(self) -> None:
        """Processes login authentication using AuthService."""
        identity = self.username_entry.get().strip()
        password = self.password_entry.get()

        user, message = self.auth_service.authenticate(identity, password)

        if user:
            self.logger.log_event("AUTH", f"User '{user.username}' (Store: {user.store_name}) logged in successfully.")
            self.msg_label.configure(text="Login successful! Loading...", text_color=Theme.SUCCESS)
            self.update_idletasks()
            if self.on_login_success:
                self.on_login_success(user)
            self.destroy()
        else:
            self.logger.log_event("AUTH", f"Failed login attempt for '{identity}'", level="WARNING")
            self.msg_label.configure(text=message, text_color=Theme.DANGER)

    def _handle_signup(self) -> None:
        """Processes pharmacy store registration."""
        store_name = self.store_name_entry.get().strip()
        owner_name = self.owner_name_entry.get().strip()
        username = self.signup_user_entry.get().strip()
        email = self.signup_email_entry.get().strip()
        password = self.signup_pwd_entry.get()
        confirm_pwd = self.signup_cpwd_entry.get()

        success, msg, created_user = self.auth_service.register_store(
            store_name=store_name,
            owner_name=owner_name,
            username=username,
            email=email,
            password=password,
            confirm_password=confirm_pwd
        )

        if success and created_user:
            self.logger.log_event("AUTH", f"New store registered: '{store_name}' by '{username}' ({created_user.store_id})")
            # Redirect to login with pre-filled username and green success message
            self._show_login_panel(
                message=f"Store '{store_name}' registered successfully! Please log in.",
                is_success=True,
                prefill_username=created_user.username
            )
        else:
            self.signup_msg_label.configure(text=msg, text_color=Theme.DANGER)
