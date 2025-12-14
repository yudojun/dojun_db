import os
import json
import requests
import sqlite3

from kivy.core.text import LabelBase
from kivy.lang import Builder
from kivy.metrics import dp

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.list import TwoLineListItem
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.snackbar import MDSnackbar
from kivymd.uix.tab import MDTabsBase


# =============================
# 폰트 등록 (한글 안정화)
# =============================
LabelBase.register(
    name="Nanum",
    fn_regular="/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    fn_bold="/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
)

LabelBase.register(
    name="Roboto",
    fn_regular="/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    fn_bold="/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
)


# =============================
# 원격 DB 정보
# =============================
REMOTE_VERSION_URL = (
    "https://raw.githubusercontent.com/yudojun/dojun_db/master/remote_version.json"
)

LOCAL_VERSION_FILE = "local_version.json"
LOCAL_DB_FILE = "data/issues.db"


# =============================
# DB 업데이트 로직
# =============================
def get_local_version():
    if not os.path.exists(LOCAL_VERSION_FILE):
        return 0
    with open(LOCAL_VERSION_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("version", 0)


def get_remote_info():
    r = requests.get(REMOTE_VERSION_URL, timeout=5)
    r.raise_for_status()
    return r.json()


def download_db(db_url):
    os.makedirs("data", exist_ok=True)
    r = requests.get(db_url, stream=True, timeout=10)
    r.raise_for_status()

    with open(LOCAL_DB_FILE, "wb") as f:
        for chunk in r.iter_content(1024):
            f.write(chunk)


def update_db_if_needed():
    try:
        local_version = get_local_version()
        remote = get_remote_info()

        remote_version = remote["version"]
        remote_db_url = remote["url"]

        if remote_version > local_version:
            download_db(remote_db_url)

            with open(LOCAL_VERSION_FILE, "w", encoding="utf-8") as f:
                json.dump({"version": remote_version}, f)

            return "updated"

        else:
            return "latest"

    except Exception as e:
        print("⚠ DB 업데이트 실패:", e)
        return "error"


# =============================
# DB 조회
# =============================
def load_issues():
    conn = sqlite3.connect(LOCAL_DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT title, summary, company, union_opt FROM issues")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_filtered_issues(keyword="", tab="전체"):
    kw = keyword.strip()
    rows = load_issues()

    def match(row):
        title, summary, company, union_opt = row
        if kw and kw not in title:
            return False
        if tab == "회사안":
            return bool(company and company.strip())
        if tab == "조합안":
            return bool(union_opt and union_opt.strip())
        return True

    return [r for r in rows if match(r)]


class Tab(MDBoxLayout, MDTabsBase):
    pass


# =============================
# 메인 화면
# =============================
class MainScreen(MDScreen):
    current_tab = "전체"

    def populate_main_list(self, keyword=""):
        self.ids.issue_list.clear_widgets()

        for row in get_filtered_issues(keyword, self.current_tab):
            title = row[0]
            item = TwoLineListItem(
                text=title,
                secondary_text="눌러서 자세히 보기",
                on_release=lambda x, t=title: app.open_detail(t),
            )
            self.ids.issue_list.add_widget(item)

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        self.current_tab = tab_text
        self.populate_main_list()


# =============================
# 상세 화면
# =============================
class DetailScreen(MDScreen):
    def set_detail(self, title):
        self.ids.detail_title.text = title
        self.ids.detail_box.clear_widgets()

        conn = sqlite3.connect(LOCAL_DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "SELECT summary, company, union_opt FROM issues WHERE title=?",
            (title,),
        )
        row = cur.fetchone()
        conn.close()

        if not row:
            return

        keys = ["핵심 요약", "회사안", "조합안"]

        for i, text in enumerate(row):
            card = MDCard(
                orientation="vertical",
                padding=dp(12),
                radius=[12],
            )
            card.add_widget(
                MDLabel(
                    text=f"[b]{keys[i]}[/b]",
                    markup=True,
                    font_name="Nanum",
                    font_size=dp(18),
                )
            )
            card.add_widget(
                MDLabel(
                    text=text,
                    font_name="Nanum",
                    size_hint_y=None,
                )
            )
            self.ids.detail_box.add_widget(card)


# =============================
# 앱 본체
# =============================
class MainApp(MDApp):
    def build(self):
        return Builder.load_file("dojun.kv")

    def on_start(self):
        status = update_db_if_needed()   # ← 결과 받기

        main = self.root.get_screen("main")
        main.populate_main_list()
        main.ids.tabs.bind(on_tab_switch=main.on_tab_switch)

        self.show_update_snackbar(status)  # ← UI 알림

    def open_detail(self, title):
        detail = self.root.get_screen("detail")
        detail.set_detail(title)
        self.root.current = "detail"

    def show_update_snackbar(self, status):
        if status == "updated":
            MDSnackbar(
                MDLabel(text="📦 새로운 쟁점 DB가 업데이트되었습니다"),
                y=dp(24),
                pos_hint={"center_x": 0.5},
                size_hint_x=0.8,
                duration=2,
            ).open()

        elif status == "latest":
            MDSnackbar(
                MDLabel(text="✅ 최신 쟁점 DB입니다"),
                y=dp(24),
                pos_hint={"center_x": 0.5},
                size_hint_x=0.8,
                duration=2,
            ).open()

        elif status == "error":
            MDSnackbar(
                MDLabel(text="⚠ DB 업데이트 확인 실패 (네트워크)"),
                y=dp(24),
                pos_hint={"center_x": 0.5},
                size_hint_x=0.8,
                duration=3,
            ).open()


# =============================
# 실행
# =============================
app = MainApp()
app.run()
