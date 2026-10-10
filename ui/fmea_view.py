"""
FMEA & Risk Audit View – Stage 8.

Provides a complete Failure Mode and Effects Analysis (FMEA) screen for the
Pharmacy Management System (Pharmacy Management System course project).

FMEA scoring scale (1–10):
  Severity (S):   1–2 Negligible | 3–4 Minor | 5–6 Moderate | 7–8 Major | 9 Very Serious | 10 Critical
  Occurrence (O): 1–2 Rare | 3–4 Occasional | 5–6 Moderate | 7–8 Frequent | 9–10 Very Frequent
  Detection (D):  Higher = WORSE. 1–2 Very likely detected | 5–6 Moderate | 9–10 Very difficult to detect

RPN = S × O × D

Risk Level Thresholds (project-defined academic categories):
  Low: 1–39 | Medium: 40–79 | High: 80–124 | Critical: 125–1000
"""
import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk
from typing import Any, Dict, List, Optional

import customtkinter as ctk

from ui.theme import Theme
from utils.fmea import (
    VALID_ACTION_STATUSES,
    FMEARecord,
    FMEAService,
    compute_risk_level,
    validate_score,
)

# Risk level → badge colour mapping
RISK_COLORS = {
    "Critical": Theme.DANGER,
    "High": Theme.WARNING,
    "Medium": Theme.PRIMARY,
    "Low": Theme.SUCCESS,
}

ACTION_STATUS_COLORS = {
    "Open": Theme.DANGER,
    "In Progress": Theme.WARNING,
    "Completed": Theme.SUCCESS,
    "Accepted": Theme.INFO,
}

SORT_OPTIONS = [
    ("RPN ↓", "rpn", "DESC"),
    ("RPN ↑", "rpn", "ASC"),
    ("Severity ↓", "severity", "DESC"),
    ("Occurrence ↓", "occurrence", "DESC"),
    ("Detection ↓", "detection", "DESC"),
    ("Risk Level", "risk_level", "ASC"),
    ("Action Status", "action_status", "ASC"),
    ("FMEA ID", "fmea_id", "ASC"),
]

PROCESSES = [
    "All", "Medicine Inventory", "Billing & Sales", "Q13 Advanced Search",
    "Database Layer", "Reports & Analytics", "Q13 Benchmark", "Authentication",
]

RISK_LEVELS = ["All", "Critical", "High", "Medium", "Low"]


