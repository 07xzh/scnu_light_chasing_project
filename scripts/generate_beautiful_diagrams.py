import os
import time

html_content = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Architecture</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            background: linear-gradient(135deg, #0f172a, #1e1b4b);
            color: white;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .mermaid {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
            backdrop-filter: blur(16px);
        }
    </style>
</head>
<body>

<div class="mermaid" id="arch">
%%{init: {'theme': 'base', 'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#f8fafc',
    'primaryBorderColor': '#3b82f6',
    'lineColor': '#60a5fa',
    'secondaryColor': '#0f172a',
    'tertiaryColor': '#1e293b',
    'clusterBkg': 'rgba(255,255,255,0.03)',
    'clusterBorder': '#475569',
    'fontSize': '18px',
    'fontFamily': 'Inter, -apple-system, sans-serif',
    'nodeBorder': '2px'
}}}%%
flowchart TD
    subgraph Frontend [前端 UI 层 (HTML5 / Canvas)]
        canvas[Canvas 渲染]
        gesture[手势捕获面板]
        trans[句子翻译区]
        side[控制侧边栏]
    end

    subgraph Backend [后端逻辑层 (FastAPI)]
        cam[camera_loop (66fps独立线程)]
        ws[ws_endpoint (async通信)]
        send[send_loop (40Hz高频推送)]
        
        pipe[HandASLPipeline (MediaPipe+Keras)]
        sub[submit_word() (业务逻辑)]
        state((Global State 核心状态机))
        
        spell[SpellChecker 纠错]
        short[ShortcutManager 快捷词]
        llm[DeepSeek API 大模型]
        auth[Face Auth 活体认证]
    end

    canvas <-->|WebSocket 二进制流| ws
    gesture <-->|WebSocket JSON| ws
    trans <-->|WebSocket JSON| ws
    side <-->|WebSocket JSON| ws

    cam -->|产生关键点| pipe
    ws -->|用户指令| sub
    send -->|拉取| state

    pipe -->|更新| state
    sub -->|更新| state
    auth -->|更新| state

    sub --> spell
    sub --> short
    sub --> llm
</div>

<script>
    mermaid.initialize({ startOnLoad: true, flowchart: { curve: 'basis', padding: 20 } });
</script>
</body>
</html>
"""

html_pipe = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Pipeline</title>
    <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
    <style>
        body {
            background: linear-gradient(135deg, #0f172a, #1e1b4b);
            color: white;
            font-family: -apple-system, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            padding: 20px;
        }
        .mermaid {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
            backdrop-filter: blur(16px);
        }
    </style>
</head>
<body>

<div class="mermaid" id="pipe">
%%{init: {'theme': 'base', 'themeVariables': {
    'primaryColor': '#1e293b',
    'primaryTextColor': '#38bdf8',
    'primaryBorderColor': '#0284c7',
    'lineColor': '#0ea5e9',
    'fontSize': '18px',
    'fontFamily': 'Inter, sans-serif',
    'nodeBorder': '2px'
}}}%%
flowchart LR
    A[帧捕获] --> B[关键点提取<br>MediaPipe]
    B --> C[静态字母分类<br>Keras 24类]
    C --> D[动态追踪<br>J/Z 字母]
    D --> E[稳定帧确认<br>连续15帧]
    E --> F[运动门控<br>防抖]
    F --> G[单词提交<br>超时/空格]
    G --> H[拼写纠错<br>混淆替换]
    H --> I[快捷词展开<br>字典映射]
    I --> J[大模型格式化<br>DeepSeek]
    J --> K(((最终自然语句)))
</div>
<script>
    mermaid.initialize({ startOnLoad: true, flowchart: { curve: 'basis', padding: 20 } });
</script>
</body>
</html>
"""

with open('arch.html', 'w', encoding='utf-8') as f: f.write(html_content)
with open('pipe.html', 'w', encoding='utf-8') as f: f.write(html_pipe)

from playwright.sync_api import sync_playwright

def screenshot(html_path, out_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(device_scale_factor=2.5) # Super Retina resolution
        page.goto(f'file:///{os.path.abspath(html_path)}')
        page.wait_for_selector('svg')
        time.sleep(2) # wait for animation
        element = page.query_selector('.mermaid')
        element.screenshot(path=out_path)
        browser.close()

print('Taking beautiful screenshots...')
screenshot('arch.html', 'arch_pretty.png')
screenshot('pipe.html', 'pipe_pretty.png')
print('Done!')
