import os, json, socket, threading, time, random, queue, pygame, sys

# --- Configuración inicial ----------------------------------------------------
BASE = os.path.dirname(__file__)
tpl = json.load(open(os.path.join(BASE, "messages.json")))
HOST, PORT = "127.0.0.1", 5000
CAR_ID = random.randint(1000, 9999)

# --- Interfaz de selección de parámetros --------------------------------------------
def get_parameters_gui():
    pygame.init()
    screen = pygame.display.set_mode((420, 320))
    pygame.display.set_caption("Configuración del coche")
    font = pygame.font.SysFont(None, 28)
    clock = pygame.time.Clock()

    # Campos de Entrada
    input_min_speed = pygame.Rect(200, 100, 120, 32)
    input_max_speed = pygame.Rect(200, 150, 120, 32)
    input_min_delay = pygame.Rect(200, 200, 120, 32)
    input_max_delay = pygame.Rect(200, 250, 120, 32)
    button_rect = pygame.Rect(150, 280, 120, 30) # Ajustar posición del botón
    direction = "WEST"

    min_speed_text = ""
    max_speed_text = ""
    min_delay_text = ""
    max_delay_text = ""
    focused_field = None

    while True:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            elif ev.type == pygame.MOUSEBUTTONDOWN:
                if input_min_speed.collidepoint(ev.pos):
                    focused_field = "min_speed"
                elif input_max_speed.collidepoint(ev.pos):
                    focused_field = "max_speed"
                elif input_min_delay.collidepoint(ev.pos):
                    focused_field = "min_delay"
                elif input_max_delay.collidepoint(ev.pos):
                    focused_field = "max_delay"
                elif button_rect.collidepoint(ev.pos):
                    try:
                        # Convertir a float y validar que min <= max
                        min_speed = float(min_speed_text)
                        max_speed = float(max_speed_text)
                        min_delay = float(min_delay_text)
                        max_delay = float(max_delay_text)
                        if min_speed > max_speed or min_delay > max_delay:
                            raise ValueError("Valores mínimos deben ser menores o iguales a los máximos.")
                        return direction, min_speed, max_speed, min_delay, max_delay
                    except ValueError as e:
                        print(f"Error de entrada: {e}")
                        pass ##
                elif 50 <= ev.pos[0] <= 130 and 45 <= ev.pos[1] <= 75:
                    direction = "WEST"
                elif 170 <= ev.pos[0] <= 250 and 45 <= ev.pos[1] <= 75:
                    direction = "EAST"
            elif ev.type == pygame.KEYDOWN and focused_field:
                if ev.key == pygame.K_BACKSPACE:
                    if focused_field == "min_speed": min_speed_text = min_speed_text[:-1]
                    elif focused_field == "max_speed": max_speed_text = max_speed_text[:-1]
                    elif focused_field == "min_delay": min_delay_text = min_delay_text[:-1]
                    elif focused_field == "max_delay": max_delay_text = max_delay_text[:-1]
                elif ev.unicode.isdigit() or ev.unicode == ".":
                    if focused_field == "min_speed": min_speed_text += ev.unicode
                    elif focused_field == "max_speed": max_speed_text += ev.unicode
                    elif focused_field == "min_delay": min_delay_text += ev.unicode
                    elif focused_field == "max_delay": max_delay_text += ev.unicode

        screen.fill((30, 30, 30))
        # Botones de dirección
        pygame.draw.rect(screen, (150,200,150) if direction=="WEST" else (80,80,80), (50,45,80,30))
        screen.blit(font.render("WEST", True, (0,0,0)), (60,50))
        pygame.draw.rect(screen, (150,200,150) if direction=="EAST" else (80,80,80), (170,45,80,30))
        screen.blit(font.render("EAST", True, (0,0,0)), (180,50))

        # Campos de entrada
        screen.blit(font.render("Vel. Mínima (px/s):", True, (255,255,255)), (40, 100))
        screen.blit(font.render("Vel. Máxima (px/s):", True, (255,255,255)), (40, 150))
        screen.blit(font.render("Delay Mínimo (s):", True, (255,255,255)), (40, 200))
        screen.blit(font.render("Delay Máximo (s):", True, (255,255,255)), (40, 250))

        pygame.draw.rect(screen, (255,255,255), input_min_speed, 2)
        pygame.draw.rect(screen, (255,255,255), input_max_speed, 2)
        pygame.draw.rect(screen, (255,255,255), input_min_delay, 2)
        pygame.draw.rect(screen, (255,255,255), input_max_delay, 2)

        screen.blit(font.render(min_speed_text, True, (255,255,255)), (input_min_speed.x+5, input_min_speed.y+5))
        screen.blit(font.render(max_speed_text, True, (255,255,255)), (input_max_speed.x+5, input_max_speed.y+5))
        screen.blit(font.render(min_delay_text, True, (255,255,255)), (input_min_delay.x+5, input_min_delay.y+5))
        screen.blit(font.render(max_delay_text, True, (255,255,255)), (input_max_delay.x+5, input_max_delay.y+5))

        # Botón
        pygame.draw.rect(screen, (100,180,100), button_rect)
        screen.blit(font.render("Iniciar", True, (0,0,0)), (button_rect.x+25, button_rect.y+7))

        pygame.display.flip()
        clock.tick(30)


