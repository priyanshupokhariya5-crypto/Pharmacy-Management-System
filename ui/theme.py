"""
Theme configuration and visual design system constants.
Provides a premium, professional Pharmacy ERP/POS palette:
Emerald Green + Deep Navy + Soft Off-White + Teal.
Compatible with CustomTkinter light mode.
"""


class Theme:
    # Appearance mode
    APPEARANCE_MODE = "Light"
    COLOR_THEME = "green"

    # Core Palette
    PRIMARY = "#087F5B"        # Emerald Green (Primary Actions & Brand)
    PRIMARY_HOVER = "#066B4C"  # Darker Emerald (Hover state)
    DEEP_NAVY = "#142B3B"      # Deep Navy (Sidebar & High Contrast Headers)
    TEAL = "#20A39E"           # Teal (Accents & Active Indicators)
    
    # Backgrounds & Surfaces
    BG_DARK = "#F4F7F8"        # Soft Off-White Main Canvas
    BG_CARD = "#FFFFFF"        # Pure White Card Surface
    BG_CARD_HOVER = "#F0F5F6"  # Subtle Tint Card Hover
    BG_SIDEBAR = "#142B3B"     # Deep Navy Sidebar (Executive ERP Look)
    BG_HEADER = "#FFFFFF"      # Header Bar
    
    # Secondary Accents
    SECONDARY = "#142B3B"      # Deep Navy Secondary
    SECONDARY_HOVER = "#1E3D52"# Lighter Navy Hover

    # Status / Badge Colors
    SUCCESS = "#237A4B"        # Forest Green (Available / Success)
    WARNING = "#B7791F"        # Amber Ochre (Low Stock / Expiring Soon)
    DANGER = "#C0392B"         # Crimson Red (Error / Out of Stock / Expired)
    INFO = "#20A39E"           # Teal (Info Badges)

    # Typography / Text Colors
    TEXT_MAIN = "#182A35"      # Dark Charcoal Navy (High-legibility primary)
    TEXT_MUTED = "#60717C"     # Neutral Slate (Subtitles & Placeholders)
    TEXT_DARK = "#FFFFFF"      # Pure White (Text on Dark Buttons/Headers)
    TEXT_SIDEBAR = "#CBD5E1"   # Soft White on Navy Sidebar
    TEXT_SIDEBAR_ACTIVE = "#FFFFFF"

    # Borders & Inputs
    BORDER_COLOR = "#DCE5E8"   # Subtle Crisp Border
    INPUT_BG = "#FFFFFF"       # Clean White Input Fields
    INPUT_BORDER = "#CBD5E1"   # Input Border

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
