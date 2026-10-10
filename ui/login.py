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
    """Modern Desktop Login Window for authenticating Admin & Pharmacist users."""

    def __init__(self, on_login_success: Optional[Callable[[User], None]] = None):
        super().__init__()
        self.on_login_success = on_login_success
        self.auth_service = AuthService()
        self.logger = get_app_logger()

        self.title("Pharmacy Management System - Login")
        self.geometry("450x620")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        # Center window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

        self._build_ui()

    def _build_ui(self) -> None:
        """Constructs the login form and demo credential helpers."""
        # Container Card
        card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=16,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        card.pack(padx=25, pady=25, fill="both", expand=True)

        # Header Section
        title_label = ctk.CTkLabel(
            card,
            text="Pharmacy Management System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        )
        title_label.pack(pady=(25, 4))

        subtitle_label = ctk.CTkLabel(
            card,
            text="Pharmacy Management System | Q13: Faster Search & Retrieval",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        subtitle_label.pack(pady=(0, 20))

        # Status / Error Message Label
        self.msg_label = ctk.CTkLabel(
            card,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            wraplength=350
        )
        self.msg_label.pack(pady=(0, 10))

        # Username Input
        username_lbl = ctk.CTkLabel(
            card,
            text="Username",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        )
        username_lbl.pack(padx=30, fill="x", pady=(0, 2))

        self.username_entry = ctk.CTkEntry(
            card,
            placeholder_text="Enter username",
            height=40,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self.username_entry.pack(padx=30, fill="x", pady=(0, 15))
        self.username_entry.focus()

        # Password Input
        password_lbl = ctk.CTkLabel(
            card,
            text="Password",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        )
        password_lbl.pack(padx=30, fill="x", pady=(0, 2))

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
        self.password_entry.pack(padx=30, fill="x", pady=(0, 8))
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
            text="LOGIN",
            font=Theme.FONT_HEADING,
            height=42,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._handle_login
        )
        self.login_btn.pack(padx=30, fill="x", pady=(0, 15))

        # Demo Credentials Quick-Fill Helper Box
        demo_frame = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=8)
        demo_frame.pack(padx=30, fill="x", pady=(0, 15))

        demo_title = ctk.CTkLabel(
            demo_frame,
            text="Demo Credentials (Click to Auto-Fill):",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        )
        demo_title.pack(pady=(6, 4))

        btn_box = ctk.CTkFrame(demo_frame, fg_color="transparent")
        btn_box.pack(pady=(0, 6))

        admin_btn = ctk.CTkButton(
            btn_box,
            text="Admin (admin / admin123)",
            font=Theme.FONT_SMALL,
            height=26,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.PRIMARY,
            command=lambda: self._fill_credentials("admin", "admin123")
        )
        admin_btn.pack(side="left", padx=5)

        pharma_btn = ctk.CTkButton(
            btn_box,
            text="Pharmacist (pharmacist / pharma123)",
            font=Theme.FONT_SMALL,
            height=26,
            fg_color=Theme.BG_CARD,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.SECONDARY,
            command=lambda: self._fill_credentials("pharmacist", "pharma123")
        )
        pharma_btn.pack(side="left", padx=5)

    def _toggle_password_visibility(self) -> None:
        """Toggles password entry show/hide mask."""
        if self.show_pwd_var.get():
            self.password_entry.configure(show="")
        else:
            self.password_entry.configure(show="*")

    def _fill_credentials(self, user: str, pwd: str) -> None:
        """Fills entry fields with selected demo credentials."""
        self.username_entry.delete(0, "end")
        self.username_entry.insert(0, user)
        self.password_entry.delete(0, "end")
        self.password_entry.insert(0, pwd)
        self.msg_label.configure(text="")

    def _handle_login(self) -> None:
        """Processes login authentication using AuthService."""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()

        user, message = self.auth_service.authenticate(username, password)

        if user:
            self.logger.log_event("AUTH", f"User '{user.username}' ({user.role}) logged in successfully.")
            self.msg_label.configure(text="Login successful! Loading...", text_color=Theme.SUCCESS)
            self.update_idletasks()
            
            # Execute callback or destroy login window
            if self.on_login_success:
                self.on_login_success(user)
            self.destroy()
        else:
            self.logger.log_event("AUTH", f"Failed login attempt for username '{username}'", level="WARNING")
            self.msg_label.configure(text=message, text_color=Theme.DANGER)
