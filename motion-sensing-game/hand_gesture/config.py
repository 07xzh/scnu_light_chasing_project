"""
Game configuration for Block Building Game
"""

# ============================================================================
# Window Settings
# ============================================================================
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 720
WINDOW_TITLE = "积木拼搭"
TARGET_FPS = 60

# ============================================================================
# Colors
# ============================================================================
COLOR_BACKGROUND = (20, 20, 35)
COLOR_PLATFORM = (80, 80, 120)
COLOR_PLATFORM_EDGE = (120, 120, 160)

# ============================================================================
# Camera Settings
# ============================================================================
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480

# ============================================================================
# Physics Settings
# ============================================================================
GRAVITY = 0.4
MAX_FALL_SPEED = 15
BOUNCE_FACTOR = 0.1
FRICTION = 0.92

# ============================================================================
# Hand Detection
# ============================================================================
GRAB_DISTANCE_THRESHOLD = 150

# ============================================================================
# Game Objects
# ============================================================================
OBJECT_SIZE_MIN = 40
OBJECT_SIZE_MAX = 70
OBJECT_COUNT = 10

# Block colors (nice pastel colors for building)
BLOCK_COLORS = [
    (255, 120, 120),   # Red
    (120, 255, 120),   # Green
    (120, 120, 255),   # Blue
    (255, 255, 120),   # Yellow
    (255, 120, 255),   # Pink
    (120, 255, 255),   # Cyan
    (255, 180, 120),   # Orange
    (180, 120, 255),   # Purple
]

# Block shapes - (type, width_factor, height_factor)
# type: 0=rectangle, 1=triangle
# width_factor and height_factor are relative to base size (50)
# Only 4 shapes: square, triangle, horizontal rect (2:1), vertical rect (2:1)
BLOCK_SHAPES = [
    (0, 1.0, 1.0),   # Square (50x50)
    (1, 1.5, 1.5),   # Triangle (75x75) - bigger for easier grab
    (0, 2.0, 1.0),   # Horizontal rectangle (100x50)
    (0, 1.0, 2.0),   # Vertical rectangle (50x100)
]

# ============================================================================
# Platform Settings
# ============================================================================
PLATFORM_WIDTH = 400
PLATFORM_HEIGHT = 20
PLATFORM_Y = 450  # Y position from top

# ============================================================================
# Debug
# ============================================================================
DEBUG_MODE = True
SHOW_CAMERA_FEED = True
