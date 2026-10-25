import os
import sys
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
import logging
logging.getLogger("tensorflow").setLevel(logging.ERROR)

try:
    import lz4.frame
    _lz4_orig_flush = lz4.frame.LZ4FrameFile.flush
    def _lz4_safe_flush(self):
        try:
            if hasattr(self, "_fp") and self._fp is not None and not getattr(self._fp, "closed", False):
                _lz4_orig_flush(self)
        except ValueError:
            pass
    lz4.frame.LZ4FrameFile.flush = _lz4_safe_flush
except ImportError:
    pass

import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
sys.path.insert(0, BASE_DIR)
sys.path.insert(0, ROOT_DIR)

import json, base64, threading, math, time, queue
from collections import deque, Counter
import asyncio
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import numpy as np
import cv2
import mediapipe as mp
from openai import OpenAI
from spellchecker import SpellChecker

from pipelines.hand_asl import HandASLPipeline, HAND_CONNECTIONS
from camera_manager import CameraManager
from face_auth import init_db, register_user, login_user, clear_all_faces
import shortcuts_manager

LETTERS = "ABCDEFGHIKLMNOPQRSTUVWXY"
spell = SpellChecker()
CONFUSABLES = {
    "A": ["T", "S"], "T": ["A", "S"], "S": ["A", "T"],
    "C": ["E", "O"], "E": ["C", "O"], "O": ["C", "E"],
    "M": ["N"], "N": ["M"], "D": ["I", "F"], "I": ["D"],
    "F": ["D", "W"], "W": ["F"], "K": ["V", "U"],
    "V": ["K", "U"], "U": ["K", "V"],
}

llm = None  # 懒加载：配置了 DEEPSEEK_API_KEY 才初始化（未配置时跳过 LLM 翻译）


def _get_llm():
    """按需创建 DeepSeek 客户端；未配置 API Key 时返回 None，不影响其他功能。"""
    global llm
    if llm is None and os.environ.get("DEEPSEEK_API_KEY"):
        try:
            llm = OpenAI(
                api_key=os.environ["DEEPSEEK_API_KEY"],
                base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            )
        except Exception as e:
            print(f"[LLM] init failed: {e}")
    return llm

app = FastAPI()
pipeline = HandASLPipeline()
camera = CameraManager()

raw_word = ""
completed = []
sentence_words = []
formatted_sentence = ""
stable_letter = None
stable_count = 0
jitter_count = 0
palm_start = None          # hand centroid when stable_letter was first set
start_landmarks = None      # snapshot of all 21 landmarks at letter start
last_committed = ""
no_result_frames = 0

last_commit_time = time.time()
sentence_expired = False
SENTENCE_TIMEOUT = 8
sentence_id = 0
current_logged_in_user = None
shortcut_mode_active = False

STABLE_FRAMES = 15
RESET_GAP = 20
WORD_TIMEOUT = 90
MIN_CONFIDENCE = 0.80

# ── Dynamic J/Z gesture tracking ──
DYNAMIC_WINDOW_FRAMES = 45
COOLDOWN_FRAMES = 15
dynamic_state = None          # None | 'tracking_J' | 'tracking_Z'
dynamic_frames_left = 0
dynamic_target = ""           # J or Z
finger_history = deque(maxlen=60)
static_votes = Counter()
cooldown = 0

# --- Global State for UI and Streaming ---
frame_queue = queue.Queue(maxsize=2)
predicted_word = ""
predicted_lock = threading.Lock()
current_state = {
    "type": "result",
    "letter": None, "conf": 0, "bar": "", "committed": False,
    "tracking": False, "detected": False, "landmarks": None,
    "raw_word": "", "completed": [], "sentence": "",
    "distance": 0, "distance_warning": None
}

latest_rgb_frame = None
latest_depth_frame = None
auth_queue = queue.Queue()


def _safe_auth(fn, *args):
    try:
        result = fn(*args)
        result["type"] = "auth_result"
        auth_queue.put(result)
    except Exception as e:
        import traceback
        traceback.print_exc()
        auth_queue.put({"type": "auth_result", "action": "error", "status": str(e)})