class FMEAView(ctk.CTkFrame):
    """
    Main FMEA & Risk Audit screen.
    Layout:
      ① Header
      ② KPI Cards (Total / Low / Medium / High / Critical / Highest RPN)
      ③ Filters & Controls row
      ④ Main FMEA table (scrollable ttk.Treeview)
      ⑤ Connection card
    """

    def __init__(self, parent, user=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.user = user
        self._service = FMEAService()
        self._all_records: List[FMEARecord] = []
        self._sort_by = "rpn"
        self._sort_dir = "DESC"

        self._process_var = tk.StringVar(value="All")
        self._risk_var = tk.StringVar(value="All")
        self._status_var = tk.StringVar(value="All")
        self._sort_var = tk.StringVar(value="RPN ↓")

        self._build_ui()
        self.refresh()

    # -----------------------------------------------------------------------
    # UI Construction
    # -----------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_COLOR,
        )
        outer.pack(fill="both", expand=True)
        self._outer = outer

        self._build_header()
        self._build_kpi_row()
        self._build_filters()
        self._build_table()
        self._build_connection_card()

    def _build_header(self) -> None:
        card = ctk.CTkFrame(self._outer, fg_color=Theme.BG_CARD, corner_radius=12)
        card.pack(fill="x", pady=(0, 12), padx=4)

        ctk.CTkLabel(
            card, text="🛡️  FMEA & Risk Audit",
            font=Theme.FONT_TITLE, text_color=Theme.SECONDARY, anchor="w",
        ).pack(fill="x", padx=20, pady=(16, 2))

        ctk.CTkLabel(
            card,
            text="Failure Mode and Effects Analysis – Pharmacy Management System ",
            font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 4))

        ctk.CTkLabel(
            card,
            text=(
                "RPN = Severity × Occurrence × Detection  |  "
                "Scores: S (1–10 impact) · O (1–10 frequency) · D (1–10, higher = harder to detect)  |  "
                "Risk thresholds: Low<40 · Medium<80 · High<125 · Critical≥125  (project-defined academic categories)"
            ),
            font=Theme.FONT_SMALL, text_color=Theme.WARNING, anchor="w",
            wraplength=1000, justify="left",
        ).pack(fill="x", padx=20, pady=(0, 14))

    def _build_kpi_row(self) -> None:
        card = ctk.CTkFrame(self._outer, fg_color="transparent")
        card.pack(fill="x", pady=(0, 10), padx=4)

        self._kpi_total = self._kpi_card(card, "Total Failure Modes", "–", Theme.PRIMARY)
        self._kpi_low = self._kpi_card(card, "Low Risk", "–", Theme.SUCCESS)
        self._kpi_medium = self._kpi_card(card, "Medium Risk", "–", Theme.PRIMARY)
        self._kpi_high = self._kpi_card(card, "High Risk", "–", Theme.WARNING)
        self._kpi_critical = self._kpi_card(card, "Critical Risk", "–", Theme.DANGER)
        self._kpi_max_rpn = self._kpi_card(card, "Highest RPN", "–", Theme.SECONDARY)

    def _kpi_card(self, parent, title: str, value: str, color: str) -> ctk.CTkLabel:
        col = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        col.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkLabel(col, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(pady=(12, 2))
        lbl = ctk.CTkLabel(col, text=value, font=Theme.FONT_TITLE, text_color=color)
        lbl.pack(pady=(0, 12))
        return lbl

    def _build_filters(self) -> None:
        card = ctk.CTkFrame(self._outer, fg_color=Theme.BG_CARD, corner_radius=12)
        card.pack(fill="x", pady=(0, 12), padx=4)

        ctk.CTkLabel(
            card, text="🔎 Filters & Controls",
            font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN, anchor="w",
        ).pack(fill="x", padx=20, pady=(14, 8))

        row = ctk.CTkFrame(card, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=(0, 4))

        # Process filter
        self._add_filter_combo(row, "Process/Module:", self._process_var, PROCESSES)
        # Risk level filter
        self._add_filter_combo(row, "Risk Level:", self._risk_var, RISK_LEVELS)
        # Action status filter
        self._add_filter_combo(row, "Action Status:", self._status_var,
                               ["All"] + list(VALID_ACTION_STATUSES))
        # Sort
        sort_labels = [s[0] for s in SORT_OPTIONS]
        self._add_filter_combo(row, "Sort by:", self._sort_var, sort_labels,
                               command=self._on_sort_changed)

        # Buttons
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=20, pady=(4, 14))

        ctk.CTkButton(
            btn_row, text="🔍 Apply Filters", width=130, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.PRIMARY,
            hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
            command=self._apply_filters,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="↺ Refresh", width=100, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG,
            hover_color=Theme.BG_CARD_HOVER, text_color=Theme.TEXT_MUTED,
            command=self.refresh,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="➕ Add Record", width=120, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.SUCCESS,
            hover_color="#8cd4a1", text_color=Theme.TEXT_DARK,
            command=self._on_add,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="✏️ Edit Selected", width=120, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.SECONDARY,
            hover_color="#b89deb", text_color=Theme.TEXT_DARK,
            command=self._on_edit,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="👁 View Details", width=120, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.INFO,
            hover_color="#6acfdf", text_color=Theme.TEXT_DARK,
            command=self._on_view_details,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="🗑 Delete", width=100, height=32,
            font=Theme.FONT_BODY, fg_color=Theme.DANGER,
            hover_color="#e05f7e", text_color=Theme.TEXT_DARK,
            command=self._on_delete,
        ).pack(side="left")

        # Status label
        self._status_lbl = ctk.CTkLabel(
            card, text="", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED
        )
        self._status_lbl.pack(anchor="w", padx=20, pady=(0, 4))

    def _add_filter_combo(self, parent, label_text: str, var: tk.StringVar,
                          values: List[str], command=None) -> None:
        col = ctk.CTkFrame(parent, fg_color="transparent")
        col.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(col, text=label_text, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0, 2))
        menu = ctk.CTkOptionMenu(
            col, values=values, variable=var,
            font=Theme.FONT_BODY,
            command=command,
        )
        menu.pack(anchor="w")

    def _build_table(self) -> None:
        card = ctk.CTkFrame(self._outer, fg_color=Theme.BG_CARD, corner_radius=12)
        card.pack(fill="x", pady=(0, 12), padx=4)

        ctk.CTkLabel(
            card, text="📋 FMEA Risk Register",
            font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN, anchor="w",
        ).pack(fill="x", padx=20, pady=(14, 6))

        # Style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "FMEA.Treeview",
            background=Theme.BG_CARD, fieldbackground=Theme.BG_CARD,
            foreground=Theme.TEXT_MAIN, rowheight=28, font=("Segoe UI", 10),
        )
        style.configure(
            "FMEA.Treeview.Heading",
            background=Theme.BG_SIDEBAR, foreground=Theme.SECONDARY,
            font=("Segoe UI", 10, "bold"),
        )
        style.map("FMEA.Treeview", background=[("selected", Theme.SECONDARY)])

        cols = (
            "ID", "Process/Module", "Failure Mode", "Potential Effect",
            "S", "O", "D", "RPN", "Risk Level", "Action Status",
        )
        tree_frame = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=8)
        tree_frame.pack(fill="x", padx=20, pady=(0, 14))

        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=14,
            style="FMEA.Treeview",
        )

        col_widths = {
            "ID": 45, "Process/Module": 170, "Failure Mode": 260,
            "Potential Effect": 220, "S": 40, "O": 40, "D": 40,
            "RPN": 60, "Risk Level": 90, "Action Status": 110,
        }
        for col in cols:
            self._tree.heading(col, text=col)
            self._tree.column(col, width=col_widths.get(col, 100), anchor="center")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="x", expand=True)
        self._tree.bind("<Double-1>", lambda e: self._on_view_details())

        # Tag colours for risk levels
        self._tree.tag_configure("Critical", foreground=Theme.DANGER)
        self._tree.tag_configure("High", foreground=Theme.WARNING)
        self._tree.tag_configure("Medium", foreground=Theme.PRIMARY)
        self._tree.tag_configure("Low", foreground=Theme.SUCCESS)

    def _build_connection_card(self) -> None:
        card = ctk.CTkFrame(self._outer, fg_color=Theme.BG_CARD, corner_radius=12)
        card.pack(fill="x", pady=(0, 12), padx=4)

        ctk.CTkLabel(
            card, text="🏆 Preventive Risk Management",
            font=Theme.FONT_SUBHEADING, text_color=Theme.SECONDARY, anchor="w",
        ).pack(fill="x", padx=20, pady=(14, 6))

        text = (
            "FMEA identifies potential process failures BEFORE they cause defects and prioritizes corrective "
            "actions using Severity, Occurrence, and Detection.\n\n"
            "RPN = Severity × Occurrence × Detection\n\n"
            "System Connections implemented in this system:\n"
            "• Poka-Yoke: Input validation prevents invalid scores, negative quantities, duplicate codes, "
            "and expired medicine from reaching the database.\n"
            "• Fact-Based Decision Making: Benchmark screen provides empirical SQL timing data; FMEA records "
            "document evidence-based risk assessment rationales.\n"
            "• Kaizen (Continuous Improvement): Action Status tracking drives open items to resolution; "
            "recommended actions are specific and measurable.\n\n"
            "Q13 – Faster Search & Retrieval Risks Addressed:\n"
            "Incorrect retrieval, unsafe sorting (fixed by whitelist), incorrect filter combinations, "
            "query failure (exception handling), and misleading performance measurement (isolated benchmark DB)."
        )
        tb = ctk.CTkTextbox(
            card, fg_color=Theme.INPUT_BG, text_color=Theme.TEXT_MAIN,
            font=Theme.FONT_BODY, height=200, corner_radius=8,
            state="disabled", wrap="word",
        )
        tb.pack(fill="x", padx=20, pady=(0, 16))
        tb.configure(state="normal")
        tb.insert("1.0", text)
        tb.configure(state="disabled")

    # -----------------------------------------------------------------------
    # Data & Refresh
    # -----------------------------------------------------------------------

    def refresh(self) -> None:
        """Reloads all records from DB and refreshes table and KPIs."""
        try:
            self._all_records = self._service.get_all_records(
                sort_by=self._sort_by, sort_dir=self._sort_dir
            )
            self._populate_table(self._all_records)
            self._update_kpis(self._all_records)
            self._set_status(f"✅ {len(self._all_records)} records loaded.", Theme.SUCCESS)
        except Exception as e:
            self._set_status(f"❌ Error loading records: {e}", Theme.DANGER)

    def _apply_filters(self) -> None:
        process = self._process_var.get()
        risk = self._risk_var.get()
        status = self._status_var.get()
        try:
            records = self._service.filter_records(
                process_module=None if process == "All" else process,
                risk_level=None if risk == "All" else risk,
                action_status=None if status == "All" else status,
                sort_by=self._sort_by,
                sort_dir=self._sort_dir,
            )
            self._populate_table(records)
            self._set_status(f"🔍 {len(records)} records match filters.", Theme.PRIMARY)
        except Exception as e:
            self._set_status(f"❌ Filter error: {e}", Theme.DANGER)

    def _populate_table(self, records: List[FMEARecord]) -> None:
        for item in self._tree.get_children():
            self._tree.delete(item)
        for rec in records:
            self._tree.insert(
                "", "end",
                iid=str(rec.fmea_id),
                values=(
                    rec.fmea_id,
                    rec.process_module,
                    rec.failure_mode[:55] + "…" if len(rec.failure_mode) > 55 else rec.failure_mode,
                    rec.potential_effect[:48] + "…" if len(rec.potential_effect) > 48 else rec.potential_effect,
                    rec.severity,
                    rec.occurrence,
                    rec.detection,
                    rec.rpn,
                    rec.risk_level,
                    rec.action_status,
                ),
                tags=(rec.risk_level,),
            )

    def _update_kpis(self, records: List[FMEARecord]) -> None:
        audit = self._service.get_risk_audit()
        self._kpi_total.configure(text=str(audit["total"]))
        self._kpi_low.configure(text=str(audit["counts"].get("Low", 0)))
        self._kpi_medium.configure(text=str(audit["counts"].get("Medium", 0)))
        self._kpi_high.configure(text=str(audit["counts"].get("High", 0)))
        self._kpi_critical.configure(text=str(audit["counts"].get("Critical", 0)))
        self._kpi_max_rpn.configure(text=str(audit.get("highest_rpn", 0)))

    def _on_sort_changed(self, value: str) -> None:
        for label, col, direction in SORT_OPTIONS:
            if label == value:
                self._sort_by = col
                self._sort_dir = direction
                break
        self._apply_filters()

    # -----------------------------------------------------------------------
    # Action handlers
    # -----------------------------------------------------------------------

    def _get_selected_record(self) -> Optional[FMEARecord]:
        selection = self._tree.selection()
        if not selection:
            messagebox.showinfo("No Selection", "Please select a record first.", parent=self)
            return None
        fmea_id = int(selection[0])
        return self._service.get_record_by_id(fmea_id)

    def _on_view_details(self) -> None:
        rec = self._get_selected_record()
        if rec:
            FMEADetailDialog(self, rec)

    def _on_add(self) -> None:
        FMEAFormDialog(self, None, self._service, callback=self.refresh)

    def _on_edit(self) -> None:
        rec = self._get_selected_record()
        if rec:
            FMEAFormDialog(self, rec, self._service, callback=self.refresh)

    def _on_delete(self) -> None:
        rec = self._get_selected_record()
        if not rec:
            return
        confirm = messagebox.askyesno(
            "Confirm Delete",
            f"Delete FMEA record #{rec.fmea_id}?\n\n"
            f"Failure Mode: {rec.failure_mode}\n\n"
            "This action cannot be undone.",
            parent=self,
        )
        if not confirm:
            return
        ok, msg = self._service.delete_record(rec.fmea_id)
        if ok:
            self._set_status(f"✅ Record #{rec.fmea_id} deleted.", Theme.SUCCESS)
            self.refresh()
        else:
            messagebox.showerror("Delete Failed", msg, parent=self)

    def _set_status(self, msg: str, color: str = Theme.TEXT_MUTED) -> None:
        self._status_lbl.configure(text=msg, text_color=color)


