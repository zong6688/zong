import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from pathlib import Path
import random
import time
from datetime import datetime

import numpy as np
from PIL import Image, ImageDraw, ImageTk
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# =========================
# Matplotlib 中文設定（避免中文顯示成方塊）
# =========================
plt.rcParams["font.sans-serif"] = [
    "Microsoft JhengHei",
    "SimHei",
    "Arial Unicode MS",
    "DejaVu Sans"
]
plt.rcParams["axes.unicode_minus"] = False

# =========================
# 基本設定
# =========================
BOARD_SIZE = 4          # 改成 6 就是 6x6
CARD_WIDTH = 120
CARD_HEIGHT = 120
CARD_SIZE = (CARD_WIDTH, CARD_HEIGHT)
ASSETS_DIR = Path("assets")
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
MISMATCH_DELAY_MS = 900


@dataclass
class Card:
    """單張卡牌物件：記錄卡牌的圖片 ID 與目前狀態。"""
    pair_id: int
    front_image: Image.Image
    is_revealed: bool = False
    is_matched: bool = False
    click_count: int = 0


class GameManager:
    """負責遊戲邏輯：洗牌、翻牌、配對判定、統計資料。"""

    def __init__(self, board_size: int, pair_images: list[Image.Image]):
        self.board_size = board_size
        self.num_pairs = (board_size * board_size) // 2
        self.pair_images = pair_images
        self.reset()

    def reset(self):
        self.cards = self._create_shuffled_cards()
        self.first_pick = None
        self.second_pick = None
        self.lock_board = False

        self.mismatch_count = 0          # 翻錯次數
        self.successful_matches = 0      # 成功配對次數
        self.total_pair_attempts = 0     # 總配對嘗試次數

        self.click_heatmap = np.zeros((self.board_size, self.board_size), dtype=int)
        self.start_time = time.time()

    def _create_shuffled_cards(self):
        deck = []
        for pair_id, img in enumerate(self.pair_images, start=1):
            deck.append(Card(pair_id=pair_id, front_image=img.copy()))
            deck.append(Card(pair_id=pair_id, front_image=img.copy()))

        random.shuffle(deck)

        grid = []
        idx = 0
        for _ in range(self.board_size):
            row = []
            for _ in range(self.board_size):
                row.append(deck[idx])
                idx += 1
            grid.append(row)
        return grid

    def pick_card(self, row: int, col: int):
        """處理玩家點牌，回傳動作結果給 GUI。"""
        if self.lock_board:
            return {"action": "locked"}

        card = self.cards[row][col]
        if card.is_revealed or card.is_matched:
            return {"action": "ignored"}

        card.is_revealed = True
        card.click_count += 1
        self.click_heatmap[row, col] += 1

        if self.first_pick is None:
            self.first_pick = (row, col)
            return {"action": "first", "position": (row, col)}

        self.second_pick = (row, col)
        self.total_pair_attempts += 1

        r1, c1 = self.first_pick
        first_card = self.cards[r1][c1]

        # 成功配對
        if first_card.pair_id == card.pair_id:
            first_card.is_matched = True
            card.is_matched = True
            self.successful_matches += 1

            positions = [self.first_pick, self.second_pick]
            self.first_pick = None
            self.second_pick = None

            won = self.successful_matches == self.num_pairs
            return {"action": "match", "positions": positions, "won": won}

        # 配對失敗
        self.mismatch_count += 1
        self.lock_board = True
        return {
            "action": "mismatch",
            "positions": [self.first_pick, self.second_pick]
        }

    def hide_mismatched_cards(self):
        """把翻錯的兩張牌蓋回去。"""
        if self.first_pick is None or self.second_pick is None:
            return

        r1, c1 = self.first_pick
        r2, c2 = self.second_pick

        self.cards[r1][c1].is_revealed = False
        self.cards[r2][c2].is_revealed = False

        self.first_pick = None
        self.second_pick = None
        self.lock_board = False

    @property
    def elapsed_seconds(self):
        return int(time.time() - self.start_time)

    @property
    def accuracy(self):
        """精準度 = 成功配對次數 / 總配對嘗試次數"""
        if self.total_pair_attempts == 0:
            return 100.0
        return (self.successful_matches / self.total_pair_attempts) * 100


