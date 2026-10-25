"""
Game Logic for Block Building Game.

The game is tuned for parent-child puzzle play: each level gives a simple
building target and unlocks the next level after the target is matched.
"""


class GameLogic:
    """
    Core game logic for hand-controlled block building.
    No scoring - just building fun!
    """

    def __init__(self, config):
        self.config = config
        self.grab_distance_threshold = config.get('grab_distance_threshold', 150)
        self._was_grabbing = False
        self._last_hand_pos = (0, 0)
        self._hand_velocity = (0, 0)
        # Hand movement sensitivity - amplify small hand movements to larger game movements
        self.sensitivity = 2.4
        self._accumulated_dx = 0
        self._accumulated_dy = 0
        # Smoothing for hand position
        self._smooth_x = 0.5
        self._smooth_y = 0.5
        self._smooth_factor = 0.5  # Balance between smooth and responsive
        self.levels = create_levels(config)
        self.current_level_index = 0
        self.unlocked_level_count = 1
        self.level_completed = False
        self.completion_timer = 0
        self.completion_hold_frames = 45
        self.last_goal_matches = []

    def reset(self):
        """Reset game state."""
        self._was_grabbing = False
        self._last_hand_pos = (0, 0)
        self._hand_velocity = (0, 0)
        self._smooth_x = 0.5
        self._smooth_y = 0.5
        self.level_completed = False
        self.completion_timer = 0
        self.last_goal_matches = []

    def get_current_level(self):
        return self.levels[self.current_level_index]

    def select_level(self, index):
        if 0 <= index < self.unlocked_level_count:
            self.current_level_index = index
            self.reset()
            return True
        return False

    def next_level(self):
        if self.current_level_index + 1 < self.unlocked_level_count:
            self.current_level_index += 1
            self.reset()
            return True
        return False

    def retry_level(self):
        self.reset()

    def _check_goal(self, object_manager):
        """Check whether all goal slots have compatible blocks nearby."""
        level = self.get_current_level()
        slots = level.get('goal_slots', [])
        matches = []
        used = set()

        for slot in slots:
            matched_block = None
            tolerance = slot.get('tolerance', level.get('tolerance', 38))
            size_tolerance = slot.get('size_tolerance', 18)
            for block in object_manager.blocks:
                if id(block) in used or block.is_grabbed:
                    continue
                if block.shape_type != slot['shape_type']:
                    continue
                if abs(block.width - slot['width']) > size_tolerance:
                    continue
                if abs(block.height - slot['height']) > size_tolerance:
                    continue
                if abs(block.x - slot['x']) <= tolerance and abs(block.y - slot['y']) <= tolerance:
                    matched_block = block
                    break

            matches.append(matched_block is not None)
            if matched_block is not None:
                used.add(id(matched_block))

        self.last_goal_matches = matches
        if slots and all(matches):
            self.completion_timer += 1
            if self.completion_timer >= self.completion_hold_frames:
                self.level_completed = True
                self.unlocked_level_count = max(
                    self.unlocked_level_count,
                    min(len(self.levels), self.current_level_index + 2)
                )
                return True
        else:
            self.completion_timer = 0
        return False

    def update_goal_state(self, object_manager):
        return self._check_goal(object_manager)

    def process_hand(self, hand_data, object_manager):
        """
        Process hand data and interact with blocks.

        Args:
            hand_data: HandData from camera
            object_manager: ObjectManager instance

        Returns:
            dict with interaction results
        """
        results = {
            'grabbed_block': None,
            'released_block': None,
        }

        if hand_data is None or not hand_data.is_valid():
            # No hand detected - release any grabbed blocks
            grabbed = object_manager.get_grabbed_blocks()
            for block in grabbed:
                block.release()
                results['released_block'] = block
            self._was_grabbing = False
            return results

        # Get hand position (normalized 0-1)
        palm_x = hand_data.palm_x
        palm_y = hand_data.palm_y

        # Apply smoothing to raw hand position
        if self._smooth_x == 0.5:  # First frame init
            self._smooth_x = palm_x
            self._smooth_y = palm_y
        self._smooth_x = self._smooth_x * (1 - self._smooth_factor) + palm_x * self._smooth_factor
        self._smooth_y = self._smooth_y * (1 - self._smooth_factor) + palm_y * self._smooth_factor

        # Clamp to safe bounds (avoid edge detection issues)
        safe_margin = 0.05
        smooth_x = max(safe_margin, min(1 - safe_margin, self._smooth_x))
        smooth_y = max(safe_margin, min(1 - safe_margin, self._smooth_y))

        # Scale to window coordinates
        window_width = self.config.get('window_width', 1280)
        window_height = self.config.get('window_height', 720)

        # Apply sensitivity - amplify small hand movements to larger game movements
        raw_x = smooth_x * window_width
        raw_y = smooth_y * window_height

        # Accumulate movement with sensitivity
        dx = raw_x - self._last_hand_pos[0]
        dy = raw_y - self._last_hand_pos[1]
        self._accumulated_dx += dx * self.sensitivity
        self._accumulated_dy += dy * self.sensitivity

        # Clamp accumulated movement
        max_move = 32  # Max pixels per frame
        self._accumulated_dx = max(-max_move, min(max_move, self._accumulated_dx))
        self._accumulated_dy = max(-max_move, min(max_move, self._accumulated_dy))

        game_x = self._last_hand_pos[0] + self._accumulated_dx
        game_y = self._last_hand_pos[1] + self._accumulated_dy

        # Calculate hand velocity for throw momentum
        self._hand_velocity = (dx * 0.5, dy * 0.5)
        self._last_hand_pos = (raw_x, raw_y)

        is_grabbing = hand_data.gesture.value == 'grab'

        # Find nearest block within grab range
        grab_range = self.grab_distance_threshold
        nearest_block = object_manager.get_block_at(game_x, game_y, grab_range)

        # Handle grab action
        if is_grabbing and not self._was_grabbing:
            # Started grabbing
            if nearest_block:
                nearest_block.grab(game_x, game_y)
                results['grabbed_block'] = nearest_block

        elif is_grabbing and self._was_grabbing:
            # Continuing to grab - move the block
            grabbed = object_manager.get_grabbed_blocks()
            if grabbed:
                block = grabbed[-1]
                block.move_to(game_x, game_y)

        elif not is_grabbing and self._was_grabbing:
            # Released grab
            grabbed = object_manager.get_grabbed_blocks()
            for block in grabbed:
                vx, vy = self._hand_velocity
                block.release(vx, vy)
                results['released_block'] = block

        self._was_grabbing = is_grabbing
        self._check_goal(object_manager)
        return results

    def get_stats(self):
        """Get game statistics (for display purposes only)."""
        return {
            'blocks_grabbed': 0,
            'level': self.current_level_index + 1,
            'unlocked': self.unlocked_level_count,
            'completed': self.level_completed,
        }


