# -*- coding: utf-8 -*-
import pygame
import csv
import os
import io
import numpy as np
from PIL import Image
from picamera2 import Picamera2

# Zwingt den Touchscreen, Berührungen als Maus-Events zu behandeln
os.environ["SDL_MOUSE_TOUCH_EVENTS"] = "1"

# ==========================================
# KONFIGURATION
# ==========================================
CSV_FILE = os.path.expanduser("~/barcodes.csv")
SAVE_DIR = os.path.expanduser("~/Pictures/fotobox_custom")
OVERLAY_IMG = os.path.expanduser("~/mein_overlay.png")
ZOOM_FILE = os.path.expanduser("~/fotobox_zoom.txt")
RES_FILE = os.path.expanduser("~/fotobox_res.txt") 
TEMP_IMG = "/tmp/temp_photo.jpg"

COUNTDOWN_SECONDS = 9
KEY_RETAKE = pygame.K_SPACE
KEY_ACCEPT = pygame.K_RETURN

# 5 Vordefinierte Auflösungen im 3:4 Format (Breite, Höhe)
RESOLUTIONS = [
    (480, 640),   # Stufe 1: Sehr schnell
    (720, 960),   # Stufe 2: Guter Kompromiss (Standard)
    (960, 1280),  # Stufe 3: Bessere Qualität
    (1200, 1600), # Stufe 4: Hoch
    (1458, 1944)  # Stufe 5: Maximal
]

# ==========================================
# INITIALISIERUNG PYGAME
# ==========================================
os.makedirs(SAVE_DIR, exist_ok=True)

pygame.init()
pygame.mouse.set_visible(False)
screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
SCREEN_WIDTH, SCREEN_HEIGHT = screen.get_size()

font_large = pygame.font.SysFont("arial", 60, bold=True)
font_medium = pygame.font.SysFont("arial", 40)
font_huge = pygame.font.SysFont("arial", 250, bold=True)

# PROPORTIONALE 3:4 BERECHNUNG FÜR DEN BILDSCHIRM
ratio = min(SCREEN_WIDTH / 3, SCREEN_HEIGHT / 4)
display_w = int(3 * ratio)
display_h = int(4 * ratio)
display_x = (SCREEN_WIDTH - display_w) // 2 
display_y = (SCREEN_HEIGHT - display_h) // 2
display_rect = pygame.Rect(display_x, display_y, display_w, display_h)

# ==========================================
# HILFSFUNKTIONEN (SPEICHERN & LADEN)
# ==========================================
def load_zoom():
    if os.path.exists(ZOOM_FILE):
        try:
            with open(ZOOM_FILE, 'r') as f:
                return float(f.read().strip())
        except:
            pass
    return 1.0

def save_zoom(zoom_factor):
    try:
        with open(ZOOM_FILE, 'w') as f:
            f.write(str(round(zoom_factor, 2)))
    except Exception as e:
        pass

def load_res_idx():
    if os.path.exists(RES_FILE):
        try:
            with open(RES_FILE, 'r') as f:
                idx = int(f.read().strip())
                if 0 <= idx < len(RESOLUTIONS):
                    return idx
        except:
            pass
    return 1  # Standard: Stufe 2

def save_res_idx(idx):
    try:
        with open(RES_FILE, 'w') as f:
            f.write(str(idx))
    except Exception as e:
        pass

# ==========================================
# KAMERA-STEUERUNG
# ==========================================
picam2 = Picamera2()