class MemoryMatchApp:
    """GUI 主程式：顯示卡牌、處理點擊、顯示數據圖表。"""

    def __init__(self, root: tk.Tk, board_size: int = BOARD_SIZE):
        self.root = root
        self.root.title("記憶翻牌大考驗 - Memory Match")
        self.root.geometry("760x860")
        self.root.minsize(700, 780)

        if (board_size * board_size) % 2 != 0:
            raise ValueError("棋盤大小必須是偶數張牌，例如 4x4 或 6x6。")

        self.board_size = board_size
        self.num_pairs = (board_size * board_size) // 2

        self.front_images = self.load_pair_images(self.num_pairs)
        self.back_image = self.create_back_image()

        self.tk_back_image = ImageTk.PhotoImage(self.back_image)
        self.tk_front_cache = {}

        self.game = GameManager(self.board_size, self.front_images)
        self.buttons = []

        self.build_ui()
        self.refresh_board()
        self.update_timer()

    def build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        title = ttk.Label(
            top,
            text="🃏 記憶翻牌大考驗",
            font=("Microsoft JhengHei", 20, "bold")
        )
        title.pack(anchor="center", pady=(0, 8))

        info = ttk.Frame(top)
        info.pack(fill="x")

        self.time_var = tk.StringVar(value="時間：0 秒")
        self.mismatch_var = tk.StringVar(value="翻錯次數：0")
        self.accuracy_var = tk.StringVar(value="精準度：100.0%")

        ttk.Label(info, textvariable=self.time_var, font=("Microsoft JhengHei", 12)).grid(row=0, column=0, padx=10, pady=5)
        ttk.Label(info, textvariable=self.mismatch_var, font=("Microsoft JhengHei", 12)).grid(row=0, column=1, padx=10, pady=5)
        ttk.Label(info, textvariable=self.accuracy_var, font=("Microsoft JhengHei", 12)).grid(row=0, column=2, padx=10, pady=5)

        ttk.Button(info, text="重新開始", command=self.restart_game).grid(row=0, column=3, padx=12)

        tip = ttk.Label(
            top,
            text="提示：把圖片放進 assets 資料夾，就會自動當作卡牌圖案；不夠時會自動產生彩色預設牌。",
            foreground="#555555"
        )
        tip.pack(anchor="w", pady=(4, 8))

        board_frame = ttk.Frame(self.root, padding=10)
        board_frame.pack(expand=True)

        self.buttons = []
        for r in range(self.board_size):
            row_buttons = []
            for c in range(self.board_size):
                btn = tk.Button(
                    board_frame,
                    image=self.tk_back_image,
                    width=CARD_WIDTH,
                    height=CARD_HEIGHT,
                    relief="raised",
                    bd=3,
                    command=lambda rr=r, cc=c: self.on_card_click(rr, cc)
                )
                btn.grid(row=r, column=c, padx=6, pady=6)
                row_buttons.append(btn)
            self.buttons.append(row_buttons)

    def restart_game(self):
        self.game = GameManager(self.board_size, self.front_images)
        self.refresh_board()
        self.update_stats_labels()

    def update_timer(self):
        self.time_var.set(f"時間：{self.game.elapsed_seconds} 秒")
        self.root.after(1000, self.update_timer)

    def update_stats_labels(self):
        self.time_var.set(f"時間：{self.game.elapsed_seconds} 秒")
        self.mismatch_var.set(f"翻錯次數：{self.game.mismatch_count}")
        self.accuracy_var.set(f"精準度：{self.game.accuracy:.1f}%")

    def on_card_click(self, row: int, col: int):
        result = self.game.pick_card(row, col)
        action = result.get("action")

        if action in {"ignored", "locked"}:
            return

        self.refresh_board()
        self.update_stats_labels()

        if action == "mismatch":
            self.root.after(MISMATCH_DELAY_MS, self.resolve_mismatch)
        elif action == "match" and result.get("won"):
            self.root.after(300, self.show_victory)

    def resolve_mismatch(self):
        self.game.hide_mismatched_cards()
        self.refresh_board()
        self.update_stats_labels()

    def refresh_board(self):
        for r in range(self.board_size):
            for c in range(self.board_size):
                card = self.game.cards[r][c]
                btn = self.buttons[r][c]

                if card.is_revealed or card.is_matched:
                    tk_img = self.get_tk_front_image(card)
                    btn.config(image=tk_img, state="normal")
                    btn.image = tk_img
                else:
                    btn.config(image=self.tk_back_image, state="normal")
                    btn.image = self.tk_back_image

                if card.is_matched:
                    btn.config(state="disabled", relief="sunken", disabledforeground="black")
                else:
                    btn.config(relief="raised")

    def get_tk_front_image(self, card: Card):
        key = (card.pair_id, id(card.front_image))
        if key not in self.tk_front_cache:
            self.tk_front_cache[key] = ImageTk.PhotoImage(card.front_image)
        return self.tk_front_cache[key]

    def show_victory(self):
        self.update_stats_labels()
        messagebox.showinfo(
            "過關！",
            f"恭喜完成配對！\n\n"
            f"總時間：{self.game.elapsed_seconds} 秒\n"
            f"翻錯次數：{self.game.mismatch_count}\n"
            f"精準度：{self.game.accuracy:.1f}%"
        )
        self.show_stats_dashboard()

    def show_stats_dashboard(self):
        stats_win = tk.Toplevel(self.root)
        stats_win.title("遊戲數據面板")
        stats_win.geometry("980x520")

        fig, axes = plt.subplots(1, 2, figsize=(11, 5))
        fig.suptitle("記憶翻牌大考驗 - 數據分析", fontsize=16)

        # 圓餅圖：成功配對 vs 翻錯次數
        success = self.game.successful_matches
        mistakes = self.game.mismatch_count
        axes[0].pie(
            [max(success, 0.0001), max(mistakes, 0.0001)],
            labels=["配對成功", "翻錯次數"],
            autopct="%1.1f%%",
            startangle=90,
            colors=["#66bb6a", "#ef5350"]
        )
        axes[0].set_title("精準度分析（成功 vs 翻錯）")

        # 熱力圖：畫面哪個位置被點最多
        heatmap = self.game.click_heatmap
        im = axes[1].imshow(heatmap, cmap="YlOrRd")
        axes[1].set_title("點擊熱力圖")
        axes[1].set_xlabel("欄位")
        axes[1].set_ylabel("列")
        axes[1].set_xticks(range(self.board_size))