def _auth_with_retry(fn, username=None):
    best_result = None
    collected_embs = []
    user_votes = Counter()
    user_dists = {}
    user_best = {}

    max_attempts = 12 if username is not None else 5
    target_frames = 5 if username is not None else 3
    for attempt in range(max_attempts):
        rgb = latest_rgb_frame.copy() if latest_rgb_frame is not None else None
        depth = latest_depth_frame.copy() if latest_depth_frame is not None else None
        if rgb is None:
            break
        if username is not None:
            result = fn(rgb, depth, username)
        else:
            result = fn(rgb, depth)
        status = result.get("status")
        if status == "success":
            if username is not None:
                collected_embs.append(result.get("embedding"))
            else:
                user = result.get("user", "")
                dist = result.get("distance", float("inf"))
                user_votes[user] += 1
                if user not in user_dists:
                    user_dists[user] = []
                user_dists[user].append(dist)
                if user not in user_best or dist < user_best[user].get("distance", float("inf")):
                    user_best[user] = result
            if len(collected_embs) >= target_frames or sum(user_votes.values()) >= target_frames:
                break
        elif status not in ("no_face", "invalid_depth"):
            best_result = result
            break
        time.sleep(0.1)

    if username is not None and collected_embs:
        from face_auth import finalize_register
        finalize_register(username, collected_embs)
        best_result = {"action": "register", "status": "success", "user": username, "insecure": False}
        print(f"[AUTH] Register done: {username}, frames={len(collected_embs)}")
    elif username is None and user_votes:
        best_user = max(user_votes, key=lambda u: (user_votes[u], -sum(user_dists[u]) / len(user_dists[u])))
        best_result = user_best[best_user]
        best_result["distance"] = float(best_result.get("distance", 0))
        best_result["votes"] = f"{user_votes[best_user]}/{sum(user_votes.values())}"
        avg = sum(user_dists[best_user]) / len(user_dists[best_user])
        print(f"[AUTH] Login done: best={best_user}, votes={best_result['votes']}, best_dist={best_result['distance']:.4f}, avg_dist={avg:.4f}")
    elif not best_result:
        best_result = {"action": "error", "status": "no_face", "message": "多次尝试未能识别人脸"}
        print(f"[AUTH] Failed: no face detected after {attempt+1} attempts, embs={len(collected_embs)}")

    best_result["type"] = "auth_result"
    auth_queue.put(best_result)
    print(f"[AUTH] Result queued: {best_result.get('status')}")

def spell_correct(word):
    if not word or len(word) < 2:
        return None
    candidates = spell.candidates(word)
    if candidates:
        return list(candidates)[0]
    active = {i: CONFUSABLES.get(c, []) for i, c in enumerate(word)}
    for i, alts in active.items():
        for alt in alts:
            c = spell.candidates(word[:i] + alt + word[i + 1:])
            if c:
                return list(c)[0]
    return None

def submit_word(w):
    global last_committed, sentence_words, formatted_sentence, sentence_id
    if not w:
        return
    if shortcut_mode_active and current_logged_in_user:
        sc = shortcuts_manager.get_user_shortcuts(current_logged_in_user)
        expanded = sc.get(w.lower(), None)
        if expanded:
            completed.append((w, expanded))
            sentence_words.append(expanded)
            print(f"  Shortcut: {w} -> {expanded}")
            joined = " ".join(sentence_words)
            if len(sentence_words) > 1 or (sentence_words and len(sentence_words[0]) > 1 and len(joined.replace(" ", "")) > 2):
                formatted_sentence = joined + "..."
            else:
                formatted_sentence = joined
            current_words = list(sentence_words)
            current_id = sentence_id
            threading.Thread(target=_llm_format, args=(current_words, current_id), daemon=True).start()
            return
    corrected = spell_correct(w)
    final = corrected if corrected else w
    completed.append((w, final))
    sentence_words.append(final)
    print(f"  Word: {w} -> {final}")
    
    # Show preview (only with ... if LLM will be called)
    joined = " ".join(sentence_words)
    if len(sentence_words) > 1 or (sentence_words and len(sentence_words[0]) > 1 and len(joined.replace(" ", "")) > 2):
        formatted_sentence = joined + "..."
    else:
        formatted_sentence = joined
    
    current_words = list(sentence_words)
    current_id = sentence_id
    threading.Thread(target=_llm_format, args=(current_words, current_id), daemon=True).start()

def _llm_format(words, t_id):
    global formatted_sentence
    if not words:
        return
    # Skip LLM for single-letter or single-short-word inputs (garbage prevention)
    joined = " ".join(words)
    if len(words) == 1 and len(words[0]) <= 1:
        if t_id == sentence_id:
            formatted_sentence = joined
        return
    if len(joined.replace(" ", "")) <= 2:
        if t_id == sentence_id:
            formatted_sentence = joined
        return

    prompt = f"Convert to natural English sentence: {joined}. Output only the sentence."

    client = _get_llm()
    if client is None:
        if t_id == sentence_id:
            formatted_sentence = joined + "..."
        return

    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=50,
            temperature=0.3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        if t_id == sentence_id:
            result = resp.choices[0].message.content
            print(f"  LLM OK: {repr(result)}")
            if result:
                formatted_sentence = result.strip()
    except Exception as e:
        print(f"  LLM Error: {e}")


