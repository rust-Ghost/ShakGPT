import pygame, os

class BackgroundMusic:
    def __init__(self, file):
        pygame.mixer.init()
        if os.path.exists(file):
            pygame.mixer.music.load(file)
            pygame.mixer.music.set_volume(0.3)

    def play(self):
        pygame.mixer.music.play(-1)
