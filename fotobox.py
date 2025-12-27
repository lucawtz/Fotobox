import RPi.GPIO as GPIO
import time
import pygame
import os

# ======================
# GPIO Setup
# ======================
GPIO.setmode(GPIO.BCM)  # BCM Nummerierung
BUTTON_PHOTO = 17       # GPIO Pin für Foto
GPIO.setup(BUTTON_PHOTO, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# ======================
# Pfade & Pygame Setup
# ======================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
LAYOUT_PATH = os.path.join(BASE_DIR, "Layout", "Overlay_Allgemein.png")
PICTURE_PATH = os.path.join(BASE_DIR, "Picture_Box")
os.makedirs(PICTURE_PATH, exist_ok=True)

pygame.init()
screen = pygame.display.set_mode((1920, 1080), pygame.FULLSCREEN)
overlay = pygame.image.load(LAYOUT_PATH).convert_alpha()

# ======================
# Funktionen
# ======================
def take_photo():
    countdown_time = 3
    font = pygame.font.Font(None, 200)
    
    for i in range(countdown_time, 0, -1):
        screen.fill((0,0,0))
        screen.blit(overlay, (0,0))
        text = font.render(str(i), True, (255, 255, 255))
        text_rect = text.get_rect(center=(960, 540))
        screen.blit(text, text_rect)
        pygame.display.flip()
        time.sleep(1)
    
    timestamp = int(time.time())
    photo_file = os.path.join(PICTURE_PATH, f"foto_{timestamp}.png")
    pygame.image.save(screen, photo_file)
    print(f"Foto gespeichert: {photo_file}")

# ======================
# Main Loop
# ======================
running = True
while running:
    # Knopf abfragen
    if GPIO.input(BUTTON_PHOTO) == GPIO.LOW:  # gedrückt
        take_photo()
        time.sleep(0.5)  # Entprellung
    
    # Pygame Events prüfen
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_q:
            running = False

    # Overlay anzeigen
    screen.fill((0,0,0))
    screen.blit(overlay, (0,0))
    pygame.display.flip()

pygame.quit()
GPIO.cleanup()