def _predict_word(partial, t_id):
    """Instant local dictionary word completion."""
    global predicted_word
    if len(partial) < 2:
        with predicted_lock:
            predicted_word = ""
        return
    try:
        candidates = [w.upper() for w in spell.word_frequency.words()
                      if w.upper().startswith(partial) and len(w) >= 3]
        candidates.sort(key=lambda w: -spell.word_frequency[w])
        if candidates:
            with predicted_lock:
                predicted_word = candidates[0]
            print(f"  Predict: {partial} -> {candidates[0]}")
    except Exception as e:
        print(f"  Predict Error: {e}")


predict_counter = 0

def _get_direction(dx, dy, threshold=0.018):
    """Quantise normalised displacement to 8-way direction (mag threshold filters jitter)."""
    mag = math.sqrt(dx * dx + dy * dy)
    if mag < threshold:
        return None
    angle = math.degrees(math.atan2(-dy, dx))
    if angle < 0:
        angle += 360
    if 22.5 <= angle < 67.5: return "NE"
    if 67.5 <= angle < 112.5: return "N"
    if 112.5 <= angle < 157.5: return "NW"
    if 157.5 <= angle < 202.5: return "W"
    if 202.5 <= angle < 247.5: return "SW"
    if 247.5 <= angle < 292.5: return "S"
    if 292.5 <= angle < 337.5: return "SE"
    return "E"

def _extract_directions(history, tip_idx, is_mirrored):
    dirs = []
    hist = list(history)
    for i in range(1, len(hist)):
        px, py = hist[i-1][tip_idx*2], hist[i-1][tip_idx*2+1]
        cx, cy = hist[i][tip_idx*2], hist[i][tip_idx*2+1]
        ps, cs = hist[i-1][4], hist[i][4]
        dx = (cx - px) if not is_mirrored else (px - cx)
        dy = (cy - py)
        scale = (ps + cs) * 0.5 + 1e-8
        d = _get_direction(dx / scale, dy / scale)
        if d: dirs.append(d)
    return dirs

def _match_j(dirs):
    """J pattern: 1+ S frames, then 1+ W/NW after the last S."""
    s_total = sum(1 for d in dirs if d == "S")
    if s_total < 1: return False
    last_s = max(i for i, d in enumerate(dirs) if d == "S")
    hook = sum(1 for d in dirs[last_s:] if d in ("W", "NW"))
    return hook >= 1


def _check_finger_motion(start_lms, cur_lms, tip_idx, threshold=0.008, ratio=1.5):
    """Return True if tip moved > threshold AND moved > ratio x any other finger."""
    target_d = math.sqrt((cur_lms[tip_idx][0] - start_lms[tip_idx][0])**2 +
                         (cur_lms[tip_idx][1] - start_lms[tip_idx][1])**2)
    if target_d < threshold:
        return False
    max_other = max(
        math.sqrt((cur_lms[i][0] - start_lms[i][0])**2 +
                  (cur_lms[i][1] - start_lms[i][1])**2)
        for i in range(21) if i != tip_idx
    )
    return target_d > max_other * ratio


# tracker snapshot for finger-motion detection
track_start_lms = None


def _match_z(dirs):
    """Z pattern: E → SW diagonal → E. Tolerates all non-critical directions."""
    phase = 0
    frames = 0
    for d in dirs:
        if phase == 0:
            if d == "E":
                frames += 1
            elif frames >= 1 and d in ("SE", "S", "SW"):
                phase, frames = 1, 1
            elif d != "E":
                frames = 0
        elif phase == 1:
            if d in ("SW", "S", "SE", "W"):
                frames += 1
            elif frames >= 1 and d == "E":
                phase, frames = 2, 1
        elif phase == 2:
            if d == "E":
                frames += 1
                if frames >= 1:
                    return True
    return False

def _evaluate_motion(start_lms, cur_lms, dynamic_target):
    """J: pinky(20) looser threshold (shorter finger). Z: index(8)."""
    if dynamic_target == "J":
        return _check_finger_motion(start_lms, cur_lms, 20, threshold=0.005, ratio=1.2)
    return _check_finger_motion(start_lms, cur_lms, 8, threshold=0.008, ratio=1.5)

