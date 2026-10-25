import cv2
import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
import os

img_path = r'C:\Users\20229\.gemini\antigravity\brain\aa5822ad-2425-4a0b-8ef0-09394d006892\.user_uploaded\media__1785290625642.jpg'
out_dir = r'C:\Users\20229\Desktop\ASL_Letters'
os.makedirs(out_dir, exist_ok=True)

img = cv2.imread(img_path)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
_, thresh = cv2.threshold(gray, 10, 255, cv2.THRESH_BINARY)

contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

rects = []
centers = []
for cnt in contours:
    x, y, w, h = cv2.boundingRect(cnt)
    if w > 10 and h > 10:
        rects.append([x, y, x+w, y+h])
        centers.append([x + w/2, y + h/2])

# Cluster close contours
Z = linkage(centers, 'single')
clusters = fcluster(Z, t=100, criterion='distance')

# Merge rects within the same cluster
merged_rects = {}
for i, c_id in enumerate(clusters):
    if c_id not in merged_rects:
        merged_rects[c_id] = rects[i]
    else:
        mx1, my1, mx2, my2 = merged_rects[c_id]
        x1, y1, x2, y2 = rects[i]
        merged_rects[c_id] = [min(mx1, x1), min(my1, y1), max(mx2, x2), max(my2, y2)]

boxes = list(merged_rects.values())
if len(boxes) != 26:
    print(f'Warning: Found {len(boxes)} clusters instead of 26!')

# Sort boxes top-to-bottom, then left-to-right
boxes.sort(key=lambda b: b[1]) # Sort by Y
rows = []
current_row = []
for b in boxes:
    if not current_row:
        current_row.append(b)
    else:
        # Check if in same row (y difference < 80 pixels)
        if abs(b[1] - current_row[-1][1]) < 80:
            current_row.append(b)
        else:
            rows.append(current_row)
            current_row = [b]
if current_row:
    rows.append(current_row)

sorted_boxes = []
for r in rows:
    r.sort(key=lambda b: b[0]) # Sort by X
    sorted_boxes.extend(r)

if len(sorted_boxes) != 26:
    print("Cannot proceed, did not find 26 letters properly.")
    exit(1)

# Map to letters and save
H, W = img.shape[:2]
padding = 10

saved_count = 0
for i, b in enumerate(sorted_boxes):
    if i == 9: # J
        continue
    if i == 25: # Z
        continue
        
    letter = chr(65 + i)
    x1, y1, x2, y2 = b
    
    # Add padding
    x1 = max(0, x1 - padding)
    y1 = max(0, y1 - padding)
    x2 = min(W, x2 + padding)
    y2 = min(H, y2 + padding)
    
    crop = img[y1:y2, x1:x2]
    
    save_path = os.path.join(out_dir, f'{letter}.jpg')
    cv2.imwrite(save_path, crop)
    saved_count += 1

print(f'Successfully cropped and saved {saved_count} letters to {out_dir}.')