def _slot(cx, cy, shape_type, width, height, color, label='', tolerance=42):
    return {
        'x': cx,
        'y': cy,
        'shape_type': shape_type,
        'width': width,
        'height': height,
        'color': color,
        'label': label,
        'tolerance': tolerance,
    }


def _block(x, y, shape_type, width, height, color):
    return {
        'x': x,
        'y': y,
        'shape_type': shape_type,
        'width': width,
        'height': height,
        'color': color,
    }


def create_levels(config):
    """Create five fixed puzzle levels with tolerant placement targets."""
    w = config.get('window_width', 1280)
    platform_y = config.get('platform_y', 500)
    cx = w // 2
    red = (255, 120, 120)
    green = (120, 220, 130)
    blue = (120, 150, 255)
    yellow = (255, 220, 90)
    orange = (255, 170, 90)
    purple = (180, 120, 255)
    brown = (160, 110, 70)

    square = (0, 56, 56)
    triangle = (1, 76, 76)
    rect = (0, 112, 56)
    tall = (0, 56, 112)

    return [
        {
            'name': '认识图形',
            'objective': '把每种图形各放一次到亮起的位置。',
            'platform_y': platform_y,
            'platform_width': 520,
            'tolerance': 48,
            'goal_slots': [
                _slot(cx - 150, platform_y - 38, square[0], square[1], square[2], red, '正方形'),
                _slot(cx, platform_y - 38, rect[0], rect[1], rect[2], blue, '长方形'),
                _slot(cx + 150, platform_y - 48, triangle[0], triangle[1], triangle[2], yellow, '三角形'),
            ],
            'blocks': [
                _block(cx - 430, 170, square[0], square[1], square[2], red),
                _block(cx + 430, 165, rect[0], rect[1], rect[2], blue),
                _block(cx - 500, 310, triangle[0], triangle[1], triangle[2], yellow),
                _block(cx + 500, 315, square[0], square[1], square[2], green),
                _block(cx - 380, 365, rect[0], rect[1], rect[2], purple),
                _block(cx + 380, 330, triangle[0], triangle[1], triangle[2], orange),
                _block(cx - 470, 455, square[0], square[1], square[2], blue),
                _block(cx + 470, 430, tall[0], tall[1], tall[2], yellow),
            ],
        },
        {
            'name': '小屋顶练习',
            'objective': '把一个三角形稳稳放到一个长方形上。',
            'platform_y': platform_y,
            'platform_width': 480,
            'goal_slots': [
                _slot(cx, platform_y - 38, rect[0], rect[1], rect[2], blue, '墙体'),
                _slot(cx, platform_y - 104, triangle[0], triangle[1], triangle[2], yellow, '屋顶'),
            ],
            'blocks': [
                _block(cx - 430, 190, rect[0], rect[1], rect[2], blue),
                _block(cx + 430, 190, triangle[0], triangle[1], triangle[2], yellow),
                _block(cx - 500, 335, square[0], square[1], square[2], green),
                _block(cx + 500, 335, rect[0], rect[1], rect[2], orange),
                _block(cx - 385, 420, triangle[0], triangle[1], triangle[2], purple),
                _block(cx + 385, 430, square[0], square[1], square[2], red),
                _block(cx - 470, 430, tall[0], tall[1], tall[2], brown),
            ],
        },
        {
            'name': '搭建小房子',
            'objective': '拼出有墙、有门、有屋顶的小房子。',
            'platform_y': platform_y,
            'platform_width': 560,
            'goal_slots': [
                _slot(cx - 92, platform_y - 38, square[0], square[1], square[2], orange, '左墙'),
                _slot(cx - 24, platform_y - 38, square[0], square[1], square[2], orange, '右墙'),
                _slot(cx + 76, platform_y - 66, tall[0], tall[1], tall[2], brown, '门'),
                _slot(cx - 58, platform_y - 118, triangle[0], triangle[1], triangle[2], yellow, '屋顶'),
            ],
            'blocks': [
                _block(cx - 430, 170, square[0], square[1], square[2], orange),
                _block(cx - 500, 305, square[0], square[1], square[2], orange),
                _block(cx + 430, 180, tall[0], tall[1], tall[2], brown),
                _block(cx + 500, 335, triangle[0], triangle[1], triangle[2], yellow),
                _block(cx - 385, 425, rect[0], rect[1], rect[2], blue),
                _block(cx + 385, 430, square[0], square[1], square[2], green),
                _block(cx - 470, 430, triangle[0], triangle[1], triangle[2], purple),
                _block(cx + 470, 430, rect[0], rect[1], rect[2], red),
                _block(cx - 380, 300, tall[0], tall[1], tall[2], brown),
            ],
        },
        {
            'name': '搭建一棵树',
            'objective': '用一个长方形和三个三角形从下到上叠成一棵树。',
            'platform_y': platform_y,
            'platform_width': 520,
            'goal_slots': [
                _slot(cx, platform_y - 66, tall[0], tall[1], tall[2], brown, '树干'),
                _slot(cx, platform_y - 160, triangle[0], triangle[1], triangle[2], green, '树冠1'),
                _slot(cx, platform_y - 236, triangle[0], triangle[1], triangle[2], green, '树冠2'),
                _slot(cx, platform_y - 312, triangle[0], triangle[1], triangle[2], green, '树冠3'),
            ],
            'blocks': [
                _block(cx - 430, 170, tall[0], tall[1], tall[2], brown),
                _block(cx + 430, 160, triangle[0], triangle[1], triangle[2], green),
                _block(cx + 500, 315, triangle[0], triangle[1], triangle[2], green),
                _block(cx - 500, 315, triangle[0], triangle[1], triangle[2], green),
                _block(cx - 385, 430, square[0], square[1], square[2], purple),
                _block(cx + 385, 425, triangle[0], triangle[1], triangle[2], yellow),
                _block(cx - 470, 420, rect[0], rect[1], rect[2], blue),
                _block(cx + 470, 430, square[0], square[1], square[2], red),
                _block(cx - 370, 305, tall[0], tall[1], tall[2], orange),
            ],
        },
        {
            'name': '搭建小桥',
            'objective': '用两个桥墩和一块桥面搭建一座小桥。',
            'platform_y': platform_y,
            'platform_width': 560,
            'goal_slots': [
                _slot(cx - 84, platform_y - 66, tall[0], tall[1], tall[2], purple, '桥墩'),
                _slot(cx + 84, platform_y - 66, tall[0], tall[1], tall[2], purple, '桥墩'),
                _slot(cx, platform_y - 150, rect[0], rect[1] + 42, rect[2], blue, '桥面'),
                _slot(cx, platform_y - 236, triangle[0], triangle[1], triangle[2], yellow, '小旗'),
            ],
            'blocks': [
                _block(cx - 430, 180, tall[0], tall[1], tall[2], purple),
                _block(cx + 430, 185, tall[0], tall[1], tall[2], purple),
                _block(cx - 500, 355, rect[0], rect[1] + 42, rect[2], blue),
                _block(cx + 500, 350, triangle[0], triangle[1], triangle[2], yellow),
                _block(cx - 385, 455, square[0], square[1], square[2], red),
                _block(cx + 385, 440, rect[0], rect[1], rect[2], green),
                _block(cx - 470, 430, triangle[0], triangle[1], triangle[2], orange),
                _block(cx + 470, 430, square[0], square[1], square[2], blue),
                _block(cx - 380, 315, tall[0], tall[1], tall[2], brown),
            ],
        },
    ]
