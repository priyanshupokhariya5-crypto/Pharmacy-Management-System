"""
Stage 9 – SQC & Continuous Improvement View.

Provides a tabbed interface:
  Tab 1 – SQC Dashboard   (live KPIs + Pareto chart)
  Tab 2 – Defect Log      (full CRUD checksheet)
  Tab 3 – Fishbone        (Ishikawa root-cause diagram)
  Tab 4 – PDCA / Kaizen   (Continuous Improvement tracker)

Q13 Focus: Faster Search & Retrieval
All seeded records are labelled as demo/initial data – not historical measurements.
"""
import tkinter as tk
from tkinter import messagebox
import tkinter.ttk as ttk
from typing import List, Optional

import customtkinter as ctk

from ui.theme import Theme
from utils.sqc import (
    DEFECT_MODULES, DEFECT_SEVERITIES, DEFECT_STATUSES,
    FISHBONE_CAUSES, PDCA_STATUSES,
    PDCAItem, SQCDefect, SQCService,
)

# matplotlib (may not be available – handled gracefully)
try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MPLOK = True
except ImportError:
    MPLOK = False

SEVERITY_COLORS = {
    "Critical": Theme.DANGER,
    "High":     Theme.WARNING,
    "Medium":   Theme.PRIMARY,
    "Low":      Theme.SUCCESS,
}
STATUS_COLORS = {
    "Open":        Theme.DANGER,
    "In Progress": Theme.WARNING,
    "Closed":      Theme.SUCCESS,
    "Accepted":    Theme.INFO,
}
PDCA_STATUS_COLORS = {
    "Plan":   Theme.PRIMARY,
    "Do":     Theme.WARNING,
    "Check":  Theme.INFO,
    "Act":    Theme.SUCCESS,
    "Closed": Theme.TEXT_MUTED,
}


# ---------------------------------------------------------------------------
# Helper: ttk.Treeview style factory
# ---------------------------------------------------------------------------

def _make_tree_style(name: str) -> None:
    s = ttk.Style()
    s.theme_use("clam")
    s.configure(f"{name}.Treeview",
                background=Theme.BG_CARD, fieldbackground=Theme.BG_CARD,
                foreground=Theme.TEXT_MAIN, rowheight=26,
                font=("Segoe UI", 10))
    s.configure(f"{name}.Treeview.Heading",
                background=Theme.BG_SIDEBAR, foreground=Theme.SECONDARY,
                font=("Segoe UI", 10, "bold"))
    s.map(f"{name}.Treeview", background=[("selected", Theme.SECONDARY)])


# ---------------------------------------------------------------------------
# Main view container
# ---------------------------------------------------------------------------

class SQCView(ctk.CTkFrame):
    """Stage 9 – SQC & Continuous Improvement main screen."""

    def __init__(self, parent, user=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self.user = user
        store_id = getattr(self.user, 'store_id', 'STORE-LEGACY-001') if self.user else 'STORE-LEGACY-001'
        self._svc = SQCService(store_id=store_id)
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        # Header
        hdr = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=12)
        hdr.pack(fill="x", pady=(0, 10), padx=4)
        ctk.CTkLabel(hdr, text="📊  SQC & Continuous Improvement",
                     font=Theme.FONT_TITLE, text_color=Theme.SECONDARY,
                     anchor="w").pack(fill="x", padx=20, pady=(12, 2))
        ctk.CTkLabel(
            hdr,
            text=(
                "Statistical Quality Control · Defect Log · Pareto Analysis · "
                "Fishbone Diagram · PDCA / Kaizen  |  Q13: Faster Search & Retrieval"
            ),
            font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 12))

        # Tabview
        self._tabs = ctk.CTkTabview(
            self, fg_color=Theme.BG_CARD, corner_radius=12,
            segmented_button_fg_color=Theme.BG_SIDEBAR,
            segmented_button_selected_color=Theme.PRIMARY,
            segmented_button_selected_hover_color=Theme.PRIMARY_HOVER,
            segmented_button_unselected_color=Theme.BG_SIDEBAR,
            segmented_button_unselected_hover_color=Theme.INPUT_BG,
        )
        self._tabs.pack(fill="both", expand=True, padx=4)
        self._tabs.add("🏠 Dashboard")
        self._tabs.add("📋 Defect Log")
        self._tabs.add("🐟 Fishbone")
        self._tabs.add("🔄 PDCA / Kaizen")

        self._dashboard_tab = SQCDashboardTab(
            self._tabs.tab("🏠 Dashboard"), self._svc
        )
        self._dashboard_tab.pack(fill="both", expand=True)

        self._defect_tab = DefectLogTab(
            self._tabs.tab("📋 Defect Log"), self._svc
        )
        self._defect_tab.pack(fill="both", expand=True)

        self._fishbone_tab = FishboneTab(self._tabs.tab("🐟 Fishbone"))
        self._fishbone_tab.pack(fill="both", expand=True)

        self._pdca_tab = PDCATab(
            self._tabs.tab("🔄 PDCA / Kaizen"), self._svc
        )
        self._pdca_tab.pack(fill="both", expand=True)

    def refresh(self) -> None:
        self._dashboard_tab.refresh()
        self._defect_tab.refresh()
        self._pdca_tab.refresh()


# ---------------------------------------------------------------------------
# Tab 1 – SQC Dashboard
# ---------------------------------------------------------------------------