def apply_zoom(cam2, zoom_factor):
    """
    Fragt dynamisch die echten Hardware-Grenzen ab, 
    damit der Zoom immer exakt zentriert ist - egal bei welchem Kameramodell.
    """
    max_crop = cam2.camera_properties.get("ScalerCropMaximum")
    
    if max_crop is not None:
        sensor_x, sensor_y, sensor_w, sensor_h = max_crop
    else:
        # Fallback, falls die Kamera Eigenschaft nicht meldet
        sensor_x, sensor_y, sensor_w, sensor_h = (0, 0, 2592, 1944) 
        
    # Wir wollen 3:4 Hochformat. Die maximale Höhe bestimmt die Breite.
    base_crop_h = sensor_h
    base_crop_w = int(sensor_h * 0.75) 
    
    # Zoom anwenden
    crop_w = int(base_crop_w / zoom_factor)
    crop_h = int(base_crop_h / zoom_factor)
    
    # Exakte Mitte des physischen Sensors bestimmen
    center_x = sensor_x + (sensor_w / 2.0)
    center_y = sensor_y + (sensor_h / 2.0)
    
    # Kasten um die Mitte aufziehen
    crop_x = int(center_x - (crop_w / 2.0))
    crop_y = int(center_y - (crop_h / 2.0))
    
    cam2.set_controls({"ScalerCrop": (crop_x, crop_y, crop_w, crop_h)})

def set_camera_resolution(idx, current_zoom):
    """Stoppt die Kamera kurz, ändert die Auflösung und startet neu."""
    w, h = RESOLUTIONS[idx]
    
    try:
        picam2.stop()
    except:
        pass
        
    config = picam2.create_preview_configuration(
        main={"size": (w, h), "format": "RGB888"},
        sensor={"output_size": (2592, 1944)} 
    )
    picam2.configure(config)
    picam2.start()
    
    # KURZE PAUSE: Zwingend erforderlich, damit der Autofokus-Befehl 
    # nicht ins Leere läuft, während der Sensor noch bootet.
    pygame.time.wait(300)
    
    # Autofokus und Zoom nach dem Neustart wiederherstellen
    picam2.set_controls({"AfMode": 2})
    apply_zoom(picam2, current_zoom)

# Initialisierung der Kamera mit gespeicherten Werten
zoom_level = load_zoom()
current_res_idx = load_res_idx()
set_camera_resolution(current_res_idx, zoom_level)

# ==========================================
# WEITERE HILFSFUNKTIONEN
# ==========================================
def check_barcode(barcode):
    if not os.path.exists(CSV_FILE):
        return False
    with open(CSV_FILE, mode='r', newline='', encoding='utf-8-sig') as file:
        reader = csv.reader(file)
        for row in reader:
            if len(row) >= 2 and row[0].strip() == barcode:
                if row[1].strip().lower() == "offen":
                    return True
    return False

def mark_barcode_processed(barcode):
    rows = []
    with open(CSV_FILE, mode='r', newline='', encoding='utf-8-sig') as file:
        for row in csv.reader(file):
            if len(row) >= 2 and row[0].strip() == barcode:
                row[1] = "bearbeitet"
            rows.append(row)
    with open(CSV_FILE, mode='w', newline='', encoding='utf-8-sig') as file:
        csv.writer(file).writerows(rows)