# --- Parámetros del GUI (ahora rangos) ----------------------------------------------------
INITIAL_DIR, MIN_SPEED, MAX_SPEED, MIN_DELAY, MAX_DELAY = get_parameters_gui()

# --- Queues(colas) entre red y GUI -----------------------------------------
net2gui = queue.Queue()
gui2net = queue.Queue()

# --- Bandera de conexión de red activa -----------------------------------------
connection_active = threading.Event()
connection_active.set() # Se asume que se encuentra conectado inicialmente

# Variables de estado del coche que se actualizarán dinámicamente
current_dir = INITIAL_DIR
current_speed = random.uniform(MIN_SPEED, MAX_SPEED)
current_delay = random.uniform(MIN_DELAY, MAX_DELAY)


def network_loop():
    sock = socket.socket();
    try:
        sock.connect((HOST, PORT)); sock.settimeout(0.1)
        # El registro inicial solo envía el ID del coche, ya que la dirección y velocidad
        # serán dinámicas.
        reg = tpl["REGISTER"].copy()
        reg.update({"id":CAR_ID}) # No enviar dir, speed, delay en REGISTER
        sock.sendall((json.dumps(reg)+"\n").encode())
        
        while connection_active.is_set(): # Bucle para seguir ejecutándose mientras haya conexión
            try:
                while True:
                    ev = gui2net.get_nowait()
                    if ev == "DO_REQUEST":
                        req = tpl["REQUEST"].copy()
                        # Enviar la dirección y velocidad actuales en cada solicitud
                        req.update({"id":CAR_ID, "dir":current_dir, "speed":current_speed}) 
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
            except Exception as e: # Atrapa todas las demás excepciones
                print(f"Error de red en recv: {e}")
                connection_active.clear() # Desconexión de señal
                break # Exit the loop
    except ConnectionRefusedError:
        print(f"Conexión rechazada. ¿Está el servidor funcionando en {HOST}:{PORT}?")
        connection_active.clear()
    except Exception as e:
        print(f"Se produjo un error inesperado durante la configuración de la red: {e}")
        connection_active.clear()
    finally:
        sock.close()
        connection_active.clear() # Asegura que la bandera esté borrada si el bucle termina por cualquier motivo

threading.Thread(target=network_loop, daemon=True).start()


# --- Simulación de puente en Pygame --------------------------------------------
pygame.init()
FPS, W, H = 60, 600, 300
BR_W = 40
BR_X = W // 2 - BR_W // 2
CAR_R = 12
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
pygame.display.set_caption(f"Coche {CAR_ID}")

