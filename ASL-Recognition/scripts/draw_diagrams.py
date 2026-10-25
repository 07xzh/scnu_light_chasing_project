import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as patches

matplotlib.use('Agg')
# Use standard sans-serif font
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial', 'sans-serif']

def draw_arch():
    fig, ax = plt.subplots(figsize=(10, 8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis('off')
    
    # Frontend Box
    ax.add_patch(patches.FancyBboxPatch((0.5, 7.5), 9, 2, boxstyle='round,pad=0.2', ec='blue', fc='#eef', lw=2))
    plt.text(5, 9.2, 'Frontend (index.html)', ha='center', va='center', fontsize=14, fontweight='bold', color='darkblue')
    
    def box(x, y, w, h, text, fc='#fff', ec='#333'):
        ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.1', ec=ec, fc=fc, lw=1.5))
        plt.text(x+w/2, y+h/2, text, ha='center', va='center', fontsize=10)
        return (x+w/2, y+h/2)
        
    def arrow(src, dst, text=''):
        ax.annotate('', xy=dst, xytext=src, arrowprops=dict(arrowstyle='->', lw=1.5, color='#555'))
        if text:
            mx, my = (src[0]+dst[0])/2, (src[1]+dst[1])/2
            plt.text(mx, my, text, ha='center', va='center', fontsize=8, bbox=dict(fc='white', ec='none', pad=1, alpha=0.8))

    c1 = box(1, 8, 1.5, 0.8, 'Canvas Render', fc='#e0f7fa', ec='#006064')
    c2 = box(3, 8, 1.5, 0.8, 'Gesture Panel', fc='#e0f7fa', ec='#006064')
    c3 = box(5, 8, 1.5, 0.8, 'Translate Area', fc='#e0f7fa', ec='#006064')
    c4 = box(7, 8, 1.5, 0.8, 'Control Sidebar', fc='#e0f7fa', ec='#006064')

    # Backend Box
    ax.add_patch(patches.FancyBboxPatch((0.5, 0.5), 9, 6.5, boxstyle='round,pad=0.2', ec='green', fc='#efe', lw=2))
    plt.text(5, 6.7, 'Backend (FastAPI & Models)', ha='center', va='center', fontsize=14, fontweight='bold', color='darkgreen')

    ws = box(4.25, 5, 1.5, 0.8, 'ws_endpoint\n(async)', fc='#fff9c4')
    cam = box(1, 5, 1.5, 0.8, 'camera_loop\n(66fps)', fc='#fff9c4')
    snd = box(7.5, 5, 1.5, 0.8, 'send_loop\n(40Hz)', fc='#fff9c4')

    pipe = box(1, 3, 1.5, 0.8, 'HandASLPipeline\n(MediaPipe+Keras)', fc='#ffccbc')
    sub = box(4.25, 3, 1.5, 0.8, 'submit_word()\n(Business Logic)', fc='#ffccbc')
    st = box(7.5, 3, 1.5, 0.8, 'Global State\n(Queues/Vars)', fc='#d1c4e9')

    spel = box(1.5, 1, 1.5, 0.8, 'SpellChecker', fc='#f8bbd0')
    shor = box(3.5, 1, 1.5, 0.8, 'ShortcutManager', fc='#f8bbd0')
    llm = box(5.5, 1, 1.5, 0.8, 'DeepSeek API', fc='#f8bbd0')
    auth = box(7.5, 1, 1.5, 0.8, 'Face Auth', fc='#f8bbd0')

    # Edges
    arrow(c1, (ws[0], ws[1]+0.4), 'WebSocket')
    arrow(c2, (ws[0], ws[1]+0.4))
    arrow(c3, (ws[0], ws[1]+0.4))
    arrow(c4, (ws[0], ws[1]+0.4))

    arrow(cam, (pipe[0], pipe[1]+0.4))
    arrow(ws, (sub[0], sub[1]+0.4))
    arrow((snd[0], snd[1]-0.4), (st[0], st[1]+0.4))

    arrow((pipe[0]+0.75, pipe[1]), (st[0]-0.75, st[1]))
    arrow((sub[0]+0.75, sub[1]), (st[0]-0.75, st[1]))
    arrow((auth[0], auth[1]+0.4), (st[0], st[1]-0.4))

    arrow((sub[0]-0.5, sub[1]-0.4), (spel[0], spel[1]+0.4))
    arrow((sub[0]-0.25, sub[1]-0.4), (shor[0], shor[1]+0.4))
    arrow((sub[0]+0.25, sub[1]-0.4), (llm[0], llm[1]+0.4))

    plt.savefig('arch_drawn.png', dpi=300, bbox_inches='tight')
    plt.close()

def draw_pipe():
    fig, ax = plt.subplots(figsize=(12, 4))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 4)
    ax.axis('off')
    
    def box(x, y, w, h, text, fc='#e3f2fd'):
        ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.1', ec='#1565c0', fc=fc, lw=1.5))
        plt.text(x+w/2, y+h/2, text, ha='center', va='center', fontsize=9, fontweight='bold')
        return (x+w/2, y+h/2)
        
    def arrow(src, dst):
        ax.annotate('', xy=dst, xytext=src, arrowprops=dict(arrowstyle='->', lw=2, color='#1565c0'))

    nodes = [
        box(0.5, 2.5, 1.5, 0.6, 'Frame Capture'),
        box(2.5, 2.5, 1.5, 0.6, 'MediaPipe Hand\n(21x3D)'),
        box(4.5, 2.5, 1.5, 0.6, 'Keras Static\n(24 Classes)'),
        box(6.5, 2.5, 1.5, 0.6, 'Dynamic J/Z\nTracking'),
        box(8.5, 2.5, 1.5, 0.6, 'Stable Frame\nConfirmation'),
        box(10.5, 2.5, 1.2, 0.6, 'Motion\nGating', fc='#fce4ec'),
        box(8.5, 1.0, 1.5, 0.6, 'Word Submit\n(Timeout/Space)', fc='#fce4ec'),
        box(6.5, 1.0, 1.5, 0.6, 'Spell\nCorrection'),
        box(4.5, 1.0, 1.5, 0.6, 'Shortcut\nExpansion'),
        box(2.5, 1.0, 1.5, 0.6, 'LLM DeepSeek\nFormat'),
        box(0.5, 1.0, 1.5, 0.6, 'Natural\nSentence', fc='#e8f5e9')
    ]
    
    for i in range(4): arrow((nodes[i][0]+0.75, nodes[i][1]), (nodes[i+1][0]-0.75, nodes[i+1][1]))
    arrow((nodes[4][0]+0.75, nodes[4][1]), (nodes[5][0]-0.6, nodes[5][1]))
    
    # U-turn
    arrow((nodes[5][0], nodes[5][1]-0.3), (nodes[5][0], nodes[6][1]+0.3))
    arrow((nodes[5][0]-0.6, nodes[6][1]), (nodes[6][0]+0.75, nodes[6][1]))
    
    for i in range(6, 10): arrow((nodes[i][0]-0.75, nodes[i][1]), (nodes[i+1][0]+0.75, nodes[i+1][1]))

    plt.savefig('pipe_drawn.png', dpi=300, bbox_inches='tight')
    plt.close()

draw_arch()
draw_pipe()
print("Images saved.")
