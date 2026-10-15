"""Entry point: python main.py"""

import sys

import pygame

from game import Game, WIDTH, HEIGHT
from logger import EventLogger


def make_fonts():
    # Pygame's built-in default font (None) - no font files needed.
    return {
        "title": pygame.font.Font(None, 84),
        "large": pygame.font.Font(None, 48),
        "medium": pygame.font.Font(None, 36),
        "small": pygame.font.Font(None, 28),
    }


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Co-op Puzzle Game")
    clock = pygame.time.Clock()
    fonts = make_fonts()

    game = Game(EventLogger())
    running = True
    try:
        while running:
            dt = clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                    else:
                        game.handle_key(event.key)
            game.update(dt)
            game.draw(screen, fonts)
            pygame.display.flip()
    finally:
        game.shutdown()     # logs session_end and closes the CSV
        pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
