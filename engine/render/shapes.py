import pygame
from typing import Tuple


def draw_text(surface: pygame.Surface, text: str, pos: Tuple[int, int], color=(230, 230, 230), size=24):
    font = pygame.font.SysFont(None, size)
    surface.blit(font.render(text, True, color), pos)
