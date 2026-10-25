# Gemini2 体感游戏 Demo

本项目的主要目标是把奥比中光 Gemini2 深度相机应用到体感游戏开发中。项目内包含两个玩法方向：

- `hand_gesture`：手势控制方块移动的参考小游戏。
- 主程序 `main.py`：双人水果对抗小游戏，使用 Gemini2 相机识别双手动作，并结合深度数据做实时调试输出。

当前主程序的游戏规则：

- 两名玩家分别站在画面左半区和右半区。
- 每名玩家有 3 条生命。
- 用手掌侧边，也就是手腕到小拇指指尖这一段，作为切割刀。
- 切到水果得分，切到炸弹扣 1 条生命。
- 每局 60 秒，时间到后得分高的一方获胜。
- 如果时间未到但某一方生命值先耗尽，则该玩家直接失败。

## 推荐设备

核心设备：

- 奥比中光 Gemini2 深度相机
- Windows 电脑
- Python 环境

推荐使用 OpenCV 的 `CAP_OBSENSOR` 后端读取 Gemini2。这个模式可以同时读取彩色图和深度图，延迟更低，也更适合实时体感游戏。

## 安装依赖

在项目目录下打开 PowerShell：

```powershell
cd D:\VScodeStore\PythonProject\体感游戏之二人对抗
pip install -r requirements.txt
```

如果手部识别无法启动，请确认已安装：

```powershell
pip install cvzone mediapipe opencv-python pygame numpy
```

如果使用 Orbbec 官方 SDK 方式，还可以安装：

```powershell
pip install pyorbbecsdk
```

不过本项目优先推荐 `--input obsensor`，不需要先改 SDK 代码。

## Gemini2 启动步骤

1. 连接 Gemini2 相机。
2. 确认相机没有被其他软件占用，例如相机预览工具、OBS、浏览器等。
3. 打开 PowerShell，进入项目目录。
4. 运行主游戏：

```powershell
python main.py --input obsensor --show-fps
```

如果成功，会看到游戏窗口中叠加相机画面，终端会实时打印玩家手部深度数据，例如：

```text
[Depth] P1: 836 mm | P2: 1042 mm
[Depth] P1: -- | P2: 1018 mm
```

说明：

- `P1` 是左半屏玩家。
- `P2` 是右半屏玩家。
- 单位是毫米 `mm`。
- `--` 表示当前没有识别到该玩家的手掌刀，或该位置没有有效深度值。

## 一键运行

项目中提供了 `run_game.bat`，可以双击运行游戏。

如果希望 `.bat` 默认使用 Gemini2 的 OBSENSOR 模式，建议内容保持为：

```bat
python main.py --input obsensor --show-fps
```

如果双击后窗口一闪而过，可以在 PowerShell 中运行它，便于看到报错信息。

## 操作方式

开始界面：

- 点击“开始游戏”按钮，或按空格开始。

游戏中：

- 左侧玩家站在画面左半区。
- 右侧玩家站在画面右半区。
- 伸出手掌，用小拇指到手腕这一侧扫过水果或炸弹。
- `R`：重新开始当前局。
- `Esc`：退出游戏。

游戏结束界面：

- 点击“重新开始”进入新一局。
- 点击“返回开始”回到开始界面。
- 也可以按 `R` 重新开始。

## 常用运行参数

优先使用 Gemini2 OBSENSOR 模式：

```powershell
python main.py --input obsensor
```

显示 FPS，方便观察实时性：

```powershell
python main.py --input obsensor --show-fps
```

全屏运行：

```powershell
python main.py --input obsensor --fullscreen
```

自动选择输入源。程序会先尝试 Gemini2，再尝试其他相机：

```powershell
python main.py --input auto
```

普通 RGB 摄像头备用模式：

```powershell
python main.py --input webcam --camera-index 0
```

键盘调试模式。没有相机时用于测试游戏规则和 UI：

```powershell
python main.py --input keyboard
```

Orbbec 官方 SDK 彩色流模式：

```powershell
python main.py --input orbbec
```

## 深度数据用途

当前版本已经读取 Gemini2 深度图，并在手掌刀中心位置采样深度值，实时输出到终端。

这一步的作用：

- 验证 Gemini2 深度流是否正常。
- 观察玩家手部到相机的距离。
- 为后续优化做准备，例如过滤背景干扰、限制有效交互距离、根据距离调整切割灵敏度。

当前深度采样逻辑在 `pose_input.py` 中：

- 先识别手腕和小拇指指尖。
- 计算手掌刀中心点。
- 将游戏画面坐标映射到深度图坐标。
- 取中心附近 7x7 区域的有效深度中位数。
- 中位数比单个像素更稳定，可以减少深度噪声影响。

## 文件结构

```text
.
├── main.py              # 双人水果对抗小游戏主程序
├── pose_input.py        # 手部识别、手掌刀输入、深度采样
├── camera_backends.py   # Gemini2 / OBSENSOR / 普通摄像头输入封装
├── run_game.bat         # 双击运行脚本
├── requirements.txt     # Python 依赖
└── hand_gesture/        # 手势控制方块移动参考小游戏
```

## 常见问题

### 1. 运行后没有相机画面

优先检查：

- Gemini2 是否已连接。
- 相机是否被其他程序占用。
- 是否使用了正确命令：

```powershell
python main.py --input obsensor
```

如果 OBSENSOR 打不开，可以临时测试普通摄像头模式：

```powershell
python main.py --input webcam --camera-index 0
```

### 2. 终端没有打印深度数据

只有 `--input obsensor` 成功读取到 Gemini2 深度图时，才会打印 `[Depth]`。

如果使用 `webcam`、`keyboard` 或只读取彩色流的 `orbbec` 模式，可能没有深度图，因此不会打印深度数据。

### 3. 手部识别不灵敏

可以尝试：

- 保证手掌在画面中清晰可见。
- 让手和背景有明显区别。
- 两名玩家分别站在左右半屏，避免交叉。
- 使用 `--show-fps` 查看帧率是否过低。

### 4. 中文显示成方框

程序会优先加载 Windows 中文字体。如果仍然显示异常，请确认系统字体目录中存在微软雅黑、黑体、等线或幼圆等中文字体。

## 项目定位

这个 Demo 不是单纯的小游戏，而是 Gemini2 深度相机应用开发展示：

- 使用 Gemini2 获取实时彩色画面。
- 使用 Gemini2 深度图获取玩家手部距离。
- 使用手部识别把人体动作转换成游戏输入。
- 用体感交互完成双人对抗玩法。
- 为后续加入距离过滤、前景分割、多人空间判断等深度相机能力打基础。