def _clear_dynamic():
    global dynamic_state, dynamic_frames_left, dynamic_target, finger_history, static_votes
    dynamic_state = None
    dynamic_frames_left = 0
    dynamic_target = ""
    finger_history.clear()
    static_votes.clear()
    global track_start_lms
    track_start_lms = None

def draw_landmarks(image, landmarks):
    """在后台画面上绘制骨架 (替代前端 Canvas)"""
    h, w, _ = image.shape
    connections = HAND_CONNECTIONS
    # 将归一化坐标转为像素坐标
    points = []
    for lm in landmarks:
        points.append((int(lm[0] * w), int(lm[1] * h)))
    
    # 画线
    for connection in connections:
        p1 = points[connection[0]]
        p2 = points[connection[1]]
        cv2.line(image, p1, p2, (0, 255, 0), 2)
    # 画点
    for p in points:
        cv2.circle(image, p, 4, (0, 0, 255), -1)
    return image

def _reset_asl_state():
    """Reset all ASL recognition state."""
    global raw_word, completed, sentence_words, formatted_sentence
    global stable_letter, stable_count, jitter_count, last_committed
    global no_result_frames, last_commit_time, sentence_expired, sentence_id
    global dynamic_state, dynamic_frames_left, dynamic_target, cooldown
    global predicted_word, palm_start, start_landmarks
    raw_word = ""
    completed = []
    sentence_words = []
    formatted_sentence = ""
    stable_letter = None
    stable_count = 0
    jitter_count = 0
    last_committed = ""
    no_result_frames = 0
    last_commit_time = time.time()
    sentence_expired = False
    sentence_id += 1
    dynamic_state = None
    dynamic_frames_left = 0
    dynamic_target = ""
    cooldown = 0
    predicted_word = ""
    palm_start = None
    start_landmarks = None
    static_votes.clear()
    finger_history.clear()