class SQCDashboardTab(ctk.CTkScrollableFrame):
    def __init__(self, parent, svc: SQCService, **kwargs):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=Theme.BORDER_COLOR, **kwargs)
        self._svc = svc
        self._pareto_canvas = None
        self._build_ui()

    def _build_ui(self) -> None:
        # KPI row
        kpi_row = ctk.CTkFrame(self, fg_color="transparent")
        kpi_row.pack(fill="x", pady=(8, 10), padx=4)
        self._k_total  = self._kpi(kpi_row, "Total Defects",      "–", Theme.PRIMARY)
        self._k_open   = self._kpi(kpi_row, "Open Defects",        "–", Theme.DANGER)
        self._k_hc     = self._kpi(kpi_row, "High/Critical",       "–", Theme.WARNING)
        self._k_top    = self._kpi(kpi_row, "Top Defect Type",     "–", Theme.SECONDARY)
        self._k_pdca_o = self._kpi(kpi_row, "PDCA Open",           "–", Theme.INFO)
        self._k_pdca_c = self._kpi(kpi_row, "PDCA Closed",         "–", Theme.SUCCESS)

        # Pareto chart area
        chart_card = ctk.CTkFrame(self, fg_color=Theme.INPUT_BG, corner_radius=10)
        chart_card.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(chart_card, text="📈 Pareto Analysis – Defect Type Frequency",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.SECONDARY,
                     anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        ctk.CTkLabel(chart_card,
                     text="Chart generated from live sqc_defects database. 80% line shows Pareto threshold.",
                     font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w",
                     ).pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkButton(chart_card, text="🔄 Refresh Chart", width=140, height=28,
                      font=Theme.FONT_SMALL, fg_color=Theme.PRIMARY,
                      hover_color=Theme.PRIMARY_HOVER, text_color=Theme.TEXT_DARK,
                      command=self.refresh).pack(anchor="w", padx=16, pady=(0, 6))
        self._chart_frame = ctk.CTkFrame(chart_card, fg_color="transparent")
        self._chart_frame.pack(fill="x", padx=12, pady=(0, 12))

        # Note
        info_card = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        info_card.pack(fill="x", padx=4, pady=(0, 8))
        ctk.CTkLabel(info_card, text="🏆 Fact-Based Decision Making & Kaizen",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.SECONDARY, anchor="w",
                     ).pack(fill="x", padx=16, pady=(12, 4))
        txt = (
            "SQC uses actual defect frequency data (not estimates) to drive Pareto analysis. "
            "The 80/20 rule identifies which defect types deserve priority corrective action.\n\n"
            "PDCA (Plan → Do → Check → Act) provides a structured continuous improvement cycle. "
            "Each improvement action is tracked from problem identification through "
            "standardization.\n\n"
            "Q13 (Faster Search & Retrieval) improvements are tracked in PDCA-001 and PDCA-005. "
            "Defect types 'Incorrect Retrieval' and 'Performance Issue' appear in the Pareto chart "
            "and drive the search optimization roadmap."
        )
        tb = ctk.CTkTextbox(info_card, height=150, fg_color=Theme.INPUT_BG,
                            state="disabled", wrap="word", corner_radius=8)
        tb.pack(fill="x", padx=16, pady=(0, 14))
        tb.configure(state="normal"); tb.insert("1.0", txt); tb.configure(state="disabled")

    def _kpi(self, parent, title, value, color) -> ctk.CTkLabel:
        col = ctk.CTkFrame(parent, fg_color=Theme.BG_CARD, corner_radius=10)
        col.pack(side="left", expand=True, fill="x", padx=(0, 8))
        ctk.CTkLabel(col, text=title, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        lbl = ctk.CTkLabel(col, text=value, font=Theme.FONT_HEADING, text_color=color)
        lbl.pack(pady=(0, 10))
        return lbl

    def refresh(self) -> None:
        kpis = self._svc.get_dashboard_kpis()
        self._k_total.configure(text=str(kpis["total_defects"]))
        self._k_open.configure(text=str(kpis["open_defects"]))
        self._k_hc.configure(text=str(kpis["high_critical_defects"]))
        self._k_top.configure(text=f"{kpis['top_defect_type']}\n({kpis['top_defect_freq']}×)",
                              font=("Segoe UI", 10, "bold"))
        self._k_pdca_o.configure(text=str(kpis["pdca_open"]))
        self._k_pdca_c.configure(text=str(kpis["pdca_closed"]))
        self._draw_pareto()

    def _draw_pareto(self) -> None:
        """Draws a Pareto chart from live DB data."""
        # Clear old chart
        for w in self._chart_frame.winfo_children():
            w.destroy()
        if self._pareto_canvas:
            try:
                self._pareto_canvas.get_tk_widget().destroy()
            except Exception:
                pass
            self._pareto_canvas = None

        pareto_data = self._svc.get_pareto_data()
        if not pareto_data:
            ctk.CTkLabel(self._chart_frame, text="No defect data for Pareto chart.",
                         font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(pady=40)
            return

        if not MPLOK:
            ctk.CTkLabel(self._chart_frame,
                         text="Matplotlib not installed. Install it with: pip install matplotlib",
                         font=Theme.FONT_BODY, text_color=Theme.WARNING).pack(pady=20)
            return

        labels = [d["defect_type"] for d in pareto_data]
        freqs  = [d["frequency"] for d in pareto_data]
        cum_pct = [d["cumulative_pct"] for d in pareto_data]

        # Shorten long labels
        short_labels = [l[:22] + "…" if len(l) > 22 else l for l in labels]

        fig, ax1 = plt.subplots(figsize=(9, 4))
        fig.patch.set_facecolor("#1e1e2e")
        ax1.set_facecolor("#313244")

        x = range(len(labels))
        bars = ax1.bar(x, freqs, color="#89b4fa", alpha=0.85, zorder=3)
        ax1.set_xticks(list(x))
        ax1.set_xticklabels(short_labels, rotation=28, ha="right",
                             color="#cdd6f4", fontsize=8.5)
        ax1.set_ylabel("Frequency", color="#cdd6f4", fontsize=9)
        ax1.tick_params(axis="y", colors="#cdd6f4")
        ax1.tick_params(axis="x", colors="#cdd6f4")
        for spine in ax1.spines.values():
            spine.set_edgecolor("#313244")

        ax2 = ax1.twinx()
        ax2.plot(list(x), cum_pct, color="#f9e2af", marker="o",
                 linewidth=2, markersize=5, label="Cumulative %")
        ax2.axhline(80, color="#f38ba8", linestyle="--", linewidth=1.4, label="80% threshold")
        ax2.set_ylim(0, 110)
        ax2.set_ylabel("Cumulative %", color="#cdd6f4", fontsize=9)
        ax2.tick_params(axis="y", colors="#cdd6f4")
        for spine in ax2.spines.values():
            spine.set_edgecolor("#313244")
        ax2.legend(loc="lower right", facecolor="#1e1e2e",
                   labelcolor="#cdd6f4", fontsize=8)

        ax1.set_title("Pareto Chart – Defect Types by Frequency (Live DB Data)",
                      color="#cba6f7", fontsize=11, pad=8)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x")
        self._pareto_canvas = canvas
        plt.close(fig)


# ---------------------------------------------------------------------------
# Tab 2 – Defect Log
# ---------------------------------------------------------------------------

class DefectLogTab(ctk.CTkFrame):
    def __init__(self, parent, svc: SQCService, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._svc = svc
        self._build_ui()

    def _build_ui(self) -> None:
        # Filter/control row
        ctrl = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        ctrl.pack(fill="x", pady=(4, 8), padx=4)
        ctk.CTkLabel(ctrl, text="🔎 Filters & Actions",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN,
                     anchor="w").pack(fill="x", padx=16, pady=(10, 6))

        frow = ctk.CTkFrame(ctrl, fg_color="transparent")
        frow.pack(fill="x", padx=16, pady=(0, 4))

        self._sev_var = tk.StringVar(value="All")
        self._stat_var = tk.StringVar(value="All")
        self._mod_var = tk.StringVar(value="All")

        for label, var, values in [
            ("Severity:", self._sev_var, ["All"] + list(DEFECT_SEVERITIES)),
            ("Status:",   self._stat_var, ["All"] + list(DEFECT_STATUSES)),
            ("Module:",   self._mod_var,  ["All"] + list(DEFECT_MODULES)),
        ]:
            col = ctk.CTkFrame(frow, fg_color="transparent")
            col.pack(side="left", padx=(0, 16))
            ctk.CTkLabel(col, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
            ctk.CTkOptionMenu(col, values=values, variable=var,
                              font=Theme.FONT_BODY, fg_color=Theme.INPUT_BG,
                              ).pack()

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))
        for text, color, cmd in [
            ("🔍 Filter",    Theme.PRIMARY, self._apply_filter),
            ("↺ Refresh",   Theme.INPUT_BG, self.refresh),
            ("➕ Add",       Theme.SUCCESS,  self._on_add),
            ("✏️ Edit",      Theme.SECONDARY, self._on_edit),
            ("🗑 Delete",    Theme.DANGER,   self._on_delete),
        ]:
            ctk.CTkButton(btn_row, text=text, width=100, height=30,
                          font=Theme.FONT_BODY, fg_color=color,
                          hover_color=Theme.BG_CARD_HOVER,
                          command=cmd).pack(side="left", padx=(0, 6))

        self._status_lbl = ctk.CTkLabel(ctrl, text="", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        self._status_lbl.pack(anchor="w", padx=16, pady=(0, 4))

        # Table
        cols = ("ID", "Date", "Module", "Defect Type", "Severity", "Freq", "Status")
        _make_tree_style("DEF")
        tree_wrap = ctk.CTkFrame(self, fg_color=Theme.INPUT_BG, corner_radius=8)
        tree_wrap.pack(fill="both", expand=True, padx=4)

        self._tree = ttk.Treeview(tree_wrap, columns=cols, show="headings",
                                  height=16, style="DEF.Treeview")
        widths = {"ID": 40, "Date": 90, "Module": 160, "Defect Type": 180,
                  "Severity": 80, "Freq": 45, "Status": 100}
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=widths.get(c, 100), anchor="center")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda e: self._on_view_detail())

        for tag, color in SEVERITY_COLORS.items():
            self._tree.tag_configure(tag, foreground=color)

    def refresh(self, records: Optional[List[SQCDefect]] = None) -> None:
        if records is None:
            records = self._svc.get_all_defects()
        for i in self._tree.get_children():
            self._tree.delete(i)
        for r in records:
            self._tree.insert("", "end", iid=str(r.defect_id),
                              values=(r.defect_id, r.date_reported, r.module,
                                      r.defect_type, r.severity, r.frequency, r.status),
                              tags=(r.severity,))
        self._status_lbl.configure(text=f"✅ {len(records)} records")

    def _apply_filter(self) -> None:
        sev  = self._sev_var.get()
        stat = self._stat_var.get()
        mod  = self._mod_var.get()
        recs = self._svc.filter_defects(
            module=None if mod == "All" else mod,
            severity=None if sev == "All" else sev,
            status=None if stat == "All" else stat,
        )
        self.refresh(recs)

    def _get_selected(self) -> Optional[SQCDefect]:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a record.", parent=self)
            return None
        return self._svc.get_defect_by_id(int(sel[0]))

    def _on_add(self) -> None:
        DefectFormDialog(self, None, self._svc, callback=self.refresh)

    def _on_edit(self) -> None:
        rec = self._get_selected()
        if rec:
            DefectFormDialog(self, rec, self._svc, callback=self.refresh)

    def _on_view_detail(self) -> None:
        rec = self._get_selected()
        if rec:
            DefectDetailDialog(self, rec)

    def _on_delete(self) -> None:
        rec = self._get_selected()
        if not rec:
            return
        if messagebox.askyesno("Confirm Delete",
                               f"Delete Defect #{rec.defect_id} – {rec.defect_type}?\n\nCannot be undone.",
                               parent=self):
            ok, msg = self._svc.delete_defect(rec.defect_id)
            if ok:
                self.refresh()
            else:
                messagebox.showerror("Error", msg, parent=self)


# ---------------------------------------------------------------------------
# Defect Detail Dialog
# ---------------------------------------------------------------------------

class DefectDetailDialog(ctk.CTkToplevel):
    def __init__(self, parent, rec: SQCDefect):
        super().__init__(parent)
        self.title(f"Defect #{rec.defect_id} – Detail")
        self.geometry("700x560")
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                    scrollbar_button_color=Theme.BORDER_COLOR)
        sc.pack(fill="both", expand=True, padx=14, pady=14)
        color = SEVERITY_COLORS.get(rec.severity, Theme.TEXT_MAIN)
        ctk.CTkLabel(sc, text=f"Defect #{rec.defect_id} – {rec.severity} Severity",
                     font=Theme.FONT_TITLE, text_color=color).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(sc, text=rec.defect_type,
                     font=Theme.FONT_HEADING, text_color=Theme.TEXT_MAIN).pack(anchor="w", pady=(0, 10))
        for label, val in [
            ("📅 Date Reported", rec.date_reported),
            ("🏭 Module", rec.module),
            ("📝 Description", rec.description),
            ("🔍 Root Cause", rec.root_cause or "Not documented"),
            ("🛠 Corrective Action", rec.corrective_action or "None"),
        ]:
            f = ctk.CTkFrame(sc, fg_color=Theme.BG_CARD, corner_radius=8)
            f.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(f, text=label, font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(8,2))
            ctk.CTkLabel(f, text=val, font=Theme.FONT_BODY,
                         justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        meta = ctk.CTkFrame(sc, fg_color=Theme.BG_CARD, corner_radius=8)
        meta.pack(fill="x", pady=(0, 8))
        mrow = ctk.CTkFrame(meta, fg_color="transparent")
        mrow.pack(fill="x", padx=12, pady=10)
        sc2 = STATUS_COLORS.get(rec.status, Theme.TEXT_MAIN)
        ctk.CTkLabel(mrow, text=f"Status: {rec.status}", font=Theme.FONT_BOLD, text_color=sc2).pack(side="left", padx=(0, 24))
        ctk.CTkLabel(mrow, text=f"Frequency: {rec.frequency}",
                     font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left", padx=(0, 24))
        ctk.CTkLabel(mrow, text=f"Reported by: {rec.reported_by}",
                     font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left")
        ctk.CTkButton(sc, text="Close", width=90, height=30, command=self.destroy).pack(pady=(16,0))


# ---------------------------------------------------------------------------
# Defect Add/Edit Form Dialog
# ---------------------------------------------------------------------------

class DefectFormDialog(ctk.CTkToplevel):
    def __init__(self, parent, rec: Optional[SQCDefect], svc: SQCService, callback=None):
        super().__init__(parent)
        self._rec = rec
        self._svc = svc
        self._cb = callback
        self.title("Edit Defect" if rec else "Log New Defect")
        self.geometry("700x700")
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        self._build()
        if rec:
            self._populate(rec)

    def _build(self) -> None:
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                    scrollbar_button_color=Theme.BORDER_COLOR)
        sc.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(sc, text="Log New Defect" if not self._rec else "Edit Defect",
                     font=Theme.FONT_HEADING, text_color=Theme.SECONDARY).pack(anchor="w", pady=(0, 10))

        # Date
        ctk.CTkLabel(sc, text="Date Reported (YYYY-MM-DD): *",
                     font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w")
        self._e_date = ctk.CTkEntry(sc, height=30, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_date.pack(fill="x", pady=(2, 8))
        self._e_date.insert(0, __import__("datetime").date.today().isoformat())

        # Module
        ctk.CTkLabel(sc, text="Module / Process:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._mod_var = tk.StringVar(value=DEFECT_MODULES[0])
        ctk.CTkOptionMenu(sc, values=list(DEFECT_MODULES), variable=self._mod_var,
                          font=Theme.FONT_BODY).pack(fill="x", pady=(2, 8))

        # Defect type
        ctk.CTkLabel(sc, text="Defect Type: *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_type = ctk.CTkEntry(sc, height=30, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_type.pack(fill="x", pady=(2, 8))

        # Description
        ctk.CTkLabel(sc, text="Description: *", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_desc = ctk.CTkTextbox(sc, height=70, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY, wrap="word")
        self._e_desc.pack(fill="x", pady=(2, 8))

        # Severity + Frequency row
        row = ctk.CTkFrame(sc, fg_color="transparent")
        row.pack(fill="x", pady=(0, 8))
        l_col = ctk.CTkFrame(row, fg_color="transparent")
        l_col.pack(side="left", fill="x", expand=True, padx=(0, 12))
        ctk.CTkLabel(l_col, text="Severity:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._sev_var = tk.StringVar(value="Medium")
        ctk.CTkOptionMenu(l_col, values=list(DEFECT_SEVERITIES), variable=self._sev_var,
                          font=Theme.FONT_BODY).pack(fill="x", pady=(2, 0))
        r_col = ctk.CTkFrame(row, fg_color="transparent")
        r_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(r_col, text="Frequency (count):", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_freq = ctk.CTkEntry(r_col, height=30, width=80, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_freq.pack(anchor="w", pady=(2, 0))
        self._e_freq.insert(0, "1")

        # Status
        ctk.CTkLabel(sc, text="Status:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._stat_var = tk.StringVar(value="Open")
        ctk.CTkOptionMenu(sc, values=list(DEFECT_STATUSES), variable=self._stat_var,
                          font=Theme.FONT_BODY).pack(fill="x", pady=(2, 8))

        # Root cause
        ctk.CTkLabel(sc, text="Root Cause:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_cause = ctk.CTkTextbox(sc, height=55, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY, wrap="word")
        self._e_cause.pack(fill="x", pady=(2, 8))

        # Corrective action
        ctk.CTkLabel(sc, text="Corrective Action:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_action = ctk.CTkTextbox(sc, height=55, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY, wrap="word")
        self._e_action.pack(fill="x", pady=(2, 8))

        # Reported by
        ctk.CTkLabel(sc, text="Reported By:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_rep = ctk.CTkEntry(sc, height=30, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_rep.pack(fill="x", pady=(2, 8))
        self._e_rep.insert(0, "QA Team")

        self._err = ctk.CTkLabel(sc, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        self._err.pack(anchor="w", pady=(4, 0))

        btn = ctk.CTkFrame(sc, fg_color="transparent")
        btn.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(btn, text="💾 Save", width=110, height=32, command=self._on_save).pack(side="left", padx=(0, 10))
        ctk.CTkButton(btn, text="Cancel", width=90, height=32, fg_color=Theme.BG_CARD, text_color=Theme.TEXT_MAIN, hover_color=Theme.INPUT_BG, command=self.destroy).pack(side="left")
    def _get_tb(self, w) -> str:
        return w.get("1.0", "end").strip()

    def _populate(self, r: SQCDefect) -> None:
        self._e_date.delete(0, "end"); self._e_date.insert(0, r.date_reported)
        self._mod_var.set(r.module)
        self._e_type.delete(0, "end"); self._e_type.insert(0, r.defect_type)
        self._e_desc.delete("1.0", "end"); self._e_desc.insert("1.0", r.description)
        self._sev_var.set(r.severity)
        self._e_freq.delete(0, "end"); self._e_freq.insert(0, str(r.frequency))
        self._stat_var.set(r.status)
        self._e_cause.delete("1.0", "end"); self._e_cause.insert("1.0", r.root_cause)
        self._e_action.delete("1.0", "end"); self._e_action.insert("1.0", r.corrective_action)
        self._e_rep.delete(0, "end"); self._e_rep.insert(0, r.reported_by)

    def _save(self) -> None:
        try:
            freq = int(self._e_freq.get().strip())
        except ValueError:
            self._err.configure(text="Frequency must be a positive integer.")
            return
        rec = SQCDefect(
            defect_id=self._rec.defect_id if self._rec else None,
            date_reported=self._e_date.get().strip(),
            module=self._mod_var.get(),
            defect_type=self._e_type.get().strip(),
            description=self._get_tb(self._e_desc),
            severity=self._sev_var.get(),
            frequency=freq,
            status=self._stat_var.get(),
            root_cause=self._get_tb(self._e_cause),
            corrective_action=self._get_tb(self._e_action),
            reported_by=self._e_rep.get().strip(),
        )
        if self._rec:
            ok, msg = self._svc.update_defect(rec)
        else:
            ok, msg = self._svc.add_defect(rec)
        if ok:
            if self._cb:
                self._cb()
            self.destroy()
        else:
            self._err.configure(text=f"❌ {msg}")


# ---------------------------------------------------------------------------
# Tab 3 – Fishbone / Ishikawa
# ---------------------------------------------------------------------------

class FishboneTab(ctk.CTkScrollableFrame):
    def __init__(self, parent, **kwargs):
        super().__init__(parent, fg_color="transparent",
                         scrollbar_button_color=Theme.BORDER_COLOR, **kwargs)
        self._build_ui()

    def _build_ui(self) -> None:
        ctk.CTkLabel(self, text="🐟 Fishbone (Ishikawa) Root Cause Diagram",
                     font=Theme.FONT_HEADING, text_color=Theme.SECONDARY,
                     anchor="w").pack(fill="x", padx=4, pady=(8, 4))
        ctk.CTkLabel(
            self,
            text=(
                "Select a major defect to view its root cause analysis by category. "
                "Categories: People · Process · Software/Code · Database/Data · Infrastructure."
            ),
            font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED, anchor="w", wraplength=900,
        ).pack(fill="x", padx=4, pady=(0, 10))

        defect_names = list(FISHBONE_CAUSES.keys())
        self._defect_var = tk.StringVar(value=defect_names[0])
        sel_row = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        sel_row.pack(fill="x", padx=4, pady=(0, 10))
        ctk.CTkLabel(sel_row, text="Major Defect:", font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(side="left", padx=12)
        ctk.CTkOptionMenu(sel_row, values=defect_names, variable=self._defect_var,
                          font=Theme.FONT_BODY,
                          command=self._on_defect_change).pack(side="left", pady=12, padx=(0, 16))

        self._diagram_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._diagram_frame.pack(fill="both", expand=True, padx=4)
        self._draw(defect_names[0])

    def _on_defect_change(self, value: str) -> None:
        self._draw(value)

    def _draw(self, defect: str) -> None:
        for w in self._diagram_frame.winfo_children():
            w.destroy()
        causes = FISHBONE_CAUSES.get(defect, {})

        # Effect label
        eff = ctk.CTkFrame(self._diagram_frame, fg_color=Theme.DANGER, corner_radius=10)
        eff.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(eff, text=f"⚠️  Effect: {defect}",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_DARK,
                     wraplength=880, justify="left").pack(padx=14, pady=10)

        CAT_COLORS = {
            "People": Theme.WARNING,
            "Process": Theme.PRIMARY,
            "Software / Code": Theme.SECONDARY,
            "Database / Data": Theme.INFO,
            "Infrastructure": Theme.SUCCESS,
        }
        CAT_ICONS = {
            "People": "👥",
            "Process": "⚙️",
            "Software / Code": "💻",
            "Database / Data": "🗄️",
            "Infrastructure": "🖥️",
        }

        for cat, items in causes.items():
            card = ctk.CTkFrame(self._diagram_frame, fg_color=Theme.BG_CARD, corner_radius=10)
            card.pack(fill="x", pady=(0, 8))
            color = CAT_COLORS.get(cat, Theme.PRIMARY)
            icon  = CAT_ICONS.get(cat, "📌")
            hdr = ctk.CTkFrame(card, fg_color=color, corner_radius=8)
            hdr.pack(fill="x", padx=10, pady=(10, 6))
            ctk.CTkLabel(hdr, text=f"{icon}  {cat}",
                         font=Theme.FONT_BOLD, text_color=Theme.TEXT_DARK
                         ).pack(anchor="w", padx=10, pady=6)
            for cause in items:
                row = ctk.CTkFrame(card, fg_color=Theme.INPUT_BG, corner_radius=6)
                row.pack(fill="x", padx=10, pady=(0, 4))
                ctk.CTkLabel(row, text=f"  → {cause}",
                             font=Theme.FONT_BODY, text_color=Theme.TEXT_MAIN,
                             anchor="w", wraplength=860, justify="left"
                             ).pack(fill="x", padx=8, pady=6)
            # spacer
            ctk.CTkFrame(card, fg_color="transparent", height=10).pack()


# ---------------------------------------------------------------------------
# Tab 4 – PDCA / Kaizen
# ---------------------------------------------------------------------------

class PDCATab(ctk.CTkFrame):
    def __init__(self, parent, svc: SQCService, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)
        self._svc = svc
        self._build_ui()

    def _build_ui(self) -> None:
        ctrl = ctk.CTkFrame(self, fg_color=Theme.BG_CARD, corner_radius=10)
        ctrl.pack(fill="x", pady=(4, 8), padx=4)
        ctk.CTkLabel(ctrl, text="🔄 PDCA / Kaizen Continuous Improvement Tracker",
                     font=Theme.FONT_SUBHEADING, text_color=Theme.TEXT_MAIN,
                     anchor="w").pack(fill="x", padx=16, pady=(10, 4))
        ctk.CTkLabel(
            ctrl,
            text="All seeded items are demo/planned improvements – not completed measured results unless stated.",
            font=Theme.FONT_SMALL, text_color=Theme.WARNING, anchor="w",
        ).pack(fill="x", padx=16, pady=(0, 6))

        frow = ctk.CTkFrame(ctrl, fg_color="transparent")
        frow.pack(fill="x", padx=16, pady=(0, 4))

        self._pstat_var = tk.StringVar(value="All")
        col = ctk.CTkFrame(frow, fg_color="transparent")
        col.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(col, text="Status Filter:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        ctk.CTkOptionMenu(col, values=["All"] + list(PDCA_STATUSES),
                          variable=self._pstat_var, font=Theme.FONT_BODY,
                          command=lambda _: self._apply_filter()).pack()

        btn_row = ctk.CTkFrame(ctrl, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(4, 12))
        for text, color, cmd in [
            ("↺ Refresh", Theme.INPUT_BG, self.refresh),
            ("➕ Add",    Theme.SUCCESS,  self._on_add),
            ("✏️ Edit",   Theme.SECONDARY, self._on_edit),
            ("🗑 Delete", Theme.DANGER,   self._on_delete),
        ]:
            ctk.CTkButton(btn_row, text=text, width=100, height=30,
                          font=Theme.FONT_BODY, fg_color=color,
                          hover_color=Theme.BG_CARD_HOVER,
                          command=cmd).pack(side="left", padx=(0, 6))

        self._p_status_lbl = ctk.CTkLabel(ctrl, text="", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED)
        self._p_status_lbl.pack(anchor="w", padx=16, pady=(0, 4))

        # Table
        cols = ("ID", "Improvement ID", "Problem (summary)", "Status", "Owner", "Date")
        _make_tree_style("PDCA")
        tree_wrap = ctk.CTkFrame(self, fg_color=Theme.INPUT_BG, corner_radius=8)
        tree_wrap.pack(fill="both", expand=True, padx=4)

        self._tree = ttk.Treeview(tree_wrap, columns=cols, show="headings",
                                  height=16, style="PDCA.Treeview")
        widths = {"ID": 40, "Improvement ID": 100, "Problem (summary)": 360,
                  "Status": 90, "Owner": 130, "Date": 90}
        for c in cols:
            self._tree.heading(c, text=c)
            self._tree.column(c, width=widths.get(c, 100), anchor="center")

        vsb = ttk.Scrollbar(tree_wrap, orient="vertical", command=self._tree.yview)
        hsb = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self._tree.xview)
        self._tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self._tree.pack(fill="both", expand=True)
        self._tree.bind("<Double-1>", lambda e: self._on_view_detail())

        for tag, color in PDCA_STATUS_COLORS.items():
            self._tree.tag_configure(tag, foreground=color)

    def refresh(self, items: Optional[List[PDCAItem]] = None) -> None:
        if items is None:
            items = self._svc.get_all_pdca()
        for i in self._tree.get_children():
            self._tree.delete(i)
        for p in items:
            summary = p.problem[:65] + "…" if len(p.problem) > 65 else p.problem
            self._tree.insert("", "end", iid=str(p.pdca_id),
                              values=(p.pdca_id, p.improvement_id, summary,
                                      p.status, p.owner, p.date_created),
                              tags=(p.status,))
        self._p_status_lbl.configure(text=f"✅ {len(items)} items")

    def _apply_filter(self) -> None:
        stat = self._pstat_var.get()
        items = self._svc.filter_pdca(status=None if stat == "All" else stat)
        self.refresh(items)

    def _get_selected(self) -> Optional[PDCAItem]:
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("No Selection", "Please select a PDCA item.", parent=self)
            return None
        return self._svc.get_pdca_by_id(int(sel[0]))

    def _on_view_detail(self) -> None:
        p = self._get_selected()
        if p:
            PDCADetailDialog(self, p)

    def _on_add(self) -> None:
        PDCAFormDialog(self, None, self._svc, callback=self.refresh)

    def _on_edit(self) -> None:
        p = self._get_selected()
        if p:
            PDCAFormDialog(self, p, self._svc, callback=self.refresh)

    def _on_delete(self) -> None:
        p = self._get_selected()
        if not p:
            return
        if messagebox.askyesno("Confirm Delete",
                               f"Delete PDCA item {p.improvement_id}?\n\nCannot be undone.",
                               parent=self):
            ok, msg = self._svc.delete_pdca(p.pdca_id)
            if ok:
                self.refresh()
            else:
                messagebox.showerror("Error", msg, parent=self)


# ---------------------------------------------------------------------------
# PDCA Detail Dialog
# ---------------------------------------------------------------------------

class PDCADetailDialog(ctk.CTkToplevel):
    def __init__(self, parent, p: PDCAItem):
        super().__init__(parent)
        self.title(f"{p.improvement_id} – PDCA Detail")
        self.geometry("720x600")
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                    scrollbar_button_color=Theme.BORDER_COLOR)
        sc.pack(fill="both", expand=True, padx=14, pady=14)
        color = PDCA_STATUS_COLORS.get(p.status, Theme.PRIMARY)
        ctk.CTkLabel(sc, text=f"{p.improvement_id} – {p.status}",
                     font=Theme.FONT_TITLE, text_color=color).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(sc, text=p.problem, font=Theme.FONT_HEADING,
                     justify="left").pack(anchor="w", pady=(0, 10))
        for label, content in [
            ("📋 PLAN", p.plan_action),
            ("▶ DO", p.do_action),
            ("✅ CHECK", p.check_action),
            ("🔁 ACT / Standardize", p.act_action),
            ("📊 Result / Metric", p.result_metric or "Not yet measured"),
            ("📝 Notes", p.notes or ""),
        ]:
            f = ctk.CTkFrame(sc, fg_color=Theme.BG_CARD, corner_radius=8)
            f.pack(fill="x", pady=(0, 6))
            ctk.CTkLabel(f, text=label, font=Theme.FONT_BOLD, text_color=Theme.TEXT_MUTED).pack(anchor="w", padx=12, pady=(8,2))
            ctk.CTkLabel(f, text=content, font=Theme.FONT_BODY,
                         justify="left").pack(anchor="w", padx=12, pady=(0, 8))
        meta = ctk.CTkFrame(sc, fg_color=Theme.BG_CARD, corner_radius=8)
        meta.pack(fill="x", pady=(0, 8))
        mrow = ctk.CTkFrame(meta, fg_color="transparent")
        mrow.pack(fill="x", padx=12, pady=10)
        ctk.CTkLabel(mrow, text=f"Owner: {p.owner}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left", padx=10)
        ctk.CTkLabel(mrow, text=f"Created: {p.date_created}", font=Theme.FONT_BODY, text_color=Theme.TEXT_MUTED).pack(side="left")
        ctk.CTkButton(sc, text="Close", width=90, height=30, command=self.destroy).pack(pady=(16,0))


# ---------------------------------------------------------------------------
# PDCA Add/Edit Form
# ---------------------------------------------------------------------------

class PDCAFormDialog(ctk.CTkToplevel):
    def __init__(self, parent, item: Optional[PDCAItem], svc: SQCService, callback=None):
        super().__init__(parent)
        self._item = item
        self._svc = svc
        self._cb = callback
        self.title("Edit PDCA Item" if item else "Add PDCA Item")
        self.geometry("700x750")
        self.configure(fg_color=Theme.BG_DARK)
        self.grab_set()
        self._build()
        if item:
            self._populate(item)

    def _tb(self, parent, label: str, height: int = 60) -> ctk.CTkTextbox:
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        w = ctk.CTkTextbox(parent, height=height, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY, wrap="word")
        w.pack(fill="x", pady=(0, 4))
        return w

    def _entry(self, parent, label: str, height: int = 30) -> ctk.CTkEntry:
        ctk.CTkLabel(parent, text=label, font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        e = ctk.CTkEntry(parent, height=height, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        e.pack(fill="x", pady=(0, 4))
        return e

    def _build(self) -> None:
        sc = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                    scrollbar_button_color=Theme.BORDER_COLOR)
        sc.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(sc, text="Add PDCA Item" if not self._item else "Edit PDCA Item",
                     font=Theme.FONT_HEADING, text_color=Theme.SECONDARY,
                     ).pack(anchor="w", pady=(0, 10))

        self._e_id     = self._entry(sc, "Improvement ID: *  (e.g. PDCA-006)")
        self._e_prob   = self._tb(sc, "Problem Statement: *", 60)
        self._e_plan   = self._tb(sc, "Plan – What will be done?", 55)
        self._e_do     = self._tb(sc, "Do – How was it implemented?", 55)
        self._e_check  = self._tb(sc, "Check – How is it verified?", 55)
        self._e_act    = self._tb(sc, "Act – Standardize / Next Cycle", 55)
        self._e_metric = self._tb(sc, "Result / Metric (or target):", 40)
        self._e_notes  = self._tb(sc, "Notes:", 40)

        row = ctk.CTkFrame(sc, fg_color="transparent")
        row.pack(fill="x", pady=(4, 0))
        lc = ctk.CTkFrame(row, fg_color="transparent")
        lc.pack(side="left", fill="x", expand=True, padx=(0, 12))
        ctk.CTkLabel(lc, text="Status:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._stat_var = tk.StringVar(value="Plan")
        ctk.CTkOptionMenu(lc, values=list(PDCA_STATUSES), variable=self._stat_var,
                          font=Theme.FONT_BODY).pack(fill="x", pady=(2, 0))
        rc = ctk.CTkFrame(row, fg_color="transparent")
        rc.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(rc, text="Owner:", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_owner = ctk.CTkEntry(rc, height=30, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_owner.pack(fill="x", pady=(2, 0))
        self._e_owner.insert(0, "Development Team")

        ctk.CTkLabel(sc, text="Date Created (YYYY-MM-DD):", font=Theme.FONT_SMALL, text_color=Theme.TEXT_MUTED).pack(anchor="w", pady=(0,4))
        self._e_date = ctk.CTkEntry(sc, height=30, fg_color=Theme.INPUT_BG, font=Theme.FONT_BODY)
        self._e_date.pack(fill="x", pady=(0, 8))
        self._e_date.insert(0, __import__("datetime").date.today().isoformat())

        self._err = ctk.CTkLabel(sc, text="", font=Theme.FONT_SMALL, text_color=Theme.DANGER)
        self._err.pack(anchor="w", pady=(4, 0))

        b = ctk.CTkFrame(sc, fg_color="transparent")
        b.pack(fill="x", pady=(8, 0))
        ctk.CTkButton(b, text="💾 Save", width=110, height=32, command=self._on_save).pack(side="left", padx=(0, 10))
        ctk.CTkButton(b, text="Cancel", width=90, height=32, fg_color=Theme.BG_CARD, text_color=Theme.TEXT_MAIN, hover_color=Theme.INPUT_BG, command=self.destroy).pack(side="left")

    def _get(self, w) -> str:
        if isinstance(w, ctk.CTkTextbox):
            return w.get("1.0", "end").strip()
        return w.get().strip()

    def _set(self, w, v: str) -> None:
        if isinstance(w, ctk.CTkTextbox):
            w.delete("1.0", "end"); w.insert("1.0", v)
        else:
            w.delete(0, "end"); w.insert(0, v)

    def _populate(self, p: PDCAItem) -> None:
        self._set(self._e_id, p.improvement_id)
        self._set(self._e_prob, p.problem)
        self._set(self._e_plan, p.plan_action)
        self._set(self._e_do, p.do_action)
        self._set(self._e_check, p.check_action)
        self._set(self._e_act, p.act_action)
        self._set(self._e_metric, p.result_metric)
        self._set(self._e_notes, p.notes)
        self._stat_var.set(p.status)
        self._set(self._e_owner, p.owner)
        self._set(self._e_date, p.date_created)

    def _save(self) -> None:
        p = PDCAItem(
            pdca_id=self._item.pdca_id if self._item else None,
            improvement_id=self._get(self._e_id),
            problem=self._get(self._e_prob),
            plan_action=self._get(self._e_plan),
            do_action=self._get(self._e_do),
            check_action=self._get(self._e_check),
            act_action=self._get(self._e_act),
            owner=self._get(self._e_owner),
            status=self._stat_var.get(),
            date_created=self._get(self._e_date),
            result_metric=self._get(self._e_metric),
            notes=self._get(self._e_notes),
        )
        if self._item:
            ok, msg = self._svc.update_pdca(p)
        else:
            ok, msg = self._svc.add_pdca(p)
        if ok:
            if self._cb:
                self._cb()
            self.destroy()
        else:
            self._err.configure(text=f"❌ {msg}")
