"""
Theme configuration and visual design system constants.
Provides color palettes, fonts, and widget parameters for CustomTkinter / Tkinter UI.
"""

class Theme:
    # Appearance mode
    APPEARANCE_MODE = "Light"
    COLOR_THEME = "green"

    # Color Palette (Professional Parrot Green Light Theme)
    BG_DARK = "#F5F8F2"        # Main Background
    BG_CARD = "#FFFFFF"        # Cards / Panels
    BG_CARD_HOVER = "#F9FDF7"  # Card Hover (very light green tint)
    BG_SIDEBAR = "#FFFFFF"     # Navigation Sidebar
    BG_HEADER = "#FFFFFF"      # Header Bar

    PRIMARY = "#66B032"        # Primary Accent (Parrot Green)
    PRIMARY_HOVER = "#3F7D20"  # Accent Hover (Dark Green)
    SECONDARY = "#3F7D20"      # Secondary Accent (Dark Green)

    # Status / Badge Colors
    SUCCESS = "#4E9F3D"        # Success / Available
    WARNING = "#E0A11A"        # Warning / Low Stock (Amber)
    DANGER = "#D9534F"         # Danger / Out of Stock (Red)
    INFO = "#66B032"           # Information (Parrot Green)

    # Typography / Text Colors
    TEXT_MAIN = "#26331F"      # Primary Text
    TEXT_MUTED = "#66705F"     # Subtitle / Muted Text
    TEXT_DARK = "#FFFFFF"      # White for contrast against Primary

    BORDER_COLOR = "#D8E4D0"   # Panel Borders
    INPUT_BG = "#EAF6DF"       # Input field background (Light Parrot Green)

    # Fonts (Family, Size, Weight)
    FONT_FAMILY = "Segoe UI"
    FONT_TITLE = ("Segoe UI", 20, "bold")
    FONT_HEADING = ("Segoe UI", 14, "bold")
    FONT_SUBHEADING = ("Segoe UI", 12, "bold")
    FONT_BODY = ("Segoe UI", 11, "normal")
    FONT_BOLD = ("Segoe UI", 11, "bold")
    FONT_SMALL = ("Segoe UI", 9, "normal")

    @classmethod
    def get_stock_color(cls, status: str) -> str:
        """Returns badge color based on stock status."""
        if status == "Available":
            return cls.SUCCESS
        elif status == "Low Stock":
            return cls.WARNING
        return cls.DANGER

    @classmethod
    def get_expiry_color(cls, status: str) -> str:
        """Returns badge color based on expiry status."""
        if status == "Valid":
            return cls.SUCCESS
        elif status == "Expiring Soon":
            return cls.WARNING
        return cls.DANGER
