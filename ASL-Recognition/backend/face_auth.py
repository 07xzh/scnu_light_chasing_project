import os
import threading
import numpy as np
import cv2
from scipy.spatial.distance import cosine

from deepface import DeepFace

LIVENESS_STD_THRESHOLD = 5.0
SIMILARITY_THRESHOLD = 0.40
MIN_FACE_DIST_CM = 30
MAX_FACE_DIST_CM = 120

_embeddings_cache = {}
_cache_lock = threading.Lock()
_face_db_dir = None


def _normalize_face(aligned):
    if aligned.dtype in (np.float32, np.float64) and aligned.max() <= 1.0:
        aligned = (aligned * 255).astype(np.uint8)
    elif aligned.dtype != np.uint8:
        aligned = aligned.astype(np.uint8)
    if aligned.ndim == 3 and aligned.shape[2] == 4:
        aligned = aligned[:, :, :3]
    return aligned


def _equalize_lighting(image):
    if len(image.shape) == 3 and image.shape[2] == 3:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        l = clahe.apply(l)
        lab = cv2.merge((l, a, b))
        return cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    return image


def init_db(base_dir):
    global _face_db_dir
    _face_db_dir = os.path.join(base_dir, "face_db")
    os.makedirs(_face_db_dir, exist_ok=True)

    with _cache_lock:
        _embeddings_cache.clear()

    if not os.path.isdir(_face_db_dir):
        return

    for fname in os.listdir(_face_db_dir):
        if not fname.lower().endswith(".jpg"):
            continue
        img_path = os.path.join(_face_db_dir, fname)
        username = os.path.splitext(fname)[0]
        try:
            emb_objs = DeepFace.represent(
                img_path=img_path,
                model_name="Facenet",
                detector_backend="skip",
                enforce_detection=False,
            )
            if emb_objs:
                with _cache_lock:
                    _embeddings_cache[username] = np.array(
                        emb_objs[0]["embedding"], dtype=np.float32
                    )
                print(f"[FACE] Cached embedding for '{username}'")
        except Exception as e:
            print(f"[FACE] Failed to cache '{username}': {e}")


def verify_liveness(depth_frame, facial_area, rgb_h=None, rgb_w=None):
    if depth_frame is None:
        print("[FACE] No depth frame – liveness bypassed (insecure_fallback)")
        return "bypassed"

    dh, dw = depth_frame.shape
    x, y, w, h = int(facial_area["x"]), int(facial_area["y"]), int(facial_area["w"]), int(facial_area["h"])

    if rgb_h and rgb_w and (rgb_h != dh or rgb_w != dw):
        sc_x = dw / float(rgb_w)
        sc_y = dh / float(rgb_h)
        x = int(x * sc_x)
        y = int(y * sc_y)
        w = int(w * sc_x)
        h = int(h * sc_y)

    fx1 = max(0, min(dw - 1, x))
    fy1 = max(0, min(dh - 1, y))
    fx2 = max(fx1 + 1, min(dw, x + w))
    fy2 = max(fy1 + 1, min(dh, y + h))

    roi = depth_frame[fy1:fy2, fx1:fx2].astype(np.float32)
    valid_all = roi[roi > 0]
    if valid_all.size == 0:
        return "invalid_depth"
    median = float(np.median(valid_all))
    margin = 30.0
    close = roi[(roi > 0) & (roi >= median - margin) & (roi <= median + margin)]
    total_px = roi.size
    valid_px = close.size
    ratio = valid_px / total_px if total_px > 0 else 0
    print(f"[FACE-LIVE] full_roi={total_px}px median={median:.0f}mm  near_face={valid_px}/{total_px} ({ratio:.1%})")

    if valid_px == 0 or ratio < 0.3:
        return "invalid_depth"

    std_mm = float(np.std(close))
    print(f"[FACE-LIVE] near_face std={std_mm:.1f}mm  (threshold={LIVENESS_STD_THRESHOLD})")
    print(f"[FACE] Depth valid pixels {valid_px}/{total_px} ({ratio:.1%})")

    if valid_px == 0 or ratio < 0.5:
        return "invalid_depth"

    std_mm = float(np.std(close))
    print(f"[FACE] Depth STD: {std_mm:.1f}mm  (threshold={LIVENESS_STD_THRESHOLD})")
    if std_mm < LIVENESS_STD_THRESHOLD:
        return "spoof"
    return "genuine"


