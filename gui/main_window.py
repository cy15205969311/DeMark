"""
主窗口类 - 现代卡片式 UI 设计
Modern Card Layout with Dark Theme
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import asyncio
import threading
from typing import Dict, List, Optional
import logging
import sys
import os
import webbrowser
import json

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_extractor import ImageExtractor
from utils.downloader import ImageDownloader

class MainWindow:
    """
    主窗口类 - 现代卡片式 UI 设计
    Modern Card Layout with Dark Theme
    """
    
    def __init__(self):
        # 设置现代深色主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("🎨 DeMark - 现代图片提取工具")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # 设置背景色
        self.root.configure(fg_color="#1a1a1a")
        
        # 初始化组件
        self.extractor = ImageExtractor()
        self.downloader = ImageDownloader()
        self.results = []
        self.is_extracting = False
        self.is_downloading = False
        self.success_count = 0
        self.fail_count = 0
        
        # 创建界面
        self._create_widgets()
        self._setup_logging()
        
        # 显示空状态
        self._update_empty_state()
        
    def _create_widgets(self):
        """创建界面组件 - 使用 Grid 布局"""
        # 配置主窗口的网格权重
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=0)  # 控制卡片
        self.root.grid_rowconfigure(1, weight=1)  # 结果画廊
        self.root.grid_rowconfigure(2, weight=0)  # 日志抽屉
        self.root.grid_rowconfigure(3, weight=0)  # 状态栏
        
        # 1. 顶部控制卡片
        self._create_control_card()
        
        # 2. 中部结果画廊
        self._create_result_gallery()
        
        # 3. 底部日志抽屉
        self._create_log_drawer()
        
        # 4. 状态栏
        self._create_status_bar()
    
    def _create_control_card(self):
        """创建顶部控制卡片"""
        control_card = ctk.CTkFrame(
            self.root,
            fg_color="#2b2b2b",
            corner_radius=10,
            height=200
        )
        control_card.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        control_card.grid_propagate(False)
        
        # 配置内部网格
        control_card.grid_columnconfigure(0, weight=1)
        
        # 标题区域
        title_frame = ctk.CTkFrame(control_card, fg_color="transparent")
        title_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="🎯 智能图片提取器",
            font=("Microsoft YaHei UI", 20, "bold"),
            text_color="#3B8ED0"
        )
        title_label.pack(side="left")
        
        # URL 输入区域
        input_frame = ctk.CTkFrame(control_card, fg_color="transparent")
        input_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=10)
        input_frame.grid_columnconfigure(0, weight=1)
        
        # URL 输入框
        self.url_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="🔗 请输入图怪兽、Canva、创客贴等平台的分享链接...",
            font=("Microsoft YaHei UI", 12),
            height=40,
            corner_radius=8,
            border_color="#3B8ED0",
            border_width=2
        )
        self.url_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        
        # 提取按钮
        self.extract_btn = ctk.CTkButton(
            input_frame,
            text="🚀 智能解析",
            command=self._on_extract_click,
            font=("Microsoft YaHei UI", 14, "bold"),
            height=40,
            width=140,
            corner_radius=8,
            fg_color="#1f538d",
            hover_color="#14375e"
        )
        self.extract_btn.grid(row=0, column=1)
        
        # 平台选择区域 (分段按钮)
        platform_frame = ctk.CTkFrame(control_card, fg_color="transparent")
        platform_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(10, 20))
        
        platform_label = ctk.CTkLabel(
            platform_frame,
            text="🎨 支持平台:",
            font=("Microsoft YaHei UI", 12, "bold")
        )
        platform_label.pack(anchor="w", pady=(0, 8))
        
        # 使用分段按钮替代传统单选按钮
        self.platform_segmented = ctk.CTkSegmentedButton(
            platform_frame,
            values=["🤖 自动", "🎨 图怪兽", "🎭 Canva", "📐 Chuangkit"],
            font=("Microsoft YaHei UI", 11),
            corner_radius=8,
            border_width=2,
            selected_color="#1f538d",
            selected_hover_color="#14375e"
        )
        self.platform_segmented.pack(fill="x", pady=(0, 5))
        self.platform_segmented.set("🤖 自动")  # 默认选择自动
    
    def _create_result_gallery(self):
        """创建中部结果画廊"""
        gallery_card = ctk.CTkFrame(
            self.root,
            fg_color="#232323",
            corner_radius=10
        )
        gallery_card.grid(row=1, column=0, sticky="nsew", padx=20, pady=10)
        
        # 配置内部网格
        gallery_card.grid_columnconfigure(0, weight=1)
        gallery_card.grid_rowconfigure(1, weight=1)
        
        # 标题区域
        gallery_header = ctk.CTkFrame(gallery_card, fg_color="transparent", height=50)
        gallery_header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        gallery_header.grid_propagate(False)
        gallery_header.grid_columnconfigure(0, weight=1)
        
        gallery_title = ctk.CTkLabel(
            gallery_header,
            text="🖼️ 提取结果画廊",
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color="#3B8ED0"
        )
        gallery_title.grid(row=0, column=0, sticky="w")
        
        # 控制按钮
        gallery_controls = ctk.CTkFrame(gallery_header, fg_color="transparent")
        gallery_controls.grid(row=0, column=1, sticky="e")
        
        # 批量下载按钮
        self.download_all_btn = ctk.CTkButton(
            gallery_controls,
            text="� 批量下载",
            command=self._download_all_images,
            width=100,
            height=30,
            corner_radius=6,
            font=("Microsoft YaHei UI", 10),
            fg_color="#2d8f2d",
            hover_color="#1e5f1e"
        )
        self.download_all_btn.pack(side="right", padx=(10, 0))
        
        # 下载设置按钮
        self.download_settings_btn = ctk.CTkButton(
            gallery_controls,
            text="⚙️ 下载设置",
            command=self._show_download_settings,
            width=100,
            height=30,
            corner_radius=6,
            font=("Microsoft YaHei UI", 10),
            fg_color="#666666",
            hover_color="#555555"
        )
        self.download_settings_btn.pack(side="right", padx=(10, 0))
        
        self.export_btn = ctk.CTkButton(
            gallery_controls,
            text="📊 导出",
            command=self._export_results,
            width=80,
            height=30,
            corner_radius=6,
            font=("Microsoft YaHei UI", 10)
        )
        self.export_btn.pack(side="right", padx=(10, 0))
        
        self.clear_results_btn = ctk.CTkButton(
            gallery_controls,
            text="🗑️ 清空",
            command=self._clear_results,
            width=80,
            height=30,
            corner_radius=6,
            font=("Microsoft YaHei UI", 10),
            fg_color="#8B4513",
            hover_color="#A0522D"
        )
        self.clear_results_btn.pack(side="right")
        
        # 可滚动结果区域
        self.result_scroll_frame = ctk.CTkScrollableFrame(
            gallery_card,
            fg_color="#1e1e1e",
            corner_radius=8,
            scrollbar_button_color="#1f538d",
            scrollbar_button_hover_color="#14375e"
        )
        self.result_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        
        # 配置滚动区域的网格 - 支持网格布局
        self.result_scroll_frame.grid_columnconfigure(0, weight=1)
        self.result_scroll_frame.grid_columnconfigure(1, weight=1)
        self.result_scroll_frame.grid_columnconfigure(2, weight=1)
    
    def _create_log_drawer(self):
        """创建底部日志抽屉"""
        log_drawer = ctk.CTkFrame(
            self.root,
            fg_color="#2b2b2b",
            corner_radius=10,
            height=120
        )
        log_drawer.grid(row=2, column=0, sticky="ew", padx=20, pady=10)
        log_drawer.grid_propagate(False)
        
        # 配置内部网格
        log_drawer.grid_columnconfigure(0, weight=1)
        log_drawer.grid_rowconfigure(1, weight=1)
        
        # 日志标题和控制
        log_header = ctk.CTkFrame(log_drawer, fg_color="transparent", height=40)
        log_header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        log_header.grid_propagate(False)
        log_header.grid_columnconfigure(0, weight=1)
        
        log_title = ctk.CTkLabel(
            log_header,
            text="📋 系统日志",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color="#3B8ED0"
        )
        log_title.grid(row=0, column=0, sticky="w")
        
        # 日志控制按钮
        log_controls = ctk.CTkFrame(log_header, fg_color="transparent")
        log_controls.grid(row=0, column=1, sticky="e")
        
        export_log_btn = ctk.CTkButton(
            log_controls,
            text="💾 导出",
            command=self._save_log,
            width=60,
            height=25,
            corner_radius=6,
            font=("Microsoft YaHei UI", 9)
        )
        export_log_btn.pack(side="right", padx=(8, 0))
        
        clear_log_btn = ctk.CTkButton(
            log_controls,
            text="🗑️ 清空",
            command=self._clear_log,
            width=60,
            height=25,
            corner_radius=6,
            font=("Microsoft YaHei UI", 9),
            fg_color="#8B4513",
            hover_color="#A0522D"
        )
        clear_log_btn.pack(side="right")
        
        # 日志文本区域 - 终端风格
        log_text_frame = ctk.CTkFrame(log_drawer, fg_color="#000000", corner_radius=6)
        log_text_frame.grid(row=1, column=0, sticky="nsew", padx=15, pady=(0, 15))
        log_text_frame.grid_columnconfigure(0, weight=1)
        log_text_frame.grid_rowconfigure(0, weight=1)
        
        self.log_text = tk.Text(
            log_text_frame,
            bg="#000000",
            fg="#00ff00",  # 绿色终端字体
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief="flat",
            borderwidth=0,
            insertbackground="#00ff00",
            selectbackground="#404040"
        )
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        
        # 日志滚动条
        log_scrollbar = ctk.CTkScrollbar(
            log_text_frame,
            orientation="vertical",
            command=self.log_text.yview
        )
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 8), pady=8)
    
    def _create_status_bar(self):
        """创建底部状态栏"""
        status_bar = ctk.CTkFrame(
            self.root,
            fg_color="#2b2b2b",
            corner_radius=10,
            height=50
        )
        status_bar.grid(row=3, column=0, sticky="ew", padx=20, pady=(10, 20))
        status_bar.grid_propagate(False)
        
        # 配置内部网格
        status_bar.grid_columnconfigure(0, weight=1)
        
        # 状态信息
        status_info_frame = ctk.CTkFrame(status_bar, fg_color="transparent")
        status_info_frame.grid(row=0, column=0, sticky="ew", padx=15, pady=10)
        status_info_frame.grid_columnconfigure(0, weight=1)
        
        self.status_label = ctk.CTkLabel(
            status_info_frame,
            text="🟢 就绪 | 成功: 0 | 失败: 0",
            font=("Microsoft YaHei UI", 11),
            anchor="w"
        )
        self.status_label.grid(row=0, column=0, sticky="w")
        
        # 进度条区域
        progress_frame = ctk.CTkFrame(status_info_frame, fg_color="transparent")
        progress_frame.grid(row=0, column=1, sticky="e")
        
        progress_label = ctk.CTkLabel(
            progress_frame,
            text="进度:",
            font=("Microsoft YaHei UI", 10)
        )
        progress_label.pack(side="left", padx=(0, 8))
        
        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            width=200,
            height=12,
            corner_radius=6,
            progress_color="#1f538d"
        )
        self.progress_bar.pack(side="right")
        self.progress_bar.set(0)
    
    def _update_empty_state(self):
        """更新空状态显示"""
        # 清空现有内容
        for widget in self.result_scroll_frame.winfo_children():
            widget.destroy()
        
        if not self.results:
            # 创建空状态显示
            empty_frame = ctk.CTkFrame(
                self.result_scroll_frame,
                fg_color="transparent",
                height=300
            )
            empty_frame.grid(row=0, column=0, columnspan=3, sticky="nsew", padx=20, pady=50)
            empty_frame.grid_propagate(False)
            
            # 空状态图标
            empty_icon = ctk.CTkLabel(
                empty_frame,
                text="🖼️",
                font=("Microsoft YaHei UI", 48)
            )
            empty_icon.pack(pady=(50, 20))
            
            # 空状态文字
            empty_text = ctk.CTkLabel(
                empty_frame,
                text="暂无数据，请在上方输入链接开始抓取",
                font=("Microsoft YaHei UI", 14),
                text_color="gray60"
            )
            empty_text.pack()
            
            # 提示文字
            hint_text = ctk.CTkLabel(
                empty_frame,
                text="支持图怪兽、Canva、创客贴、抖音、小红书等平台",
                font=("Microsoft YaHei UI", 12),
                text_color="gray40"
            )
            hint_text.pack(pady=(10, 0))
    
    def _setup_logging(self):
        """设置日志系统"""
        class GUILogHandler(logging.Handler):
            def __init__(self, text_widget):
                super().__init__()
                self.text_widget = text_widget
            
            def emit(self, record):
                msg = self.format(record)
                # 在主线程中更新GUI
                self.text_widget.after(0, self._append_log, msg)
            
            def _append_log(self, msg):
                self.text_widget.config(state=tk.NORMAL)
                self.text_widget.insert(tk.END, msg + "\n")
                self.text_widget.see(tk.END)
                self.text_widget.config(state=tk.DISABLED)
        
        # 配置日志
        handler = GUILogHandler(self.log_text)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)
    
    def _on_extract_click(self):
        """提取按钮点击事件"""
        if self.is_extracting:
            messagebox.showwarning("警告", "正在提取中，请稍候...")
            return
        
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("错误", "请输入URL")
            return
        
        # 获取选择的平台
        platform_map = {
            "🤖 自动": "auto",
            "🎨 图怪兽": "818ps",
            "🎭 Canva": "Canva",
            "📐 Chuangkit": "Chuangkit"
        }
        platform = platform_map.get(self.platform_segmented.get(), "auto")
        
        # 自动识别平台
        if platform == "auto":
            platform = self._detect_platform(url)
        
        # 在后台线程中执行提取
        self.is_extracting = True
        self.extract_btn.configure(text="⏳ 提取中...", state="disabled")
        self.progress_bar.set(0.1)
        
        thread = threading.Thread(
            target=self._extract_in_background,
            args=(url, platform)
        )
        thread.daemon = True
        thread.start()
    
    def _extract_in_background(self, url: str, platform: str):
        """后台提取函数"""
        loop = None
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 执行提取
            result = loop.run_until_complete(
                self.extractor.extract_image(url, platform)
            )
            
            # 在主线程中更新结果
            self.root.after(0, self._on_extract_success, result)
            
        except Exception as e:
            # 在主线程中显示错误
            self.root.after(0, self._on_extract_error, str(e))
        finally:
            # 恢复按钮状态
            self.root.after(0, self._reset_extract_button)
            
            # 确保事件循环正确关闭
            if loop and not loop.is_closed():
                try:
                    # 关闭所有未完成的任务
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    
                    # 等待所有任务完成
                    if pending:
                        loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                    
                    # 关闭事件循环
                    loop.close()
                except Exception as e:
                    logging.warning(f"事件循环关闭警告: {e}")
    
    def _on_extract_success(self, result: Dict):
        """提取成功回调"""
        logging.info(f"✅ 提取成功: {result.get('imageUrl', '')[:80]}")
        
        # 添加到结果列表
        self.results.append(result)
        self.success_count += 1
        
        # 重新创建结果卡片
        self._refresh_result_gallery()
        
        # 更新状态
        self._update_status()
        
        messagebox.showinfo("成功", "图片提取成功！")
    
    def _on_extract_error(self, error_msg: str):
        """提取失败回调"""
        logging.error(f"❌ 提取失败: {error_msg}")
        
        # 添加失败记录
        self.results.append({
            'success': False,
            'error': error_msg,
            'platform': 'Unknown'
        })
        self.fail_count += 1
        
        # 重新创建结果卡片
        self._refresh_result_gallery()
        
        # 更新状态
        self._update_status()
        
        messagebox.showerror("提取失败", f"无法提取图片:\n{error_msg}")
    
    def _reset_extract_button(self):
        """重置提取按钮"""
        self.is_extracting = False
        self.extract_btn.configure(text="🚀 智能解析", state="normal")
        self.progress_bar.set(0)
    
    def _refresh_result_gallery(self):
        """刷新结果画廊"""
        # 清空现有内容
        for widget in self.result_scroll_frame.winfo_children():
            widget.destroy()
        
        if not self.results:
            self._update_empty_state()
            return
        
        # 创建网格布局的结果卡片
        row = 0
        col = 0
        max_cols = 3  # 每行最多3个卡片
        
        for i, result in enumerate(self.results):
            self._create_result_card(result, row, col)
            
            col += 1
            if col >= max_cols:
                col = 0
                row += 1
    
    def _create_result_card(self, result: Dict, row: int, col: int):
        """创建结果卡片 - 网格布局"""
        # 卡片容器
        card = ctk.CTkFrame(
            self.result_scroll_frame,
            fg_color="#2b2b2b",
            corner_radius=12,
            width=350,
            height=200
        )
        card.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        card.grid_propagate(False)
        
        # 配置卡片内部网格
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(1, weight=1)
        
        # 卡片头部
        header = ctk.CTkFrame(card, fg_color="transparent", height=50)
        header.grid(row=0, column=0, sticky="ew", padx=15, pady=(15, 5))
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        
        # 状态图标
        success = result.get('imageUrl') is not None
        status_icon = "✅" if success else "❌"
        status_color = "#2d8f2d" if success else "#d32f2f"
        
        status_frame = ctk.CTkFrame(
            header,
            fg_color=status_color,
            width=40,
            height=40,
            corner_radius=20
        )
        status_frame.grid(row=0, column=0, sticky="w")
        status_frame.grid_propagate(False)
        
        status_label = ctk.CTkLabel(
            status_frame,
            text=status_icon,
            font=("Microsoft YaHei UI", 16)
        )
        status_label.place(relx=0.5, rely=0.5, anchor="center")
        
        # 平台信息
        platform_info = ctk.CTkFrame(header, fg_color="transparent")
        platform_info.grid(row=0, column=1, sticky="ew", padx=(15, 0))
        
        platform_label = ctk.CTkLabel(
            platform_info,
            text=f"🎨 {result.get('platform', 'Unknown')}",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color="#3B8ED0",
            anchor="w"
        )
        platform_label.pack(fill="x")
        
        source_label = ctk.CTkLabel(
            platform_info,
            text=f"📡 {result.get('source', 'Unknown')}",
            font=("Microsoft YaHei UI", 10),
            text_color="gray60",
            anchor="w"
        )
        source_label.pack(fill="x")
        
        # 卡片内容
        content = ctk.CTkFrame(card, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=15, pady=5)
        content.grid_columnconfigure(0, weight=1)
        
        if success:
            # 成功时显示URL
            url_text = result.get('imageUrl', '')
            if len(url_text) > 60:
                url_text = url_text[:60] + "..."
            
            url_label = ctk.CTkLabel(
                content,
                text=f"🔗 {url_text}",
                font=("Microsoft YaHei UI", 10),
                text_color="gray70",
                anchor="w",
                wraplength=300
            )
            url_label.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        else:
            # 失败时显示错误信息
            error_text = result.get('error', '未知错误')
            if len(error_text) > 80:
                error_text = error_text[:80] + "..."
            
            error_label = ctk.CTkLabel(
                content,
                text=f"❌ {error_text}",
                font=("Microsoft YaHei UI", 10),
                text_color="#ff6b6b",
                anchor="w",
                wraplength=300
            )
            error_label.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # 操作按钮
        if success:
            btn_frame = ctk.CTkFrame(content, fg_color="transparent")
            btn_frame.grid(row=1, column=0, sticky="ew")
            
            copy_btn = ctk.CTkButton(
                btn_frame,
                text="📋 复制",
                command=lambda: self._copy_url(result.get('imageUrl')),
                width=80,
                height=28,
                corner_radius=6,
                font=("Microsoft YaHei UI", 9),
                fg_color="#1f538d",
                hover_color="#14375e"
            )
            copy_btn.pack(side="left", padx=(0, 8))
            
            preview_btn = ctk.CTkButton(
                btn_frame,
                text="👁️ 预览",
                command=lambda: self._preview_image(result.get('imageUrl')),
                width=80,
                height=28,
                corner_radius=6,
                font=("Microsoft YaHei UI", 9),
                fg_color="gray60",
                hover_color="gray50"
            )
            preview_btn.pack(side="left", padx=(0, 8))
            
            download_btn = ctk.CTkButton(
                btn_frame,
                text="⬇️ 下载",
                command=lambda: self._download_image(result),
                width=80,
                height=28,
                corner_radius=6,
                font=("Microsoft YaHei UI", 9),
                fg_color="#2d8f2d",
                hover_color="#1e5f1e"
            )
            download_btn.pack(side="left")
    
    def _detect_platform(self, url: str) -> str:
        """自动检测平台"""
        url_lower = url.lower()
        if '818ps.com' in url_lower or 'tuguaishou.com' in url_lower:
            return '818ps'
        elif 'canva.com' in url_lower or 'canva.cn' in url_lower:
            return 'Canva'
        elif 'chuangkit.com' in url_lower:
            return 'Chuangkit'
        else:
            return 'Unknown'
    
    def _clear_log(self):
        """清空日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def _save_log(self):
        """保存日志"""
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt"), ("所有文件", "*.*")],
                title="保存日志文件"
            )
            if filename:
                content = self.log_text.get(1.0, tk.END)
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("成功", f"日志已保存到: {filename}")
        except Exception as e:
            messagebox.showerror("错误", f"保存日志失败: {e}")
    
    def _export_results(self):
        """导出结果"""
        if not self.results:
            messagebox.showwarning("警告", "没有可导出的结果")
            return
        
        try:
            filename = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON文件", "*.json"), ("所有文件", "*.*")],
                title="导出结果文件"
            )
            if filename:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(self.results, f, ensure_ascii=False, indent=2)
                messagebox.showinfo("成功", f"结果已导出到: {filename}")
        except Exception as e:
            messagebox.showerror("错误", f"导出结果失败: {e}")
    
    def _clear_results(self):
        """清空结果"""
        if messagebox.askyesno("确认", "确定要清空所有结果吗？"):
            self.results.clear()
            self.success_count = 0
            self.fail_count = 0
            self._update_empty_state()
            self._update_status()
    
    def _copy_url(self, url: str):
        """复制URL到剪贴板"""
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            messagebox.showinfo("成功", "链接已复制到剪贴板")
    
    def _preview_image(self, url: str):
        """预览图片"""
        if url:
            webbrowser.open(url)
    
    def _download_image(self, result: Dict):
        """下载单张图片"""
        if self.is_downloading:
            messagebox.showwarning("提示", "正在下载中，请稍候...")
            return
        
        image_url = result.get('imageUrl')
        platform = result.get('platform', 'Unknown')
        
        if not image_url:
            messagebox.showerror("错误", "无效的图片URL")
            return
        
        # 在新线程中执行下载
        def download_thread():
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_download_single(image_url, platform))
            finally:
                loop.close()
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    async def _async_download_single(self, image_url: str, platform: str):
        """异步下载单张图片"""
        try:
            self.is_downloading = True
            self._safe_update_status("📥 开始下载图片...")
            
            # 进度回调函数
            def progress_callback(progress, downloaded, total):
                if total > 0:
                    message = f"📥 下载中... {progress:.1f}% ({downloaded}/{total} bytes)"
                    self._safe_update_status(message)
            
            # 执行下载
            result = await self.downloader.download_image(
                image_url, 
                progress_callback=progress_callback,
                platform=platform
            )
            
            if result['success']:
                message = f"✅ 下载完成: {result['filename']}"
                self._safe_update_status(message)
                # 使用线程安全的消息框
                self.root.after(0, lambda: messagebox.showinfo("下载完成", f"图片已保存到: {result['file_path']}"))
            else:
                error_msg = result.get('error', 'Unknown error')
                message = f"❌ 下载失败: {error_msg}"
                self._safe_update_status(message)
                self.root.after(0, lambda: messagebox.showerror("下载失败", error_msg))
                
        except Exception as e:
            message = f"❌ 下载异常: {e}"
            self._safe_update_status(message)
            self.root.after(0, lambda: messagebox.showerror("下载异常", str(e)))
        finally:
            self.is_downloading = False
    
    def _download_all_images(self):
        """下载所有成功提取的图片"""
        if self.is_downloading:
            messagebox.showwarning("提示", "正在下载中，请稍候...")
            return
        
        # 获取所有成功的结果
        successful_results = [r for r in self.results if r.get('imageUrl')]
        
        if not successful_results:
            messagebox.showwarning("提示", "没有可下载的图片")
            return
        
        # 确认下载
        if not messagebox.askyesno("确认下载", f"确定要下载 {len(successful_results)} 张图片吗？"):
            return
        
        # 在新线程中执行批量下载
        def download_thread():
            try:
                # 创建新的事件循环
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(self._async_download_batch(successful_results))
            finally:
                loop.close()
        
        threading.Thread(target=download_thread, daemon=True).start()
    
    async def _async_download_batch(self, results: List[Dict]):
        """异步批量下载图片"""
        try:
            self.is_downloading = True
            message = f"📦 开始批量下载 {len(results)} 张图片..."
            self._safe_update_status(message)
            
            # 提取URL和平台信息
            download_tasks = []
            for result in results:
                image_url = result.get('imageUrl')
                platform = result.get('platform', 'Unknown')
                if image_url:
                    download_tasks.append((image_url, platform))
            
            # 进度回调函数
            def progress_callback(completed, total, result):
                progress = (completed / total) * 100
                status = "成功" if result.get('success') else "失败"
                message = f"📦 批量下载进度: {completed}/{total} ({progress:.1f}%) - 最新: {status}"
                self._safe_update_status(message)
            
            # 执行批量下载
            image_urls = [task[0] for task in download_tasks]
            platform = download_tasks[0][1] if download_tasks else "Mixed"
            
            batch_result = await self.downloader.batch_download(
                image_urls,
                progress_callback=progress_callback,
                platform=platform,
                max_concurrent=3
            )
            
            if batch_result['success']:
                successful = batch_result['successful']
                failed = batch_result['failed']
                message = f"✅ 批量下载完成: 成功 {successful}, 失败 {failed}"
                self._safe_update_status(message)
                success_msg = f"下载完成！\n成功: {successful} 张\n失败: {failed} 张"
                self.root.after(0, lambda: messagebox.showinfo("批量下载完成", success_msg))
            else:
                error_msg = batch_result.get('error', 'Unknown error')
                message = f"❌ 批量下载失败: {error_msg}"
                self._safe_update_status(message)
                self.root.after(0, lambda: messagebox.showerror("批量下载失败", error_msg))
                
        except Exception as e:
            message = f"❌ 批量下载异常: {e}"
            self._safe_update_status(message)
            self.root.after(0, lambda: messagebox.showerror("批量下载异常", str(e)))
        finally:
            self.is_downloading = False
    
    def _update_status(self, message: str = None):
        """更新状态栏"""
        if message:
            # 如果提供了消息，显示消息
            self.status_label.configure(text=message)
        else:
            # 否则显示默认状态
            total = len(self.results)
            self.status_label.configure(
                text=f"🟢 就绪 | 成功: {self.success_count} | 失败: {self.fail_count} | 总计: {total}"
            )
    
    def _safe_update_status(self, message: str):
        """线程安全的状态更新"""
        self.root.after(0, lambda: self._update_status(message))
    
    def _show_download_settings(self):
        """显示下载设置对话框"""
        settings_window = ctk.CTkToplevel(self.root)
        settings_window.title("下载设置")
        settings_window.geometry("400x300")
        settings_window.transient(self.root)
        settings_window.grab_set()
        
        # 居中显示
        settings_window.geometry("+%d+%d" % (
            self.root.winfo_rootx() + 50,
            self.root.winfo_rooty() + 50
        ))
        
        # 下载目录设置
        dir_frame = ctk.CTkFrame(settings_window)
        dir_frame.pack(fill="x", padx=20, pady=20)
        
        ctk.CTkLabel(dir_frame, text="下载目录:", font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=10, pady=(10, 5))
        
        dir_display_frame = ctk.CTkFrame(dir_frame)
        dir_display_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        current_dir = str(self.downloader.download_dir)
        self.dir_label = ctk.CTkLabel(
            dir_display_frame, 
            text=current_dir, 
            font=("Microsoft YaHei UI", 10),
            anchor="w"
        )
        self.dir_label.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        
        browse_btn = ctk.CTkButton(
            dir_display_frame,
            text="浏览",
            command=lambda: self._browse_download_dir(settings_window),
            width=60,
            height=30
        )
        browse_btn.pack(side="right", padx=10, pady=10)
        
        # 下载统计
        stats_frame = ctk.CTkFrame(settings_window)
        stats_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        ctk.CTkLabel(stats_frame, text="下载统计:", font=("Microsoft YaHei UI", 12)).pack(anchor="w", padx=10, pady=(10, 5))
        
        stats = self.downloader.get_download_stats()
        stats_text = f"已下载文件: {stats['total_files']} 个\n总大小: {stats['total_size_mb']} MB"
        
        ctk.CTkLabel(
            stats_frame, 
            text=stats_text, 
            font=("Microsoft YaHei UI", 10),
            anchor="w"
        ).pack(anchor="w", padx=10, pady=(0, 10))
        
        # 按钮
        btn_frame = ctk.CTkFrame(settings_window)
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))
        
        open_dir_btn = ctk.CTkButton(
            btn_frame,
            text="打开下载目录",
            command=lambda: self._open_download_dir(),
            width=120,
            height=35
        )
        open_dir_btn.pack(side="left", padx=10, pady=10)
        
        close_btn = ctk.CTkButton(
            btn_frame,
            text="关闭",
            command=settings_window.destroy,
            width=80,
            height=35
        )
        close_btn.pack(side="right", padx=10, pady=10)
    
    def _browse_download_dir(self, parent_window):
        """浏览选择下载目录"""
        new_dir = filedialog.askdirectory(
            title="选择下载目录",
            initialdir=str(self.downloader.download_dir)
        )
        
        if new_dir:
            self.downloader.download_dir = Path(new_dir)
            self.downloader.download_dir.mkdir(parents=True, exist_ok=True)
            self.dir_label.configure(text=new_dir)
            self._safe_update_status(f"📁 下载目录已更改: {new_dir}")
    
    def _open_download_dir(self):
        """打开下载目录"""
        import subprocess
        import platform
        
        download_path = str(self.downloader.download_dir)
        
        try:
            if platform.system() == "Windows":
                subprocess.run(["explorer", download_path])
            elif platform.system() == "Darwin":  # macOS
                subprocess.run(["open", download_path])
            else:  # Linux
                subprocess.run(["xdg-open", download_path])
        except Exception as e:
            messagebox.showerror("错误", f"无法打开目录: {e}")
    
    def run(self):
        """运行主窗口"""
        self.root.mainloop()

# 启动应用
if __name__ == "__main__":
    app = MainWindow()
    app.run()