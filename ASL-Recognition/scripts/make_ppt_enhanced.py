#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ASL Pro Studio — 增强版演示 PPT 生成脚本
设计理念：深色科技风 / Dark Tech，配合项目原有的 Apple Blue 主色
参考 PPT Master 设计原则：清晰的视觉层级、统一的色彩系统、充足的留白、
有目的的图片使用、一致的字体比例。
"""

import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import nsmap
from pptx.oxml import parse_xml

# ============================================================
# 画布与配色
# ============================================================
SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)

# 色彩系统
C_BG = RGBColor(0x0B, 0x0F, 0x17)          # 深背景
C_BG_SOFT = RGBColor(0x11, 0x18, 0x24)     # 卡片背景
C_BG_CARD = RGBColor(0x16, 0x1F, 0x2E)     # 稍亮卡片
C_ACCENT = RGBColor(0x00, 0x7A, 0xFF)      # Apple Blue
C_ACCENT_GLOW = RGBColor(0x33, 0x99, 0xFF) # 亮蓝
C_TEAL = RGBColor(0x00, 0xD4, 0xAA)        # 青绿
C_GREEN = RGBColor(0x10, 0xB9, 0x81)       # 成功绿
C_PURPLE = RGBColor(0x8B, 0x5C, 0xF6)      # 紫
C_WHITE = RGBColor(0xFF, 0xFF, 0xFF)
C_TEXT = RGBColor(0xE5, 0xE7, 0xEB)        # 主文字
C_MUTED = RGBColor(0x9C, 0xA3, 0xAF)       # 次要文字
C_DIM = RGBColor(0x6B, 0x72, 0x80)         # 暗淡文字

# 字体
F_HEAD = "Microsoft YaHei"
F_BODY = "Microsoft YaHei"
F_LATIN = "Arial"

# 素材路径
IMG_DIR = r"C:\Users\20229\Desktop\项目图片素材"
OUT_PATH = os.path.join(os.path.expanduser("~"), "Desktop", "ASL_Pro_Studio_展示PPT.pptx")

# ============================================================
# 工具函数
# ============================================================
prs = Presentation()
prs.slide_width = SLIDE_W
prs.slide_height = SLIDE_H


def set_bg(slide, color=C_BG):
    """设置纯色背景"""
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_rect(slide, left, top, width, height, fill_color, line_color=None, line_width=None, radius=0):
    """添加矩形/圆角矩形"""
    if radius:
        shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.adjustments[0] = radius
    else:
        shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    if line_color:
        shape.line.color.rgb = line_color
        shape.line.width = line_width or Pt(1)
    else:
        shape.line.fill.background()
    return shape


def add_line(slide, left, top, width, color, thickness=Pt(2)):
    """添加装饰线"""
    line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, thickness)
    line.fill.solid()
    line.fill.fore_color.rgb = color
    line.line.fill.background()
    return line


def add_text(slide, left, top, width, height, text, font_size, color=C_TEXT,
             bold=False, align=PP_ALIGN.LEFT, font_name=F_HEAD, line_space=1.2):
    """添加文本框"""
    tx = slide.shapes.add_textbox(left, top, width, height)
    tf = tx.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.color.rgb = color
    p.font.bold = bold
    p.font.name = font_name
    p.alignment = align
    p.line_space = line_space
    return tx


def add_bullet_list(slide, left, top, width, height, items, font_size, color=C_TEXT,
                    bullet_color=C_ACCENT, line_space=1.4):
    """添加带项目符号的列表"""
    tx = slide.shapes.add_textbox(left, top, width, height)
    tf = tx.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        p.text = item
        p.font.size = font_size
        p.font.color.rgb = color
        p.font.name = F_BODY
        p.level = 0
        p.space_after = Pt(10)
        # 使用自定义项目符号字符
        p.text = "▸  " + item
        # 设置段落间距
        p.line_space = line_space
        p.space_after = Pt(8)
    return tx


def add_numbered_list(slide, left, top, width, height, items, font_size, color=C_TEXT):
    """添加编号列表"""
    tx = slide.shapes.add_textbox(left, top, width, height)
    tf = tx.text_frame
    tf.word_wrap = True
    for i, item in enumerate(items):
        if i == 0:
            p = tf.paragraphs[0]
        else:
            p = tf.add_paragraph()
        num = f"{i+1:02d}"
        p.text = f"{num}  {item}"
        p.font.size = font_size
        p.font.color.rgb = color
        p.font.name = F_BODY
        p.line_space = 1.35
        p.space_after = Pt(10)
    return tx


def add_section_header(slide, title, subtitle=None):
    """统一的章节标题装饰"""
    # 顶部装饰线
    add_line(slide, Inches(0.8), Inches(0.65), Inches(0.9), C_ACCENT, Pt(3))
    # 标题
    add_text(slide, Inches(0.8), Inches(0.85), Inches(11.5), Inches(0.9),
             title, Pt(40), C_WHITE, bold=True)
    if subtitle:
        add_text(slide, Inches(0.8), Inches(1.45), Inches(11.5), Inches(0.5),
                 subtitle, Pt(18), C_MUTED)


def add_corner_accent(slide):
    """右下角装饰圆形"""
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(12.3), Inches(6.3), Inches(1.5), Inches(1.5))
    circle.fill.solid()
    circle.fill.fore_color.rgb = C_ACCENT
    circle.fill.transparency = 0.92
    circle.line.fill.background()


def add_image(slide, img_path, left, top, width=None, height=None, max_h=None, max_w=None):
    """添加图片并可选限制尺寸"""
    if not os.path.exists(img_path):
        return None
    from PIL import Image as PILImage
    with PILImage.open(img_path) as img:
        w_px, h_px = img.size
    aspect = w_px / h_px

    if width and not height:
        height = width / aspect
    elif height and not width:
        width = height * aspect
    elif not width and not height:
        # 默认宽度
        width = Inches(4)
        height = width / aspect

    if max_h and height > max_h:
        height = max_h
        width = height * aspect
    if max_w and width > max_w:
        width = max_w
        height = width / aspect

    pic = slide.shapes.add_picture(img_path, left, top, width, height)
    return pic


# ============================================================
# 第 1 页：封面
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)

# 背景装饰
add_rect(sl, Inches(0), Inches(0), SLIDE_W, SLIDE_H, C_BG, radius=0)
# 顶部蓝色渐变装饰条
glow = sl.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), SLIDE_W, Inches(0.15))
glow.fill.solid()
glow.fill.fore_color.rgb = C_ACCENT
glow.line.fill.background()

# 左侧大标题
add_text(sl, Inches(0.8), Inches(2.0), Inches(11), Inches(1.2),
         "ASL Pro Studio", Pt(72), C_WHITE, bold=True)
add_text(sl, Inches(0.8), Inches(3.15), Inches(11), Inches(0.7),
         "实时美国手语识别系统", Pt(36), C_ACCENT, bold=True)

# 副标题
add_text(sl, Inches(0.8), Inches(4.0), Inches(9.5), Inches(0.8),
         "Face ID · 个性化快捷词 · LLM 智能格式化 · 深度活体检测",
         Pt(22), C_TEXT)

# 装饰线
add_line(sl, Inches(0.8), Inches(5.0), Inches(2.5), C_ACCENT, Pt(3))

# 底部信息
add_text(sl, Inches(0.8), Inches(5.3), Inches(9), Inches(0.6),
         "基于计算机视觉的端到端手语沟通辅助平台",
         Pt(18), C_MUTED)
add_text(sl, Inches(0.8), Inches(6.5), Inches(9), Inches(0.5),
         "2026 项目展示", Pt(14), C_DIM)

# 右侧装饰大圆环
for r, alpha in [(2.8, 0.08), (2.3, 0.12), (1.8, 0.16)]:
    c = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(10.5), Inches(2.0), Inches(r), Inches(r))
    c.fill.solid()
    c.fill.fore_color.rgb = C_ACCENT
    c.fill.transparency = 1 - alpha
    c.line.fill.background()

# ============================================================
# 第 2 页：项目背景
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "项目背景", "Project Background")

# 左侧大数字卡片
add_rect(sl, Inches(0.8), Inches(2.3), Inches(3.5), Inches(4.0), C_BG_CARD, radius=0.1)
add_text(sl, Inches(1.0), Inches(2.5), Inches(3.1), Inches(0.8),
         "沟通鸿沟", Pt(20), C_MUTED)
add_text(sl, Inches(1.0), Inches(3.2), Inches(3.1), Inches(1.2),
         "70M+", Pt(52), C_ACCENT, bold=True)
add_text(sl, Inches(1.0), Inches(4.5), Inches(3.1), Inches(1.6),
         "全球听障人士数量庞大，而健听人群普遍不懂手语，日常沟通存在显著障碍。",
         Pt(16), C_TEXT, line_space=1.3)

# 右侧内容
items = [
    "手语是听障人士的主要沟通方式，但学习门槛高、普及率低",
    "传统文字输入在移动场景下效率低，无法支持自然流畅交流",
    "现有 ASL 识别工具多缺乏身份认证、个性化与上下文理解能力",
    "本项目旨在构建一个实时、准确、安全且可个性化的手语识别平台"
]
add_bullet_list(sl, Inches(4.8), Inches(2.4), Inches(7.6), Inches(4.2), items, Pt(22), C_TEXT)

# 底部装饰
add_line(sl, Inches(4.8), Inches(6.5), Inches(7.6), C_BG_CARD, Pt(1))
add_text(sl, Inches(4.8), Inches(6.65), Inches(7.6), Inches(0.4),
         "核心目标：让手语识别像语音输入一样自然可用",
         Pt(16), C_TEAL, bold=True)

# ============================================================
# 第 3 页：核心能力
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "核心能力", "Core Capabilities")

# 4 个能力卡片
cards = [
    ("实时手语识别", "24 个静态字母 + J/Z 动态追踪，66fps 采集，40Hz 状态推送", C_ACCENT),
    ("Face ID 认证", "DeepFace + MTCNN + 深度相机活体检测，多帧投票制登录", C_TEAL),
    ("个性化快捷词", "A-Z 自定义映射，单字母展开完整短语，登录用户私有词库", C_PURPLE),
    ("LLM 智能成句", "DeepSeek-V4 将拼写单词格式化为自然英语句子", C_GREEN),
]

for i, (title, desc, color) in enumerate(cards):
    row = i // 2
    col = i % 2
    x = Inches(0.8 + col * 6.0)
    y = Inches(2.3 + row * 2.3)
    add_rect(sl, x, y, Inches(5.6), Inches(1.9), C_BG_CARD, radius=0.08)
    # 顶部色条
    add_rect(sl, x, y, Inches(5.6), Inches(0.08), color, radius=0)
    add_text(sl, x + Inches(0.25), y + Inches(0.25), Inches(5.1), Inches(0.5),
             title, Pt(24), C_WHITE, bold=True)
    add_text(sl, x + Inches(0.25), y + Inches(0.85), Inches(5.1), Inches(0.9),
             desc, Pt(17), C_MUTED, line_space=1.3)

# ============================================================
# 第 4 页：系统架构
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "系统架构", "System Architecture")

# 放置架构图
add_image(sl, os.path.join(IMG_DIR, "arch_drawn.png"),
          left=Inches(0.7), top=Inches(1.9), max_w=Inches(12.0), max_h=Inches(5.0))

# 底部图例
add_text(sl, Inches(0.8), Inches(6.9), Inches(12), Inches(0.4),
         "前端 HTML5 Canvas + WebSocket  ↔  后端 FastAPI + MediaPipe + Keras + DeepFace",
         Pt(15), C_DIM, align=PP_ALIGN.CENTER)

# ============================================================
# 第 5 页：识别流水线
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "核心识别流水线", "Recognition Pipeline")

# 放置流水线图
add_image(sl, os.path.join(IMG_DIR, "pipe_drawn.png"),
          left=Inches(0.5), top=Inches(1.8), max_w=Inches(12.3), max_h=Inches(4.8))

# 底部关键参数
params = [
    "稳定帧 STABLE=15",
    "动态窗 DYNAMIC=45",
    "置信度 ≥0.80",
    "单词超时 90 帧",
    "断句超时 8s",
]
for i, p in enumerate(params):
    x = Inches(0.8 + i * 2.45)
    add_rect(sl, x, Inches(6.75), Inches(2.2), Inches(0.42), C_BG_CARD, radius=0.05)
    add_text(sl, x, Inches(6.78), Inches(2.2), Inches(0.4), p, Pt(13), C_TEXT, align=PP_ALIGN.CENTER)

# ============================================================
# 第 6 页：手部关键点检测
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "手部关键点检测", "Hand Landmark Detection")

# 左侧图片
add_image(sl, os.path.join(IMG_DIR, "mediapipe-hand-landmarks.png"),
          left=Inches(0.7), top=Inches(2.0), max_w=Inches(7.0), max_h=Inches(4.8))

# 右侧说明
add_text(sl, Inches(8.0), Inches(2.2), Inches(4.8), Inches(0.6),
         "MediaPipe Hand Landmarker", Pt(26), C_WHITE, bold=True)
items = [
    "提取手部 21 个 3D 关键点 (x, y, z)",
    "自动 GPU 优先，失败降级 CPU",
    "关键点按边界框归一化到 [0,1]",
    "取 (x, y) 送入 Keras 分类器",
    "几何规则二次修正易混淆字母"
]
add_bullet_list(sl, Inches(8.0), Inches(2.9), Inches(4.8), Inches(3.5), items, Pt(18), C_TEXT)

# 右侧底部高亮
add_rect(sl, Inches(8.0), Inches(6.2), Inches(4.8), Inches(0.7), C_BG_CARD, radius=0.05)
add_text(sl, Inches(8.15), Inches(6.35), Inches(4.5), Inches(0.5),
         "易混淆: D/I, F/W, K/V/U, A/T/S, C/E/O, M/N",
         Pt(15), C_ACCENT, bold=True)

# ============================================================
# 第 7 页：动态 J/Z 追踪
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "动态 J/Z 手势追踪", "Dynamic Gesture Tracking")

# 两个说明卡片
add_rect(sl, Inches(0.8), Inches(2.2), Inches(5.8), Inches(2.4), C_BG_CARD, radius=0.08)
add_rect(sl, Inches(0.8), Inches(2.2), Inches(5.8), Inches(0.08), C_ACCENT)
add_text(sl, Inches(1.0), Inches(2.45), Inches(5.4), Inches(0.5), "J 识别", Pt(24), C_WHITE, bold=True)
add_text(sl, Inches(1.0), Inches(3.05), Inches(5.4), Inches(1.4),
         "手部先向下移动 (S)，再向左/上钩 (W/NW)。\n追踪食指方向序列，匹配 S→W/NW 模式。",
         Pt(17), C_MUTED, line_space=1.4)

add_rect(sl, Inches(6.8), Inches(2.2), Inches(5.8), Inches(2.4), C_BG_CARD, radius=0.08)
add_rect(sl, Inches(6.8), Inches(2.2), Inches(5.8), Inches(0.08), C_TEAL)
add_text(sl, Inches(7.0), Inches(2.45), Inches(5.4), Inches(0.5), "Z 识别", Pt(24), C_WHITE, bold=True)
add_text(sl, Inches(7.0), Inches(3.05), Inches(5.4), Inches(1.4),
         "手部做 Z 字形运动。\n追踪食指方向序列，匹配 E→SW→E 模式。",
         Pt(17), C_MUTED, line_space=1.4)

# 下方流程
flow_items = [
    "I/D 稳定 15 帧 → 进入动态追踪模式",
    "45 帧观察窗内检测方向序列",
    "运动门控：目标手指位移 > threshold 且 > ratio 倍其他手指",
    "失败回退：观察窗耗尽未检测到 → 回退为 I/D"
]
add_bullet_list(sl, Inches(0.8), Inches(5.0), Inches(11.8), Inches(1.8), flow_items, Pt(20), C_TEXT)

# ============================================================
# 第 8 页：Face ID 认证系统
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "Face ID 认证系统", "Face Authentication")

# 左侧流程
steps = [
    ("人脸检测", "MTCNN 级联网络 + 无效框过滤", C_ACCENT),
    ("光照归一化", "CLAHE 在 LAB 空间 L 通道增强", C_TEAL),
    ("特征提取", "DeepFace Facenet 128 维 embedding", C_PURPLE),
    ("活体检测", "深度相机 ROI 深度标准差 > 5mm", C_GREEN),
    ("匹配登录", "多帧投票 + 平均余弦距离阈值 0.40", C_ACCENT),
]
for i, (title, desc, color) in enumerate(steps):
    y = Inches(2.2 + i * 0.95)
    # 编号圆
    c = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(0.85), y + Inches(0.05), Inches(0.55), Inches(0.55))
    c.fill.solid()
    c.fill.fore_color.rgb = color
    c.line.fill.background()
    add_text(sl, Inches(0.85), y + Inches(0.12), Inches(0.55), Inches(0.45),
             str(i+1), Pt(18), C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(sl, Inches(1.6), y, Inches(4.5), Inches(0.4), title, Pt(20), C_WHITE, bold=True)
    add_text(sl, Inches(1.6), y + Inches(0.42), Inches(4.5), Inches(0.4), desc, Pt(15), C_MUTED)

# 右侧安全机制卡片
add_rect(sl, Inches(6.6), Inches(2.2), Inches(6.0), Inches(4.6), C_BG_CARD, radius=0.08)
add_text(sl, Inches(6.85), Inches(2.45), Inches(5.5), Inches(0.5),
         "安全机制", Pt(24), C_WHITE, bold=True)
sec_items = [
    "距离检测：有效范围 30-120cm，超出拒绝",
    "人脸框过大 (>85%) 或过小 (≤30px) 拒识",
    "人脸中心靠近画面边缘拒识",
    "平面照片/屏幕攻击 STD<5mm → 拒绝",
    "登录最多 5 次重试，注册最多 12 次"
]
add_bullet_list(sl, Inches(6.85), Inches(3.1), Inches(5.5), Inches(3.5), sec_items, Pt(17), C_TEXT)

# ============================================================
# 第 9 页：个性化快捷词
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "个性化快捷词系统", "Personalized Shortcuts")

# 流程图
flow = [
    ("登录", "Face ID 认证成功"),
    ("开启", "侧边栏 Toggle 开关"),
    ("配置", "A-Z 自定义映射"),
    ("触发", "手势/Chip 点击"),
    ("展开", "单字母 → 完整短语"),
    ("成句", "LLM 自然语句格式化"),
]
for i, (title, desc) in enumerate(flow):
    x = Inches(0.7 + i * 2.05)
    # 卡片
    add_rect(sl, x, Inches(2.2), Inches(1.85), Inches(1.6), C_BG_CARD, radius=0.06)
    add_text(sl, x, Inches(2.35), Inches(1.85), Inches(0.45), title, Pt(18), C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(sl, x, Inches(2.85), Inches(1.85), Inches(0.8), desc, Pt(12), C_MUTED, align=PP_ALIGN.CENTER, line_space=1.2)
    if i < len(flow) - 1:
        # 箭头
        add_text(sl, x + Inches(1.8), Inches(2.85), Inches(0.4), Inches(0.4), "→", Pt(24), C_ACCENT, bold=True, align=PP_ALIGN.CENTER)

# 示例
add_text(sl, Inches(0.8), Inches(4.2), Inches(3), Inches(0.4), "使用示例", Pt(20), C_WHITE, bold=True)
examples = [
    ("A", "Hello", "你好"),
    ("D", "Doctor", "我需要医生"),
    ("H", "Help", "我需要帮助"),
    ("W", "Water", "我想喝水"),
]
for i, (key, phrase, cn) in enumerate(examples):
    x = Inches(0.8 + i * 3.1)
    add_rect(sl, x, Inches(4.7), Inches(2.8), Inches(1.6), C_BG_CARD, radius=0.08)
    # 字母徽章
    b = sl.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.2), Inches(4.85), Inches(0.55), Inches(0.55))
    b.fill.solid()
    b.fill.fore_color.rgb = C_ACCENT
    b.line.fill.background()
    add_text(sl, x + Inches(0.2), Inches(4.92), Inches(0.55), Inches(0.45), key, Pt(22), C_WHITE, bold=True, align=PP_ALIGN.CENTER)
    add_text(sl, x + Inches(0.9), Inches(4.9), Inches(1.7), Inches(0.45), phrase, Pt(18), C_WHITE, bold=True)
    add_text(sl, x + Inches(0.9), Inches(5.35), Inches(1.7), Inches(0.4), cn, Pt(14), C_MUTED)

# 底部说明
add_text(sl, Inches(0.8), Inches(6.6), Inches(12), Inches(0.4),
         "数据持久化：shortcuts.json（用户级）+ threading.Lock 并发保护",
         Pt(15), C_DIM)

# ============================================================
# 第 10 页：前端 UI 设计
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "前端交互界面", "Frontend UI")

# 左侧：UI 区域说明
ui_zones = [
    ("实时视频区", "Canvas 渲染 + 手部骨架叠加", C_ACCENT),
    ("动作捕获面板", "当前字母、置信度、停留进度", C_TEAL),
    ("句子翻译区", "原始拼写 + LLM 格式化结果", C_PURPLE),
    ("侧边栏控制", "Face ID、快捷词、参数滑块", C_GREEN),
]
for i, (title, desc, color) in enumerate(ui_zones):
    y = Inches(2.2 + i * 1.15)
    add_rect(sl, Inches(0.8), y, Inches(0.12), Inches(0.5), color)
    add_text(sl, Inches(1.05), y, Inches(4.5), Inches(0.4), title, Pt(20), C_WHITE, bold=True)
    add_text(sl, Inches(1.05), y + Inches(0.42), Inches(4.5), Inches(0.4), desc, Pt(15), C_MUTED)

# 右侧：模拟 UI 面板
add_rect(sl, Inches(6.0), Inches(2.0), Inches(6.8), Inches(4.8), C_BG_CARD, radius=0.1)
# 顶部栏
add_rect(sl, Inches(6.0), Inches(2.0), Inches(6.8), Inches(0.5), C_BG_SOFT, radius=0.1)
add_text(sl, Inches(6.2), Inches(2.08), Inches(3), Inches(0.4), "实时识别系统", Pt(14), C_WHITE, bold=True)
# 视频区
add_rect(sl, Inches(6.2), Inches(2.7), Inches(4.0), Inches(2.4), RGBColor(0,0,0), radius=0.05)
add_text(sl, Inches(7.2), Inches(3.65), Inches(2.0), Inches(0.5), "Video", Pt(18), C_DIM, align=PP_ALIGN.CENTER)
# 侧边信息
add_rect(sl, Inches(10.4), Inches(2.7), Inches(2.2), Inches(1.1), C_BG_SOFT, radius=0.05)
add_text(sl, Inches(10.55), Inches(2.85), Inches(1.9), Inches(0.3), "当前字母", Pt(11), C_MUTED)
add_text(sl, Inches(10.55), Inches(3.15), Inches(1.9), Inches(0.5), "H", Pt(36), C_ACCENT, bold=True)
add_rect(sl, Inches(10.4), Inches(3.95), Inches(2.2), Inches(1.15), C_BG_SOFT, radius=0.05)
add_text(sl, Inches(10.55), Inches(4.1), Inches(1.9), Inches(0.3), "已识别", Pt(11), C_MUTED)
add_text(sl, Inches(10.55), Inches(4.35), Inches(1.9), Inches(0.5), "HEL", Pt(18), C_WHITE, bold=True)
# 底部翻译
add_rect(sl, Inches(6.2), Inches(5.3), Inches(6.4), Inches(1.2), C_BG_SOFT, radius=0.05)
add_text(sl, Inches(6.35), Inches(5.45), Inches(3), Inches(0.3), "当前输入", Pt(11), C_MUTED)
add_text(sl, Inches(6.35), Inches(5.75), Inches(6), Inches(0.4), "HELLO", Pt(22), C_WHITE, bold=True)
add_text(sl, Inches(6.35), Inches(6.15), Inches(6), Inches(0.3), "Hello, nice to meet you.", Pt(13), C_TEAL)

# ============================================================
# 第 11 页：模型训练
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "模型训练与调优", "Model Training")

# 左侧训练曲线
add_image(sl, os.path.join(IMG_DIR, "training-and-validation-accuracy-and-loss.png"),
          left=Inches(0.7), top=Inches(2.0), max_w=Inches(6.0), max_h=Inches(4.6))

# 右侧说明
add_text(sl, Inches(7.0), Inches(2.2), Inches(5.8), Inches(0.5),
         "训练配置", Pt(24), C_WHITE, bold=True)
config_items = [
    "模型：Keras 全连接分类网络 (model5.keras)",
    "输入：21 个手部关键点归一化后的 (x, y) 坐标",
    "输出：24 个静态字母类别 (A-Y，不含 J/Z)",
    "损失函数：Categorical Crossentropy",
    "优化器：Adam，学习率调度",
    "数据增强：多 batch/epoch 超参对比实验"
]
add_bullet_list(sl, Inches(7.0), Inches(2.8), Inches(5.8), Inches(3.5), config_items, Pt(17), C_TEXT)

# 底部 batch 对比
add_text(sl, Inches(0.8), Inches(6.7), Inches(12), Inches(0.4),
         "实验对比：BATCH_32/64/128 × EPOCH_20/100 × LR_0.001/0.0005/0.0001",
         Pt(15), C_DIM, align=PP_ALIGN.CENTER)

# ============================================================
# 第 12 页：混淆矩阵
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "识别效果评估", "Evaluation Results")

# 左侧混淆矩阵
add_image(sl, os.path.join(IMG_DIR, "Confusion Matrix.png"),
          left=Inches(0.5), top=Inches(1.9), max_w=Inches(6.4), max_h=Inches(5.0))

# 右侧指标
add_text(sl, Inches(7.2), Inches(2.2), Inches(5.6), Inches(0.5),
         "性能表现", Pt(24), C_WHITE, bold=True)

metrics = [
    ("整体准确率", "> 95%", "对角线集中，分类置信度高"),
    ("易混淆对", "D/I, K/V/U", "通过几何规则二次修正"),
    ("动态字母", "J/Z", "方向序列匹配补充静态模型"),
    ("实时性", "66fps", "MediaPipe GPU + 轻量分类器"),
]
for i, (label, value, note) in enumerate(metrics):
    y = Inches(2.9 + i * 1.05)
    add_text(sl, Inches(7.2), y, Inches(2.8), Inches(0.4), label, Pt(16), C_MUTED)
    add_text(sl, Inches(7.2), y + Inches(0.35), Inches(2.0), Inches(0.55), value, Pt(32), C_ACCENT, bold=True)
    add_text(sl, Inches(9.4), y + Inches(0.42), Inches(3.4), Inches(0.4), note, Pt(15), C_TEXT)

# ============================================================
# 第 13 页：关键问题与解决方案
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "关键问题与解决方案", "Challenges & Solutions")

challenges = [
    ("闭包作用域陷阱", "send_loop 嵌套函数赋值全局变量缺少 global 声明，快捷词系统失效", "显式声明 global 修复模块级状态"),
    ("登录匹配误判", "最低距离制易被偶然低距离翻盘", "改为多帧投票 + 平均距离平票裁决"),
    ("Stale 帧覆盖登录态", "current_state 在 auth_result 后到达，覆盖 _loggedInUser", "result handler 增加 null 防护"),
    ("光照差异影响识别", "宿舍暗光 vs 实验室亮光导致 embedding 偏移", "注册/登录均引入 CLAHE 光照归一化"),
    ("快捷词与登录态耦合", "_loggedInUser 设置依赖 shortcuts 字段", "解耦为两个独立分支设置"),
]
for i, (title, problem, solution) in enumerate(challenges):
    row = i // 2
    col = i % 2
    x = Inches(0.7 + col * 6.1)
    y = Inches(2.15 + row * 2.45)
    add_rect(sl, x, y, Inches(5.8), Inches(2.25), C_BG_CARD, radius=0.08)
    add_text(sl, x + Inches(0.2), y + Inches(0.15), Inches(5.4), Inches(0.45), title, Pt(18), C_WHITE, bold=True)
    add_text(sl, x + Inches(0.2), y + Inches(0.62), Inches(5.4), Inches(0.55),
             f"问题：{problem}", Pt(13), C_MUTED, line_space=1.2)
    add_text(sl, x + Inches(0.2), y + Inches(1.35), Inches(5.4), Inches(0.7),
             f"解决：{solution}", Pt(14), C_TEAL, bold=True, line_space=1.2)

# ============================================================
# 第 14 页：演示流程
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "演示流程", "Demo Flow")

steps_demo = [
    "启动 FastAPI 服务，浏览器访问 localhost:8765",
    "人脸注册：输入用户名 → 10 秒多角度采集 → 5 帧融合",
    "人脸登录：3 秒倒计时 → DeepFace 匹配 → 投票确认 → Welcome",
    "开启快捷词模式，侧边栏显示用户私有 Chip 面板",
    "手语输入：比划字母 → 稳定确认 → 空格提交 → 拼写纠错",
    "快捷词触发：比划 A 自动展开为 Hello",
    "LLM 成句：连续输入多个单词，自动格式化为自然语句"
]
add_numbered_list(sl, Inches(0.8), Inches(2.2), Inches(12.0), Inches(4.5), steps_demo, Pt(20), C_TEXT)

# 底部提示
add_rect(sl, Inches(0.8), Inches(6.55), Inches(12.0), Inches(0.55), C_BG_CARD, radius=0.05)
add_text(sl, Inches(1.0), Inches(6.65), Inches(11.6), Inches(0.4),
         "预期效果：实验室登录准确率 95%+，CLAHE 优化后宿舍环境准确率明显提升",
         Pt(16), C_TEAL, bold=True, align=PP_ALIGN.CENTER)

# ============================================================
# 第 15 页：未来展望
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)
add_section_header(sl, "未来展望", "Future Roadmap")

roadmap = [
    ("多环境注册融合", "采集不同光照/角度样本，平均 embedding 提高鲁棒性", "短期"),
    ("模型轻量化", "TensorFlow Lite 替代 Keras，降低资源依赖", "短期"),
    ("中文手语 CSL", "中文手语数据集 + 新分类模型", "中期"),
    ("移动端适配", "WebRTC + React Native 前端", "中期"),
    ("连续手语识别", "LSTM / Transformer 序列模型，词组级识别", "中期"),
    ("TTS 语音输出", "文字转语音，完成无障碍沟通闭环", "中期"),
    ("云端部署", "Docker + Azure App Service 公网访问", "长期"),
    ("历史记录分析", "识别日志持久化 + 统计 + 模型迭代", "长期"),
]
for i, (title, desc, phase) in enumerate(roadmap):
    col = i // 4
    row = i % 4
    x = Inches(0.7 + col * 6.1)
    y = Inches(2.1 + row * 1.25)
    color = C_ACCENT if phase == "短期" else (C_TEAL if phase == "中期" else C_PURPLE)
    # 时间标签
    add_rect(sl, x, y, Inches(0.9), Inches(0.38), color, radius=0.03)
    add_text(sl, x, y + Inches(0.03), Inches(0.9), Inches(0.35), phase, Pt(11), C_WHITE, align=PP_ALIGN.CENTER)
    add_text(sl, x + Inches(1.05), y, Inches(3.5), Inches(0.38), title, Pt(17), C_WHITE, bold=True)
    add_text(sl, x + Inches(1.05), y + Inches(0.38), Inches(3.9), Inches(0.4), desc, Pt(13), C_MUTED, line_space=1.2)

# ============================================================
# 第 16 页：致谢
# ============================================================
sl = prs.slides.add_slide(prs.slide_layouts[6])
set_bg(sl)

# 装饰
for r, alpha in [(3.5, 0.05), (2.8, 0.08), (2.1, 0.12)]:
    c = sl.shapes.add_shape(MSO_SHAPE.OVAL, Inches(5.0), Inches(1.0), Inches(r), Inches(r))
    c.fill.solid()
    c.fill.fore_color.rgb = C_ACCENT
    c.fill.transparency = 1 - alpha
    c.line.fill.background()

add_text(sl, Inches(0), Inches(2.6), SLIDE_W, Inches(1.0),
         "谢谢观看", Pt(64), C_WHITE, bold=True, align=PP_ALIGN.CENTER)
add_text(sl, Inches(0), Inches(3.75), SLIDE_W, Inches(0.7),
         "ASL Pro Studio — 让手语沟通更自然", Pt(28), C_ACCENT, align=PP_ALIGN.CENTER)
add_text(sl, Inches(0), Inches(4.6), SLIDE_W, Inches(0.5),
         "Face ID · 个性化快捷词 · LLM 智能格式化 · 活体检测",
         Pt(18), C_MUTED, align=PP_ALIGN.CENTER)

add_line(sl, Inches(5.5), Inches(5.5), Inches(2.3), C_ACCENT, Pt(3))
add_text(sl, Inches(0), Inches(5.8), SLIDE_W, Inches(0.4),
         "欢迎提问与交流", Pt(16), C_DIM, align=PP_ALIGN.CENTER)

# ============================================================
# 保存
# ============================================================
prs.save(OUT_PATH)
print(f"PPT 已保存到: {OUT_PATH}")
