"""Shared style sheet for the Student Productivity Agent Frontend — Deep Nebula Tech Theme."""

APP_STYLE = """
/* ═══════════════════════════════════════════════════════════════════════════
   DEEP NEBULA TECH  ·  Color Tokens
   ─────────────────────────────────────────────────────────────────────────
   Void Black    #050810   Deep Space    #0a0e1a   Nebula Dark  #0e1328
   Panel Glass   #111833   Surface       #151d3a
   Electric Cyan #22d3ee   Nebula Blue   #3b82f6   Violet Glow  #8b5cf6
   Aurora Green  #10b981   Stellar Rose  #f472b6   Amber Pulse  #f59e0b
   Text Primary  #f0f4ff   Text Soft     #c4cff0   Text Muted   #6b7fa3
   Text Dim      #3d506e   Text Ghost    #263350
   Border Subtle rgba(99,132,255,0.10)   Border Glow  rgba(99,132,255,0.28)
   Focus Ring    rgba(34,211,238,0.50)   Hover Glow   rgba(34,211,238,0.12)
═══════════════════════════════════════════════════════════════════════════ */

/* ── Root & Pages ───────────────────────────────────────────────────────── */
QMainWindow, QWidget#AppRoot {
    background-color: #050810;
    color: #f0f4ff;
    font-family: "Inter", "SF Pro Display", "Segoe UI", "Helvetica Neue", "Arial", sans-serif;
}

QWidget#AuthPage, QWidget#HomePage {
    background-color: transparent;
}

QWidget#DashboardPage {
    background-color: #050810;
}

/* ── Sidebar — deep frosted panel ───────────────────────────────────────── */
QFrame#SidebarFrame {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0a0e1a, stop:1 #0e1328);
    border: none;
    border-right: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 0px;
}

/* ── Transparent containers ─────────────────────────────────────────────── */
QFrame#CenterFrame, QFrame#TraceFrame, QFrame#WorkspaceCard {
    background-color: transparent;
    border: none;
    border-radius: 0px;
}

/* ── Homepage — nav bar with subtle glow ─────────────────────────────────── */
QFrame#HomeNavBar {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 rgba(14, 19, 40, 0.95), stop:0.5 rgba(17, 24, 51, 0.9),
        stop:1 rgba(14, 19, 40, 0.95));
    border: none;
    border-bottom: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 0px;
}

/* ── Homepage — hero section with nebula gradient ────────────────────────── */
QFrame#HomeHeroCard {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(59, 130, 246, 0.08), stop:0.4 rgba(139, 92, 246, 0.06),
        stop:0.7 rgba(34, 211, 238, 0.04), stop:1 rgba(14, 19, 40, 0.6));
    border: 1px solid rgba(99, 132, 255, 0.15);
    border-radius: 20px;
}

QLabel#AuthKicker {
    color: #22d3ee;
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 2px;
}

/* ── Homepage — feature cards with glass border ──────────────────────────── */
QFrame#HomeFeatureCard {
    background-color: rgba(17, 24, 51, 0.6);
    border: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 14px;
}

QFrame#HomeFeatureCard:hover {
    border: 1px solid rgba(34, 211, 238, 0.3);
}

/* ── Homepage — skill cards with icon glow ───────────────────────────────── */
QFrame#HomeSkillCard {
    background-color: rgba(14, 19, 40, 0.7);
    border: 1px solid rgba(99, 132, 255, 0.1);
    border-radius: 14px;
}

QFrame#HomeSkillCard:hover {
    border: 1px solid rgba(139, 92, 246, 0.3);
}

/* ── Homepage — banner with gradient accent ──────────────────────────────── */
QFrame#HomeBannerCard {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(59, 130, 246, 0.1), stop:0.5 rgba(139, 92, 246, 0.08),
        stop:1 rgba(34, 211, 238, 0.06));
    border: 1px solid rgba(99, 132, 255, 0.18);
    border-radius: 16px;
}

/* ── Auth & cards — glassmorphism panels ─────────────────────────────────── */
QFrame#AuthHeroFrame, QFrame#AuthCard {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 rgba(17, 24, 51, 0.92), stop:1 rgba(14, 19, 40, 0.95));
    border: 1px solid rgba(99, 132, 255, 0.18);
    border-radius: 18px;
}

QFrame#AgentResultCard, QFrame#ResultSubCard {
    background-color: rgba(17, 24, 51, 0.85);
    border: 1px solid rgba(99, 132, 255, 0.14);
    border-radius: 14px;
}

QFrame#MiniConflictCard {
    background-color: rgba(244, 63, 94, 0.08);
    border: 1px solid rgba(244, 63, 94, 0.22);
    border-radius: 12px;
}

QFrame#FeaturePill {
    background-color: rgba(139, 92, 246, 0.08);
    border: 1px solid rgba(139, 92, 246, 0.22);
    border-radius: 20px;
}

/* ── Typography ─────────────────────────────────────────────────────────── */
QLabel#TitleLabel, QLabel#HomeBrand, QLabel#HeroTitle, QLabel#AuthTitle,
QLabel#HomeHeroTitle, QLabel#HomeSectionTitle, QLabel#SectionTitle {
    color: #f0f4ff;
    font-weight: 700;
}

QLabel#TitleLabel     { font-size: 24px; }
QLabel#HomeBrand      {
    font-size: 20px;
    color: #22d3ee;
    letter-spacing: 1px;
}
QLabel#HeroTitle      { font-size: 32px; }
QLabel#AuthTitle      { font-size: 24px; }
QLabel#HomeHeroTitle  {
    font-size: 42px;
    color: #f0f4ff;
    letter-spacing: -0.5px;
}
QLabel#HomeSectionTitle {
    font-size: 22px;
    color: #c4cff0;
    letter-spacing: 0.3px;
}
QLabel#SectionTitle   { font-size: 16px; }

QLabel#SubtitleLabel, QLabel#HeroBody, QLabel#AuthFooter, QLabel#HintText,
QLabel#HomeHeroSubtitle, QLabel#MutedText, QLabel#CardTitle {
    color: #6b7fa3;
}

QLabel#SubtitleLabel { font-size: 14px; }
QLabel#HeroBody, QLabel#AuthFooter, QLabel#HintText, QLabel#MutedText { font-size: 14px; }
QLabel#HomeHeroSubtitle { font-size: 16px; line-height: 1.5; }
QLabel#CardTitle {
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    color: #8b5cf6;
    font-weight: 600;
}

QLabel#CardValue {
    font-size: 24px;
    font-weight: 700;
    color: #22d3ee;
}

QLabel#WorkspaceName {
    font-size: 20px;
    font-weight: 700;
    color: #f0f4ff;
}

QLabel#BodyText {
    color: #c4cff0;
    font-size: 15px;
    line-height: 1.6;
}

QLabel#ResultQueryLabel {
    padding: 8px 14px;
    border-radius: 8px;
    background-color: rgba(34, 211, 238, 0.08);
    color: #22d3ee;
    font-size: 14px;
    border: 1px solid rgba(34, 211, 238, 0.2);
}

QLabel#BadgeLabel, QLabel#WorkspaceStat {
    padding: 5px 12px;
    border-radius: 8px;
    background-color: rgba(139, 92, 246, 0.1);
    color: #a78bfa;
    font-size: 12px;
    font-weight: 600;
    border: 1px solid rgba(139, 92, 246, 0.22);
}

QLabel#MessageTypeChip {
    padding: 3px 10px;
    border-radius: 999px;
    background-color: rgba(139, 92, 246, 0.12);
    color: #a78bfa;
    font-size: 11px;
    font-weight: 600;
    border: 1px solid rgba(139, 92, 246, 0.25);
}

QLabel#SkillIcon {
    font-size: 13px;
    font-weight: 700;
    color: #22d3ee;
    background-color: rgba(34, 211, 238, 0.1);
    border: 1px solid rgba(34, 211, 238, 0.18);
    border-radius: 8px;
    padding: 6px 10px;
    letter-spacing: 1px;
}

/* ── Buttons ────────────────────────────────────────────────────────────── */
QPushButton {
    min-height: 36px;
    padding: 0 16px;
    border-radius: 8px;
    border: 1px solid rgba(99, 132, 255, 0.15);
    color: #c4cff0;
    background-color: rgba(99, 132, 255, 0.06);
    font-weight: 500;
    font-size: 13px;
}

QPushButton:hover {
    background-color: rgba(34, 211, 238, 0.12);
    border-color: rgba(34, 211, 238, 0.35);
    color: #f0f4ff;
}

QPushButton#PrimaryButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:1 #22d3ee);
    color: #050810;
    border: none;
    font-weight: 700;
}

QPushButton#PrimaryButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #60a5fa, stop:1 #67e8f9);
}

QPushButton#HeaderHitlButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #3b82f6, stop:1 #22d3ee);
    border: none;
    border-radius: 10px;
    color: #050810;
    font-weight: 800;
    min-height: 34px;
    padding: 0 16px;
}

QPushButton#HeaderHitlButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #60a5fa, stop:1 #67e8f9);
}

QPushButton#SidebarActionButton {
    background-color: rgba(18, 36, 80, 0.62);
    border: 1px solid rgba(103, 157, 255, 0.28);
    border-radius: 10px;
    color: #dbe7ff;
    font-size: 12px;
    font-weight: 700;
    min-height: 34px;
    padding: 0 10px;
}

QPushButton#SidebarActionButton:hover {
    background-color: rgba(34, 211, 238, 0.15);
    border-color: rgba(103, 232, 249, 0.45);
    color: #ffffff;
}

QPushButton#SidebarActionButton:disabled {
    background-color: rgba(18, 28, 56, 0.45);
    border-color: rgba(103, 157, 255, 0.12);
    color: #4b5d7b;
}

/* ── Send button (circular arrow) — glowing orb ─────────────────────────── */
QPushButton#SendButton {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #3b82f6, stop:1 #22d3ee);
    color: #050810;
    border-radius: 18px;
    min-width: 36px;
    max-width: 36px;
    min-height: 36px;
    max-height: 36px;
    border: none;
    font-size: 16px;
    font-weight: 700;
}

QPushButton#SendButton:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #60a5fa, stop:1 #67e8f9);
}

QPushButton#SendButton:disabled {
    background-color: rgba(99, 132, 255, 0.1);
    color: #263350;
}

/* ── Inputs ─────────────────────────────────────────────────────────────── */
QLineEdit, QTextEdit, QListWidget, QTextBrowser {
    background-color: rgba(14, 19, 40, 0.8);
    border: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 12px;
    padding: 10px 14px;
    color: #f0f4ff;
    font-size: 14px;
    selection-background-color: #3b82f6;
    selection-color: #050810;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid rgba(34, 211, 238, 0.4);
}

QLineEdit#AuthInput {
    background-color: #0a0e1a;
    border: 1px solid rgba(99, 132, 255, 0.18);
    min-height: 44px;
    border-radius: 10px;
}

QLineEdit#AuthInput:focus {
    border: 1px solid rgba(34, 211, 238, 0.55);
}

/* ── Mode dropdown ──────────────────────────────────────────────────────── */
QPushButton#ModeDropdownButton {
    min-height: 36px;
    min-width: 140px;
    padding: 0 12px;
    border-radius: 8px;
    background-color: transparent;
    border: none;
    color: #c4cff0;
    font-weight: 600;
    font-size: 14px;
    text-align: left;
}

QPushButton#ModeDropdownButton:hover {
    background-color: rgba(34, 211, 238, 0.08);
    color: #22d3ee;
}

QMenu#ModeDropdownMenu {
    background-color: #0e1328;
    border: 1px solid rgba(99, 132, 255, 0.2);
    border-radius: 10px;
    padding: 4px;
    color: #f0f4ff;
}

QMenu#ModeDropdownMenu::item {
    padding: 8px 14px;
    border-radius: 6px;
    margin: 2px;
    color: #c4cff0;
}

QMenu#ModeDropdownMenu::item:selected {
    background-color: rgba(34, 211, 238, 0.12);
    color: #22d3ee;
}

QMenu#ModeDropdownMenu::indicator { width: 12px; height: 12px; }

QMenu#ModeDropdownMenu::indicator:checked {
    image: none;
    background-color: #22d3ee;
    border-radius: 6px;
}

QMenu#ModeDropdownMenu::indicator:unchecked {
    image: none;
    background-color: transparent;
}

/* ── List widgets ───────────────────────────────────────────────────────── */
QListWidget#ConversationList, QListWidget#ResourceList,
QListWidget#DailyScheduleList, QListWidget#ScheduleConflictList {
    background-color: transparent;
    border: none;
    padding: 4px;
    outline: none;
}

QListWidget#ConversationList::item, QListWidget#ResourceList::item {
    margin: 2px 0;
    padding: 10px 12px;
    border-radius: 8px;
    color: #c4cff0;
}

QListWidget#ConversationList::item:selected, QListWidget#ResourceList::item:selected {
    background-color: rgba(34, 211, 238, 0.1);
    border: 1px solid rgba(34, 211, 238, 0.25);
    color: #22d3ee;
}

QListWidget#ConversationList::item:hover:!selected, QListWidget#ResourceList::item:hover:!selected {
    background-color: rgba(99, 132, 255, 0.06);
    color: #f0f4ff;
}

QListWidget#DailyScheduleList::item {
    background-color: rgba(99, 132, 255, 0.05);
    border: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 8px;
    margin: 4px 0;
    padding: 12px;
    color: #f0f4ff;
}

QListWidget#ScheduleConflictList::item {
    background-color: rgba(244, 63, 94, 0.07);
    border: 1px solid rgba(244, 63, 94, 0.2);
    border-radius: 8px;
    margin: 4px 0;
    padding: 12px;
    color: #f0f4ff;
}

/* ── Tabs ───────────────────────────────────────────────────────────────── */
QTabWidget::pane {
    border: none;
    background-color: transparent;
    top: -1px;
}

QTabBar::tab {
    background-color: transparent;
    color: #3d506e;
    min-width: 100px;
    min-height: 36px;
    border-bottom: 2px solid transparent;
    margin-right: 12px;
    padding: 8px 12px;
    font-size: 14px;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: #22d3ee;
    border-bottom: 2px solid #22d3ee;
}

QTabBar::tab:hover:!selected {
    color: #c4cff0;
    border-bottom: 2px solid rgba(34, 211, 238, 0.3);
}

/* ── PanelCard — glass panels for calendar, detail, etc. ─────────────────── */
QFrame#PanelCard {
    background-color: rgba(14, 19, 40, 0.65);
    border: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 14px;
}

/* ── Calendar ───────────────────────────────────────────────────────────── */
QCalendarWidget#ScheduleCalendar {
    background-color: transparent;
    border: none;
    color: #f0f4ff;
}

QCalendarWidget#ScheduleCalendar QWidget {
    alternate-background-color: transparent;
    background-color: transparent;
    color: #f0f4ff;
}

/* Calendar navigation header */
QCalendarWidget#ScheduleCalendar QWidget#qt_calendar_navigationbar {
    background-color: rgba(14, 19, 40, 0.5);
    border-bottom: 1px solid rgba(99, 132, 255, 0.1);
    border-top-left-radius: 10px;
    border-top-right-radius: 10px;
    padding: 4px;
}

QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_prevmonth,
QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_nextmonth {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    border-radius: 6px;
    padding: 0px;
    background-color: transparent;
    color: #c4cff0;
    border: 1px solid rgba(99, 132, 255, 0.1);
    font-size: 14px;
}

QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_prevmonth:hover,
QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_nextmonth:hover {
    background-color: rgba(34, 211, 238, 0.12);
    border-color: rgba(34, 211, 238, 0.3);
    color: #22d3ee;
}

QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_monthbutton,
QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_yearbutton {
    min-height: 28px;
    max-height: 28px;
    border-radius: 6px;
    padding: 4px 10px;
    background-color: transparent;
    color: #c4cff0;
    border: none;
    font-size: 13px;
    font-weight: 600;
}

QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_monthbutton:hover,
QCalendarWidget#ScheduleCalendar QToolButton#qt_calendar_yearbutton:hover {
    background-color: rgba(34, 211, 238, 0.1);
    color: #22d3ee;
}

/* Generic tool button fallback */
QCalendarWidget#ScheduleCalendar QToolButton {
    min-height: 28px;
    max-height: 28px;
    border-radius: 6px;
    padding: 4px 10px;
    background-color: transparent;
    color: #c4cff0;
    border: none;
}

QCalendarWidget#ScheduleCalendar QToolButton:hover {
    background-color: rgba(34, 211, 238, 0.1);
    color: #22d3ee;
}

/* Calendar month menu (dropdown when clicking month) */
QCalendarWidget#ScheduleCalendar QMenu {
    background-color: #0e1328;
    border: 1px solid rgba(99, 132, 255, 0.2);
    border-radius: 8px;
    padding: 4px;
    color: #f0f4ff;
}

QCalendarWidget#ScheduleCalendar QMenu::item {
    padding: 6px 14px;
    border-radius: 4px;
    color: #c4cff0;
}

QCalendarWidget#ScheduleCalendar QMenu::item:selected {
    background-color: rgba(34, 211, 238, 0.15);
    color: #22d3ee;
}

/* Calendar date grid */
QCalendarWidget#ScheduleCalendar QAbstractItemView {
    background-color: #0a0e1a;
    border: 1px solid rgba(99, 132, 255, 0.12);
    border-bottom-left-radius: 10px;
    border-bottom-right-radius: 10px;
    color: #c4cff0;
    selection-background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #3b82f6, stop:1 #22d3ee);
    selection-color: #050810;
    outline: none;
    gridline-color: rgba(99, 132, 255, 0.08);
    font-size: 13px;
}

/* Weekday header row */
QCalendarWidget#ScheduleCalendar QTableView QHeaderView::section {
    background-color: rgba(14, 19, 40, 0.6);
    color: #6b7fa3;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    border: none;
    border-bottom: 1px solid rgba(99, 132, 255, 0.1);
    padding: 6px 0;
}

/* ── Scrollbars ─────────────────────────────────────────────────────────── */
QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea#SchedulePageScroll, QScrollArea#ScheduleDetailScroll,
QWidget#SchedulePageContent, QWidget#ScheduleDetailContent {
    background-color: transparent;
}

QScrollBar:vertical {
    width: 6px;
    background-color: transparent;
    margin: 4px 0;
}

QScrollBar::handle:vertical {
    background-color: rgba(99, 132, 255, 0.18);
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover {
    background-color: rgba(34, 211, 238, 0.4);
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

/* ── Legacy bubble frames ───────────────────────────────────────────────── */
QFrame#UserBubble {
    background-color: rgba(59, 130, 246, 0.08);
    border: 1px solid rgba(59, 130, 246, 0.15);
    border-radius: 16px;
}

QFrame#AgentBubble {
    background-color: transparent;
    border: none;
}

/* ── Text browser ───────────────────────────────────────────────────────── */
QTextBrowser#ResultMarkdown {
    background-color: transparent;
    border: none;
    padding: 0px;
}

/* ── Conflict card ──────────────────────────────────────────────────────── */
QFrame#ConflictCard {
    background-color: rgba(244, 63, 94, 0.07);
    border: 1px solid rgba(244, 63, 94, 0.22);
    border-radius: 12px;
}

/* ── Trace items — glowing status indicators ─────────────────────────────── */
QFrame#TraceItemDone, QFrame#TraceItemRunning,
QFrame#TraceItemPending, QFrame#TraceItemError {
    background-color: rgba(14, 19, 40, 0.9);
    border: 1px solid rgba(99, 132, 255, 0.1);
    border-radius: 8px;
}

QFrame#TraceItemDone    { border-left: 3px solid #10b981; }
QFrame#TraceItemRunning { border-left: 3px solid #22d3ee; }
QFrame#TraceItemPending { border-left: 3px solid #f59e0b; }
QFrame#TraceItemError   { border-left: 3px solid #ef4444; }

/* ── Header bar ─────────────────────────────────────────────────────────── */
QFrame#AppHeaderBar {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #0a0e1a, stop:1 #0e1328);
    border-bottom: 1px solid rgba(99, 132, 255, 0.15);
    min-height: 48px;
    max-height: 48px;
}

/* ── Chat composer card ─────────────────────────────────────────────────── */
QFrame#ChatComposerCard {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 #0e1328, stop:1 #0a0e1a);
    border-top: 1px solid rgba(99, 132, 255, 0.12);
    border-radius: 0px;
}

QTextEdit#ChatComposer {
    background-color: rgba(14, 19, 40, 0.85);
    border: 1px solid rgba(99, 132, 255, 0.18);
    border-radius: 14px;
    padding: 10px 14px;
    color: #f0f4ff;
    font-size: 15px;
    line-height: 1.5;
}

QTextEdit#ChatComposer:focus {
    border: 1px solid rgba(34, 211, 238, 0.45);
}

/* ── Chat scroll area ───────────────────────────────────────────────────── */
QScrollArea#ChatScrollArea, QScrollArea#ChatScrollArea > QWidget {
    background-color: transparent;
}

/* ── AI-Studio-style message bubbles ────────────────────────────────────── */

/* Timestamp / sender label */
QLabel#BubbleTimeLabel {
    color: #3d506e;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.4px;
}

/* User message: plain text, no card */
QLabel#UserMessageText {
    color: #c4cff0;
    font-size: 15px;
    line-height: 1.7;
}

/* Agent message card — subtle nebula glow */
QFrame#AgentMessageCard {
    background-color: rgba(17, 24, 51, 0.85);
    border: 1px solid rgba(99, 132, 255, 0.18);
    border-radius: 14px;
}

/* Agent message body text */
QLabel#AgentMessageText {
    color: #f0f4ff;
    font-size: 15px;
    line-height: 1.7;
}

/* ── Inline trace toggle button ─────────────────────────────────────────── */
QPushButton#TraceToggleButton {
    background-color: transparent;
    border: none;
    border-top: 1px solid rgba(99, 132, 255, 0.1);
    border-radius: 0px;
    color: #22d3ee;
    font-size: 12px;
    font-weight: 600;
    text-align: left;
    padding: 0 0 0 2px;
    letter-spacing: 0.3px;
}

QPushButton#TraceToggleButton:hover {
    color: #67e8f9;
    background-color: transparent;
}

/* ── Inline trace body ───────────────────────────────────────────────────── */
QWidget#TraceInlineBody {
    background-color: transparent;
}
"""