def camera_loop():
    global raw_word, completed, stable_letter, stable_count, jitter_count, last_committed
    global no_result_frames, sentence_words, formatted_sentence
    global dynamic_state, dynamic_frames_left, dynamic_target, finger_history, static_votes, cooldown
    global last_commit_time, sentence_expired, sentence_id
    global frame_queue, current_state, palm_start, start_landmarks
    global predicted_word, predicted_lock, predict_counter
    global track_start_lms
    global latest_rgb_frame, latest_depth_frame

    print("[CAMERA THREAD] Background capture started.")
    
    last_tick = 0.0
    TICK_INTERVAL = 0.015  # ~66 fps
    
    while True:
        rgb_frame, depth_frame = camera.get_frames()
        if rgb_frame is None:
            time.sleep(0.01)
            continue

        latest_rgb_frame = rgb_frame
        latest_depth_frame = depth_frame

        now = time.time()
        if now - last_tick < TICK_INTERVAL:
            continue
        last_tick = now
            
        frame_to_process = rgb_frame.copy()

        # ── ASL 模式 ──
        result = pipeline.process(frame_to_process)
        
        # 前端视频镜像显示，需要同步翻转方向判定
        is_mirrored = True
        distance_val = 0
        warning = None
        depth_pip_b64 = ""

        if depth_frame is not None:
            try:
                d_min, d_max = 200.0, 2000.0
                d_clip = np.clip(depth_frame.astype(np.float32), d_min, d_max)
                d_norm = ((d_clip - d_min) / (d_max - d_min) * 255).astype(np.uint8)
                d_color = cv2.applyColorMap(d_norm, cv2.COLORMAP_JET)
                d_small = cv2.resize(d_color, (160, 120), interpolation=cv2.INTER_NEAREST)
                _, d_buf = cv2.imencode('.jpg', d_small, [cv2.IMWRITE_JPEG_QUALITY, 60])
                depth_pip_b64 = base64.b64encode(d_buf.tobytes()).decode('ascii')
            except Exception:
                pass

        if not sentence_expired and raw_word == "" and last_commit_time:
            if time.time() - last_commit_time > SENTENCE_TIMEOUT and not dynamic_state:
                sentence_expired = True

        if cooldown > 0:
            cooldown -= 1

        if result:
            no_result_frames = 0
            letter, conf, lms = result["letter"], result["conf"], result["landmarks"]
            
            # --- 核心：物理距离测算 ---
            h, w, _ = rgb_frame.shape
            palm_x = int(lms[9][0] * w)
            palm_y = int(lms[9][1] * h)
            
            # 限制在画面内
            palm_x = max(0, min(w - 1, palm_x))
            palm_y = max(0, min(h - 1, palm_y))

            if camera.mode == "ORBBEC" and depth_frame is not None:
                # 硬件级深度 (通常返回的是毫米)
                dh, dw = depth_frame.shape
                dx = int(lms[9][0] * dw)
                dy = int(lms[9][1] * dh)
                dx = max(0, min(dw - 1, dx))
                dy = max(0, min(dh - 1, dy))
                
                dist_mm = depth_frame[dy, dx]
                distance_val = dist_mm / 10.0 # 转换为 cm
                
                # 若取到 0 可能是黑洞，尝试周围像素，再不行用像素距离估算
                if distance_val == 0:
                    region = depth_frame[max(0,dy-2):min(dh,dy+3), max(0,dx-2):min(dw,dx+3)]
                    valid = region[region > 0]
                    if len(valid) > 0:
                        distance_val = float(np.median(valid)) / 10.0
                    else:
                        wrist = np.array([lms[0][0]*w, lms[0][1]*h])
                        mid = np.array([lms[9][0]*w, lms[9][1]*h])
                        pixel_dist = float(np.linalg.norm(mid - wrist)) + 1e-8
                        distance_val = (100.0 / pixel_dist) * 40.0
            else:
                # 算法平替 (OpenCV 模式)
                wrist = np.array([lms[0][0]*w, lms[0][1]*h])
                mid = np.array([lms[9][0]*w, lms[9][1]*h])
                pixel_dist = float(np.linalg.norm(mid - wrist)) + 1e-8
                # 假设：焦距/人手比例下，手掌像素长 100px 对应大概 40cm
                distance_val = (100.0 / pixel_dist) * 40.0

            # 距离阈值警告
            if distance_val < 35:
                warning = "too_close"
                if distance_val < 30:
                    distance_val = 0
            elif distance_val > 75:
                warning = "too_far"
            if no_result_frames == 0 and int(time.time() * 10) % 30 == 0:
                print(f"  [DIST] {distance_val:.0f}cm  mode={camera.mode}  warn={warning}")

            if warning:
                current_state = {
                    "type": "result",
                    "letter": None, "conf": 0, "bar": "", "committed": False,
                    "tracking": False, "detected": False,
                    "landmarks": lms,
                    "raw_word": raw_word,
                    "predicted": "",
                    "completed": [{"raw": r, "corrected": c} for r, c in completed],
                    "sentence": formatted_sentence,
                    "distance": int(distance_val),
                    "distance_warning": warning,
                    "shortcut_mode": shortcut_mode_active,
                    "logged_in_user": current_logged_in_user,
                    "depth_pip": depth_pip_b64
                }
                ret, buffer = cv2.imencode('.jpg', rgb_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ret:
                    while frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                        except queue.Empty:
                            break
                    frame_queue.put_nowait(buffer.tobytes())
                continue

            # 原有手势逻辑
            if lms:
                wrist_norm = np.array([lms[0][0], lms[0][1]])
                mid_norm = np.array([lms[9][0], lms[9][1]])
                scale = float(np.linalg.norm(mid_norm - wrist_norm)) + 1e-8
                finger_history.append((lms[8][0], lms[8][1], lms[20][0], lms[20][1], scale))

            flashed = ""
            if dynamic_state is not None:
                dynamic_frames_left -= 1
                static_votes[letter] += 1
                if dynamic_frames_left % 8 == 0:
                    tip_idx = 20 if dynamic_target == "J" else 8
                    d = math.sqrt((lms[tip_idx][0] - track_start_lms[tip_idx][0])**2 +
                                  (lms[tip_idx][1] - track_start_lms[tip_idx][1])**2)
                    max_other = max(
                        math.sqrt((lms[i][0] - track_start_lms[i][0])**2 +
                                  (lms[i][1] - track_start_lms[i][1])**2)
                        for i in range(21) if i != tip_idx
                    )
                    print(f"  [{dynamic_target}] t-{dynamic_frames_left:02d}  tip={d:.4f}  max_other={max_other:.4f}")

                cur_snap = [(lm[0], lm[1]) for lm in lms]
                if _evaluate_motion(track_start_lms, cur_snap, dynamic_target):
                    if sentence_expired:
                        sentence_id += 1
                        completed.clear()
                        sentence_words.clear()
                        formatted_sentence = ""
                        sentence_expired = False
                        raw_word = ""
                    raw_word += dynamic_target
                    last_committed = dynamic_target
                    last_commit_time = time.time()
                    flashed = dynamic_target
                    stable_letter = None
                    stable_count = 0
                    _clear_dynamic()
                    cooldown = COOLDOWN_FRAMES
                elif dynamic_frames_left <= 0:
                    fallback = "I" if dynamic_state == "tracking_J" else "D"
                    if sentence_expired:
                        sentence_id += 1
                        completed.clear()
                        sentence_words.clear()
                        formatted_sentence = ""
                        sentence_expired = False
                        raw_word = ""
                    raw_word += fallback
                    last_committed = fallback
                    last_commit_time = time.time()
                    stable_letter = None
                    stable_count = 0
                    _clear_dynamic()
                    cooldown = COOLDOWN_FRAMES

            elif cooldown <= 0 and conf >= MIN_CONFIDENCE:
                # motion gate — reject if ANY landmark drifted during stable hold
                cur_lms = [(lm[0], lm[1]) for lm in lms]
                motion_reject = False
                if start_landmarks is not None and letter == stable_letter:
                    max_d2 = 0.0
                    for i in range(21):
                        dx = cur_lms[i][0] - start_landmarks[i][0]
                        dy = cur_lms[i][1] - start_landmarks[i][1]
                        d2 = dx * dx + dy * dy
                        if d2 > max_d2: max_d2 = d2
                    if max_d2 > 0.010:
                        motion_reject = True

                if motion_reject:
                    stable_letter = None
                    stable_count = 0
                    jitter_count = 0
                    start_landmarks = None
                elif letter == stable_letter:
                    stable_count += 1
                    jitter_count = 0
                else:
                    if stable_letter is None:
                        stable_letter = letter
                        stable_count = 1
                        jitter_count = 0
                        start_landmarks = cur_lms
                    else:
                        jitter_count += 1
                        if jitter_count >= 5:
                            stable_letter = letter
                            stable_count = 1
                            jitter_count = 0
                            start_landmarks = cur_lms

                if stable_count >= STABLE_FRAMES and (letter != last_committed or letter in ("I", "D")):
                    if letter in ("I", "D"):
                        print(f"  >>> TRACKING START: letter={letter}  target={'J' if letter=='I' else 'Z'}")
                        dynamic_state = "tracking_J" if letter == "I" else "tracking_Z"
                        dynamic_frames_left = DYNAMIC_WINDOW_FRAMES
                        dynamic_target = "J" if letter == "I" else "Z"
                        static_votes.clear()
                        finger_history.clear()
                        # snapshot current landmark positions for finger-motion detection
                        track_start_lms = [(lm[0], lm[1]) for lm in lms]
                    else:
                        print(f"  >>> COMMIT: letter={letter}  (NOT I/D)")
                        if sentence_expired:
                            sentence_id += 1
                            completed.clear()
                            sentence_words.clear()
                            formatted_sentence = ""
                            sentence_expired = False
                            raw_word = ""
                        raw_word += letter
                        last_committed = letter
                        last_commit_time = time.time()
                        stable_letter = None
                        stable_count = 0
                        start_landmarks = None
                        cooldown = COOLDOWN_FRAMES
                        # trigger word prediction
                        predict_counter += 1
                        c = predict_counter
                        threading.Thread(target=_predict_word, args=(raw_word, c), daemon=True).start()

            elif cooldown <= 0:
                stable_letter = None
                stable_count = 0
                jitter_count = 0

            tracking = dynamic_state is not None
            display_letter = flashed if flashed else (dynamic_target if tracking else letter)
            bar = "#" * min(stable_count, STABLE_FRAMES) + "_" * max(0, STABLE_FRAMES - stable_count)
            
            current_state = {
                "type": "result",
                "letter": display_letter, "conf": round(conf, 3),
                "bar": bar, "committed": conf >= MIN_CONFIDENCE and not tracking,
                "tracking": tracking, "detected": bool(flashed),
                "landmarks": lms,
                "raw_word": raw_word,
                "predicted": predicted_word if predicted_word and predicted_word.startswith(raw_word) else "",
                "completed": [{"raw": r, "corrected": c} for r, c in completed],
                "sentence": formatted_sentence,
                "distance": int(distance_val),
                "distance_warning": warning,
                "shortcut_mode": shortcut_mode_active,
                "logged_in_user": current_logged_in_user,
                "depth_pip": depth_pip_b64
            }
        else:
            no_result_frames += 1
            if no_result_frames >= RESET_GAP:
                last_committed = ""
                stable_letter = None
                stable_count = 0
                jitter_count = 0
                if dynamic_state:
                    _clear_dynamic()
            if no_result_frames >= WORD_TIMEOUT and raw_word:
                submit_word(raw_word)
                raw_word = ""
                last_committed = ""
                last_commit_time = time.time()

            current_state = {
                "type": "result",
                "letter": None, "conf": 0, "bar": "", "committed": False,
                "tracking": False, "detected": False,
                "raw_word": raw_word,
                "predicted": predicted_word if predicted_word and predicted_word.startswith(raw_word) else "",
                "completed": [{"raw": r, "corrected": c} for r, c in completed],
                "sentence": formatted_sentence,
                "distance": 0,
                "distance_warning": None,
                "shortcut_mode": shortcut_mode_active,
                "logged_in_user": current_logged_in_user,
                "depth_pip": depth_pip_b64
            }

        # Encode and push to frame queue (discard oldest if full)
        ret, buffer = cv2.imencode('.jpg', rgb_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
        if ret:
            while frame_queue.full():
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    break
            frame_queue.put_nowait(buffer.tobytes())

@app.on_event("startup")
def startup():
    print("[INFO] Loading ASL model...")
    pipeline.load()
    init_db(BASE_DIR)
    # 清理 Orbbec SDK 堆积日志
    import glob as _g
    for _log in _g.glob(os.path.join(ROOT_DIR, "Log", "OrbbecSDK.log*")) + _g.glob(os.path.join(BASE_DIR, "Log", "OrbbecSDK.log*")):
        try:
            os.remove(_log)
        except OSError:
            pass
    t = threading.Thread(target=camera_loop, daemon=True)
    t.start()
    print("[INFO] Server ready at http://localhost:8765")


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global raw_word, completed, sentence_words, formatted_sentence
    global last_committed, last_commit_time, sentence_id, sentence_expired
    global cooldown, stable_letter, stable_count
    global predicted_word, track_start_lms
    global STABLE_FRAMES, DYNAMIC_WINDOW_FRAMES, SENTENCE_TIMEOUT
    global current_logged_in_user, shortcut_mode_active
    
    await ws.accept()
    print("[WS] Client connected")

    # 启动一个后台任务定期发送当前状态给客户端
    async def send_loop():
        global current_logged_in_user, shortcut_mode_active
        while True:
            try:
                await ws.send_json(current_state)
                latest = None
                while True:
                    try:
                        latest = frame_queue.get_nowait()
                    except queue.Empty:
                        break
                if latest is not None:
                    await ws.send_bytes(latest)
                try:
                    auth_msg = auth_queue.get_nowait()
                    if auth_msg.get("status") == "success":
                        user = auth_msg.get("user")
                        action = auth_msg.get("action")
                        if user and action in ("login", "register"):
                            current_logged_in_user = user
                            auth_msg["shortcuts"] = shortcuts_manager.get_user_shortcuts(user)
                            print(f"[WS] Set current_logged_in_user={user}, shortcuts attached")
                        elif auth_msg.get("action") == "clear_faces" or auth_msg.get("action") == "logout" or auth_msg.get("status") == "cleared":
                            current_logged_in_user = None
                            shortcut_mode_active = False
                            print(f"[WS] Cleared login state")
                    try:
                        await ws.send_json(auth_msg)
                        print(f"[WS] sent auth_result: {auth_msg.get('status')}")
                    except Exception as se:
                        print(f"[WS] send auth_result FAILED: {se}")
                except queue.Empty:
                    pass
                if int(time.time() * 10) % 300 == 0:
                    print(f"[WS] send_loop alive, queue_size={auth_queue.qsize()}")
                await asyncio.sleep(0.025)  # 40 Hz
            except Exception:
                break
                
    task = asyncio.create_task(send_loop())

    while True:
        try:
            msg = await ws.receive_text()
            data = json.loads(msg)

            if data.get("type") == "command":
                cmd = data.get("cmd", "")

                if cmd == "space":
                    submit_word(raw_word)
                    raw_word = ""
                    last_committed = ""
                    predicted_word = ""
                    last_commit_time = time.time()
                    stable_letter = None
                    stable_count = 0
                    cooldown = COOLDOWN_FRAMES
                    _clear_dynamic()
                elif cmd == "accept_predict":
                    if predicted_word and predicted_word.startswith(raw_word):
                        raw_word = predicted_word
                    submit_word(raw_word)
                    raw_word = ""
                    last_committed = ""
                    predicted_word = ""
                    last_commit_time = time.time()
                    stable_letter = None
                    stable_count = 0
                    cooldown = COOLDOWN_FRAMES
                    _clear_dynamic()
                elif cmd == "backspace":
                    if raw_word:
                        raw_word = raw_word[:-1]
                        last_committed = raw_word[-1] if raw_word else ""
                    elif completed:
                        completed.pop()
                        if sentence_words: sentence_words.pop()
                        sentence_id += 1
                        last_commit_time = time.time()
                        if sentence_words:
                            formatted_sentence = " ".join(sentence_words) + "..."
                            current_words = list(sentence_words)
                            current_id = sentence_id
                            threading.Thread(target=_llm_format, args=(current_words, current_id), daemon=True).start()
                        else:
                            formatted_sentence = ""
                elif cmd == "reset":
                    raw_word = ""
                    last_committed = ""
                    predicted_word = ""
                    _clear_dynamic()
                elif cmd == "clear":
                    raw_word = ""
                    last_committed = ""
                    completed = []
                    sentence_words = []
                    formatted_sentence = ""
                    sentence_expired = False
                    last_commit_time = time.time()
                    sentence_id += 1
                    _clear_dynamic()
                elif cmd == "register" or cmd == "login":
                    rgb_snap = latest_rgb_frame.copy() if latest_rgb_frame is not None else None
                    depth_snap = latest_depth_frame.copy() if latest_depth_frame is not None else None
                    if rgb_snap is None:
                        auth_queue.put({
                            "type": "auth_result",
                            "action": cmd,
                            "status": "no_camera",
                        })
                    else:
                        uname = data.get("username", "User")
                        if cmd == "register":
                            threading.Thread(
                                target=lambda: _auth_with_retry(register_user, username=uname),
                                daemon=True,
                            ).start()
                        else:
                            threading.Thread(
                                target=lambda: _auth_with_retry(login_user),
                                daemon=True,
                            ).start()
                elif cmd == "clear_faces":
                    _safe_auth(clear_all_faces)
                elif cmd == "logout":
                    global current_logged_in_user, shortcut_mode_active
                    current_logged_in_user = None
                    shortcut_mode_active = False
                    print("[WS] Logged out successfully")
                elif cmd == "toggle_shortcuts":
                    shortcut_mode_active = data.get("active", False)
                elif cmd == "update_shortcuts":
                    if current_logged_in_user:
                        sc_data = data.get("shortcuts", {})
                        shortcuts_manager.update_user_shortcuts(current_logged_in_user, sc_data)
                elif cmd == "shortcut_expand":
                    key = data.get("key", "").upper()
                    if shortcut_mode_active and current_logged_in_user and key:
                        if sentence_expired:
                            sentence_id += 1
                            completed.clear()
                            sentence_words.clear()
                            formatted_sentence = ""
                            sentence_expired = False
                            raw_word = ""
                        sc = shortcuts_manager.get_user_shortcuts(current_logged_in_user)
                        expanded = sc.get(key.lower(), key)
                        completed.append((key, expanded))
                        sentence_words.append(expanded)
                        last_commit_time = time.time()
                        print(f"  Shortcut expand: {key} -> {expanded}")
                        joined = " ".join(sentence_words)
                        if len(sentence_words) > 1 or (sentence_words and len(sentence_words[0]) > 1 and len(joined.replace(" ", "")) > 2):
                            formatted_sentence = joined + "..."
                        else:
                            formatted_sentence = joined
                        current_words = list(sentence_words)
                        current_id = sentence_id
                        threading.Thread(target=_llm_format, args=(current_words, current_id), daemon=True).start()
            
            elif data.get("type") == "setting":
                if "stable_frames" in data:
                    STABLE_FRAMES = data["stable_frames"]
                if "dynamic_window" in data:
                    DYNAMIC_WINDOW_FRAMES = data["dynamic_window"]
                if "sentence_timeout" in data:
                    SENTENCE_TIMEOUT = data["sentence_timeout"]
                    
        except Exception:
            break

    task.cancel()
    print("[WS] Client disconnected")

@app.get("/")
def index():
    from fastapi.responses import Response
    with open(os.path.join(ROOT_DIR, "frontend", "index.html"), encoding="utf-8") as f:
        content = f.read()
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

app.mount("/static", StaticFiles(directory=os.path.join(ROOT_DIR, "frontend")), name="static")
