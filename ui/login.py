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
        self.minsize(1050, 680)
        self.resizable(True, True)
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        target_w = min(1280, max(1050, int(screen_w * 0.88)))
        target_h = min(820, max(680, int(screen_h * 0.88)))
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

    SUPPORTED_ROLES = ["Owner", "Admin", "Pharmacist", "Cashier", "Inventory Manager"]

    def _show_login_panel(
        self,
        message: str = "",
        is_success: bool = False,
        prefill_username: str = "",
        preselect_store_id: str = "",
        preselect_role: str = ""
    ) -> None:
        """Constructs and displays the user-controlled 5-field login interface."""
        if self._current_panel:
            self._current_panel.destroy()

        self.title("Pharmacy Management System - Login")

        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_columnconfigure(1, weight=0, minsize=480)

        main_card = ctk.CTkFrame(
            self,
            fg_color=Theme.BG_CARD,
            corner_radius=18,
            border_width=1,
            border_color=Theme.BORDER_COLOR,
            width=480
        )
        main_card.grid(row=1, column=1, padx=20, pady=20, sticky="n")
        self._current_panel = main_card

        # Top Header Banner
        header_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        header_frame.pack(fill="x", padx=30, pady=(24, 8))

        ctk.CTkLabel(
            header_frame,
            text="🏥  Pharmacy Management System",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(anchor="center")

        ctk.CTkLabel(
            header_frame,
            text="Point of Sale & Clinical ERP  •  Multi-Store Edition",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="center", pady=(3, 0))

        # Horizontal Divider
        ctk.CTkFrame(main_card, height=1, fg_color=Theme.BORDER_COLOR).pack(fill="x", padx=25, pady=(12, 12))

        # Form Container
        form_frame = ctk.CTkFrame(main_card, fg_color="transparent")
        form_frame.pack(fill="both", expand=True, padx=30, pady=(0, 20))

        # Feedback / Status Message Banner
        self.msg_label = ctk.CTkLabel(
            form_frame,
            text=message,
            font=Theme.FONT_SMALL,
            text_color=Theme.SUCCESS if is_success else Theme.DANGER,
            wraplength=420,
            justify="center"
        )
        self.msg_label.pack(fill="x", pady=(0, 10))

        # =====================================================================
        # FIELD 1: Pharmacy Store Dropdown
        # =====================================================================
        ctk.CTkLabel(
            form_frame,
            text="1. Pharmacy Store *",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(fill="x", pady=(0, 3))

        stores = self.auth_service.get_available_stores(include_test=False)
        self._store_options = [f"{s['store_name']} ({s['store_id']})" for s in stores]
        self._store_id_map = {f"{s['store_name']} ({s['store_id']})": s["store_id"] for s in stores}

        if self._store_options:
            default_store_str = self._store_options[0]
            if preselect_store_id:
                for opt, sid in self._store_id_map.items():
                    if sid == preselect_store_id:
                        default_store_str = opt
                        break
            self._selected_store_id = self._store_id_map.get(default_store_str)
            menu_values = self._store_options
        else:
            default_store_str = "— No Stores Registered —"
            self._selected_store_id = None
            menu_values = ["— No Stores Registered —"]

        self._store_menu = ctk.CTkOptionMenu(
            form_frame,
            values=menu_values,
            command=self._on_store_changed,
            height=38,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_MAIN,
            dropdown_text_color=Theme.TEXT_MAIN
        )
        self._store_menu.set(default_store_str)
        self._store_menu.pack(fill="x", pady=(0, 12))

        # =====================================================================
        # FIELD 2: Role Dropdown
        # =====================================================================
        ctk.CTkLabel(
            form_frame,
            text="2. Role *",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(fill="x", pady=(0, 3))

        initial_role = preselect_role if preselect_role in self.SUPPORTED_ROLES else "Owner"
        self._role_menu = ctk.CTkOptionMenu(
            form_frame,
            values=self.SUPPORTED_ROLES,
            command=self._on_role_changed,
            height=38,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_MAIN,
            dropdown_text_color=Theme.TEXT_MAIN
        )
        self._role_menu.set(initial_role)
        self._role_menu.pack(fill="x", pady=(0, 2))

        # Role status message below dropdown
        self._role_status_lbl = ctk.CTkLabel(
            form_frame,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.WARNING,
            wraplength=420,
            anchor="w"
        )
        self._role_status_lbl.pack(fill="x", pady=(0, 10))

        # =====================================================================
        # FIELD 3: Username Field
        # =====================================================================
        ctk.CTkLabel(
            form_frame,
            text="3. Username *",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(fill="x", pady=(0, 3))

        self.username_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Enter your assigned username",
            height=38,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self.username_entry.pack(fill="x", pady=(0, 12))
        if prefill_username:
            self.username_entry.insert(0, prefill_username)

        # =====================================================================
        # FIELD 4: Password Field
        # =====================================================================
        ctk.CTkLabel(
            form_frame,
            text="4. Password *",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN,
            anchor="w"
        ).pack(fill="x", pady=(0, 3))

        self.password_entry = ctk.CTkEntry(
            form_frame,
            placeholder_text="Enter your account password",
            show="*",
            height=38,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            border_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN
        )
        self.password_entry.pack(fill="x", pady=(0, 4))
        self.password_entry.bind("<Return>", lambda e: self._handle_login())

        # Show / Hide Password Checkbox
        import tkinter as tk
        self.show_pwd_var = tk.BooleanVar(value=False)
        self.show_pwd_cb = ctk.CTkCheckBox(
            form_frame,
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
        self.show_pwd_cb.pack(anchor="w", pady=(0, 14))

        if prefill_username:
            self.password_entry.focus()
        else:
            self.username_entry.focus()

        # =====================================================================
        # FIELD 5: Login Button
        # =====================================================================
        self.login_btn = ctk.CTkButton(
            form_frame,
            text="LOGIN TO STORE",
            font=Theme.FONT_HEADING,
            height=42,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            corner_radius=8,
            command=self._handle_login
        )
        self.login_btn.pack(fill="x", pady=(0, 14))

        # =====================================================================
        # Onboarding Action: Register New Pharmacy Store
        # =====================================================================
        reg_box = ctk.CTkFrame(
            form_frame,
            fg_color=Theme.BG_DARK,
            corner_radius=10,
            border_width=1,
            border_color=Theme.BORDER_COLOR
        )
        reg_box.pack(fill="x", pady=(0, 0))

        ctk.CTkLabel(
            reg_box,
            text="New Pharmacy Store Owner?",
            font=Theme.FONT_SUBHEADING,
            text_color=Theme.TEXT_MAIN
        ).pack(pady=(8, 2))

        ctk.CTkButton(
            reg_box,
            text="Register New Pharmacy Store",
            font=Theme.FONT_SUBHEADING,
            height=34,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.PRIMARY,
            border_width=1,
            border_color=Theme.PRIMARY,
            corner_radius=8,
            command=self._show_signup_panel
        ).pack(fill="x", padx=16, pady=(0, 10))

        self._check_role_accounts()

    def _on_store_changed(self, choice: str) -> None:
        self._selected_store_id = self._store_id_map.get(choice)
        self._check_role_accounts()

    def _on_role_changed(self, choice: str) -> None:
        self._check_role_accounts()

    def _check_role_accounts(self) -> None:
        if not self._selected_store_id:
            self._role_status_lbl.configure(
                text="ℹ️ No registered stores. Please click 'Register New Pharmacy Store' below to get started.",
                text_color=Theme.PRIMARY
            )
            return

        current_role = self._role_menu.get()
        count = self.auth_service.count_role_accounts(self._selected_store_id, current_role)
        if count == 0:
            self._role_status_lbl.configure(
                text=f"⚠️ No active accounts found for role '{current_role}' in this store.",
                text_color=Theme.WARNING
            )
        else:
            self._role_status_lbl.configure(
                text="",
                text_color=Theme.TEXT_MUTED
            )

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
        """Processes login authentication using AuthService with Store and Role verification."""
        store_choice = self._store_menu.get() if hasattr(self, '_store_menu') else ""
        store_id = self._store_id_map.get(store_choice)
        role = self._role_menu.get() if hasattr(self, '_role_menu') else ""
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not store_id:
            self.msg_label.configure(
                text="Please select or register a valid pharmacy store.",
                text_color=Theme.DANGER
            )
            return

        user, message = self.auth_service.authenticate_with_store_and_role(
            store_id=store_id,
            role=role,
            username=username,
            password=password
        )

        if user:
            self.logger.log_event("AUTH", f"User '{user.username}' (Store: {user.store_name}) logged in successfully.")
            self.msg_label.configure(text="Login successful! Loading...", text_color=Theme.SUCCESS)
            self.update_idletasks()
            if self.on_login_success:
                self.on_login_success(user)
            self.destroy()
        else:
            self.logger.log_event("AUTH", f"Failed login attempt for '{username}' ({role}) at '{store_id}': {message}", level="WARNING")
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
