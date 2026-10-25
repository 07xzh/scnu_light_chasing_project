"""
Game objects - Platform and Draggable Blocks
"""

import pygame
import math
import random


class Platform:
    """Static platform for building blocks."""

    def __init__(self, x, y, width, height):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.rect = pygame.Rect(x - width//2, y - height//2, width, height)

    def draw(self, surface):
        """Draw the platform."""
        # Main platform body
        pygame.draw.rect(surface, (80, 80, 120), self.rect, border_radius=5)

        # Top edge highlight
        pygame.draw.rect(surface, (120, 120, 160), self.rect, 2, border_radius=5)

        # Grid pattern on platform
        for gx in range(self.rect.x, self.rect.right, 20):
            pygame.draw.line(surface, (60, 60, 100), (gx, self.rect.top), (gx, self.rect.bottom), 1)


class Block:
    """Draggable block with physics."""

    def __init__(self, x, y, width, height, color, shape_type=0):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.color = color
        self.original_color = color
        self.shape_type = shape_type  # 0=rect, 1=triangle, 2=diamond, 3=hexagon

        # Physics - tuned for stable stacking, minimal shaking
        self.vx = 0
        self.vy = 0
        self.gravity = 0.4  # Lower gravity for precision
        self.friction = 0.7  # Higher friction
        self.bounce = 0.01  # Almost no bounce
        self.max_speed = 8  # Lower max speed

        # State
        self.is_grabbed = False
        self.grab_offset_x = 0
        self.grab_offset_y = 0
        self.rotation = 0
        self.rotation_speed = 0  # No rotation

        # Visual
        self.glow_timer = 0
        self._bounce_count = 0

    @property
    def rect(self):
        return pygame.Rect(
            self.x - self.width // 2,
            self.y - self.height // 2,
            self.width,
            self.height
        )

    @property
    def size(self):
        return (self.width + self.height) // 2

    def get_collision_radius(self):
        """Get effective collision radius."""
        return max(self.width, self.height) // 2

    def _get_points(self):
        """Get shape points for drawing."""
        hw, hh = self.width // 2, self.height // 2
        cx, cy = self.x, self.y

        if self.shape_type == 0:  # Rectangle
            return [
                (cx - hw, cy - hh), (cx + hw, cy - hh),
                (cx + hw, cy + hh), (cx - hw, cy + hh)
            ]
        elif self.shape_type == 1:  # Triangle (pointing up)
            return [
                (cx, cy - hh),  # Top
                (cx + hw, cy + hh),  # Bottom right
                (cx - hw, cy + hh)   # Bottom left
            ]
        elif self.shape_type == 2:  # Diamond
            return [
                (cx, cy - hh),  # Top
                (cx + hw, cy),  # Right
                (cx, cy + hh),  # Bottom
                (cx - hw, cy)   # Left
            ]
        elif self.shape_type == 3:  # Hexagon
            w = hw * 0.8
            h = hh * 0.8
            return [
                (cx - w, cy - h), (cx + w, cy - h),
                (cx + w + w*0.3, cy), (cx + w, cy + h),
                (cx - w, cy + h), (cx - w - w*0.3, cy)
            ]
        return [(cx - hw, cy - hh), (cx + hw, cy - hh),
                (cx + hw, cy + hh), (cx - hw, cy + hh)]

    def _get_collision_rects(self):
        """Get collision rectangles for non-rect shapes."""
        if self.shape_type == 0:
            return [self.rect]
        # For other shapes, use a slightly smaller rect
        shrink = 4
        return [self.rect.inflate(-shrink, -shrink)]

    def grab(self, hand_x, hand_y):
        """Grab the block at hand position."""
        self.is_grabbed = True
        self.grab_offset_x = self.x - hand_x
        self.grab_offset_y = self.y - hand_y
        self.vx = 0
        self.vy = 0
        self.color = (255, 200, 100)  # Highlight color

    def release(self, vx=0, vy=0):
        """Release the block with velocity."""
        self.is_grabbed = False
        self.color = self.original_color
        self.vx = vx * 0.3
        self.vy = vy * 0.3
        self._bounce_count = 0

    def move_to(self, x, y):
        """Move block to hand position."""
        if self.is_grabbed:
            # Smooth follow
            target_x = x + self.grab_offset_x
            target_y = y + self.grab_offset_y
            self.vx = (target_x - self.x) * 0.5
            self.vy = (target_y - self.y) * 0.5
            self.x = target_x
            self.y = target_y

    def update(self, dt, window_width, window_height, platforms):
        """Update block physics with sub-stepping for accuracy."""
        if self.is_grabbed:
            return

        # Sub-stepping for better collision detection
        steps = 4
        for _ in range(steps):
            # Apply gravity (reduced per step)
            self.vy += self.gravity * 0.25

            # Apply friction
            self.vx *= self.friction

            # Clamp velocity
            self.vx = max(-self.max_speed, min(self.max_speed, self.vx))
            self.vy = max(-self.max_speed, min(self.max_speed, self.vy))

            # Update position (smaller steps)
            self.x += self.vx / steps
            self.y += self.vy / steps

            # Platform collisions - check at each sub-step
            self._handle_platform_collisions(platforms, window_width, window_height)

            # Wall collisions
            self._handle_wall_collisions(window_width, window_height)

    def _handle_platform_collisions(self, platforms, window_width, window_height):
        """Handle collision with platforms - robust detection using rect."""
        for platform in platforms:
            plat_rect = platform.rect

            # Check if rects overlap
            if not self.rect.colliderect(plat_rect):
                continue

            # If block is above or at platform level, snap to top
            if self.rect.bottom >= plat_rect.top:
                self.y = plat_rect.top - self.height // 2
                if self.vy > 0:
                    self.vy = 0
                self.vx *= 0.85
                self._bounce_count = 0

    def _handle_wall_collisions(self, window_width, window_height):
        """Handle collision with window boundaries."""
        half_w = self.width // 2
        half_h = self.height // 2

        # Left wall
        if self.x - half_w < 0:
            self.x = half_w
            self.vx = -self.vx * self.bounce

        # Right wall
        if self.x + half_w > window_width:
            self.x = window_width - half_w
            self.vx = -self.vx * self.bounce

        # Top wall
        if self.y - half_h < 0:
            self.y = half_h
            self.vy = -self.vy * self.bounce

        # Bottom wall (ground)
        if self.y + half_h > window_height:
            self.y = window_height - half_h
            if abs(self.vy) > 1:
                self.vy = -self.vy * self.bounce
                self._bounce_count += 1
            else:
                self.vy = 0

    def contains_point(self, x, y):
        """Check if point is within block (with generous hit area for easier grab)."""
        # Use larger hit area for easier grabbing
        hw = self.width // 2 * 1.25
        hh = self.height // 2 * 1.25
        return (abs(x - self.x) <= hw and abs(y - self.y) <= hh)

    def collides_with(self, other):
        """Check collision with another block using AABB."""
        # Simple AABB collision
        return self.rect.colliderect(other.rect)

    def handle_collision(self, other):
        """Resolve collision - blocks push apart, no overlap."""
        if self.is_grabbed or other.is_grabbed:
            return

        # Get bounding rectangles
        self_rect = self.rect
        other_rect = other.rect

        # Check if rects actually overlap
        if not self_rect.colliderect(other_rect):
            return

        # Calculate center positions
        self_cx = self_rect.centerx
        self_cy = self_rect.centery
        other_cx = other_rect.centerx
        other_cy = other_rect.centery

        # Determine which block is on top based on center y position
        if self_cy < other_cy:
            # self is above other - should stack on top
            # Only resolve as vertical stack, ignore horizontal offset
            self.y = other_rect.top - self.height // 2
            self.vy = 0
            self.vx *= 0.8
        else:
            # other is above self - other should be on top
            other.y = self_rect.top - other.height // 2
            other.vy = 0
            other.vx *= 0.8

    def trigger_glow(self):
        """Trigger glow effect."""
        self.glow_timer = 1.0

    def draw(self, surface):
        """Draw the block."""
        glow = self.glow_timer * 0.5 if self.glow_timer > 0 else 0
        points = self._get_points()

        # Glow effect
        if glow > 0:
            glow_surf = pygame.Surface((self.width + 20, self.height + 20), pygame.SRCALPHA)
            glow_color = (*self.color, int(80 * glow))
            if self.shape_type == 0:
                pygame.draw.rect(glow_surf, glow_color,
                               (10, 10, self.width, self.height), border_radius=6)
            else:
                offset_points = [(p[0] - self.x + 10, p[1] - self.y + 10) for p in points]
                pygame.draw.polygon(glow_surf, glow_color, offset_points)
            surface.blit(glow_surf, (self.x - self.width//2 - 10, self.y - self.height//2 - 10))

        # Draw shape - colorful blocks without white outline
        if self.shape_type == 0:
            # Rectangle - solid color
            pygame.draw.rect(surface, self.color, self.rect, border_radius=6)
            # Subtle inner shadow for depth instead of white border
            inner = self.rect.inflate(-6, -6)
            if inner.width > 0 and inner.height > 0:
                darker = tuple(max(0, c - 30) for c in self.color)
                pygame.draw.rect(surface, darker, inner, border_radius=4)
        else:
            # Polygon shapes - solid color
            pygame.draw.polygon(surface, self.color, points)
            # Subtle inner shadow
            if len(points) >= 3:
                cx = sum(p[0] for p in points) / len(points)
                cy = sum(p[1] for p in points) / len(points)
                inner_scale = 0.7
                inner_points = [
                    (cx + (p[0] - cx) * inner_scale, cy + (p[1] - cy) * inner_scale)
                    for p in points
                ]
                darker = tuple(max(0, c - 30) for c in self.color)
                pygame.draw.polygon(surface, darker, inner_points)


class ObjectManager:
    """Manages blocks and platforms."""

    def __init__(self, config):
        self.config = config
        self.blocks = []
        self.platforms = []
        self.goal_slots = []
        self.goal_matches = []
        self.level_config = None
        self.window_width = config.get('window_width', 1280)
        self.window_height = config.get('window_height', 720)

    def setup_level(self, level_config=None):
        """Set up the level with platform and blocks."""
        self.blocks.clear()
        self.platforms.clear()
        self.level_config = level_config
        self.goal_slots = list(level_config.get('goal_slots', [])) if level_config else []
        self.goal_matches = [False] * len(self.goal_slots)

        # Create central platform
        platform = Platform(
            x=self.window_width // 2,
            y=(level_config or self.config).get('platform_y', self.config.get('platform_y', 450)),
            width=(level_config or self.config).get('platform_width', self.config.get('platform_width', 400)),
            height=self.config.get('platform_height', 20)
        )
        self.platforms.append(platform)

        if level_config and level_config.get('blocks'):
            for item in level_config['blocks']:
                self.blocks.append(Block(
                    item['x'], item['y'],
                    item['width'], item['height'],
                    item['color'], item['shape_type']
                ))
            return

        # Create scattered blocks around the platform
        block_count = self.config.get('object_count', 10)
        colors = self.config.get('block_colors', [
            (255, 120, 120), (120, 255, 120), (120, 120, 255),
            (255, 255, 120), (255, 120, 255), (120, 255, 255),
            (255, 180, 120), (180, 120, 255),
        ])
        shapes = self.config.get('block_shapes', [
            (1.0, 1.0), (2.0, 1.0), (1.0, 2.0), (2.0, 0.5),
        ])

        base_size = 50

        # Pre-assign colors to ensure even distribution
        color_pool = colors * (block_count // len(colors) + 1)
        random.shuffle(color_pool)
        assigned_colors = color_pool[:block_count]

        for i in range(block_count):
            shape = random.choice(shapes)
            shape_type = int(shape[0])
            w = int(base_size * shape[1])
            h = int(base_size * shape[2])
            color = assigned_colors[i]

            # Spawn blocks around the platform - not too far left/right
            attempts = 0
            while attempts < 100:
                side = random.choice(['left', 'right', 'top', 'top_left', 'top_right'])
                if side == 'left':
                    x = random.randint(80, platform.rect.left - 50)
                    y = random.randint(150, 380)
                elif side == 'right':
                    x = random.randint(platform.rect.right + 50, self.window_width - 80)
                    y = random.randint(150, 380)
                elif side == 'top_left':
                    x = random.randint(100, platform.rect.left - 30)
                    y = random.randint(60, 180)
                elif side == 'top_right':
                    x = random.randint(platform.rect.right + 30, self.window_width - 100)
                    y = random.randint(60, 180)
                else:  # top
                    x = random.randint(150, self.window_width - 150)
                    y = random.randint(60, 150)

                # Check not too close to other blocks (relaxed)
                too_close = False
                for block in self.blocks:
                    dist = math.sqrt((block.x - x) ** 2 + (block.y - y) ** 2)
                    if dist < max(w, h) + 20:  # Reduced from +40
                        too_close = True
                        break

                if not too_close:
                    break
                attempts += 1

            block = Block(x, y, w, h, color, shape_type)
            block.vy = 0
            self.blocks.append(block)

    def update(self, dt):
        """Update all objects with multiple passes for stability."""
        # Multiple passes for stable stacking
        for _ in range(3):
            for block in self.blocks:
                block.update(dt, self.window_width, self.window_height, self.platforms)

            # Handle block-to-block collisions (multiple passes)
            for _ in range(2):
                for i in range(len(self.blocks)):
                    for j in range(i + 1, len(self.blocks)):
                        if self.blocks[i].collides_with(self.blocks[j]):
                            self.blocks[i].handle_collision(self.blocks[j])

    def set_goal_matches(self, matches):
        self.goal_matches = list(matches)

    def get_block_at(self, x, y, grab_radius=0):
        """Get topmost block at position, or nearest block inside grab radius."""
        for block in reversed(self.blocks):
            if block.contains_point(x, y):
                return block
        if grab_radius <= 0:
            return None

        nearest = None
        nearest_score = grab_radius
        for block in reversed(self.blocks):
            dx = block.x - x
            dy = block.y - y
            score = math.sqrt(dx * dx + dy * dy) - block.get_collision_radius()
            if score < nearest_score:
                nearest = block
                nearest_score = score
        if nearest is not None and nearest_score <= grab_radius:
            return nearest
        return None

    def draw(self, surface):
        """Draw all objects."""
        self._draw_goal_slots(surface)

        # Draw platforms
        for platform in self.platforms:
            platform.draw(surface)

        # Draw blocks
        for block in self.blocks:
            block.draw(surface)

    def _draw_goal_slots(self, surface):
        """Draw translucent target silhouettes for the current puzzle."""
        font = pygame.font.Font(None, 18)
        for index, slot in enumerate(self.goal_slots):
            matched = index < len(self.goal_matches) and self.goal_matches[index]
            color = slot.get('color', (255, 255, 255))
            alpha = 95 if not matched else 145
            x, y = slot['x'], slot['y']
            w, h = slot['width'], slot['height']
            rect = pygame.Rect(x - w // 2, y - h // 2, w, h)
            layer = pygame.Surface((w + 20, h + 24), pygame.SRCALPHA)
            local_rect = pygame.Rect(10, 10, w, h)
            draw_color = (*color, alpha)
            outline_color = (255, 255, 255, 210 if matched else 150)

            if slot['shape_type'] == 1:
                points = [(10 + w // 2, 10), (10 + w, 10 + h), (10, 10 + h)]
                pygame.draw.polygon(layer, draw_color, points)
                pygame.draw.polygon(layer, outline_color, points, 3)
            else:
                pygame.draw.rect(layer, draw_color, local_rect, border_radius=6)
                pygame.draw.rect(layer, outline_color, local_rect, 3, border_radius=6)

            if matched:
                pygame.draw.circle(layer, (120, 255, 150, 230), (w + 8, 10), 8)
                pygame.draw.line(layer, (20, 80, 35, 255), (w + 4, 10), (w + 7, 14), 2)
                pygame.draw.line(layer, (20, 80, 35, 255), (w + 7, 14), (w + 13, 6), 2)

            label = slot.get('label', '')
            if label:
                text = font.render(label, True, (230, 230, 235))
                text_rect = text.get_rect(center=(w // 2 + 10, h + 18))
                layer.blit(text, text_rect)

            surface.blit(layer, (rect.x - 10, rect.y - 10))

    def get_grabbed_blocks(self):
        """Get list of grabbed blocks."""
        return [b for b in self.blocks if b.is_grabbed]

    def release_all(self):
        """Release all grabbed blocks."""
        for block in self.blocks:
            if block.is_grabbed:
                block.release()
