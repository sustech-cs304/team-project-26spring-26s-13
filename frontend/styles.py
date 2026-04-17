"""Shared style sheet for the Student Productivity Agent God Xun-Frontend."""

APP_STYLE = """
QMainWindow, QWidget#AppRoot {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 #09111f,
        stop: 0.4 #101a33,
        stop: 1 #172546
    );
    color: #edf2ff;
    font-family: "Arial";
}

QWidget#AuthPage {
    background: transparent;
}

QWidget#HomePage {
    background: transparent;
}

QFrame#SidebarFrame,
QFrame#CenterFrame,
QFrame#TraceFrame,
QFrame#WorkspaceCard,
QFrame#PanelCard,
QFrame#UserBubble,
QFrame#AgentBubble,
QFrame#AgentResultCard,
QFrame#ResultSubCard,
QFrame#MiniConflictCard,
QFrame#TraceItemDone,
QFrame#TraceItemRunning,
QFrame#TraceItemPending,
QFrame#TraceItemError,
QFrame#AuthHeroFrame,
QFrame#AuthCard,
QFrame#FeaturePill,
QFrame#HomeNavBar,
QFrame#HomeHeroCard,
QFrame#HomeFeatureCard,
QFrame#HomeSkillCard,
QFrame#HomeBannerCard {
    border-radius: 18px;
}

QFrame#SidebarFrame,
QFrame#CenterFrame,
QFrame#TraceFrame,
QFrame#WorkspaceCard,
QFrame#PanelCard,
QFrame#AuthHeroFrame,
QFrame#AuthCard,
QFrame#HomeNavBar,
QFrame#HomeHeroCard,
QFrame#HomeFeatureCard,
QFrame#HomeSkillCard,
QFrame#HomeBannerCard {
    background: rgba(10, 18, 35, 0.78);
    border: 1px solid rgba(255, 255, 255, 0.10);
}

QFrame#FeaturePill {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.08);
}

QFrame#AgentResultCard {
    background: rgba(23, 33, 58, 0.82);
    border: 1px solid rgba(121, 158, 255, 0.20);
}

QFrame#ResultSubCard {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.09);
}

QFrame#MiniConflictCard {
    background: rgba(255, 121, 121, 0.10);
    border: 1px solid rgba(255, 160, 160, 0.20);
}

QFrame#SidebarFrame {
    background: rgba(7, 14, 28, 0.88);
    border: 1px solid rgba(163, 188, 255, 0.08);
}

QFrame#WorkspaceCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba(66, 108, 228, 0.28),
        stop: 1 rgba(29, 164, 186, 0.16)
    );
    border: 1px solid rgba(141, 189, 255, 0.22);
}

QFrame#HomeHeroCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 1,
        stop: 0 rgba(16, 28, 58, 0.92),
        stop: 0.55 rgba(22, 38, 78, 0.86),
        stop: 1 rgba(38, 50, 98, 0.80)
    );
}

QFrame#HomeBannerCard {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 rgba(74, 102, 214, 0.34),
        stop: 1 rgba(52, 145, 215, 0.24)
    );
}

QLabel#TitleLabel {
    font-size: 30px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#HomeBrand {
    font-size: 22px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#AuthKicker {
    color: #8ab6ff;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 1px;
}

QLabel#HeroTitle {
    font-size: 38px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#AuthTitle {
    font-size: 28px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#HomeHeroTitle {
    font-size: 46px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#SubtitleLabel {
    font-size: 13px;
    color: #a9b6d6;
}

QLabel#HeroBody,
QLabel#AuthFooter,
QLabel#HintText {
    color: #cfd9f6;
    font-size: 14px;
}

QLabel#HomeHeroSubtitle {
    color: #e0e7ff;
    font-size: 18px;
    line-height: 1.5;
}

QLabel#HomeSectionTitle {
    font-size: 28px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#SectionTitle {
    font-size: 17px;
    font-weight: 700;
    color: #f4f7ff;
}

QLabel#CardTitle {
    font-size: 12px;
    letter-spacing: 0.5px;
    color: #9cadcf;
    text-transform: uppercase;
}

QLabel#CardValue {
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#WorkspaceName {
    font-size: 24px;
    font-weight: 700;
    color: #ffffff;
}

QLabel#ResultQueryLabel {
    padding: 8px 12px;
    border-radius: 12px;
    background: rgba(90, 124, 255, 0.14);
    border: 1px solid rgba(121, 156, 255, 0.20);
    color: #eef3ff;
    font-size: 13px;
}

QLabel#BodyText,
QLabel#MutedText {
    color: #dce4fb;
    font-size: 13px;
}

QLabel#MutedText {
    color: #9eadcf;
}

QLabel#BadgeLabel {
    padding: 10px 14px;
    border-radius: 12px;
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #eef3ff;
    font-weight: 600;
}

QLabel#WorkspaceStat {
    padding: 8px 10px;
    border-radius: 10px;
    background: rgba(255, 255, 255, 0.08);
    border: 1px solid rgba(255, 255, 255, 0.12);
    color: #f4f7ff;
    font-size: 12px;
    font-weight: 600;
}

QLabel#MessageTypeChip {
    padding: 4px 10px;
    border-radius: 999px;
    background: rgba(115, 193, 255, 0.12);
    border: 1px solid rgba(115, 193, 255, 0.22);
    color: #cfe8ff;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
}

QLabel#SkillIcon {
    font-size: 12px;
    font-weight: 700;
    color: #8ab6ff;
    letter-spacing: 1px;
}

QPushButton {
    min-height: 40px;
    padding: 0 16px;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #eef3ff;
    background: rgba(255, 255, 255, 0.06);
    font-weight: 600;
}

QPushButton:hover {
    background: rgba(255, 255, 255, 0.12);
}

QPushButton#PrimaryButton {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #5a7cff,
        stop: 1 #73c1ff
    );
    color: #071120;
    border: none;
}

QPushButton#PrimaryButton:hover {
    background: qlineargradient(
        x1: 0, y1: 0, x2: 1, y2: 0,
        stop: 0 #7c97ff,
        stop: 1 #95d4ff
    );
}

QLineEdit,
QTextEdit,
QListWidget,
QTextBrowser {
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    border-radius: 14px;
    padding: 10px;
    color: #f1f5ff;
    selection-background-color: #5a7cff;
}

QLineEdit#AuthInput {
    background: rgba(255, 255, 255, 0.09);
    border: 1px solid rgba(255, 255, 255, 0.14);
    min-height: 42px;
}

QPushButton#ModeDropdownButton {
    min-height: 38px;
    min-width: 150px;
    padding: 0 14px;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.05);
    border: 1px solid rgba(255, 255, 255, 0.10);
    color: #eef3ff;
    font-weight: 600;
    text-align: left;
}

QPushButton#ModeDropdownButton:hover {
    background: rgba(255, 255, 255, 0.08);
}

QMenu#ModeDropdownMenu {
    background: rgba(13, 22, 42, 0.98);
    border: 1px solid rgba(121, 156, 255, 0.20);
    border-radius: 12px;
    padding: 6px;
    color: #eef3ff;
}

QMenu#ModeDropdownMenu::item {
    padding: 10px 14px;
    border-radius: 10px;
    margin: 2px 4px;
}

QMenu#ModeDropdownMenu::item:selected {
    background: rgba(90, 124, 255, 0.24);
}

QMenu#ModeDropdownMenu::item:checked {
    background: rgba(90, 124, 255, 0.18);
}

QMenu#ModeDropdownMenu::indicator {
    width: 12px;
    height: 12px;
}

QMenu#ModeDropdownMenu::indicator:checked {
    image: none;
    background: rgba(115, 193, 255, 0.90);
    border-radius: 6px;
}

QMenu#ModeDropdownMenu::indicator:non-exclusive:unchecked,
QMenu#ModeDropdownMenu::indicator:exclusive:unchecked {
    image: none;
    background: transparent;
}

QMenu#ModeDropdownMenu::indicator:exclusive:checked,
QMenu#ModeDropdownMenu::indicator:non-exclusive:checked {
    image: none;
    background: rgba(115, 193, 255, 0.90);
    border-radius: 6px;
}

QMenu#ModeDropdownMenu {
    color: #eef3ff;
}

QTextEdit {
    padding-top: 12px;
}

QListWidget#ConversationList,
QListWidget#ResourceList {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 8px;
    outline: none;
}

QListWidget#ConversationList::item,
QListWidget#ResourceList::item {
    margin: 4px 0;
    padding: 10px 12px;
    border-radius: 12px;
    border: 1px solid transparent;
    color: #eef3ff;
}

QListWidget#ConversationList::item {
    background: rgba(255, 255, 255, 0.04);
}

QListWidget#ResourceList::item {
    background: rgba(255, 255, 255, 0.025);
}

QListWidget#ConversationList::item:selected {
    background: rgba(95, 129, 255, 0.26);
    border: 1px solid rgba(143, 174, 255, 0.30);
}

QListWidget#ResourceList::item:selected {
    background: rgba(83, 191, 214, 0.20);
    border: 1px solid rgba(115, 214, 230, 0.26);
}

QTabWidget::pane {
    border: 1px solid rgba(255, 255, 255, 0.10);
    background: rgba(9, 15, 28, 0.55);
    border-radius: 16px;
    top: -1px;
}

QTabBar::tab {
    background: rgba(255, 255, 255, 0.05);
    color: #aebcdf;
    min-width: 130px;
    min-height: 36px;
    border-top-left-radius: 12px;
    border-top-right-radius: 12px;
    margin-right: 6px;
    padding: 8px 14px;
}

QTabBar::tab:selected {
    background: rgba(90, 124, 255, 0.28);
    color: #ffffff;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    width: 10px;
    background: transparent;
    margin: 4px 0 4px 0;
}

QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 0.18);
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame#UserBubble {
    background: rgba(74, 126, 255, 0.28);
    border: 1px solid rgba(132, 167, 255, 0.35);
}

QFrame#AgentBubble {
    background: rgba(110, 82, 235, 0.20);
    border: 1px solid rgba(162, 145, 255, 0.24);
}

QTextBrowser#ResultMarkdown {
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 14px;
    padding: 10px;
}

QFrame#ConflictCard {
    background: rgba(255, 121, 121, 0.12);
    border: 1px solid rgba(255, 149, 149, 0.24);
}

QFrame#TraceItemDone {
    background: rgba(102, 204, 153, 0.12);
    border: 1px solid rgba(102, 204, 153, 0.25);
}

QFrame#TraceItemRunning {
    background: rgba(90, 124, 255, 0.12);
    border: 1px solid rgba(90, 124, 255, 0.26);
}

QFrame#TraceItemPending {
    background: rgba(255, 188, 92, 0.12);
    border: 1px solid rgba(255, 188, 92, 0.26);
}

QFrame#TraceItemError {
    background: rgba(255, 104, 104, 0.14);
    border: 1px solid rgba(255, 126, 126, 0.30);
}
"""