bridge_busy = False #Se actualiza desde el servidor
bridge_dir = None   #Se actualiza desde el servidor
state = "WAITING"

# Nueva variable para controlar si el coche está esperando un GRANT después de una solicitud
waiting_for_grant = False 
LAST_REQUEST_TIME = 0 # Para un posible timeout de solicitud

# Variables de posición y movimiento (se actualizan al cruzar)
x = -CAR_R if current_dir == "WEST" else W + CAR_R
y = H // 2
mv = 1 if current_dir == "WEST" else -1 # Dirección de movimiento del auto

# Programar la primera solicitud con un retraso aleatorio inicial
next_action_time = time.time() + random.uniform(MIN_DELAY, MAX_DELAY) # Se renombra para ser más general

running = True
while running:
    # Comprueba si la conexión sigue activa
    if not connection_active.is_set():
        print("Desconectado del servidor. Cerrando Pygame.")
        running = False
        continue

    dt = clock.tick(FPS) / 1000.0
    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            running = False

    while not net2gui.empty():
        ev = net2gui.get()
        if isinstance(ev, tuple) and ev[0] == "STATUS":
            _, bridge_busy, bridge_dir = ev   #Recibe el estado del puente
            # print(f"Coche {CAR_ID} STATUS: busy={bridge_busy}, dir={bridge_dir}. Mi dir={current_dir}, Estado={state}, esperando_grant={waiting_for_grant}")
            
        elif ev == "GRANT":
            state = "CROSSING"
            waiting_for_grant = False # Se ha recibido GRANT
            LAST_REQUEST_TIME = 0 # Reiniciar el tiempo de la última solicitud
            current_speed = random.uniform(MIN_SPEED, MAX_SPEED) 
            
            # --- CORRECCIÓN CRÍTICA AQUÍ: Resetear posición y dirección cuando se concede el paso ---
            x = -CAR_R if current_dir == "WEST" else W + CAR_R
            mv = 1 if current_dir == "WEST" else -1
            # ---------------------------------------------------------------------------------------

            print(f"Coche {CAR_ID} inicia cruce {current_dir} con velocidad {current_speed:.2f} px/s")

        elif ev == "ACK_FINISH":
            state = "WAITING"
            # Cambiar dirección para el próximo cruce
            current_dir = "EAST" if current_dir == "WEST" else "WEST"
            
            # NO resetear la posición (x) y mv aquí. Se hará en el GRANT.
            
            # Establecer el momento de la próxima solicitud con un retraso aleatorio
            current_delay = random.uniform(MIN_DELAY, MAX_DELAY)
            next_action_time = time.time() + current_delay 
            print(f"Coche {CAR_ID} finalizó cruce. Esperará {current_delay:.2f}s para ir hacia {current_dir}")

    # Lógica de solicitud del auto
    # Solo solicita si está en WAITING, no está ya esperando un GRANT, y su tiempo de acción ha llegado.
    if state == "WAITING" and not waiting_for_grant and time.time() >= next_action_time:
        gui2net.put("DO_REQUEST")
        waiting_for_grant = True # Marcamos que estamos esperando la respuesta del servidor
        LAST_REQUEST_TIME = time.time() # Guardamos el momento de la solicitud
        print(f"Coche {CAR_ID} solicitando cruzar hacia {current_dir} (primera vez o reintento)")

    # Agregamos una lógica de reintento si no se recibe GRANT después de un timeout
    timeout_request_sec = 2.0 # Puedes ajustar este valor si el ping/latencia es muy alto
    if state == "WAITING" and waiting_for_grant and (time.time() - LAST_REQUEST_TIME > timeout_request_sec):
        # El servidor no respondió con un GRANT a tiempo, asumimos que no nos lo concedió o el mensaje se perdió.
        # Volvemos a permitir una nueva solicitud.
        waiting_for_grant = False 
        next_action_time = time.time() + 0.5 # Pequeño delay antes del siguiente reintento para evitar inundar
        print(f"Coche {CAR_ID}: Timeout de GRANT. Reintentará en {0.5:.2f}s.")

    if state == "CROSSING":
        x += mv * current_speed * dt
        # Comprueba si el auto ha cruzado completamente el puente
        # Ajustado para que el centro del coche haya pasado el límite exterior
        if (current_dir == "WEST" and x - CAR_R >= W) or \
           (current_dir == "EAST" and x + CAR_R <= 0):
            gui2net.put("FINISHED_CROSS")
            # El estado se establecerá en "WAITING" mediante ACK_FINISH desde el servidor

    screen.fill((30,30,30))

    # --- Dibuja líneas de puente ---
    bridge_line_y_top = H // 2 - CAR_R - 5
    bridge_line_y_bottom = H // 2 + CAR_R + 5
    line_color = (200, 200, 200)
    line_thickness = 2

    pygame.draw.line(screen, line_color, (0, bridge_line_y_top), (W, bridge_line_y_top), line_thickness)
    pygame.draw.line(screen, line_color, (0, bridge_line_y_bottom), (W, bridge_line_y_bottom), line_thickness)

    # --- Sección del puente ---
    pygame.draw.rect(screen, (50, 50, 50), (BR_X, bridge_line_y_top, BR_W, bridge_line_y_bottom - bridge_line_y_top))
    pygame.draw.rect(screen, (100, 100, 100), (BR_X, bridge_line_y_top, BR_W, bridge_line_y_bottom - bridge_line_y_top), 1) # Border

    # --- Dibujar semáforo ---
    traffic_light_size = 20
    traffic_light_x = BR_X + BR_W // 2 - traffic_light_size // 2
    traffic_light_y = bridge_line_y_top - traffic_light_size - 10

    traffic_light_color = (100, 100, 0) # Default yellow/orange
    if not bridge_busy:
        traffic_light_color = (0, 200, 0) # Green if bridge is free
    elif bridge_busy and bridge_dir == current_dir: # Usar current_dir aquí
        traffic_light_color = (200, 100, 0) # Orange if busy by a car in our direction
    elif bridge_busy and bridge_dir != current_dir: # Usar current_dir aquí
        traffic_light_color = (200, 0, 0) # Red if busy by opposite direction

    pygame.draw.circle(screen, traffic_light_color, (traffic_light_x + traffic_light_size // 2, traffic_light_y + traffic_light_size // 2), traffic_light_size // 2)
    pygame.draw.rect(screen, (50, 50, 50), (traffic_light_x, traffic_light_y, traffic_light_size, traffic_light_size), 2) # Outline

    # Draw the car
    ccol = (200,200,0) if state == "WAITING" else (0,200,200)
    pygame.draw.circle(screen, ccol, (int(x), y), CAR_R)

    font = pygame.font.SysFont(None, 24)
    screen.blit(font.render(f"Puente: {'OCUPADO' if bridge_busy else 'LIBRE'} dir={bridge_dir or 'N/A'}", True, (255,255,255)), (10,10))
    screen.blit(font.render(f"Estado: {state}", True, (255,255,255)), (10,35))
    screen.blit(font.render(f"Dirección: {current_dir}", True, (255,255,255)), (10,60))
    screen.blit(font.render(f"Velocidad: {current_speed:.1f} px/s", True, (255,255,255)), (10,85))
    screen.blit(font.render(f"Delay: {current_delay:.1f} s", True, (255,255,255)), (10,110))
    if not connection_active.is_set():
        screen.blit(font.render("¡DESCONECTADO DEL SERVIDOR!", True, (255,0,0)), (W // 2 - 150, H - 30))

    pygame.display.flip()

pygame.quit()
sys.exit()