def draw_centered_text(text, color=(255, 255, 255), bg_color=(0, 0, 0)):
    screen.fill(bg_color)
    lines = text.split('\n')
    total_height = len(lines) * 70
    start_y = (SCREEN_HEIGHT - total_height) // 2
    for line in lines:
        text_surface = font_large.render(line, True, color)
        screen.blit(text_surface, text_surface.get_rect(center=(SCREEN_WIDTH // 2, start_y)))
        start_y += 70
    pygame.display.update()

def get_pygame_frame():
    frame = picam2.capture_array("main")
    frame = frame[:, :, ::-1]
    frame = np.swapaxes(frame, 0, 1)
    surface = pygame.surfarray.make_surface(frame)
    surface = pygame.transform.rotate(surface, 180)
    return pygame.transform.smoothscale(surface, (display_w, display_h))

# ==========================================
# HAUPTPROGRAMM (STATE MACHINE)
# ==========================================
state = "WAITING"
barcode_buffer = ""
current_barcode = None
btn_retake_rect = None
btn_accept_rect = None

try:
    overlay_surface = pygame.image.load(OVERLAY_IMG).convert_alpha()
    overlay_surface = pygame.transform.smoothscale(overlay_surface, (display_w, display_h))
except:
    overlay_surface = None

running = True
draw_centered_text("Willkommen!\nBitte scanne deinen Barcode.")

while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
            
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

            if state == "WAITING":
                if event.key == pygame.K_z:
                    state = "ZOOM_MODE"
                    barcode_buffer = ""
                    continue

                if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB):
                    scanned_code = barcode_buffer.strip()
                    barcode_buffer = ""
                    if not scanned_code: continue
                        
                    if check_barcode(scanned_code):
                        current_barcode = scanned_code
                        draw_centered_text(f"Code [{current_barcode}] erkannt!\nMach dich bereit...", color=(50, 255, 50))
                        pygame.time.wait(1500)
                        state = "COUNTDOWN"
                    else:
                        draw_centered_text(f"Gelesen: [{scanned_code}]\nUngültig oder schon benutzt!", color=(255, 50, 50))
                        pygame.time.wait(2500)
                        draw_centered_text("Willkommen!\nBitte scanne deinen Barcode.")
                else:
                    if event.unicode.isprintable():
                        barcode_buffer += event.unicode

            elif state == "REVIEW":
                if event.key == KEY_ACCEPT:
                    draw_centered_text("Bild wird gespeichert...")
                    os.rename(TEMP_IMG, os.path.join(SAVE_DIR, f"{current_barcode}.jpg"))
                    mark_barcode_processed(current_barcode)
                    draw_centered_text("Fertig!\nVielen Dank.", color=(50, 255, 50))
                    pygame.time.wait(3000)
                    current_barcode = None
                    state = "WAITING"
                    draw_centered_text("Willkommen!\nBitte scanne deinen Barcode.")
                    
                elif event.key == KEY_RETAKE:
                    draw_centered_text("Neuer Versuch...")
                    pygame.time.wait(1000)
                    state = "COUNTDOWN"

        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.FINGERDOWN):
            if state == "REVIEW":
                pos_x, pos_y = event.pos if event.type == pygame.MOUSEBUTTONDOWN else (int(event.x * SCREEN_WIDTH), int(event.y * SCREEN_HEIGHT))
                if btn_accept_rect and btn_accept_rect.collidepoint(pos_x, pos_y):
                    draw_centered_text("Bild wird gespeichert...")
                    os.rename(TEMP_IMG, os.path.join(SAVE_DIR, f"{current_barcode}.jpg"))
                    mark_barcode_processed(current_barcode)
                    draw_centered_text("Fertig!\nVielen Dank.", color=(50, 255, 50))
                    pygame.time.wait(3000)
                    current_barcode = None
                    state = "WAITING"
                    draw_centered_text("Willkommen!\nBitte scanne deinen Barcode.")
                elif btn_retake_rect and btn_retake_rect.collidepoint(pos_x, pos_y):
                    draw_centered_text("Neuer Versuch...")
                    pygame.time.wait(1000)
                    state = "COUNTDOWN"

    # --- ZUSTAND: ZOOM & AUFLÖSUNG EINRICHTEN ---
    if state == "ZOOM_MODE":
        live_img = get_pygame_frame()
        screen.fill((0, 0, 0)) 
        screen.blit(live_img, display_rect) 

        res_w, res_h = RESOLUTIONS[current_res_idx]
        menu_lines = [
            f"Zoom: {zoom_level:.1f}x  (P: +, M: -)",
            f"Auflösung: Stufe {current_res_idx + 1}/5 [{res_w}x{res_h}]  (H: +, L: -)",
            "Z: Speichern & Beenden"
        ]

        text_surfaces = [font_medium.render(txt, True, (255, 255, 255)) for txt in menu_lines]
        max_w = max(surf.get_width() for surf in text_surfaces)
        total_h = len(text_surfaces) * 45
        
        box_rect = pygame.Rect(0, 0, max_w + 40, total_h + 20)
        box_rect.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - total_h // 2 - 20)
        
        pygame.draw.rect(screen, (0, 0, 0), box_rect)
        pygame.draw.rect(screen, (255, 255, 255), box_rect, 2)
        
        start_y = box_rect.top + 10
        for surf in text_surfaces:
            surf_rect = surf.get_rect(center=(SCREEN_WIDTH // 2, start_y + 22))
            screen.blit(surf, surf_rect)
            start_y += 45

        pygame.display.update()

        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                elif ev.key == pygame.K_z: 
                    save_zoom(zoom_level)
                    save_res_idx(current_res_idx)
                    state = "WAITING"
                    draw_centered_text("Willkommen!\nBitte scanne deinen Barcode.")
                elif ev.key == pygame.K_p: 
                    zoom_level = min(4.0, zoom_level + 0.1)
                    apply_zoom(picam2, zoom_level)
                elif ev.key == pygame.K_m: 
                    zoom_level = max(1.0, zoom_level - 0.1)
                    apply_zoom(picam2, zoom_level)
                elif ev.key == pygame.K_h:
                    if current_res_idx < len(RESOLUTIONS) - 1:
                        current_res_idx += 1
                        set_camera_resolution(current_res_idx, zoom_level)
                elif ev.key == pygame.K_l:
                    if current_res_idx > 0:
                        current_res_idx -= 1
                        set_camera_resolution(current_res_idx, zoom_level)

    # --- ZUSTAND: COUNTDOWN & AUFNAHME ---
    if state == "COUNTDOWN":
        start_ticks = pygame.time.get_ticks()
        countdown_timer = COUNTDOWN_SECONDS
        
        while countdown_timer > 0 and running:
            live_img = get_pygame_frame()
            screen.fill((0, 0, 0)) 
            screen.blit(live_img, display_rect) 

            if overlay_surface:
                screen.blit(overlay_surface, display_rect)

            countdown_surface = font_huge.render(str(countdown_timer), True, (255, 255, 255))
            screen.blit(countdown_surface, countdown_surface.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)))
            pygame.display.update()

            countdown_timer = COUNTDOWN_SECONDS - int((pygame.time.get_ticks() - start_ticks) / 1000.0)

            for ev in pygame.event.get():
                if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                    running = False

        if running:
            screen.fill((255, 255, 255))
            pygame.display.update()
            
            picam2.capture_file(TEMP_IMG)
            
            try:
                img_pil = Image.open(TEMP_IMG).rotate(180, expand=True)
                img_pil.save(TEMP_IMG, quality=95)
                
                review_img = pygame.transform.smoothscale(pygame.image.load(TEMP_IMG), (display_w, display_h))
                screen.fill((0, 0, 0))
                screen.blit(review_img, display_rect)
                
                btn_width, btn_height = 350, 80
                btn_y = SCREEN_HEIGHT - 120
                btn_retake_rect = pygame.Rect(SCREEN_WIDTH // 2 - btn_width - 20, btn_y, btn_width, btn_height)
                btn_accept_rect = pygame.Rect(SCREEN_WIDTH // 2 + 20, btn_y, btn_width, btn_height)
                
                pygame.draw.rect(screen, (200, 50, 50), btn_retake_rect, border_radius=10)
                pygame.draw.rect(screen, (50, 200, 50), btn_accept_rect, border_radius=10)
                
                screen.blit(font_medium.render("Neuaufnahme", True, (255, 255, 255)), font_medium.render("Neuaufnahme", True, (255, 255, 255)).get_rect(center=btn_retake_rect.center))
                screen.blit(font_medium.render("Speichern", True, (255, 255, 255)), font_medium.render("Speichern", True, (255, 255, 255)).get_rect(center=btn_accept_rect.center))
                
                pygame.display.update()
            except Exception as e:
                draw_centered_text("Fehler bei der Bildanzeige.")
                
            state = "REVIEW"

picam2.stop()
pygame.quit()