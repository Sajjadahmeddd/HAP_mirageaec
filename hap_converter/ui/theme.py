"""Design tokens + application stylesheet, matched to the HAP_ext mockups:
navy shell accents, olive-green primary actions, light warm-gray canvas,
white rounded cards, red PDF iconography.
"""

NAVY = "#141B4D"
ORANGE = "#E8862E"
NAVY_SOFT = "#3D4B9E"
BLUE = "#1E5EDB"
GREEN = "#6E8B23"
GREEN_DARK = "#5A731C"
GREEN_SOFT = "#EDF2DC"
RED = "#D64545"
RED_SOFT = "#FDEDED"
CANVAS = "#F4F4F1"
CARD = "#FFFFFF"
BORDER = "#E4E4DE"
TEXT = "#1E2230"
TEXT_MUTED = "#8A8D98"
TITLEBAR = "#E9E9E6"

FONT = "Segoe UI"

APP_QSS = f"""
* {{
    font-family: "{FONT}";
    color: {TEXT};
}}
QMainWindow, #Canvas {{
    background: {CANVAS};
}}

/* ---------- title bar ---------- */
#TitleBar {{
    background: {TITLEBAR};
}}
#BrandLabel {{
    font-size: 16px;
    font-weight: 800;
}}
#VersionLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 700;
    padding-top: 3px;
}}
QPushButton#WinBtn, QPushButton#WinBtnClose {{
    background: #1E1E1E;
    color: white;
    border: none;
    border-radius: 11px;
    min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px;
    font-size: 11px;
    font-weight: 700;
}}
QPushButton#WinBtn:hover {{ background: #444444; }}
QPushButton#WinBtnClose:hover {{ background: {RED}; }}

/* ---------- product tabs ---------- */
#TabBar {{
    background: {TITLEBAR};
}}
QPushButton[tabRole="tab"] {{
    background: #DCDCD8;
    color: #6B6E78;
    border: none;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 9px 26px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton[tabRole="tab"]:disabled {{
    color: #9B9EA8;
}}
QPushButton[tabRole="tab"][tabActive="true"] {{
    background: {NAVY};
    color: white;
}}

/* ---------- cards ---------- */
#Card, #PanelCard {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 16px;
}}
#InfoCard {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
#InfoCardTitle {{ font-size: 13px; font-weight: 700; }}
#InfoCardBody  {{ font-size: 11px; color: {TEXT_MUTED}; }}

/* ---------- generic text ---------- */
#H1 {{ font-size: 26px; font-weight: 800; }}
#H2 {{ font-size: 15px; font-weight: 700; }}
#Muted {{ color: {TEXT_MUTED}; font-size: 12px; }}
#Small {{ color: {TEXT_MUTED}; font-size: 11px; }}

/* ---------- buttons ---------- */
QPushButton#Primary {{
    background: {GREEN};
    color: white;
    border: none;
    border-radius: 19px;
    padding: 10px 34px;
    font-size: 13px;
    font-weight: 700;
}}
QPushButton#Primary:hover {{ background: {GREEN_DARK}; }}
QPushButton#Primary:disabled {{ background: #C9CFB6; color: #F4F4F1; }}
QPushButton#Secondary {{
    background: {CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 19px;
    padding: 10px 28px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#Secondary:hover {{ border-color: {GREEN}; color: {GREEN_DARK}; }}
QPushButton#Secondary:disabled {{ color: {TEXT_MUTED}; }}
QPushButton#Ghost {{
    background: transparent;
    border: none;
    color: {GREEN_DARK};
    font-size: 12px;
    font-weight: 600;
    text-decoration: underline;
}}
QPushButton#Processing {{
    background: #D8D8D3;
    color: #6B6E78;
    border: none;
    border-radius: 19px;
    padding: 10px 34px;
    font-size: 13px;
    font-weight: 700;
}}

/* ---------- drop zone ---------- */
#DropZone {{
    background: {CARD};
    border: 2px dashed #C9C9C2;
    border-radius: 16px;
}}
#DropZone[dropActive="true"] {{
    border-color: {GREEN};
    background: {GREEN_SOFT};
}}
#DropZone[dropError="true"] {{
    border-color: {RED};
    background: {RED_SOFT};
}}

/* ---------- pills / chips ---------- */
#PillOk {{
    background: {GREEN_SOFT};
    color: {GREEN_DARK};
    border-radius: 10px;
    padding: 4px 14px;
    font-size: 10px;
    font-weight: 800;
}}
#PillFail {{
    background: {RED_SOFT};
    color: {RED};
    border-radius: 10px;
    padding: 4px 14px;
    font-size: 10px;
    font-weight: 800;
}}
#Chip {{
    background: {GREEN_SOFT};
    color: {GREEN_DARK};
    border-radius: 8px;
    padding: 5px 12px;
    font-size: 10px;
    font-weight: 700;
}}
#SheetTab {{
    background: {NAVY};
    color: white;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    padding: 8px 18px;
    font-size: 11px;
    font-weight: 700;
}}

/* ---------- feature band (home) ---------- */
#FeatureBand {{
    background: {NAVY};
    border-radius: 18px;
}}
#FeatureBand QLabel {{ color: white; }}
#FeatureChipTitle {{ font-size: 12px; font-weight: 700; color: white; }}

/* ---------- progress ---------- */
QProgressBar {{
    background: #E7E7E2;
    border: none;
    border-radius: 5px;
    min-height: 10px;
    max-height: 10px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {GREEN};
    border-radius: 5px;
}}

/* ---------- recents ---------- */
#RecentItem {{
    background: transparent;
    border: none;
    border-radius: 10px;
}}
#RecentItem:hover {{ background: {CANVAS}; }}
#RecentName {{ font-size: 12px; font-weight: 700; }}
#PdfBadge {{
    background: {RED_SOFT};
    color: {RED};
    border: 1px solid #F5C6C6;
    border-radius: 8px;
    font-size: 9px;
    font-weight: 800;
}}

/* ---------- preview table ---------- */
QTableWidget {{
    background: {CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: {BORDER};
    font-size: 11px;
}}
QHeaderView::section {{
    background: #F7F7F4;
    color: {TEXT};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 6px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QTableWidget::item {{ padding: 4px 8px; }}

/* ---------- step timeline ---------- */
#StepDotDone {{
    background: {GREEN};
    color: white;
    border-radius: 11px;
    font-size: 11px;
    font-weight: 800;
    min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px;
}}
#StepDotPending {{
    background: #E2E2DD;
    color: {TEXT_MUTED};
    border-radius: 11px;
    font-size: 11px;
    font-weight: 800;
    min-width: 22px; max-width: 22px;
    min-height: 22px; max-height: 22px;
}}
#EtaBox {{
    background: {GREEN_SOFT};
    border: 1px solid #DCE5C2;
    border-radius: 10px;
}}
#EtaValue {{ color: {RED}; font-size: 15px; font-weight: 800; }}

/* ---------- misc ---------- */
QRadioButton {{ font-size: 13px; font-weight: 600; }}
QRadioButton:disabled {{ color: {TEXT_MUTED}; }}
#SummaryStrip {{
    background: #F7F7F4;
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
#SummaryKey {{ color: {TEXT_MUTED}; font-size: 10px; font-weight: 700; }}
#SummaryVal {{ font-size: 12px; font-weight: 700; }}
#StatusOk {{ color: {GREEN_DARK}; font-size: 12px; font-weight: 700; }}
#StatusFail {{ color: {RED}; font-size: 12px; font-weight: 700; }}
QScrollArea {{ border: none; background: transparent; }}

/* ---------- message boxes (dark, per user preference) ---------- */
QMessageBox {{
    background: #1F1F1F;
}}
QMessageBox QLabel {{
    color: white;
    font-size: 12px;
}}
QMessageBox QPushButton {{
    background: {GREEN};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 6px 22px;
    font-size: 12px;
    font-weight: 700;
    min-width: 60px;
}}
QMessageBox QPushButton:hover {{ background: {GREEN_DARK}; }}
#IssueRowFrame {{
    background: {RED_SOFT};
    border: 1px solid #F5C6C6;
    border-radius: 10px;
}}
#IssueBadge {{
    background: {RED};
    color: white;
    border-radius: 8px;
    padding: 3px 6px;
    font-size: 10px;
    font-weight: 800;
}}
#IssueText {{ font-size: 12px; color: {TEXT}; }}
"""
