"""
Authorized Staff & User Account Management Module.
Provides UI interface and modal for Store Owners and Admins to manage staff accounts:
- View all staff accounts scoped strictly to the authenticated store.
- Add new staff accounts with Full Name, Username, Role, Email, and Password.
- Allowed roles: Admin, Pharmacist, Cashier, Inventory Manager.
- Activate / Deactivate staff accounts with protection against self-deactivation.
- Enforces backend RBAC (PERM_MANAGE_USERS) and store isolation.
"""
import tkinter as tk
from tkinter import messagebox
from typing import Optional, List, Dict, Any
import customtkinter as ctk

from models.user import (
    User,
    ROLE_OWNER,
    ROLE_ADMIN,
    ROLE_PHARMACIST,
    ROLE_CASHIER,
    ROLE_INVENTORY_MANAGER,
    PERM_MANAGE_USERS,
    normalize_role,
    has_permission
)
from services.auth_service import AuthService
from services.rbac import require_permission, require_store_access
from ui.theme import Theme
from utils.logger import get_app_logger


STAFF_ALLOWED_ROLES = [ROLE_ADMIN, ROLE_PHARMACIST, ROLE_CASHIER, ROLE_INVENTORY_MANAGER]


class AddStaffAccountModal(ctk.CTkToplevel):
    """Modal dialog allowing authorized Owners and Admins to provision new staff accounts."""

    def __init__(self, parent, acting_user: User, auth_service: AuthService, on_success_callback=None):
        super().__init__(parent)
        self.acting_user = acting_user
        self.auth_service = auth_service
        self.on_success_callback = on_success_callback
        self.logger = get_app_logger()

        self.title("Add New Staff Account")
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        width = 540
        # Responsive height: fits on smaller displays while ensuring fixed footer visibility
        height = min(620, max(460, int(screen_h * 0.82)))
        x = (screen_w - width) // 2
        y = max(10, (screen_h - height) // 2)
        self.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")
        self.minsize(460, 420)
        self.resizable(True, True)
        self.configure(fg_color=Theme.BG_DARK)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self) -> None:
        container = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        container.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. Header Frame (Top)
        header_frame = ctk.CTkFrame(container, fg_color="transparent")
        header_frame.pack(fill="x", padx=20, pady=(16, 6), side="top")

        ctk.CTkLabel(
            header_frame,
            text="👥 Create Staff Account",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(anchor="w", pady=(0, 2))

        ctk.CTkLabel(
            header_frame,
            text=f"Assigning staff to Store: {self.acting_user.store_name} ({self.acting_user.store_id})",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w", pady=(0, 2))

        # 2. Fixed Footer Action Buttons (Bottom) - Permanently anchored and always visible
        btn_box = ctk.CTkFrame(container, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(12, 16), side="bottom")

        cancel_btn = ctk.CTkButton(
            btn_box,
            text="Cancel",
            width=110,
            height=38,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.destroy
        )
        cancel_btn.pack(side="left")

        self.submit_btn = ctk.CTkButton(
            btn_box,
            text="✓ Create Staff Account",
            height=38,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            font=Theme.FONT_BOLD,
            command=self._handle_create_account
        )
        self.submit_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

        # 3. Scrollable Form Container (Middle) - Scrolls vertically on any screen resolution
        scroll_form = ctk.CTkScrollableFrame(container, fg_color="transparent")
        scroll_form.pack(fill="both", expand=True, padx=16, pady=(4, 6), side="top")

        # Error banner inside scrollable container
        self.error_banner = ctk.CTkLabel(
            scroll_form,
            text="",
            font=Theme.FONT_SMALL,
            text_color=Theme.DANGER,
            anchor="w"
        )
        self.error_banner.pack(fill="x", padx=6, pady=(0, 6))

        form = ctk.CTkFrame(scroll_form, fg_color="transparent")
        form.pack(fill="x", padx=6)

        # 1. Full Name
        ctk.CTkLabel(form, text="Full Name *", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.name_entry = ctk.CTkEntry(form, placeholder_text="e.g. Ramesh Patel", height=36, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.name_entry.pack(fill="x", pady=(0, 8))

        # 2. Username
        ctk.CTkLabel(form, text="Username *", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.user_entry = ctk.CTkEntry(form, placeholder_text="e.g. ramesh_cashier", height=36, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.user_entry.pack(fill="x", pady=(0, 8))

        # 3. Role Selection
        ctk.CTkLabel(form, text="Role *", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.role_menu = ctk.CTkOptionMenu(
            form,
            values=STAFF_ALLOWED_ROLES,
            height=36,
            fg_color=Theme.INPUT_BG,
            button_color=Theme.PRIMARY,
            button_hover_color=Theme.PRIMARY_HOVER,
            dropdown_fg_color=Theme.BG_CARD,
            dropdown_text_color=Theme.TEXT_MAIN
        )
        self.role_menu.set(ROLE_PHARMACIST)
        self.role_menu.pack(fill="x", pady=(0, 8))

        # 4. Optional Email
        ctk.CTkLabel(form, text="Email Address (Optional)", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.email_entry = ctk.CTkEntry(form, placeholder_text="e.g. ramesh@pharmacy.local", height=36, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.email_entry.pack(fill="x", pady=(0, 8))

        # 5. Password & Confirm Password
        ctk.CTkLabel(form, text="Password (Min 4 chars) *", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.pass_entry = ctk.CTkEntry(form, placeholder_text="Enter secure password", show="•", height=36, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.pass_entry.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(form, text="Confirm Password *", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(4, 2))
        self.confirm_entry = ctk.CTkEntry(form, placeholder_text="Re-enter password", show="•", height=36, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.confirm_entry.pack(fill="x", pady=(0, 8))

        # Show password toggle
        self.show_pass_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            form,
            text="Show Password",
            variable=self.show_pass_var,
            font=Theme.FONT_SMALL,
            command=self._toggle_password_visibility
        ).pack(anchor="w", pady=(2, 8))

        # Active status checkbox
        self.is_active_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            form,
            text="Active Account (Permitted to log in immediately)",
            variable=self.is_active_var,
            font=Theme.FONT_SMALL,
            checkmark_color=Theme.TEXT_DARK,
            fg_color=Theme.PRIMARY
        ).pack(anchor="w", pady=(2, 14))

    def _toggle_password_visibility(self) -> None:
        char = "" if self.show_pass_var.get() else "•"
        self.pass_entry.configure(show=char)
        self.confirm_entry.configure(show=char)

    def _handle_create_account(self) -> None:
        full_name = self.name_entry.get().strip()
        username = self.user_entry.get().strip()
        role = self.role_menu.get().strip()
        email = self.email_entry.get().strip()
        password = self.pass_entry.get()
        confirm_pass = self.confirm_entry.get()
        is_active = self.is_active_var.get()

        self.error_banner.configure(text="")

        if not full_name:
            self.error_banner.configure(text="⚠️ Full Name is required.")
            self.name_entry.focus()
            return

        if not username or len(username) < 3:
            self.error_banner.configure(text="⚠️ Username must be at least 3 characters.")
            self.user_entry.focus()
            return

        if not password or len(password) < 4:
            self.error_banner.configure(text="⚠️ Password must be at least 4 characters.")
            self.pass_entry.focus()
            return

        if password != confirm_pass:
            self.error_banner.configure(text="⚠️ Passwords do not match.")
            self.confirm_entry.focus()
            return

        # Attempt account creation with acting_user authorization
        success, msg = self.auth_service.create_user(
            username=username,
            password=password,
            role=role,
            store_id=self.acting_user.store_id,
            full_name=full_name,
            email=email if email else None,
            is_active=is_active,
            acting_user=self.acting_user
        )

        if success:
            messagebox.showinfo("Success", f"Staff account '{username}' ({role}) created successfully!", parent=self)
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            self.error_banner.configure(text=f"⚠️ {msg}")



class ResetPasswordModal(ctk.CTkToplevel):
    """Modal dialog allowing authorized Owners and Admins to securely reset a staff account password."""

    def __init__(self, parent, target_user: User, acting_user: User, auth_service: AuthService, on_success_callback=None):
        super().__init__(parent)
        self.target_user = target_user
        self.acting_user = acting_user
        self.auth_service = auth_service
        self.on_success_callback = on_success_callback

        self.title(f"Reset Password - @{target_user.username}")
        self.geometry("480x420")
        self.resizable(False, False)
        self.configure(fg_color=Theme.BG_DARK)

        self.transient(parent)
        self.grab_set()
        self.focus_set()

        self._build_ui()

    def _build_ui(self) -> None:
        card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12, border_width=1, border_color=Theme.BORDER_COLOR)
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card,
            text="🔑 Reset Staff Password",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            card,
            text=f"Resetting password for {self.target_user.full_name or self.target_user.username} (@{self.target_user.username}) — {self.target_user.role}",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED,
            wraplength=420,
            justify="left"
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # Generator button
        gen_box = ctk.CTkFrame(card, fg_color="transparent")
        gen_box.pack(fill="x", padx=20, pady=(0, 10))

        ctk.CTkButton(
            gen_box,
            text="🎲 Generate Secure Temp Password",
            height=32,
            font=Theme.FONT_SMALL,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self._generate_temp_password
        ).pack(side="left")

        # Password Entry
        ctk.CTkLabel(card, text="New Temporary Password (min 6 chars):", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=20, pady=(4, 2))
        self.pwd_entry = ctk.CTkEntry(card, height=36, font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG, border_color=Theme.BORDER_COLOR)
        self.pwd_entry.pack(fill="x", padx=20, pady=(0, 8))

        # Status / Feedback label
        self.feedback_lbl = ctk.CTkLabel(card, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER, wraplength=420)
        self.feedback_lbl.pack(fill="x", padx=20, pady=(0, 10))

        # Buttons footer
        btn_box = ctk.CTkFrame(card, fg_color="transparent")
        btn_box.pack(fill="x", padx=20, pady=(12, 16), side="bottom")

        ctk.CTkButton(
            btn_box,
            text="Cancel",
            width=100,
            height=36,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.destroy
        ).pack(side="left")

        self.submit_btn = ctk.CTkButton(
            btn_box,
            text="Set New Password",
            height=36,
            font=Theme.FONT_BOLD,
            fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER,
            text_color=Theme.TEXT_DARK,
            command=self._handle_reset
        )
        self.submit_btn.pack(side="right", fill="x", expand=True, padx=(10, 0))

    def _generate_temp_password(self) -> None:
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        temp_pwd = ''.join(secrets.choice(alphabet) for _ in range(10))
        self.pwd_entry.delete(0, "end")
        self.pwd_entry.insert(0, temp_pwd)
        self.feedback_lbl.configure(text="✓ Generated 10-character secure temporary password.", text_color=Theme.SUCCESS)

    def _handle_reset(self) -> None:
        new_pwd = self.pwd_entry.get().strip()
        if not new_pwd or len(new_pwd) < 6:
            self.feedback_lbl.configure(text="Password must be at least 6 characters long.", text_color=Theme.DANGER)
            return

        success, msg = self.auth_service.reset_password(
            user_id=self.target_user.user_id,
            new_password=new_pwd,
            acting_user=self.acting_user
        )

        if success:
            # Copy to clipboard
            try:
                self.clipboard_clear()
                self.clipboard_append(new_pwd)
            except Exception:
                pass

            messagebox.showinfo(
                "Password Reset Successful",
                f"Password for @{self.target_user.username} has been reset successfully!\n\n"
                f"Temporary Password: {new_pwd}\n\n"
                "(Password has been copied to clipboard. Share it securely with the staff member; it will not be displayed again.)",
                parent=self
            )
            if self.on_success_callback:
                self.on_success_callback()
            self.destroy()
        else:
            self.feedback_lbl.configure(text=msg, text_color=Theme.DANGER)


class StaffManagementView(ctk.CTkFrame):
    """
    Main View for Staff & User Account Management.
    Accessible only to Owner and Admin roles.
    """

    def __init__(self, parent, user: User, on_navigate_callback=None, **kwargs):
        super().__init__(parent, fg_color=Theme.BG_DARK, **kwargs)
        self.user = user
        self.on_navigate_callback = on_navigate_callback
        self.auth_service = AuthService()
        self.logger = get_app_logger()

        self._build_ui()
        self.refresh_staff_list()

    def _build_ui(self) -> None:
        # Header Toolbar
        toolbar = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=64, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
        toolbar.pack(fill="x", padx=16, pady=(16, 12))
        toolbar.pack_propagate(False)

        title_box = ctk.CTkFrame(toolbar, fg_color="transparent")
        title_box.pack(side="left", padx=16, pady=10)

        ctk.CTkLabel(
            title_box,
            text="👥  Staff & User Accounts",
            font=Theme.FONT_TITLE,
            text_color=Theme.PRIMARY
        ).pack(anchor="w")

        ctk.CTkLabel(
            title_box,
            text=f"Store: {self.user.store_name} ({self.user.store_id}) — Authorized Role Management",
            font=Theme.FONT_SMALL,
            text_color=Theme.TEXT_MUTED
        ).pack(anchor="w")

        # Add Staff Button (guarded for Owner/Admin)
        if self.user.has_permission(PERM_MANAGE_USERS):
            add_btn = ctk.CTkButton(
                toolbar,
                text="➕ Add Staff Account",
                font=Theme.FONT_BOLD,
                height=36,
                fg_color=Theme.PRIMARY,
                hover_color=Theme.PRIMARY_HOVER,
                text_color=Theme.TEXT_DARK,
                command=self._open_add_staff_modal
            )
            add_btn.pack(side="right", padx=16, pady=14)

        refresh_btn = ctk.CTkButton(
            toolbar,
            text="🔄 Refresh",
            width=90,
            height=36,
            font=Theme.FONT_BODY,
            fg_color=Theme.INPUT_BG,
            hover_color=Theme.BORDER_COLOR,
            text_color=Theme.TEXT_MAIN,
            command=self.refresh_staff_list
        )
        refresh_btn.pack(side="right", padx=(0, 8), pady=14)

        # Search Bar
        search_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, height=48, corner_radius=8, border_width=1, border_color=Theme.BORDER_COLOR)
        search_card.pack(fill="x", padx=16, pady=(0, 12))
        search_card.pack_propagate(False)

        ctk.CTkLabel(search_card, text="🔍", font=Theme.FONT_HEADING).pack(side="left", padx=(14, 6))
        self.search_entry = ctk.CTkEntry(
            search_card,
            placeholder_text="Search staff by name, username, or role...",
            fg_color="transparent",
            border_width=0,
            text_color=Theme.TEXT_MAIN
        )
        self.search_entry.pack(side="left", fill="both", expand=True, padx=4, pady=6)
        self.search_entry.bind("<KeyRelease>", lambda e: self._filter_staff())

        # Scrollable Staff List Container
        self.scroll_frame = ctk.CTkScrollableFrame(
            self,
            fg_color="transparent",
            label_text="Registered Store Staff Members",
            label_font=Theme.FONT_BOLD,
            label_text_color=Theme.TEXT_MUTED
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

    def _open_add_staff_modal(self) -> None:
        self._active_modal = AddStaffAccountModal(
            self,
            acting_user=self.user,
            auth_service=self.auth_service,
            on_success_callback=self.refresh_staff_list
        )

    def refresh_staff_list(self) -> None:
        """Loads and displays staff accounts for the current store."""
        try:
            self.cached_users = self.auth_service.get_store_users(
                store_id=self.user.store_id,
                acting_user=self.user
            )
        except Exception as e:
            self.cached_users = []
            messagebox.showerror("Access Error", f"Unable to fetch store users: {e}", parent=self)
            return

        self._render_staff_cards(self.cached_users)

    def _filter_staff(self) -> None:
        query = self.search_entry.get().strip().lower()
        if not query:
            self._render_staff_cards(self.cached_users)
            return

        filtered = [
            u for u in self.cached_users
            if query in (u.full_name or "").lower()
            or query in u.username.lower()
            or query in u.role.lower()
            or query in (u.email or "").lower()
        ]
        self._render_staff_cards(filtered)

    def _render_staff_cards(self, users: List[User]) -> None:
        for child in self.scroll_frame.winfo_children():
            child.destroy()

        if not users:
            empty_card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=8, height=120)
            empty_card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                empty_card,
                text="No staff accounts found matching your query.\nClick '+ Add Staff Account' above to register team members.",
                font=Theme.FONT_BODY,
                text_color=Theme.TEXT_MUTED
            ).pack(expand=True, pady=24)
            return

        role_icons = {
            ROLE_OWNER: "👑",
            ROLE_ADMIN: "🛡️",
            ROLE_PHARMACIST: "💊",
            ROLE_CASHIER: "💰",
            ROLE_INVENTORY_MANAGER: "📦"
        }

        role_colors = {
            ROLE_OWNER: "#f59e0b",
            ROLE_ADMIN: "#3b82f6",
            ROLE_PHARMACIST: "#10b981",
            ROLE_CASHIER: "#14b8a6",
            ROLE_INVENTORY_MANAGER: "#8b5cf6"
        }

        for u in users:
            card = ctk.CTkFrame(self.scroll_frame, fg_color=Theme.BG_CARD, corner_radius=10, border_width=1, border_color=Theme.BORDER_COLOR)
            card.pack(fill="x", pady=4, padx=4)

            # Left: Avatar & Details
            left_box = ctk.CTkFrame(card, fg_color="transparent")
            left_box.pack(side="left", padx=16, pady=12, fill="both", expand=True)

            role_icon = role_icons.get(u.canonical_role, "👤")
            role_color = role_colors.get(u.canonical_role, Theme.PRIMARY)

            top_row = ctk.CTkFrame(left_box, fg_color="transparent")
            top_row.pack(fill="x")

            name_text = u.full_name if u.full_name else u.username.capitalize()
            ctk.CTkLabel(top_row, text=name_text, font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(side="left", padx=(0, 10))

            # Role Pill
            role_pill = ctk.CTkFrame(top_row, fg_color=role_color, corner_radius=6)
            role_pill.pack(side="left", padx=(0, 10))
            ctk.CTkLabel(
                role_pill,
                text=f"{role_icon} {u.role}",
                font=Theme.FONT_SMALL,
                text_color=Theme.TEXT_DARK
            ).pack(padx=8, pady=2)

            # Active status badge
            status_text = "● Active" if u.is_active else "○ Deactivated"
            status_color = Theme.SUCCESS if u.is_active else Theme.DANGER
            ctk.CTkLabel(top_row, text=status_text, font=Theme.FONT_SMALL, text_color=status_color).pack(side="left")

            # Meta details
            meta_text = f"Username: @{u.username} | Email: {u.email or 'N/A'} | Store ID: {u.store_id}"
            ctk.CTkLabel(left_box, text=meta_text, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(4, 0))

            # Right: Action Buttons (Guarded)
            if self.user.has_permission(PERM_MANAGE_USERS) and u.user_id != self.user.user_id and u.canonical_role != ROLE_OWNER:
                right_box = ctk.CTkFrame(card, fg_color="transparent")
                right_box.pack(side="right", padx=16, pady=12)

                toggle_text = "Deactivate" if u.is_active else "Reactivate"
                toggle_color = Theme.DANGER if u.is_active else Theme.SUCCESS

                # Toggle Status Button
                btn = ctk.CTkButton(
                    right_box,
                    text=toggle_text,
                    width=95,
                    height=30,
                    font=Theme.FONT_SMALL,
                    fg_color=toggle_color,
                    hover_color="#e11d48" if u.is_active else "#059669",
                    text_color=Theme.TEXT_DARK,
                    command=lambda target_u=u: self._toggle_staff_status(target_u)
                )
                btn.pack(side="right")

                # Reset Password Button
                reset_btn = ctk.CTkButton(
                    right_box,
                    text="🔑 Reset Password",
                    width=115,
                    height=30,
                    font=Theme.FONT_SMALL,
                    fg_color=Theme.INPUT_BG,
                    hover_color=Theme.BORDER_COLOR,
                    text_color=Theme.TEXT_MAIN,
                    command=lambda target_u=u: self._open_reset_modal(target_u)
                )
                reset_btn.pack(side="right", padx=(0, 6))

    def _toggle_staff_status(self, target_user: User) -> None:
        new_status = not target_user.is_active
        action_word = "reactivate" if new_status else "deactivate"

        if not messagebox.askyesno(
            "Confirm Account Status Change",
            f"Are you sure you want to {action_word} account '@{target_user.username}'?",
            parent=self
        ):
            return

        success, msg = self.auth_service.set_user_active_status(
            user_id=target_user.user_id,
            is_active=new_status,
            acting_user=self.user
        )

        if success:
            messagebox.showinfo("Status Updated", msg, parent=self)
            self.refresh_staff_list()
        else:
            messagebox.showerror("Error", msg, parent=self)


    def _open_reset_modal(self, target_user: User) -> None:
        self._active_reset_modal = ResetPasswordModal(
            self,
            target_user=target_user,
            acting_user=self.user,
            auth_service=self.auth_service,
            on_success_callback=self.refresh_staff_list
        )
