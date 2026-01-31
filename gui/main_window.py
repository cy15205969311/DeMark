"""
主窗口类 - 现代化界面设计
集成三层架构提取器和实时日志显示
"""
import customtkinter as ctk
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import asyncio
import threading
from typing import Dict, List, Optional
import logging
import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_extractor import ImageExtractor

class MainWindow:
    """
    主窗口类 - 现代化界面设计
    集成三层架构提取器和实时日志显示
    """
    
    def __init__(self):
        # 设置主题
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # 创建主窗口
        self.root = ctk.CTk()
        self.root.title("🎨 多平台图片爬取工具 v2.0 - 基于成功Node.js逻辑")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)
        
        # 设置窗口图标和样式
        try:
            self.root.iconbitmap(default="")  # 可以添加图标文件
        except:
            pass
        
        # 初始化组件
        self.extractor = ImageExtractor()
        self.results = []
        self.is_extracting = False
        
        # 创建界面
        self._create_widgets()
        self._setup_logging()
        
    def _create_widgets(self):
        """创建界面组件"""
        # 主容器
        main_frame = ctk.CTkFrame(self.root)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # 顶部输入区域
        self._create_input_section(main_frame)
        
        # 中间日志区域
        self._create_log_section(main_frame)
        
        # 底部结果区域
        self._create_result_section(main_frame)
        
        # 状态栏
        self._create_status_bar(main_frame)
    
    def _create_input_section(self, parent):
        """创建输入区域"""
        input_frame = ctk.CTkFrame(parent, corner_radius=15)
        input_frame.pack(fill="x", padx=10, pady=10)
        
        # 标题区域
        title_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        title_frame.pack(fill="x", padx=15, pady=(15, 10))
        
        title_label = ctk.CTkLabel(
            title_frame, 
            text="🎯 智能图片提取", 
            font=("Microsoft YaHei UI", 18, "bold"),
            text_color=("#1f538d", "#14375e")
        )
        title_label.pack(side="left")
        
        # URL输入区域
        url_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        url_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        url_label = ctk.CTkLabel(
            url_frame, 
            text="📎 链接输入:", 
            font=("Microsoft YaHei UI", 14, "bold")
        )
        url_label.pack(anchor="w", pady=(0, 8))
        
        # URL输入框和按钮
        url_input_frame = ctk.CTkFrame(url_frame, fg_color="transparent")
        url_input_frame.pack(fill="x", pady=(0, 15))
        
        self.url_entry = ctk.CTkEntry(
            url_input_frame, 
            placeholder_text="🔗 请输入图怪兽、可画、创可贴、抖音或小红书的分享链接...",
            font=("Microsoft YaHei UI", 12),
            height=45,
            corner_radius=10,
            border_width=2
        )
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        self.extract_btn = ctk.CTkButton(
            url_input_frame,
            text="🚀 智能解析",
            command=self._on_extract_click,
            font=("Microsoft YaHei UI", 13, "bold"),
            height=45,
            width=140,
            corner_radius=10,
            hover_color=("#1f538d", "#14375e")
        )
        self.extract_btn.pack(side="right")
        
        # 平台选择区域
        platform_frame = ctk.CTkFrame(input_frame, fg_color="transparent")
        platform_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        platform_title = ctk.CTkLabel(
            platform_frame, 
            text="🎨 支持平台:", 
            font=("Microsoft YaHei UI", 12, "bold")
        )
        platform_title.pack(anchor="w", pady=(0, 8))
        
        # 平台选择按钮组
        platform_buttons_frame = ctk.CTkFrame(platform_frame, fg_color="transparent")
        platform_buttons_frame.pack(fill="x")
        
        self.platform_var = tk.StringVar(value="auto")
        platforms = [
            ("🤖 自动识别", "auto"),
            ("🎨 图怪兽", "818ps"),
            ("🎭 可画", "Canva"),
            ("📐 创可贴", "创可贴"),
            ("🎵 抖音", "抖音"),
            ("📱 小红书", "小红书")
        ]
        
        for i, (text, value) in enumerate(platforms):
            radio = ctk.CTkRadioButton(
                platform_buttons_frame,
                text=text,
                variable=self.platform_var,
                value=value,
                font=("Microsoft YaHei UI", 11),
                radiobutton_width=18,
                radiobutton_height=18
            )
            radio.pack(side="left", padx=(0, 20), pady=5)
    
    def _create_log_section(self, parent):
        """创建日志区域"""
        log_frame = ctk.CTkFrame(parent, corner_radius=15)
        log_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # 日志标题和控制
        log_header = ctk.CTkFrame(log_frame, fg_color="transparent")
        log_header.pack(fill="x", padx=15, pady=(15, 10))
        
        log_title = ctk.CTkLabel(
            log_header, 
            text="📋 实时日志", 
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=("#1f538d", "#14375e")
        )
        log_title.pack(side="left")
        
        # 日志控制按钮
        log_controls = ctk.CTkFrame(log_header, fg_color="transparent")
        log_controls.pack(side="right")
        
        clear_log_btn = ctk.CTkButton(
            log_controls,
            text="🗑️ 清空",
            command=self._clear_log,
            width=80,
            height=30,
            corner_radius=8,
            font=("Microsoft YaHei UI", 10)
        )
        clear_log_btn.pack(side="right", padx=(10, 0))
        
        save_log_btn = ctk.CTkButton(
            log_controls,
            text="💾 保存",
            command=self._save_log,
            width=80,
            height=30,
            corner_radius=8,
            font=("Microsoft YaHei UI", 10)
        )
        save_log_btn.pack(side="right")
        
        # 日志文本区域
        log_text_frame = ctk.CTkFrame(log_frame, corner_radius=10)
        log_text_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
        
        self.log_text = tk.Text(
            log_text_frame,
            bg="#1a1a1a",
            fg="#ffffff",
            font=("Consolas", 10),
            wrap=tk.WORD,
            state=tk.DISABLED,
            relief="flat",
            borderwidth=0,
            insertbackground="#ffffff",
            selectbackground="#404040"
        )
        
        log_scrollbar = ctk.CTkScrollbar(log_text_frame, orientation="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True, padx=10, pady=10)
        log_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)
    
    def _create_result_section(self, parent):
        """创建结果展示区域"""
        result_frame = ctk.CTkFrame(parent, corner_radius=15)
        result_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        # 结果标题和控制
        result_header = ctk.CTkFrame(result_frame, fg_color="transparent")
        result_header.pack(fill="x", padx=15, pady=(15, 10))
        
        result_title = ctk.CTkLabel(
            result_header, 
            text="🎯 提取结果", 
            font=("Microsoft YaHei UI", 16, "bold"),
            text_color=("#1f538d", "#14375e")
        )
        result_title.pack(side="left")
        
        # 结果控制按钮
        result_controls = ctk.CTkFrame(result_header, fg_color="transparent")
        result_controls.pack(side="right")
        
        export_btn = ctk.CTkButton(
            result_controls,
            text="📊 导出",
            command=self._export_results,
            width=80,
            height=30,
            corner_radius=8,
            font=("Microsoft YaHei UI", 10)
        )
        export_btn.pack(side="right", padx=(10, 0))
        
        clear_results_btn = ctk.CTkButton(
            result_controls,
            text="🗑️ 清空",
            command=self._clear_results,
            width=80,
            height=30,
            corner_radius=8,
            font=("Microsoft YaHei UI", 10)
        )
        clear_results_btn.pack(side="right")
        
        # 结果展示区域 (可滚动)
        self.result_scroll_frame = ctk.CTkScrollableFrame(
            result_frame, 
            height=180,
            corner_radius=10,
            scrollbar_button_color=("#1f538d", "#14375e")
        )
        self.result_scroll_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))
    
    def _create_status_bar(self, parent):
        """创建状态栏"""
        status_frame = ctk.CTkFrame(parent, corner_radius=10, height=50)
        status_frame.pack(fill="x", padx=10, pady=(0, 10))
        status_frame.pack_propagate(False)
        
        # 状态信息
        status_info_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        status_info_frame.pack(side="left", fill="both", expand=True, padx=15, pady=10)
        
        self.status_label = ctk.CTkLabel(
            status_info_frame,
            text="🟢 状态: 就绪 | ✅ 成功: 0 | ❌ 失败: 0 | 📊 总计: 0",
            font=("Microsoft YaHei UI", 11),
            anchor="w"
        )
        self.status_label.pack(side="left", fill="x", expand=True)
        
        # 进度条区域
        progress_frame = ctk.CTkFrame(status_frame, fg_color="transparent")
        progress_frame.pack(side="right", padx=15, pady=10)
        
        progress_label = ctk.CTkLabel(
            progress_frame,
            text="进度:",
            font=("Microsoft YaHei UI", 10)
        )
        progress_label.pack(side="left", padx=(0, 8))
        
        self.progress_bar = ctk.CTkProgressBar(
            progress_frame, 
            width=200,
            height=16,
            corner_radius=8,
            progress_color=("#1f538d", "#14375e")
        )
        self.progress_bar.pack(side="right")
        self.progress_bar.set(0)
    
    def _setup_logging(self):
        """设置日志系统"""
        # 创建自定义日志处理器
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
        
        platform = self.platform_var.get()
        
        # 自动识别平台
        if platform == "auto":
            platform = self._detect_platform(url)
        
        # 在后台线程中执行提取
        self.is_extracting = True
        self.extract_btn.configure(text="提取中...", state="disabled")
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
        
        # 创建结果卡片
        self._create_result_card(result)
        
        # 更新状态
        self._update_status()
        
        messagebox.showinfo("成功", "图片提取成功！")
    
    def _on_extract_error(self, error_msg: str):
        """提取失败回调"""
        logging.error(f"❌ 提取失败: {error_msg}")
        messagebox.showerror("提取失败", f"无法提取图片:\n{error_msg}")
        self._update_status()
    
    def _reset_extract_button(self):
        """重置提取按钮"""
        self.is_extracting = False
        self.extract_btn.configure(text="🚀 智能解析", state="normal")
        self.progress_bar.set(0)
    
    def _create_result_card(self, result: Dict):
        """创建结果卡片"""
        card_frame = ctk.CTkFrame(self.result_scroll_frame, corner_radius=12)
        card_frame.pack(fill="x", padx=5, pady=8)
        
        # 主要信息区域
        main_info_frame = ctk.CTkFrame(card_frame, fg_color="transparent")
        main_info_frame.pack(fill="x", padx=15, pady=15)
        
        # 左侧状态图标
        status_frame = ctk.CTkFrame(main_info_frame, width=60, height=60, corner_radius=30)
        status_frame.pack(side="left", padx=(0, 15))
        status_frame.pack_propagate(False)
        
        status_icon = "✅" if result.get('imageUrl') else "❌"
        status_label = ctk.CTkLabel(
            status_frame,
            text=status_icon,
            font=("Microsoft YaHei UI", 24)
        )
        status_label.pack(expand=True)
        
        # 右侧信息区域
        info_frame = ctk.CTkFrame(main_info_frame, fg_color="transparent")
        info_frame.pack(side="left", fill="both", expand=True)
        
        # 平台和来源信息
        platform_source_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        platform_source_frame.pack(fill="x", pady=(0, 8))
        
        platform_label = ctk.CTkLabel(
            platform_source_frame,
            text=f"🎨 {result.get('platform', 'Unknown')}",
            font=("Microsoft YaHei UI", 14, "bold"),
            text_color=("#1f538d", "#14375e")
        )
        platform_label.pack(side="left")
        
        source_label = ctk.CTkLabel(
            platform_source_frame,
            text=f"📡 {result.get('source', 'Unknown')}",
            font=("Microsoft YaHei UI", 11),
            text_color=("gray60", "gray40")
        )
        source_label.pack(side="right")
        
        # URL信息
        url_text = result.get('imageUrl', '')
        if len(url_text) > 80:
            url_text = url_text[:80] + "..."
        
        url_label = ctk.CTkLabel(
            info_frame,
            text=f"🔗 {url_text}",
            font=("Microsoft YaHei UI", 10),
            text_color=("gray70", "gray30"),
            anchor="w"
        )
        url_label.pack(fill="x", pady=(0, 10))
        
        # 操作按钮区域
        btn_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        btn_frame.pack(fill="x")
        
        copy_btn = ctk.CTkButton(
            btn_frame,
            text="📋 复制链接",
            command=lambda: self._copy_url(result.get('imageUrl')),
            width=100,
            height=32,
            corner_radius=8,
            font=("Microsoft YaHei UI", 10),
            hover_color=("#1f538d", "#14375e")
        )
        copy_btn.pack(side="left", padx=(0, 10))
        
        if result.get('imageUrl'):
            preview_btn = ctk.CTkButton(
                btn_frame,
                text="👁️ 预览",
                command=lambda: self._preview_image(result.get('imageUrl')),
                width=80,
                height=32,
                corner_radius=8,
                font=("Microsoft YaHei UI", 10),
                fg_color=("gray70", "gray30"),
                hover_color=("gray60", "gray40")
            )
            preview_btn.pack(side="left", padx=(0, 10))
            
            download_btn = ctk.CTkButton(
                btn_frame,
                text="⬇️ 下载",
                command=lambda: self._download_image(result),
                width=80,
                height=32,
                corner_radius=8,
                font=("Microsoft YaHei UI", 10),
                fg_color=("#2d8f2d", "#1e5f1e"),
                hover_color=("#247a24", "#1a4f1a")
            )
            download_btn.pack(side="left")
    
    def _detect_platform(self, url: str) -> str:
        """自动检测平台"""
        url_lower = url.lower()
        if '818ps.com' in url_lower or 'tuguaishou.com' in url_lower:
            return '818ps'
        elif 'canva.com' in url_lower:
            return 'Canva'
        elif 'chuangkit.com' in url_lower:
            return '创可贴'
        elif 'douyin.com' in url_lower or 'dy.com' in url_lower:
            return '抖音'
        elif 'xiaohongshu.com' in url_lower or 'xhs.com' in url_lower:
            return '小红书'
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
            from tkinter import filedialog
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
            from tkinter import filedialog
            import json
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
            # 清空结果显示区域
            for widget in self.result_scroll_frame.winfo_children():
                widget.destroy()
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
            import webbrowser
            webbrowser.open(url)
    
    def _download_image(self, result: Dict):
        """下载图片"""
        # 这里可以实现图片下载功能
        messagebox.showinfo("提示", "下载功能将在后续版本中实现")
    
    def _update_status(self):
        """更新状态栏"""
        success_count = len([r for r in self.results if r.get('imageUrl')])
        total_count = len(self.results)
        fail_count = total_count - success_count
        
        self.status_label.configure(
            text=f"🟢 状态: 就绪 | ✅ 成功: {success_count} | ❌ 失败: {fail_count} | 📊 总计: {total_count}"
        )
    
    def run(self):
        """运行主窗口"""
        self.root.mainloop()

# 启动应用
if __name__ == "__main__":
    app = MainWindow()
    app.run()