def get_largest_face(rgb_frame):
    faces = DeepFace.extract_faces(
        img_path=rgb_frame,
        detector_backend="mtcnn",
        enforce_detection=False,
    )
    if not faces:
        return None

    best = max(
        faces,
        key=lambda f: f["facial_area"]["w"] * f["facial_area"]["h"],
    )
    fa = best["facial_area"]
    x, y, w, h = int(fa["x"]), int(fa["y"]), int(fa["w"]), int(fa["h"])
    fh, fw = rgb_frame.shape[:2]
    # Reject if face box covers nearly the whole frame (detection failed)
    if w <= 0 or h <= 0:
        return None
    if w * h > fw * fh * 0.85:
        print(f"[FACE] Detection appears invalid - box covers entire frame")
        return None
    if x + w / 2 > fw * 0.9 or y + h / 2 > fh * 0.9:
        print(f"[FACE] Face near frame edge, likely false detection")
        return None
    x = max(0, x)
    y = max(0, y)
    w = min(w, fw - x)
    h = min(h, fh - y)
    if w <= 30 or h <= 30:
        print(f"[FACE] Face box too small ({w}x{h}), rejecting")
        return None
    crop = rgb_frame[y:y + h, x:x + w]
    return {
        "facial_area": fa,
        "face": crop,
    }


