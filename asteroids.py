import math
import random
import sys
from typing import List, Tuple

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame

# ------------------------
# Config
# ------------------------
WIDTH, HEIGHT = 900, 700
FPS = 60

SHIP_RADIUS = 12
SHIP_TURN_SPEED = 220          # deg/sec
SHIP_THRUST_FORWARD = 220              # px/sec^2
SHIP_THRUST_BACKWARD = -110              # px/sec^2
SHIP_MAX_SPEED = 420
SHIP_INVULN_TIME = 2.0         # seconds after respawn
SHIP_RESPAWN_DELAY = 1.0
START_LIVES = 3

BULLET_SPEED = 550
BULLET_LIFETIME = 1.2
FIRE_COOLDOWN = 0.05

ASTEROID_MIN_SPEED = 40
ASTEROID_MAX_SPEED = 80
ASTEROID_SIZES = {
    3: {"radius": 48, "score": 20, "children": 2},
    2: {"radius": 28, "score": 50, "children": 2},
    1: {"radius": 16, "score": 100, "children": 0},
}

STAR_COUNT = 80

# ------------------------
# Helpers
# ------------------------
Vec = pygame.math.Vector2


def wrap_position(pos: Vec) -> Vec:
    x, y = pos
    return Vec(x % WIDTH, y % HEIGHT)


def angle_to_vector(angle_deg: float) -> Vec:
    rad = math.radians(angle_deg)
    return Vec(math.cos(rad), math.sin(rad))


def random_spawn_point(avoid: Vec = None, min_dist: float = 160) -> Vec:
    while True:
        p = Vec(random.uniform(0, WIDTH), random.uniform(0, HEIGHT))
        if avoid is None or p.distance_to(avoid) >= min_dist:
            return p

# ------------------------
# Entities
# ------------------------


class Ship:
    def __init__(self, pos: Vec):
        self.pos = Vec(pos)
        self.vel = Vec(0, 0)
        self.angle = -90  # facing up
        self.thrusting = False
        self.thrus_forward = False
        self.alive = True
        self.invuln = 0.0
        self.respawn_timer = 0.0

    def update(self, dt: float, keys):
        if not self.alive:
            self.respawn_timer -= dt
            if self.respawn_timer <= 0:
                self.alive = True
                self.invuln = SHIP_INVULN_TIME
            return

        turn = 0
        if keys[pygame.K_LEFT]:
            turn -= 1
        if keys[pygame.K_RIGHT]:
            turn += 1
        self.angle += turn * SHIP_TURN_SPEED * dt

        self.thrusting = keys[pygame.K_UP] or keys[pygame.K_DOWN]
        self.thrust_forward = bool(keys[pygame.K_UP])
        if self.thrusting:
            thrust_vec = SHIP_THRUST_FORWARD if self.thrust_forward else SHIP_THRUST_BACKWARD
            self.vel += angle_to_vector(self.angle) * thrust_vec * dt

        # Clamp speed
        if self.vel.length() > SHIP_MAX_SPEED:
            self.vel.scale_to_length(SHIP_MAX_SPEED)

        self.pos = wrap_position(self.pos + self.vel * dt)
        if self.invuln > 0:
            self.invuln -= dt

    def kill(self):
        self.alive = False
        self.vel = Vec(0, 0)
        self.pos = Vec(WIDTH / 2, HEIGHT / 2)
        self.angle = -90
        self.respawn_timer = SHIP_RESPAWN_DELAY

    def shape_points(self) -> List[Tuple[float, float]]:
        # A simple triangle ship
        forward = angle_to_vector(self.angle)
        right = angle_to_vector(self.angle + 140)
        left = angle_to_vector(self.angle - 140)
        tip = self.pos + forward * (SHIP_RADIUS * 1.8)
        p2 = self.pos + right * SHIP_RADIUS
        p3 = self.pos + left * SHIP_RADIUS
        return [tip, p2, p3]

    def draw(self, surf):
        if not self.alive:
            return
        color = (255, 255, 255)
        if self.invuln > 0 and int(self.invuln * 10) % 2 == 0:
            color = (140, 140, 140)  # flicker while invulnerable
        pygame.draw.polygon(surf, color, self.shape_points(), width=2)
        # thrust flame
        if self.thrusting:
            back = self.pos - angle_to_vector(self.angle) * (SHIP_RADIUS * 1.2)
            jitter = random.uniform(0.8, 1.2)
            flame = [
                back + angle_to_vector(self.angle + 180 +
                                       20) * SHIP_RADIUS * 0.9,
                back - angle_to_vector(self.angle) *
                SHIP_RADIUS * 1.7 * jitter,
                back + angle_to_vector(self.angle + 180 -
                                       20) * SHIP_RADIUS * 0.9,
            ]
            flame_color = (255, 200, 80) if self.thrust_forward else (0, 128, 255)
            pygame.draw.polygon(surf, flame_color, flame, width=1)

    def radius(self) -> float:
        return SHIP_RADIUS


class Bullet:
    def __init__(self, pos: Vec, angle: float):
        self.pos = Vec(pos)
        self.vel = angle_to_vector(angle) * BULLET_SPEED
        self.life = BULLET_LIFETIME

    def update(self, dt: float):
        self.pos = wrap_position(self.pos + self.vel * dt)
        self.life -= dt

    def dead(self) -> bool:
        return self.life <= 0

    def draw(self, surf):
        pygame.draw.circle(surf, (255, 255, 255), self.pos, 2)


