import cv2
import numpy as np
import time
import threading
import pygame
import os
import json
from PIL import Image
import pytesseract
import tkinter as tk
from tkinter import messagebox, filedialog
from collections import Counter


class GuandanCardTracker:
    def __init__(self):
        # 初始化游戏状态
        self.is_running = False
        self.game_area = None  # 游戏界面区域
        self.hand_area = None  # 自己手牌区域
        self.player_areas = [None, None, None]  # 其他三家出牌区域

        # 区域配置文件
        self.config_file = "guandan_regions.json"

        # 卡牌识别相关
        self.card_templates = self.load_card_templates()
        self.card_count = self.initialize_card_count()

        # 界面初始化
        self.init_ui()

        # 音效初始化
        pygame.mixer.init()
        self.alert_sound = pygame.mixer.Sound('alert.wav') if os.path.exists('alert.wav') else None

        # 尝试加载已保存的区域数据
        self.load_regions()

    def load_card_templates(self):
        """加载卡牌模板图像，用于模板匹配"""
        templates = {}

        # 加载模板图像的路径（假设已有标准模板）
        template_dir = "card_templates/"

        # 检查模板目录是否存在
        if not os.path.exists(template_dir):
            os.makedirs(template_dir)
            print(f"模板目录不存在，已创建: {template_dir}")
            print("请将卡牌模板图像放入此目录")
            return templates

        # 卡牌值
        values = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
        jokers = ["BJoker", "RJoker"]

        # 加载普通牌（不区分花色，每种点数只需一个模板）
        for value in values:
            template_path = f"{template_dir}{value}.png"
            if os.path.exists(template_path):
                templates[value] = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)

        # 加载王牌
        for joker in jokers:
            template_path = f"{template_dir}{joker}.png"
            if os.path.exists(template_path):
                templates[joker] = cv2.imread(template_path)

        print(f"已加载 {len(templates)} 个卡牌模板")
        return templates

    def initialize_card_count(self):
        """初始化卡牌计数器（掼蛋是双副牌）"""
        card_count = {}

        # 普通牌 (不区分花色，每种点数有8张)
        values = ["3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A", "2"]
        for value in values:
            card_count[value] = 8

        # 王牌
        card_count["BJoker"] = 2
        card_count["RJoker"] = 2

        return card_count

    def init_ui(self):
        """初始化用户界面"""
        self.root = tk.Tk()
        self.root.title("掼蛋记牌器")
        self.root.geometry("400x300")

        # 创建按钮框架
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=10)

        # 开始游戏按钮
        self.start_button = tk.Button(button_frame, text="开始游戏", command=self.start_game, width=15, height=2)
        self.start_button.pack(side=tk.LEFT, padx=10)

        # 结束游戏按钮
        self.stop_button = tk.Button(button_frame, text="结束游戏", command=self.stop_game, width=15, height=2,
                                     state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=10)

        # 区域设置框架
        area_frame = tk.Frame(self.root)
        area_frame.pack(pady=5)

        # 设置区域按钮
        self.setup_button = tk.Button(area_frame, text="设置游戏区域", command=self.setup_areas, width=15, height=2)
        self.setup_button.pack(side=tk.LEFT, padx=5)

        # 保存区域按钮
        self.save_button = tk.Button(area_frame, text="保存区域", command=self.save_regions, width=15, height=2)
        self.save_button.pack(side=tk.LEFT, padx=5)

        # 加载区域按钮
        self.load_button = tk.Button(area_frame, text="加载区域", command=self.load_regions_dialog, width=15, height=2)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # 创建卡牌统计显示区
        self.card_stats_frame = tk.Frame(self.root)
        self.card_stats_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.card_stats_text = tk.Text(self.card_stats_frame, height=10, width=50)
        self.card_stats_text.pack(fill=tk.BOTH, expand=True)

        # 状态栏
        self.status_var = tk.StringVar()
        self.status_var.set("准备就绪")
        self.status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 更新界面状态
        self.update_ui_state()

    def update_ui_state(self):
        """根据当前状态更新界面按钮状态"""
        has_regions = all([self.game_area, self.hand_area] + self.player_areas)

        # 更新保存按钮状态
        if has_regions:
            self.save_button.config(state=tk.NORMAL)
        else:
            self.save_button.config(state=tk.DISABLED)

        # 如果游戏正在运行，禁用设置和加载按钮
        if self.is_running:
            self.setup_button.config(state=tk.DISABLED)
            self.load_button.config(state=tk.DISABLED)
        else:
            self.setup_button.config(state=tk.NORMAL)
            self.load_button.config(state=tk.NORMAL)

    def on_close(self):
        """关闭窗口时的处理"""
        if self.is_running:
            self.stop_game()
        self.root.destroy()

    # def setup_areas(self):
    #     """设置游戏区域"""
    #     self.status_var.set("正在设置游戏区域...")
    #
    #     # 使用OpenCV捕获屏幕
    #     screen = self.capture_screen()
    #     if screen is None:
    #         messagebox.showerror("错误", "无法捕获屏幕")
    #         self.status_var.set("设置失败")
    #         return
    #
    #     # 显示屏幕截图并让用户选择区域
    #     if self.select_regions(screen):
    #         self.status_var.set("游戏区域设置完成")
    #         self.update_ui_state()
    #     else:
    #         self.status_var.set("游戏区域设置取消")

    def setup_areas(self):
        """设置游戏区域"""
        self.status_var.set("正在设置游戏区域...")

        # 使用OpenCV捕获屏幕
        screen = self.capture_screen()
        if screen is None:
            messagebox.showerror("错误", "无法捕获屏幕")
            self.status_var.set("设置失败")
            return

        # 显示屏幕截图并让用户选择区域
        if self.select_game_area(screen):
            self.status_var.set("游戏区域设置完成")
            self.update_ui_state()
        else:
            self.status_var.set("游戏区域设置取消")


    def select_game_area(self, screen):
        """让用户在屏幕截图上选择游戏区域"""
        # 缩放图像以适应屏幕
        h, w = screen.shape[:2]
        scale_factor = min(1.0, 1200 / w, 800 / h)
        scaled_w, scaled_h = int(w * scale_factor), int(h * scale_factor)
        scaled_screen = cv2.resize(screen, (scaled_w, scaled_h))

        # 创建窗口进行区域选择
        window_name = "选择游戏区域"
        cv2.namedWindow(window_name)

        regions = []
        current_rect = None
        drawing = False

        def mouse_callback(event, x, y, flags, param):
            nonlocal drawing, current_rect, regions

            if event == cv2.EVENT_LBUTTONDOWN:
                drawing = True
                current_rect = [(x, y)]

            elif event == cv2.EVENT_MOUSEMOVE:
                if drawing:
                    img_copy = scaled_screen.copy()

                    # 绘制当前正在绘制的矩形
                    cv2.rectangle(img_copy, current_rect[0], (x, y), (0, 0, 255), 2)
                    cv2.imshow(window_name, img_copy)

            elif event == cv2.EVENT_LBUTTONUP:
                drawing = False
                current_rect.append((x, y))
                regions.append(current_rect)

                img_copy = scaled_screen.copy()
                cv2.rectangle(img_copy, current_rect[0], current_rect[1], (0, 255, 0), 2)
                cv2.imshow(window_name, img_copy)

                # 完成选择
                time.sleep(1)  # 给用户查看最终结果的时间
                cv2.destroyWindow(window_name)

        cv2.setMouseCallback(window_name, mouse_callback)
        cv2.imshow(window_name, scaled_screen)
        cv2.waitKey(0)

        # 将选定的区域转换回原始尺寸
        if len(regions) == 1:
            self.game_area = self.scale_region(regions[0], 1 / scale_factor)
            # 这里设置比例
            self.calculate_regions()
            return True
        else:
            messagebox.showwarning("警告", f"需要选择1个区域，但选择了{len(regions)}个")
            return False

    def calculate_regions(self):
        """根据游戏区域和比例计算其他区域"""
        if not self.game_area:
            return

        # 提取游戏区域坐标
        x1, y1 = self.game_area[0]
        x2, y2 = self.game_area[1]
        width = x2 - x1
        height = y2 - y1

        # 计算手牌区域（已存在）
        self.hand_area = (
            (int(x1 + 0.0097 * width), int(y1 + 0.5286 * height)),
            (int(x1 + 0.9893 * width), int(y1 + 0.9337 * height))
        )

        # 计算三个玩家区域（新增）
        self.player_areas = [
            # Player 1（左下玩家）
            (
                (int(x1 + 0.0754 * width), int(y1 + 0.3001 * height)),  # 左上角
                (int(x1 + 0.3757 * width), int(y1 + 0.4883 * height))  # 右下角
            ),
            # Player 2（上方玩家）
            (
                (int(x1 + 0.2668 * width), int(y1 + 0.1239 * height)),  # 左上角
                (int(x1 + 0.6880 * width), int(y1 + 0.2932 * height))  # 右下角
            ),
            # Player 3（右下玩家）
            (
                (int(x1 + 0.6030 * width), int(y1 + 0.2773 * height)),  # 左上角
                (int(x1 + 0.9329 * width), int(y1 + 0.4642 * height))  # 右下角
            )
        ]

        # 验证坐标有效性（可选）
        for area in [self.hand_area] + self.player_areas:
            assert area[0][0] < area[1][0], "水平坐标无效"
            assert area[0][1] < area[1][1], "垂直坐标无效"

    def select_regions(self, screen):
        """让用户在屏幕截图上选择游戏区域"""
        # 缩放图像以适应屏幕
        h, w = screen.shape[:2]
        scale_factor = min(1.0, 1200 / w, 800 / h)
        scaled_w, scaled_h = int(w * scale_factor), int(h * scale_factor)
        scaled_screen = cv2.resize(screen, (scaled_w, scaled_h))

        # 创建窗口进行区域选择
        window_name = "选择游戏区域 (按顺序选择: 1.游戏界面 2.自己手牌区 3-5.其他三家出牌区)"
        cv2.namedWindow(window_name)

        regions = []
        current_rect = None
        drawing = False

        def mouse_callback(event, x, y, flags, param):
            nonlocal drawing, current_rect, regions

            if event == cv2.EVENT_LBUTTONDOWN:
                drawing = True
                current_rect = [(x, y)]

            elif event == cv2.EVENT_MOUSEMOVE:
                if drawing:
                    img_copy = scaled_screen.copy()

                    # 绘制已保存的矩形
                    for i, r in enumerate(regions):
                        cv2.rectangle(img_copy, r[0], r[1], (0, 255, 0), 2)
                        cv2.putText(img_copy, f"区域 {i + 1}",
                                    (r[0][0], r[0][1] - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

                    # 绘制当前正在绘制的矩形
                    cv2.rectangle(img_copy, current_rect[0], (x, y), (0, 0, 255), 2)
                    cv2.imshow(window_name, img_copy)

            elif event == cv2.EVENT_LBUTTONUP:
                drawing = False
                current_rect.append((x, y))
                regions.append(current_rect)

                img_copy = scaled_screen.copy()
                for i, r in enumerate(regions):
                    cv2.rectangle(img_copy, r[0], r[1], (0, 255, 0), 2)
                    cv2.putText(img_copy, f"区域 {i + 1}",
                                (r[0][0], r[0][1] - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                cv2.imshow(window_name, img_copy)

                # 如果选择了5个区域，完成选择
                if len(regions) == 5:
                    time.sleep(1)  # 给用户查看最终结果的时间
                    cv2.destroyWindow(window_name)

        cv2.setMouseCallback(window_name, mouse_callback)
        cv2.imshow(window_name, scaled_screen)
        cv2.waitKey(0)

        # 将选定的区域转换回原始尺寸
        if len(regions) == 5:
            self.game_area = self.scale_region(regions[0], 1 / scale_factor)
            self.hand_area = self.scale_region(regions[1], 1 / scale_factor)
            self.player_areas = [
                self.scale_region(regions[2], 1 / scale_factor),
                self.scale_region(regions[3], 1 / scale_factor),
                self.scale_region(regions[4], 1 / scale_factor)
            ]
            return True
        else:
            messagebox.showwarning("警告", f"需要选择5个区域，但只选择了{len(regions)}个")
            return False

    def save_regions(self):
        """保存选定的区域数据到文件"""
        if not all([self.game_area, self.hand_area] + self.player_areas):
            messagebox.showwarning("警告", "没有区域数据可保存")
            return

        # 准备保存的数据结构
        regions_data = {
            "game_area": self.game_area,
            "hand_area": self.hand_area,
            "player_areas": self.player_areas
        }

        # 打开文件对话框选择保存位置
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON文件", "*.json")],
            initialfile=self.config_file
        )

        if not file_path:
            return  # 用户取消了保存操作

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(regions_data, f)

            self.config_file = file_path
            self.status_var.set(f"区域数据已保存至: {file_path}")
            messagebox.showinfo("成功", f"区域数据已保存至: {file_path}")
        except Exception as e:
            messagebox.showerror("保存失败", f"保存区域数据失败: {e}")

    def load_regions(self):
        """从默认配置文件加载区域数据"""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    regions_data = json.load(f)

                self.game_area = tuple(tuple(p) for p in regions_data["game_area"])
                self.hand_area = tuple(tuple(p) for p in regions_data["hand_area"])
                self.player_areas = [tuple(tuple(p) for p in area) for area in regions_data["player_areas"]]

                self.status_var.set(f"已加载区域数据")
                self.update_ui_state()
                return True
            except Exception as e:
                print(f"加载区域数据失败: {e}")
                return False
        return False

    def load_regions_dialog(self):
        """打开文件对话框选择要加载的区域数据文件"""
        file_path = filedialog.askopenfilename(
            filetypes=[("JSON文件", "*.json")],
            initialdir=os.path.dirname(self.config_file)
        )

        if not file_path:
            return  # 用户取消了加载操作

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                regions_data = json.load(f)

            self.game_area = tuple(tuple(p) for p in regions_data["game_area"])
            self.hand_area = tuple(tuple(p) for p in regions_data["hand_area"])
            self.player_areas = [tuple(tuple(p) for p in area) for area in regions_data["player_areas"]]

            self.config_file = file_path
            self.status_var.set(f"已加载区域数据: {file_path}")
            messagebox.showinfo("成功", f"已加载区域数据: {file_path}")
            self.update_ui_state()
        except Exception as e:
            messagebox.showerror("加载失败", f"加载区域数据失败: {e}")

    def scale_region(self, region, factor):
        """按比例缩放区域坐标"""
        return (
            (int(region[0][0] * factor), int(region[0][1] * factor)),
            (int(region[1][0] * factor), int(region[1][1] * factor))
        )

    def start_game(self):
        """开始游戏记牌"""
        if not all([self.game_area, self.hand_area] + self.player_areas):
            messagebox.showwarning("警告", "请先设置游戏区域")
            return

        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.update_ui_state()

        # 重置卡牌计数
        self.card_count = self.initialize_card_count()

        # 开始记牌线程
        self.tracking_thread = threading.Thread(target=self.tracking_loop)
        self.tracking_thread.daemon = True
        self.tracking_thread.start()

        self.status_var.set("记牌中...")

    def stop_game(self):
        """停止游戏记牌"""
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.update_ui_state()
        self.status_var.set("已停止记牌")

    def capture_screen(self):
        """捕获屏幕"""
        try:
            # 使用PIL截取屏幕
            import pyautogui
            screenshot = pyautogui.screenshot()
            screenshot = np.array(screenshot)
            return cv2.cvtColor(screenshot, cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"截屏错误: {e}")
            return None

    def recognize_cards(self, image, region_name):
        """识别图像中的卡牌"""
        if not self.card_templates:
            print("没有卡牌模板可用")
            return []
        # 使用模板匹配方法
        return self.recognize_cards_template(image, region_name)

    def recognize_cards_template(self, image, region_name):
        """使用模板匹配识别卡牌（不区分花色）"""
        # 转换为灰度图

        found_cards = []
        img = image

        # 对每个卡牌模板进行匹配
        for card_name, template in self.card_templates.items():
            if card_name in ["BJoker", "RJoker"]:

                #获取模板的原始尺寸
                template_height, template_width = template.shape[:2]

                # 定义缩放比例范围
                scales = np.linspace(0.5, 1.5, 20)

                for scale in scales:
                    # 缩放模板
                    resized_template = cv2.resize(template, (int(template_width * scale), int(template_height * scale)))
                    resized_height, resized_width = resized_template.shape[:2]

                    # 跳过过小的模板
                    if resized_height > img.shape[0] or resized_width > img.shape[1]:
                        continue

                    # 模板匹配
                    result = cv2.matchTemplate(img, resized_template, cv2.TM_CCOEFF_NORMED)

                    # 设定阈值
                    threshold = 0.9
                    locations = np.where(result >= threshold)

                    # 找到匹配位置
                    for pt in zip(*locations[::-1]):
                        # 避免重复检测（临近位置视为同一张牌）
                        duplicate = False
                        for found_card in found_cards:
                            if found_card["name"] == card_name and (abs(pt[1] - found_card["position"][1]) < 10 and abs(
                                    pt[0] - found_card["position"][0]) < 10):
                                duplicate = True
                                break

                        if not duplicate:
                            found_cards.append({
                                "name": card_name,
                                "position": pt
                            })


            else:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                # 获取模板的原始尺寸
                template_height, template_width = template.shape[:2]

                # 定义缩放比例范围
                scales = np.linspace(0.5, 1.5, 20)

                for scale in scales:
                    # 缩放模板
                    resized_template = cv2.resize(template, (int(template_width * scale), int(template_height * scale)))
                    resized_height, resized_width = resized_template.shape[:2]

                    # 跳过过小的模板
                    if resized_height > gray.shape[0] or resized_width > gray.shape[1]:
                        continue

                    # 模板匹配
                    result = cv2.matchTemplate(gray, resized_template, cv2.TM_CCOEFF_NORMED)

                    # 设定阈值
                    threshold = 0.9
                    locations = np.where(result >= threshold)

                    # 找到匹配位置
                    for pt in zip(*locations[::-1]):
                        # 避免重复检测（临近位置视为同一张牌）
                        duplicate = False
                        for found_card in found_cards:
                            if found_card["name"] == card_name and (abs(pt[1] - found_card["position"][1]) < 10 and abs(pt[0] - found_card["position"][0]) < 10):
                                duplicate = True
                                break

                        if not duplicate:
                            found_cards.append({
                                "name": card_name,
                                "position": pt
                            })

        # 按x坐标排序（从左到右）
        found_cards.sort(key=lambda x: x["position"][0])

        # 返回卡牌名称列表
        return [card["name"] for card in found_cards]

    def tracking_loop(self):
        """记牌主循环"""
        last_hand_cards = []
        last_player_played = [[], [], []]
        is_initial = False
        while self.is_running:
            try:
                # 捕获屏幕
                screen = self.capture_screen()
                if screen is None:
                    time.sleep(1)
                    continue

                # 获取游戏区域
                game_img = screen[
                           self.game_area[0][1]:self.game_area[1][1],
                           self.game_area[0][0]:self.game_area[1][0]
                           ]

                # 获取手牌区域
                hand_img = screen[
                           self.hand_area[0][1]:self.hand_area[1][1],
                           self.hand_area[0][0]:self.hand_area[1][0]
                           ]

                # 获取其他玩家区域
                player_imgs = []
                for area in self.player_areas:
                    player_img = screen[
                                 area[0][1]:area[1][1],
                                 area[0][0]:area[1][0]
                                 ]
                    player_imgs.append(player_img)

                # 识别手牌
                current_hand = self.recognize_cards(hand_img, "手牌")
                print(f"手牌: {current_hand}")
                # 检测手牌变化
                # if current_hand != last_hand_cards:
                #     removed_cards = [card for card in last_hand_cards if card not in current_hand or
                #                      last_hand_cards.count(card) > current_hand.count(card)]
                #     for card in removed_cards:
                #         if self.card_count.get(card, 0) > 0:
                #             self.card_count[card] -= 1
                #
                #     last_hand_cards = current_hand.copy()

                if not is_initial:
                    for card in current_hand:
                        if self.card_count.get(card, 0) > 0:
                            self.card_count[card] -= 1
                    is_initial = True

                # 识别其他玩家出的牌
                for i, player_img in enumerate(player_imgs):
                    current_played = self.recognize_cards(player_img, f"玩家{i + 1}")
                    print(f"玩家{i + 1} 出牌: {current_played}")

                    # 检测其他玩家出牌变化
                    if current_played != last_player_played[i]:
                        new_cards = [card for card in current_played if card not in last_player_played[i] or
                                     current_played.count(card) > last_player_played[i].count(card)]

                        for card in new_cards:
                            if self.card_count.get(card, 0) > 0:
                                self.card_count[card] -= 1

                        last_player_played[i] = current_played.copy()

                # 更新界面显示
                self.update_display()

                # 轻微延迟，减少CPU使用
                time.sleep(0.5)

            except Exception as e:
                print(f"记牌循环错误: {e}")
                time.sleep(1)

    def update_display(self):
        """更新界面显示"""
        if not self.is_running:
            return

        self.card_stats_text.delete(1.0, tk.END)

        # 按点数排序显示
        values = ["2", "A", "K", "Q", "J", "10", "9", "8", "7", "6", "5", "4", "3"]
        jokers = ["RJoker", "BJoker"]

        # 生成显示文本
        display_text = "剩余牌数统计:\n\n"

        # 先显示普通牌
        for value in values:
            count = self.card_count.get(value, 0)
            if count > 0:
                display_text += f"{value}: {count}张\n"

        # 再显示王牌
        for joker in jokers:
            count = self.card_count.get(joker, 0)
            if count > 0:
                display_text += f"{joker}: {count}张\n"

        self.card_stats_text.insert(tk.END, display_text)

    def run(self):
        """运行程序"""
        self.root.mainloop()


# 创建并运行程序
if __name__ == "__main__":
    app = GuandanCardTracker()
    app.run()