def get_face_distance(depth_frame, facial_area, rgb_h=None, rgb_w=None):
    if depth_frame is None:
        return None
    dh, dw = depth_frame.shape
    x, y, w, h = int(facial_area["x"]), int(facial_area["y"]), int(facial_area["w"]), int(facial_area["h"])
    print(f"[FACE-DIST] RGB: {rgb_w}x{rgb_h}  Depth: {dw}x{dh}  face_box=({x},{y},{w},{h})")
    if rgb_h and rgb_w and (rgb_h != dh or rgb_w != dw):
        sc_x = dw / float(rgb_w)
        sc_y = dh / float(rgb_h)
        x = int(x * sc_x)
        y = int(y * sc_y)
        w = int(w * sc_x)
        h = int(h * sc_y)
        print(f"[FACE-DIST] scaled face_box=({x},{y},{w},{h})")
    # Use center point instead of region - more reliable
    cx = min(max(x + w // 2, 0), dw - 1)
    cy = min(max(y + h // 2, 0), dh - 1)
    # Also sample a few pixels around center
    vals = []
    for dy_off in (-2, 0, 2):
        for dx_off in (-2, 0, 2):
            px = min(max(cx + dx_off, 0), dw - 1)
            py = min(max(cy + dy_off, 0), dh - 1)
            v = depth_frame[py, px]
            if v > 0:
                vals.append(v)
    print(f"[FACE-DIST] center=({cx},{cy})  sample_values={vals}")
    if len(vals) < 3:
        return None
    median_mm = float(np.median(vals))
    print(f"[FACE-DIST] median={median_mm:.0f}mm -> {median_mm / 10:.1f}cm")
    return median_mm / 10.0


def register_user(rgb_frame, depth_frame, username):
    h, w = rgb_frame.shape[:2]
    face_info = get_largest_face(rgb_frame)
    if face_info is None:
        return {"action": "register", "status": "no_face"}

    face_dist = get_face_distance(depth_frame, face_info["facial_area"], rgb_h=h, rgb_w=w)
    if face_dist is not None:
        if face_dist < MIN_FACE_DIST_CM:
            return {"action": "register", "status": "too_close", "distance": int(face_dist)}
        if face_dist > MAX_FACE_DIST_CM:
            return {"action": "register", "status": "too_far", "distance": int(face_dist)}

    liveness = verify_liveness(depth_frame, face_info["facial_area"], rgb_h=h, rgb_w=w)
    liveness_failed = liveness not in ("genuine", "bypassed")

    if liveness_failed:
        return {"action": "register", "status": liveness}

    save_path = os.path.join(_face_db_dir, f"{username}.jpg")
    save_frame = _normalize_face(face_info["face"])
    save_frame = _equalize_lighting(save_frame)
    cv2.imwrite(save_path, save_frame)
    print(f"[FACE] Saved registered face to {save_path}  shape={save_frame.shape}  dtype={save_frame.dtype}")

    emb = None
    try:
        emb_objs = DeepFace.represent(
            img_path=save_frame,
            model_name="Facenet",
            detector_backend="skip",
            enforce_detection=False,
        )
        if emb_objs:
            emb = np.array(emb_objs[0]["embedding"], dtype=np.float32)
            with _cache_lock:
                _embeddings_cache[username] = emb
    except Exception as e:
        print(f"[FACE] Failed to compute embedding for '{username}': {e}")

    insecure = " (insecure_fallback)" if liveness == "bypassed" else ""
    return {"action": "register", "status": "success", "user": username, "insecure": liveness == "bypassed", "embedding": emb}


def login_user(rgb_frame, depth_frame):
    h, w = rgb_frame.shape[:2]
    face_info = get_largest_face(rgb_frame)
    if face_info is None:
        return {"action": "login", "status": "no_face"}

    face_dist = get_face_distance(depth_frame, face_info["facial_area"], rgb_h=h, rgb_w=w)
    if face_dist is not None:
        if face_dist < MIN_FACE_DIST_CM:
            return {"action": "login", "status": "too_close", "distance": int(face_dist)}
        if face_dist > MAX_FACE_DIST_CM:
            return {"action": "login", "status": "too_far", "distance": int(face_dist)}

    liveness = verify_liveness(depth_frame, face_info["facial_area"], rgb_h=h, rgb_w=w)
    liveness_failed = liveness not in ("genuine", "bypassed")

    if liveness_failed:
        return {"action": "login", "status": liveness}

    aligned = _normalize_face(face_info["face"])
    aligned = _equalize_lighting(aligned)
    try:
        emb_objs = DeepFace.represent(
            img_path=aligned,
            model_name="Facenet",
            detector_backend="skip",
            enforce_detection=False,
        )
        live_emb = np.array(emb_objs[0]["embedding"], dtype=np.float32)
    except Exception as e:
        print(f"[FACE] Failed to compute live embedding: {e}")
        return {"action": "login", "status": "embedding_error"}

    with _cache_lock:
        usernames = list(_embeddings_cache.keys())
        cached_embs = [(_embeddings_cache[u], u) for u in usernames]

    if not cached_embs:
        return {"action": "login", "status": "unknown"}

    best_dist = float("inf")
    best_user = None
    for cached_emb, u in cached_embs:
        dist = cosine(live_emb, cached_emb)
        print(f"[FACE]   vs '{u}': distance={dist:.4f}")
        if dist < best_dist:
            best_dist = dist
            best_user = u

    print(f"[FACE] Best match: '{best_user}' distance={best_dist:.4f}  (threshold={SIMILARITY_THRESHOLD})")

    if best_dist >= SIMILARITY_THRESHOLD:
        return {"action": "login", "status": "unknown"}

    insecure = " (insecure_fallback)" if liveness == "bypassed" else ""
    return {"action": "login", "status": "success", "user": best_user, "insecure": liveness == "bypassed", "distance": best_dist}


def clear_all_faces():
    import glob
    with _cache_lock:
        _embeddings_cache.clear()
    if _face_db_dir and os.path.isdir(_face_db_dir):
        for f in glob.glob(os.path.join(_face_db_dir, "*.jpg")):
            os.remove(f)
        print(f"[FACE] Cleared all registered faces from {_face_db_dir}")
    return {"action": "clear_faces", "status": "cleared"}


def finalize_register(username, embeddings):
    valid = [e for e in embeddings if e is not None]
    if not valid:
        print(f"[FACE] No valid embeddings for '{username}'")
        return
    avg_emb = np.mean(valid, axis=0)
    avg_emb = avg_emb / np.linalg.norm(avg_emb)
    with _cache_lock:
        _embeddings_cache[username] = avg_emb.astype(np.float32)
    print(f"[FACE] Registered '{username}' with {len(valid)} frame embeddings averaged")