# ---------------------------------------------------------------------------
# Detail Dialog
# ---------------------------------------------------------------------------

class FMEADetailDialog(ctk.CTkToplevel):
    """Read-only detail view for a single FMEA record."""

    def __init__(self, parent, record: FMEARecord):
        super().__init__(parent)
        self.title(f"FMEA Detail – #{record.fmea_id}")
        self.geometry("760x700")
        self.resizable(True, True)
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        self._build(record)

    def _build(self, r: FMEARecord) -> None:
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_COLOR,
        )
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        risk_color = RISK_COLORS.get(r.risk_level, Theme.TEXT_MAIN)

        # Header
        ctk.CTkLabel(
            scroll,
            text=f"FMEA #{r.fmea_id} – {r.risk_level} Risk",
            font=Theme.FONT_TITLE, text_color=risk_color,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            scroll, text=r.failure_mode,
            font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN,
        ).pack(anchor="w", pady=(0, 12))

        sections = [
            ("🏭 Process / Module",    r.process_module),
            ("⚠️  Potential Effect",    r.potential_effect),
            ("🔍 Potential Cause",      r.potential_cause),
            ("🛡️  Prevention Control",  r.prevention_control),
            ("🔔 Detection Control",    r.detection_control),
            ("💡 Recommended Action",   r.recommended_action),
        ]
        for title, content in sections:
            self._section(scroll, title, content)

        # Scores
        scores_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=10)
        scores_frame.pack(fill="x", pady=(8, 8))
        ctk.CTkLabel(scores_frame, text="📊 FMEA Scores",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", padx=16, pady=(12, 6))

        for label, val, rationale in [
            ("Severity (S)", r.severity, r.severity_rationale),
            ("Occurrence (O)", r.occurrence, r.occurrence_rationale),
            ("Detection (D)", r.detection, r.detection_rationale),
        ]:
            row = ctk.CTkFrame(scores_frame, fg_color=Theme.INPUT_BG, corner_radius=8)
            row.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row, text=f"{label}: {val}/10",
                         font=Theme.FONT_BOLD, text_color=Theme.PRIMARY).pack(anchor="w", padx=12, pady=(6, 2))
            ctk.CTkLabel(row, text=rationale,
                         font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED,
                         wraplength=680, justify="left").pack(anchor="w", padx=12, pady=(0, 8))

        # RPN & Risk
        rpn_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=10)
        rpn_frame.pack(fill="x", pady=(0, 8))
        rrow = ctk.CTkFrame(rpn_frame, fg_color="transparent")
        rrow.pack(fill="x", padx=16, pady=12)
        ctk.CTkLabel(rrow, text=f"RPN = {r.severity} × {r.occurrence} × {r.detection} = {r.rpn}",
                     font=Theme.FONT_HEADING, text_color=risk_color).pack(side="left")
        ctk.CTkLabel(rrow, text=f"  |  Risk Level: {r.risk_level}",
                     font=Theme.FONT_HEADING, text_color=risk_color).pack(side="left")

        # Status & owner
        meta_frame = ctk.CTkFrame(scroll, fg_color=Theme.BG_CARD, corner_radius=10)
        meta_frame.pack(fill="x", pady=(0, 8))
        mrow = ctk.CTkFrame(meta_frame, fg_color="transparent")
        mrow.pack(fill="x", padx=16, pady=12)
        sc = ACTION_STATUS_COLORS.get(r.action_status, Theme.TEXT_MAIN)
        ctk.CTkLabel(mrow, text=f"Status: {r.action_status}",
                     font=Theme.FONT_BOLD, text_color=sc).pack(side="left", padx=(0, 24))
        ctk.CTkLabel(mrow, text=f"Owner: {r.owner}",
                     font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left")

        ctk.CTkButton(
            scroll, text="Close", width=100, height=32,
            command=self.destroy,
        ).pack(pady=(8, 0))

    def _section(self, parent, title: str, content: str) -> None:
        frame = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=8)
        frame.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(frame, text=title,
                     font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(8, 2))
        ctk.CTkLabel(frame, text=content,
                     font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN,
                     wraplength=700, justify="left").pack(anchor="w", padx=12, pady=(0, 8))


