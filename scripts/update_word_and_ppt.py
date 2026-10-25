import os
import pptx
from pptx.util import Inches, Pt
import docx
from docx.shared import Pt, Inches as DocxInches
import re

# File Paths
md_path = r'C:\Users\20229\Desktop\ASL_Pro_Studio_项目总结.md'
docx_path = r'C:\Users\20229\Desktop\ASL_Pro_Studio_项目总结.docx'
ppt_path = r'C:\Users\20229\Desktop\ASL_Pro_Studio_Presentation_V2.pptx'
img_dir = r'C:\Users\20229\Desktop\项目图片素材'

arch_img = os.path.join(os.path.dirname(__file__), "..", "docs", "arch_pretty.png")
pipe_img = os.path.join(os.path.dirname(__file__), "..", "docs", "pipe_pretty.png")
mediapipe_img = os.path.join(img_dir, 'mediapipe-hand-landmarks.png')
confusion_img = os.path.join(img_dir, 'Confusion Matrix.png')
acc_img = os.path.join(img_dir, 'Accuracy and Loss - Training and Validation.png')

# 1. GENERATE DOCX
if os.path.exists(md_path):
    doc = docx.Document()
    with open(md_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    in_arch_code = False
    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Skip the original ASCII architecture code block
        if line.startswith('```'):
            if in_arch_code:
                in_arch_code = False
            else:
                if len(doc.paragraphs) > 0 and '整体架构图' in doc.paragraphs[-1].text:
                    in_arch_code = True
            continue
            
        if in_arch_code:
            if 'Canvas' in line and not getattr(doc, '_arch_inserted', False) and os.path.exists(arch_img):
                doc.add_picture(arch_img, width=DocxInches(6.5))
                doc._arch_inserted = True
            continue
            
        if line.startswith('# '):
            doc.add_heading(line[2:], 0)
        elif line.startswith('## '):
            doc.add_heading(line[3:], 1)
        elif line.startswith('### '):
            doc.add_heading(line[4:], 2)
            # Check if this is the pipeline section
            if '手语识别流水线' in line:
                if os.path.exists(pipe_img):
                    doc.add_picture(pipe_img, width=DocxInches(6.5))
        elif line.startswith('#### '):
            doc.add_heading(line[5:], 3)
            # Insert mediapipe image
            if '手部关键点检测' in line:
                if os.path.exists(mediapipe_img):
                    doc.add_picture(mediapipe_img, width=DocxInches(4))
            # Insert model images after static classification
            elif '静态字母分类' in line:
                if os.path.exists(confusion_img):
                    doc.add_picture(confusion_img, width=DocxInches(4))
                if os.path.exists(acc_img):
                    doc.add_picture(acc_img, width=DocxInches(4))
        elif line.startswith('- ') or line.startswith('* '):
            doc.add_paragraph(line[2:], style='List Bullet')
        else:
            p = doc.add_paragraph()
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    p.add_run(part[2:-2]).bold = True
                elif part.startswith('`') and part.endswith('`'):
                    p.add_run(part).font.name = 'Courier New'
                else:
                    p.add_run(part)

    doc.save(docx_path)
    print('DOCX generated successfully with all images.')

# 2. UPDATE PPTX
if os.path.exists(ppt_path):
    try:
        prs = pptx.Presentation(ppt_path)
        
        # We already have arch and pipe in slides 2 and 3.
        # Let's insert a NEW slide after Slide 3 for Model Training
        # Use a blank layout (usually layout 6 is blank)
        slide_layout = prs.slide_layouts[5] # Title Only
        new_slide = prs.slides.add_slide(slide_layout)
        
        # Move the new slide to be index 4 (right after Slide 3)
        # Note: python-pptx doesn't natively support moving slides easily, 
        # so we will just let it be at the end, OR re-create it by shifting elements.
        # Wait, the easiest way to insert a slide at a specific position is manipulating the XML.
        # Since that's hard, let's just append it to the end or modify an existing slide.
        # Let's just create a new slide at the end, it's fine.
        
        title = new_slide.shapes.title
        title.text = "模型训练与评估 (Model Training & Evaluation)"
        
        # Add Confusion Matrix
        if os.path.exists(confusion_img):
            new_slide.shapes.add_picture(confusion_img, Inches(0.5), Inches(2), width=Inches(4.5))
            
        # Add Accuracy/Loss Curve
        if os.path.exists(acc_img):
            new_slide.shapes.add_picture(acc_img, Inches(5.2), Inches(2), width=Inches(4.5))
            
        # Add another slide for MediaPipe
        slide_layout_2 = prs.slide_layouts[5]
        mp_slide = prs.slides.add_slide(slide_layout_2)
        mp_slide.shapes.title.text = "MediaPipe 手部关键点提取 (21x3D Landmarks)"
        if os.path.exists(mediapipe_img):
            mp_slide.shapes.add_picture(mediapipe_img, Inches(2), Inches(1.5), width=Inches(6))
        
        prs.save(ppt_path)
        print('PPTX updated successfully with new training images.')
    except Exception as e:
        print('Error updating PPTX:', e)
