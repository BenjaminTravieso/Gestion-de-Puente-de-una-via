import os, json, socket, threading, time, random, queue, pygame, sys

# ——— Configuración inicial ——————————————————————————————
BASE      = os.path.dirname(__file__)
tpl       = json.load(open(os.path.join(BASE, "messages.json")))
HOST, PORT= "127.0.0.1", 5000
CAR_ID    = random.randint(1000, 9999)

# ——— Interfaz de selección de parámetros ——————————————————————
def get_parameters_gui():
    pygame.init()
    screen = pygame.display.set_mode((420, 320))
    pygame.display.set_caption("Configuración del coche")
    font = pygame.font.SysFont(None, 28)
    clock = pygame.time.Clock()

    # Campos de entrada
    input_speed = pygame.Rect(200, 100, 120, 32)
    input_delay = pygame.Rect(200, 150, 120, 32)
    button_rect = pygame.Rect(150, 240, 120, 40)
    direction = "WEST"

    speed_text = ""
    delay_text = ""
    focused_field = None

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if input_speed.collidepoint(ev.pos):
                    focused_field = "speed"
                elif input_delay.collidepoint(ev.pos):
                    focused_field = "delay"
                elif button_rect.collidepoint(ev.pos):
                    try:
                        speed = float(speed_text)
                        delay = float(delay_text)
                        return direction, speed, delay
                    except:
                        pass
                elif 50 <= ev.pos[0] <= 130 and 45 <= ev.pos[1] <= 75:
                    direction = "WEST"
                elif 170 <= ev.pos[0] <= 250 and 45 <= ev.pos[1] <= 75:
                    direction = "EAST"
            elif ev.type == pygame.KEYDOWN and focused_field:
                if ev.key == pygame.K_BACKSPACE:
                    if focused_field == "speed": speed_text = speed_text[:-1]
                    elif focused_field == "delay": delay_text = delay_text[:-1]
                elif ev.unicode.isdigit() or ev.unicode == ".":
                    if focused_field == "speed": speed_text += ev.unicode
                    elif focused_field == "delay": delay_text += ev.unicode

        screen.fill((30, 30, 30))
        # Dirección
        pygame.draw.rect(screen, (150,200,150) if direction=="WEST" else (80,80,80), (50,45,80,30))
        screen.blit(font.render("WEST", True, (0,0,0)), (60,50))
        pygame.draw.rect(screen, (150,200,150) if direction=="EAST" else (80,80,80), (170,45,80,30))
        screen.blit(font.render("EAST", True, (0,0,0)), (180,50))

        # Campos
        screen.blit(font.render("Velocidad (px/s):", True, (255,255,255)), (40, 100))
        screen.blit(font.render("Delay (segundos):", True, (255,255,255)), (40, 150))
        pygame.draw.rect(screen, (255,255,255), input_speed, 2)
        pygame.draw.rect(screen, (255,255,255), input_delay, 2)
        screen.blit(font.render(speed_text, True, (255,255,255)), (input_speed.x+5, input_speed.y+5))
        screen.blit(font.render(delay_text, True, (255,255,255)), (input_delay.x+5, input_delay.y+5))

        # Botón
        pygame.draw.rect(screen, (100,180,100), button_rect)
        screen.blit(font.render("Iniciar", True, (0,0,0)), (button_rect.x+25, button_rect.y+7))

        pygame.display.flip()
        clock.tick(30)

# ——— Parámetros desde GUI ————————————————————————————————————————
DIR, SPEED, DELAY = get_parameters_gui()

# ——— Colas entre red y GUI —————————————————————————————————————————
net2gui = queue.Queue()
gui2net = queue.Queue()

def network_loop():
    sock = socket.socket(); sock.connect((HOST, PORT)); sock.settimeout(0.1)
    reg = tpl["REGISTER"].copy()
    reg.update({"id":CAR_ID, "dir":DIR, "speed":SPEED, "delay":DELAY})
    sock.sendall((json.dumps(reg)+"\n").encode())

    while True:
        try:
            while True:
                ev = gui2net.get_nowait()
                if ev == "DO_REQUEST":
                    req = tpl["REQUEST"].copy()
                    req.update({"id":CAR_ID, "dir":DIR, "speed":SPEED, "delay":DELAY})
                    sock.sendall((json.dumps(req)+"\n").encode())
                elif ev == "FINISHED_CROSS":
                    fin = tpl["FINISH"].copy(); fin["id"] = CAR_ID
                    sock.sendall((json.dumps(fin)+"\n").encode())
        except queue.Empty:
            pass

        try:
            raw = sock.recv(1024).decode()
            for line in raw.strip().splitlines():
                msg = json.loads(line)
                t = msg.get("type")
                if t == tpl["STATUS"]["type"]:
                    net2gui.put(("STATUS", msg["busy"], msg["dir"]))
                elif t == tpl["GRANT"]["type"]:
                    net2gui.put("GRANT")
                elif t == tpl["ACK_FINISH"]["type"]:
                    net2gui.put("ACK_FINISH")
        except socket.timeout:
            continue
        except:
            break
    sock.close()

threading.Thread(target=network_loop, daemon=True).start()

# ——— Simulación puente en Pygame ————————————————————————————————
pygame.init()
FPS, W, H = 60, 600, 300
BR_W = 40
BR_X = W // 2 - BR_W // 2
CAR_R = 12
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
pygame.display.set_caption(f"Coche {CAR_ID}")

bridge_busy = False
bridge_dir = None
state = "WAITING"
x = -CAR_R if DIR == "WEST" else W + CAR_R
y = H // 2
mv = 1 if DIR == "WEST" else -1
next_req = time.time() + 1.0
requested = False

running = True
while running:
    dt = clock.tick(FPS) / 1000.0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    while not net2gui.empty():
        ev = net2gui.get()
        if isinstance(ev, tuple) and ev[0] == "STATUS":
            _, bridge_busy, bridge_dir = ev
        elif ev == "GRANT":
            state = "CROSSING"; requested = False
        elif ev == "ACK_FINISH":
            state = "WAITING"
            x = -CAR_R if DIR == "WEST" else W + CAR_R
            next_req = time.time() + DELAY

    if state == "WAITING" and not requested and time.time() >= next_req:
        gui2net.put("DO_REQUEST"); requested = True

    if state == "CROSSING":
        x += mv * SPEED * dt
        if x < -CAR_R or x > W + CAR_R:
            gui2net.put("FINISHED_CROSS")

    screen.fill((30,30,30))
    col = (50,200,50) if not bridge_busy else (200,50,50)
    pygame.draw.rect(screen, col, (BR_X, 0, BR_W, H))
    ccol = (200,200,0) if state == "WAITING" else (0,200,200)
    pygame.draw.circle(screen, ccol, (int(x), y), CAR_R)

    font = pygame.font.SysFont(None, 24)
    screen.blit(font.render(f"Puente: {'OCUPADO' if bridge_busy else 'LIBRE'} dir={bridge_dir}", True, (255,255,255)), (10,10))
    screen.blit(font.render(f"Estado: {state}", True, (255,255,255)), (10,35))
    screen.blit(font.render(f"Dirección: {DIR}", True, (255,255,255)), (10,60))
    screen.blit(font.render(f"Velocidad: {SPEED:.1f} px/s", True, (255,255,255)), (10,85))
    screen.blit(font.render(f"Delay: {DELAY:.1f} s", True, (255,255,255)), (10,110))

    pygame.display.flip()

pygame.quit()