# ASL 手语识别与翻译 — GitHub 开源项目调研总结

> 调研时间：2026-07-24  
> 涵盖：开源模型、数据集、框架、论文索引

---

## 一、综合框架 / 完整软件

| 项目 | 星数 | 简介 |
|------|------|------|
| [sign/translate](https://github.com/sign/translate) | 779 | sign.mt — 实时手语翻译 PWA 应用，支持 Android/iOS/Web，涵盖手语识别和手语生成 |
| [sign-language-translator/sign-language-translator](https://github.com/sign-language-translator/sign-language-translator) | 361 | Python 手语翻译框架库，支持自定义文本↔手语翻译器，集成 MediaPipe 姿态提取、语言模型等 |

---

## 二、实时识别 / 翻译系统

| 项目 | 星数 | 简介 |
|------|------|------|
| [BelalC/sign2text](https://github.com/BelalC/sign2text) | 163 | 实时 AI 手语 26 字母手指拼写识别，OpenCV + 迁移学习 (VGG16/ResNet/MobileNet)，需摄像头 |
| [emnikhil/Sign-Language-To-Text-Conversion](https://github.com/emnikhil/Sign-Language-To-Text-Conversion) | 356 | 实时 ASL 手语转文字系统，CNN + OpenCV，带 tkinter GUI，98% 字母识别准确率 |

---

## 三、高星竞赛方案 / 论文模型

| 项目 | 星数 | 简介 |
|------|------|------|
| [ChristofHenkel/kaggle-asl-fingerspelling-1st-place-solution](https://github.com/ChristofHenkel/kaggle-asl-fingerspelling-1st-place-solution) | 176 | Google ASL 手指拼写识别 Kaggle 第1名，SqueezeFormer + Transformer 解码器，PyTorch→TFLite 完整流程 |
| [neccam/nslt](https://github.com/neccam/nslt) | 156 | Neural Sign Language Translation (CVPR 2018) — 经典视频→英语翻译方案 |
| [kayoyin/transformer-slt](https://github.com/kayoyin/transformer-slt) | 158 | STMC-Transformer (COLING 2020)，基于 Transformer 的手语翻译，PHOENIX 数据集 SOTA |
| [DEV-D-GR8/SignSense](https://github.com/DEV-D-GR8/SignSense) | 18 | 基于 Transformer 的实时 ASL 识别 |

---

## 四、数据集

| 项目 / 名称 | 简介 |
|-------------|------|
| [chevalierNoir/OpenASL](https://github.com/chevalierNoir/OpenASL) | OpenASL — 大规模开放域 ASL-英语翻译数据集 (EMNLP 2022)，220 签名者，98,417 视频片段 |
| [microsoft/ASL-citizen-code](https://github.com/microsoft/ASL-citizen-code) | 微软 ASL Citizen 数据集代码与基线 |
| [asnsams/Video-Sign-Language-Dateset](https://github.com/asnsams/Video-Sign-Language-Dateset) | 手语数据集汇总表，含 17+ 种语言的词级视频数据集链接 |
| WLASL | [https://github.com/dxli94/WLASL](https://github.com/dxli94/WLASL) — 2000 词类，21,083 视频 |
| MS-ASL | [https://github.com/microsoft/MS-ASL](https://github.com/microsoft/MS-ASL) — 1000 词类 |
| YouTube-ASL | Google Research — 大规模，984 小时，开源域 ASL 平行语料 |
| How2Sign | [https://how2sign.github.io/](https://how2sign.github.io/) — 多模态连续 ASL |

---

## 五、论文/资源索引 (Awesome Lists)

| 项目 | 星数 | 简介 |
|------|------|------|
| [VIPL-SLP/Awesome-Sign-Language-Processing](https://github.com/VIPL-SLP/Awesome-Sign-Language-Processing) | 256 | 最全 — 收录 SLR/SLT/SLP 顶会论文 + 21 个数据集汇总表 |
| [ZechengLi19/Awesome-Sign-Language](https://github.com/ZechengLi19/Awesome-Sign-Language) | 221 | 手语论文分类列表 (ISLR / CSLR / SLT / SLP)，含数据集链接和年份分类 |

---

## 六、本地部署可行性评估

### 可直接 pip install / clone 即用

| 项目 | 方式 | 说明 |
|------|------|------|
| **sign-language-translator** | `pip install sign-language-translator` | 内置巴基斯坦手语 776 手势数据，自动下载；手语→文本模块尚未就绪 |
| **sign2text** | clone + `pip install -r requirements.txt` | 含预训练权重，直接摄像头识别 26 字母；CPU 可跑，准确率约 70-85% (实时) |
| **emnikhil/Sign-Language-To-Text-Conversion** | clone + 需要自己录数据 | 无预训练模型和数据，需手动用摄像头录制 A-Z 手势后训练 |

### 需要 GPU / 复杂配置 (不推荐本地)

| 项目 | 原因 |
|------|------|
| sign/translate | Angular+Ionic+Firebase 全栈应用，面向生产 |
| kaggle-1st-place | 需 Docker + NVIDIA GPU 容器 |
| nslt (CVPR 2018) | Python 2.7 + TF 1.3，已过时 |
| transformer-slt | 需下载 PHOENIX 数据集 + 完整训练 pipeline |

---

## 七、数据需求与训练时间估计

| 场景 | 硬件 | 预计时间 |
|------|------|----------|
| 简单字母分类 (CNN，26 字母，公开数据集) | CPU | 几小时 ~ 1 天 |
| 简单字母分类 (CNN，26 字母，自己录数据) | CPU | 数据采集半天 + 训练几小时 |
| 词级孤立手语识别 (如 WLASL/MS-ASL) | GPU | 1 ~ 3 天 |
| 连续手语翻译 (视频→句子) | GPU (A100) | 数天 ~ 数周 |
| 从头构建完整 ASL 翻译器 | GPU + 大量标注 | 数周 ~ 数月 |

**关键瓶颈不是训练速度，而是数据准备**：自己录制标注数据占 80% 时间，使用公开数据集可大幅缩短。

---

## 八、快速上手建议

| 目标 | 推荐方案 |
|------|----------|
| 快速体验手语翻译概念 | `pip install sign-language-translator` |
| 摄像头实时识别字母 | clone `sign2text`，`python live_demo.py -m MobileNet` |
| 做学术论文 | 读 Awesome-Sign-Language-Processing，选最新方案复现 |
| 做 ASL 产品 | 使用 WLASL/MS-ASL/OpenASL 公开数据集 + 研究级模型 |