class Asteroid:
    def __init__(self, pos: Vec, size: int):
        self.pos = Vec(pos)
        self.size = size  # 1 small, 2 medium, 3 large
        speed = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED)
        angle = random.uniform(0, 360)
        self.vel = angle_to_vector(angle) * speed
        self.rot = random.uniform(-60, 60)  # deg/sec
        self.angle = random.uniform(0, 360)
        self.radius = ASTEROID_SIZES[size]["radius"]
        # Generate a jagged polygon
        self.points = []
        verts = random.randint(8, 12)
        for i in range(verts):
            a = (i / verts) * 2 * math.pi
            r = self.radius * random.uniform(0.75, 1.15)
            self.points.append(Vec(math.cos(a) * r, math.sin(a) * r))

    def update(self, dt: float):
        self.pos = wrap_position(self.pos + self.vel * dt)
        self.angle += self.rot * dt

    def draw(self, surf):
        rot_points = []
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        for p in self.points:
            x = p.x * cos_a - p.y * sin_a
            y = p.x * sin_a + p.y * cos_a
            rot_points.append((self.pos.x + x, self.pos.y + y))
        pygame.draw.polygon(surf, (255, 255, 255), rot_points, width=2)

    def split(self) -> List["Asteroid"]:
        children = []
        child_count = ASTEROID_SIZES[self.size]["children"]
        if child_count == 0:
            return children
        for _ in range(child_count):
            child = Asteroid(self.pos, self.size - 1)
            # Give children a little extra push
            child.vel = self.vel.rotate(
                random.uniform(-40, 40)) * random.uniform(1.1, 1.5)
            children.append(child)
        return children

# ------------------------
# Game
# ------------------------


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Asteroids (Pygame)")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("consolas", 22)
        self.big_font = pygame.font.SysFont("consolas", 48)
        self.reset(full=True)
        self.stars = [(random.randrange(WIDTH), random.randrange(HEIGHT), random.choice((1, 2)))
                      for _ in range(STAR_COUNT)]
        self.fire_timer = 0.0

    def reset(self, full=False):
        self.ship = Ship(Vec(WIDTH / 2, HEIGHT / 2))
        if full:
            self.lives = START_LIVES
            self.score = 0
            self.wave = 0
        self.bullets: List[Bullet] = []
        self.asteroids: List[Asteroid] = []
        self.spawn_wave()

    def spawn_wave(self):
        self.wave += 1
        # Spawn 3 + wave asteroids (cap a bit)
        count = min(6 + self.wave, 10)
        self.asteroids.clear()
        for _ in range(count):
            a = Asteroid(random_spawn_point(
                avoid=self.ship.pos, min_dist=220), size=3)
            self.asteroids.append(a)

    def handle_input(self, dt: float):
        keys = pygame.key.get_pressed()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
                if event.key == pygame.K_r and self.lives <= 0:
                    self.reset(full=True)

        # Ship updates include reading keys
        self.ship.update(dt, keys)

        # shooting
        self.fire_timer -= dt
        if self.ship.alive and self.fire_timer <= 0 and keys[pygame.K_SPACE]:
            self.bullets.append(Bullet(self.ship.pos + angle_to_vector(self.ship.angle) * SHIP_RADIUS * 1.6,
                                       self.ship.angle))
            self.fire_timer = FIRE_COOLDOWN

    def update_world(self, dt: float):
        # Update bullets
        for b in self.bullets:
            b.update(dt)
        self.bullets = [b for b in self.bullets if not b.dead()]

        # Update asteroids
        for a in self.asteroids:
            a.update(dt)

        # Collisions: bullets vs asteroids
        new_asteroids: List[Asteroid] = []
        for a in self.asteroids:
            hit = None
            for b in self.bullets:
                if a.pos.distance_to(b.pos) <= a.radius:
                    hit = b
                    break
            if hit:
                self.score += ASTEROID_SIZES[a.size]["score"]
                self.bullets.remove(hit)
                new_asteroids.extend(a.split())
            else:
                new_asteroids.append(a)
        self.asteroids = new_asteroids

        # Collisions: ship vs asteroids
        if self.ship.alive and self.ship.invuln <= 0:
            for a in self.asteroids:
                if self.ship.pos.distance_to(a.pos) <= (a.radius + self.ship.radius()):
                    # ship dies
                    self.lives -= 1
                    self.ship.kill()
                    break
        else:
            # still advance timers even if invulnerable
            pass

        # Wave clear
        if not self.asteroids:
            self.spawn_wave()

    def draw_hud(self):
        # score/lives
        score_s = self.font.render(
            f"Score: {self.score}", True, (255, 255, 255))
        lives_s = self.font.render(
            f"Lives: {self.lives}", True, (255, 255, 255))
        wave_s = self.font.render(f"Wave: {self.wave}", True, (255, 255, 255))
        self.screen.blit(score_s, (12, 10))
        self.screen.blit(lives_s, (12, 36))
        self.screen.blit(wave_s, (12, 62))

        if self.lives <= 0:
            overlay = self.big_font.render(
                "GAME OVER - Press R to Restart", True, (255, 180, 180))
            rect = overlay.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            self.screen.blit(overlay, rect)

    def draw_background(self):
        self.screen.fill((5, 5, 10))
        # parallax-ish twinkle stars
        for (x, y, r) in self.stars:
            pygame.draw.circle(self.screen, (200, 200, 200), (x, y), r)

    def draw(self):
        self.draw_background()
        # asteroids
        for a in self.asteroids:
            a.draw(self.screen)
        # bullets
        for b in self.bullets:
            b.draw(self.screen)
        # ship
        self.ship.draw(self.screen)
        # HUD
        self.draw_hud()

        pygame.display.flip()

    def run(self):
        while True:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_input(dt)
            if self.lives > 0:
                self.update_world(dt)
            self.draw()


# ------------------------
# Main
# ------------------------
if __name__ == "__main__":
    Game().run()
