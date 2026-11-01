"""
Pytest configuration for Pharmacy Management System.
Ensures Win32 Tkinter and Tcl/Tk environment paths are initialized cleanly across all test suites.
"""
import os
import sys

if sys.platform.startswith("win"):
    base_py = os.path.dirname(sys.executable)
    tcl_dir = os.path.join(base_py, "tcl", "tcl8.6")
    tk_dir = os.path.join(base_py, "tcl", "tk8.6")
    if os.path.exists(tcl_dir) and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = tcl_dir
    if os.path.exists(tk_dir) and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = tk_dir

