"""Shared style sheet for the Student Productivity Agent Frontend Relevant."""

APP_STYLE = """
QMainWindow, QWidget#AppRoot {
    background-color: #212121;
    color: #ececec;
    font-family: "Inter", "Segoe UI", "Helvetica Neue", "Arial", sans-serif;
}

QWidget#AuthPage, QWidget#HomePage {
    background-color: transparent;
}

QFrame#SidebarFrame {
    background-color: #171717;
    border: none;
    border-right: 1px solid #2f2f2f;
    border-radius: 0px;
}

QFrame#CenterFrame, QFrame#TraceFrame, QFrame#WorkspaceCard, QFrame#PanelCard, QFrame#HomeNavBar, QFrame#HomeHeroCard, QFrame#HomeFeatureCard, QFrame#HomeSkillCard, QFrame#HomeBannerCard {
    background-color: transparent;
    border: none;
    border-radius: 0px;
}

QFrame#AuthHeroFrame, QFrame#AuthCard {
    background-color: #171717;
    border: 1px solid #2f2f2f;
    border-radius: 12px;
}

QFrame#AgentResultCard, QFrame#ResultSubCard {
    background-color: #212121;
    border: 1px solid #383838;
    border-radius: 12px;
}

QFrame#MiniConflictCard {
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 12px;
}

QFrame#FeaturePill {
    background-color: #2f2f2f;
    border: 1px solid #383838;
    border-radius: 18px;
}

QLabel#TitleLabel, QLabel#HomeBrand, QLabel#HeroTitle, QLabel#AuthTitle, QLabel#HomeHeroTitle, QLabel#HomeSectionTitle, QLabel#SectionTitle {
    color: #ececec;
    font-weight: 600;
}

QLabel#TitleLabel { font-size: 24px; }
QLabel#HomeBrand { font-size: 20px; }
QLabel#HeroTitle { font-size: 32px; }
QLabel#AuthTitle { font-size: 24px; }
QLabel#HomeHeroTitle { font-size: 40px; }
QLabel#HomeSectionTitle { font-size: 24px; }
QLabel#SectionTitle { font-size: 16px; }

QLabel#SubtitleLabel, QLabel#HeroBody, QLabel#AuthFooter, QLabel#HintText, QLabel#HomeHeroSubtitle, QLabel#MutedText, QLabel#CardTitle {
    color: #b4b4b4;
}

QLabel#SubtitleLabel { font-size: 14px; }
QLabel#HeroBody, QLabel#AuthFooter, QLabel#HintText, QLabel#MutedText { font-size: 14px; }
QLabel#HomeHeroSubtitle { font-size: 16px; line-height: 1.5; }
QLabel#CardTitle { font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }

QLabel#CardValue {
    font-size: 24px;
    font-weight: 600;
    color: #ececec;
}

QLabel#WorkspaceName {
    font-size: 20px;
    font-weight: 600;
    color: #ececec;
}

QLabel#BodyText {
    color: #ececec;
    font-size: 15px;
    line-height: 1.6;
}

QLabel#ResultQueryLabel {
    padding: 8px 12px;
    border-radius: 8px;
    background-color: #2f2f2f;
    color: #ececec;
    font-size: 14px;
}

QLabel#BadgeLabel, QLabel#WorkspaceStat {
    padding: 6px 12px;
    border-radius: 8px;
    background-color: #2f2f2f;
    color: #ececec;
    font-size: 13px;
    font-weight: 500;
}

QLabel#MessageTypeChip {
    padding: 4px 10px;
    border-radius: 999px;
    background-color: #2f2f2f;
    color: #ececec;
    font-size: 12px;
    font-weight: 600;
}

QLabel#SkillIcon {
    font-size: 14px;
    font-weight: 600;
    color: #ececec;
}

QPushButton {
    min-height: 38px;
    padding: 0 16px;
    border-radius: 8px;
    border: 1px solid #383838;
    color: #ececec;
    background-color: #2f2f2f;
    font-weight: 500;
    font-size: 14px;
}

QPushButton:hover {
    background-color: #383838;
}

QPushButton#PrimaryButton {
    background-color: #ececec;
    color: #171717;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background-color: #d4d4d4;
}

QPushButton#SendButton {
    background-color: #ececec;
    color: #171717;
    border-radius: 16px;
    min-width: 32px;
    max-width: 32px;
    min-height: 32px;
    max-height: 32px;
    border: none;
}

QPushButton#SendButton:hover {
    background-color: #d4d4d4;
}

QPushButton#SendButton:disabled {
    background-color: #2f2f2f;
    color: #676767;
}

QLineEdit, QTextEdit, QListWidget, QTextBrowser {
    background-color: #2f2f2f;
    border: 1px solid #383838;
    border-radius: 12px;
    padding: 12px;
    color: #ececec;
    font-size: 15px;
    selection-background-color: #ececec;
    selection-color: #171717;
}

QLineEdit#AuthInput {
    background-color: #171717;
    border: 1px solid #383838;
    min-height: 44px;
    border-radius: 8px;
}

QPushButton#ModeDropdownButton {
    min-height: 36px;
    min-width: 140px;
    padding: 0 12px;
    border-radius: 8px;
    background-color: transparent;
    border: none;
    color: #ececec;
    font-weight: 600;
    font-size: 15px;
    text-align: left;
}

QPushButton#ModeDropdownButton:hover {
    background-color: #2f2f2f;
}

QMenu#ModeDropdownMenu {
    background-color: #2f2f2f;
    border: 1px solid #383838;
    border-radius: 8px;
    padding: 4px;
    color: #ececec;
}

QMenu#ModeDropdownMenu::item {
    padding: 8px 12px;
    border-radius: 6px;
    margin: 2px;
}

QMenu#ModeDropdownMenu::item:selected {
    background-color: #383838;
}

QMenu#ModeDropdownMenu::indicator {
    width: 12px;
    height: 12px;
}

QMenu#ModeDropdownMenu::indicator:checked {
    image: none;
    background-color: #ececec;
    border-radius: 6px;
}

QMenu#ModeDropdownMenu::indicator:unchecked {
    image: none;
    background-color: transparent;
}

QListWidget#ConversationList, QListWidget#ResourceList, QListWidget#DailyScheduleList, QListWidget#ScheduleConflictList {
    background-color: transparent;
    border: none;
    padding: 4px;
    outline: none;
}

QListWidget#ConversationList::item, QListWidget#ResourceList::item {
    margin: 2px 0;
    padding: 10px 12px;
    border-radius: 8px;
    color: #ececec;
}

QListWidget#ConversationList::item:selected, QListWidget#ResourceList::item:selected {
    background-color: #2f2f2f;
    border: none;
}

QListWidget#ConversationList::item:hover:!selected, QListWidget#ResourceList::item:hover:!selected {
    background-color: #212121;
}

QListWidget#DailyScheduleList::item {
    background-color: #2f2f2f;
    border: 1px solid #383838;
    border-radius: 8px;
    margin: 4px 0;
    padding: 12px;
    color: #ececec;
}

QListWidget#ScheduleConflictList::item {
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 8px;
    margin: 4px 0;
    padding: 12px;
    color: #ececec;
}

QTabWidget::pane {
    border: none;
    background-color: transparent;
    top: -1px;
}

QTabBar::tab {
    background-color: transparent;
    color: #b4b4b4;
    min-width: 100px;
    min-height: 36px;
    border-bottom: 2px solid transparent;
    margin-right: 16px;
    padding: 8px 12px;
    font-size: 14px;
    font-weight: 500;
}

QTabBar::tab:selected {
    color: #ececec;
    border-bottom: 2px solid #ececec;
}

QTabBar::tab:hover:!selected {
    color: #d4d4d4;
    border-bottom: 2px solid #383838;
}

QCalendarWidget#ScheduleCalendar {
    background-color: transparent;
    border: none;
    color: #ececec;
}

QCalendarWidget#ScheduleCalendar QWidget {
    alternate-background-color: transparent;
    background-color: transparent;
    color: #ececec;
}

QCalendarWidget#ScheduleCalendar QToolButton {
    min-height: 30px;
    max-height: 30px;
    border-radius: 6px;
    padding: 4px 10px;
    background-color: transparent;
    color: #ececec;
}

QCalendarWidget#ScheduleCalendar QToolButton:hover {
    background-color: #2f2f2f;
}

QCalendarWidget#ScheduleCalendar QAbstractItemView {
    background-color: #171717;
    border: 1px solid #2f2f2f;
    border-radius: 8px;
    color: #ececec;
    selection-background-color: #ececec;
    selection-color: #171717;
    outline: none;
}

QScrollArea {
    border: none;
    background-color: transparent;
}

QScrollArea#SchedulePageScroll, QScrollArea#ScheduleDetailScroll, QWidget#SchedulePageContent, QWidget#ScheduleDetailContent {
    background-color: transparent;
}

QScrollBar:vertical {
    width: 8px;
    background-color: transparent;
    margin: 4px 0 4px 0;
}

QScrollBar::handle:vertical {
    background-color: #383838;
    border-radius: 4px;
    min-height: 20px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame#UserBubble {
    background-color: #2f2f2f;
    border: none;
    border-radius: 18px;
}

QFrame#AgentBubble {
    background-color: transparent;
    border: none;
}

QTextBrowser#ResultMarkdown {
    background-color: transparent;
    border: none;
    padding: 0px;
}

QFrame#ConflictCard {
    background-color: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.2);
    border-radius: 12px;
}

QFrame#TraceItemDone, QFrame#TraceItemRunning, QFrame#TraceItemPending, QFrame#TraceItemError {
    background-color: #171717;
    border: 1px solid #2f2f2f;
    border-radius: 8px;
}

QFrame#TraceItemDone { border-left: 3px solid #10b981; }
QFrame#TraceItemRunning { border-left: 3px solid #3b82f6; }
QFrame#TraceItemPending { border-left: 3px solid #f59e0b; }
QFrame#TraceItemError { border-left: 3px solid #ef4444; }

/* ── Header bar ─────────────────────────────────────────────────────────── */
QFrame#AppHeaderBar {
    background-color: #171717;
    border-bottom: 1px solid #2f2f2f;
    min-height: 48px;
    max-height: 48px;
}

/* ── Chat composer card ─────────────────────────────────────────────────── */
QFrame#ChatComposerCard {
    background-color: #171717;
    border-top: 1px solid #2f2f2f;
    border-radius: 0px;
}

QTextEdit#ChatComposer {
    background-color: #2f2f2f;
    border: 1px solid #3a3a3a;
    border-radius: 14px;
    padding: 10px 14px;
    color: #ececec;
    font-size: 15px;
    line-height: 1.5;
}

QTextEdit#ChatComposer:focus {
    border: 1px solid #555555;
}

/* ── Chat scroll area ───────────────────────────────────────────────────── */
QScrollArea#ChatScrollArea, QScrollArea#ChatScrollArea > QWidget {
    background-color: transparent;
}
"""