# ---------------------------------------------------------------------------
# Add / Edit Form Dialog
# ---------------------------------------------------------------------------

class FMEAFormDialog(ctk.CTkToplevel):
    """
    Add or Edit dialog for an FMEA record.
    RPN is displayed read-only and recalculated live whenever S/O/D changes.
    RPN cannot be manually edited.
    """

    def __init__(self, parent, record: Optional[FMEARecord],
                 service: FMEAService, callback=None):
        super().__init__(parent)
        self._record = record
        self._service = service
        self._callback = callback
        self.title("Edit FMEA Record" if record else "Add FMEA Record")
        self.geometry("780x820")
        self.resizable(True, True)
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        self._build_form()
        if record:
            self._populate(record)

    # ---- Widgets ----

    def _entry(self, parent, label: str, height: int = 32) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        e = ctk.CTkEntry(parent, height=height, fg_color=Theme.INPUT_BG,
                         font=Theme.FONT_BODY)
        e.pack(fill="x", pady=(0, 4))
        return e

    def _textbox(self, parent, label: str, height: int = 60) -> ctk.CTkTextbox:
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        tb = ctk.CTkTextbox(parent, height=height, fg_color=Theme.INPUT_BG,
                            font=Theme.FONT_BODY, wrap="word")
        tb.pack(fill="x", pady=(0, 4))
        return tb

    def _score_entry(self, parent, label: str) -> ctk.CTkEntry:
        """Creates a score entry (1–10) wired to live RPN recalculation."""
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        e = ctk.CTkEntry(parent, width=80, height=32, fg_color=Theme.INPUT_BG,
                         font=Theme.FONT_BODY)
        e.pack(anchor="w", pady=(0, 4))
        e.bind("<KeyRelease>", self._update_rpn_display)
        return e

    def _build_form(self) -> None:
        scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=Theme.BORDER_COLOR,
        )
        scroll.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            scroll,
            text="Edit FMEA Record" if self._record else "Add FMEA Record",
            font=Theme.FONT_HEADING, text_color=Theme.SECONDARY,
        ).pack(anchor="w", pady=(0, 12))

        # Process
        ctk.CTkLabel(scroll, text="Process / Module:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._process_var = tk.StringVar(value=PROCESSES[1])
        ctk.CTkOptionMenu(
            scroll, values=PROCESSES[1:], variable=self._process_var,
            font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG,
        ).pack(anchor="w", pady=(0, 4))

        self._e_failure = self._entry(scroll, "Failure Mode: *")
        self._e_effect = self._textbox(scroll, "Potential Effect: *")
        self._e_cause = self._textbox(scroll, "Potential Cause: *")
        self._e_prevention = self._textbox(scroll, "Existing Prevention Control:")
        self._e_detection = self._textbox(scroll, "Existing Detection Control:")
        self._e_action = self._textbox(scroll, "Recommended Action: *")

        # Scores row
        score_row = ctk.CTkFrame(scroll, fg_color="transparent")
        score_row.pack(fill="x", pady=(8, 0))

        s_col = ctk.CTkFrame(score_row, fg_color=Theme.BG_CARD, corner_radius=8)
        s_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(s_col, text="Severity (S) 1–10:", font=Theme.FONT_BOLD, text_color=Theme.PRIMARY).pack(pady=(6,2))
        self._e_s = self._score_entry_in(s_col)
        self._e_s_rat = self._textbox_in(s_col, "Severity Rationale:")

        o_col = ctk.CTkFrame(score_row, fg_color=Theme.BG_CARD, corner_radius=8)
        o_col.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkLabel(o_col, text="Occurrence (O) 1–10:", font=Theme.FONT_BOLD, text_color=Theme.PRIMARY).pack(pady=(6,2))
        self._e_o = self._score_entry_in(o_col)
        self._e_o_rat = self._textbox_in(o_col, "Occurrence Rationale:")

        d_col = ctk.CTkFrame(score_row, fg_color=Theme.BG_CARD, corner_radius=8)
        d_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(d_col, text="Detection (D) 1–10:", font=Theme.FONT_BOLD, text_color=Theme.PRIMARY).pack(pady=(6,2))
        self._e_d = self._score_entry_in(d_col)
        self._e_d_rat = self._textbox_in(d_col, "Detection Rationale:")

        # RPN display (read-only)
        rpn_frame = ctk.CTkFrame(scroll, fg_color=Theme.INPUT_BG, corner_radius=8)
        rpn_frame.pack(fill="x", pady=(8, 4))
        rrow = ctk.CTkFrame(rpn_frame, fg_color="transparent")
        rrow.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(rrow, text="RPN (auto-computed):",
                     font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(side="left")
        self._rpn_lbl = ctk.CTkLabel(rrow, text="–",
                                     font=Theme.FONT_HEADING, text_color=Theme.SECONDARY)
        self._rpn_lbl.pack(side="left", padx=12)
        self._risk_lbl = ctk.CTkLabel(rrow, text="",
                                      font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED)
        self._risk_lbl.pack(side="left")

        # Action Status & Owner
        meta_row = ctk.CTkFrame(scroll, fg_color="transparent")
        meta_row.pack(fill="x", pady=(8, 0))

        stat_col = ctk.CTkFrame(meta_row, fg_color="transparent")
        stat_col.pack(side="left", fill="x", expand=True, padx=(0, 12))
        ctk.CTkLabel(stat_col, text="Action Status:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._status_var = tk.StringVar(value="Open")
        ctk.CTkOptionMenu(
            stat_col, values=list(VALID_ACTION_STATUSES),
            variable=self._status_var, font=Theme.FONT_BODY,
        ).pack(anchor="w", pady=(4, 0))

        owner_col = ctk.CTkFrame(meta_row, fg_color="transparent")
        owner_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(owner_col, text="Owner / Responsible Role:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_owner = ctk.CTkEntry(
            owner_col, height=32, fg_color=Theme.INPUT_BG,
            font=Theme.FONT_BODY,
        )
        self._e_owner.pack(fill="x", pady=(4, 0))
        self._e_owner.insert(0, "Development Team")

        # Error label
        self._err_lbl = ctk.CTkLabel(scroll, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        self._err_lbl.pack(anchor="w", pady=(6, 0))

        # Buttons
        btn_row = ctk.CTkFrame(scroll, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))
        ctk.CTkButton(
            btn_row, text="💾 Save", width=120, height=34,
            command=self._on_save,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            btn_row, text="Cancel", width=100, height=34,
            command=self.destroy,
        ).pack(side="left")

    def _score_entry_in(self, parent) -> ctk.CTkEntry:
        e = ctk.CTkEntry(parent, width=70, height=30, fg_color=Theme.INPUT_BG,
                         font=Theme.FONT_BODY)
        e.pack(anchor="w", padx=10, pady=(4, 0))
        e.bind("<KeyRelease>", self._update_rpn_display)
        return e

    def _textbox_in(self, parent, label: str) -> ctk.CTkTextbox:
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        tb = ctk.CTkTextbox(parent, height=55, fg_color=Theme.BG_DARK, font=Theme.FONT_BODY, wrap="word")
        tb.pack(fill="x", padx=10, pady=(0, 10))
        return tb

    def _get_text(self, widget) -> str:
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def _set_text(self, widget, text: str) -> None:
        if isinstance(widget, ctk.CTkTextbox):
            widget.delete("1.0", "end")
            widget.insert("1.0", text)
        else:
            widget.delete(0, "end")
            widget.insert(0, text)

    def _populate(self, r: FMEARecord) -> None:
        self._process_var.set(r.process_module)
        self._set_text(self._e_failure, r.failure_mode)
        self._set_text(self._e_effect, r.potential_effect)
        self._set_text(self._e_cause, r.potential_cause)
        self._set_text(self._e_prevention, r.prevention_control)
        self._set_text(self._e_detection, r.detection_control)
        self._set_text(self._e_action, r.recommended_action)
        self._set_text(self._e_s, str(r.severity))
        self._set_text(self._e_s_rat, r.severity_rationale)
        self._set_text(self._e_o, str(r.occurrence))
        self._set_text(self._e_o_rat, r.occurrence_rationale)
        self._set_text(self._e_d, str(r.detection))
        self._set_text(self._e_d_rat, r.detection_rationale)
        self._status_var.set(r.action_status)
        self._set_text(self._e_owner, r.owner)
        self._update_rpn_display()

    def _update_rpn_display(self, event=None) -> None:
        """Recalculates RPN live as S/O/D values change. RPN field is read-only."""
        try:
            s = int(self._e_s.get())
            o = int(self._e_o.get())
            d = int(self._e_d.get())
            if all(1 <= v <= 10 for v in (s, o, d)):
                rpn = s * o * d
                risk = compute_risk_level(rpn)
                self._rpn_lbl.configure(text=str(rpn))
                self._risk_lbl.configure(text=f"→ {risk}")
            else:
                self._rpn_lbl.configure(text="–", text_color=Theme.TEXT_MUTED)
                self._risk_lbl.configure(text="(invalid scores)", text_color=Theme.DANGER)
        except (ValueError, TypeError):
            self._rpn_lbl.configure(text="–", text_color=Theme.TEXT_MUTED)
            self._risk_lbl.configure(text="(enter 1–10)", text_color=Theme.WARNING)

    def _on_save(self) -> None:
        # Validate scores with validate_score helper
        s_val, s_err = validate_score(self._e_s.get(), "Severity")
        o_val, o_err = validate_score(self._e_o.get(), "Occurrence")
        d_val, d_err = validate_score(self._e_d.get(), "Detection")

        errors = [e for e in [s_err, o_err, d_err] if e]
        if errors:
            self._err_lbl.configure(text=" | ".join(errors))
            return

        rec = FMEARecord(
            fmea_id=self._record.fmea_id if self._record else None,
            process_module=self._process_var.get(),
            failure_mode=self._get_text(self._e_failure),
            potential_effect=self._get_text(self._e_effect),
            potential_cause=self._get_text(self._e_cause),
            prevention_control=self._get_text(self._e_prevention),
            detection_control=self._get_text(self._e_detection),
            severity=s_val,
            severity_rationale=self._get_text(self._e_s_rat),
            occurrence=o_val,
            occurrence_rationale=self._get_text(self._e_o_rat),
            detection=d_val,
            detection_rationale=self._get_text(self._e_d_rat),
            recommended_action=self._get_text(self._e_action),
            action_status=self._status_var.get(),
            owner=self._get_text(self._e_owner),
        )

        val_errors = rec.validate()
        if val_errors:
            self._err_lbl.configure(text=" | ".join(val_errors))
            return

        if self._record:
            ok, msg = self._service.update_record(rec)
        else:
            ok, msg = self._service.add_record(rec)

        if ok:
            if self._callback:
                self._callback()
            self.destroy()
        else:
            self._err_lbl.configure(text=f"❌ {msg}")
