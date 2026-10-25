# 体感游戏（Motion Sensing Game）

基于 Orbbec 深度相机的两个体感游戏，原项目来自深圳大学创新短课。

- `hand_gesture/` — 积木拼搭：握拳抓取、张手释放
- `双人切水果游戏/` — 双人水果对抗：手掌刀切割

## Windows 复现

依赖：`pip install pygame opencv-python mediapipe numpy cvzone pyorbbecsdk2`

切水果：`cd 双人切水果游戏` 然后 `python apply_rgbd_patch.py`、`python main.py --input orbbec --show-fps`

积木拼搭：`cd hand_gesture` 然后 `python apply_blocks_patch.py`、`python main.py`

详细步骤见《体感游戏 · Windows 复现手册》。
