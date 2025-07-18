# server.py 
import socket, threading, json, queue, time, os

# --- Carga de plantillas JSON ------------------------------------------------
BASE = os.path.dirname(__file__)
tpl = json.load(open(os.path.join(BASE, "messages.json")))
HOST, PORT = '0.0.0.0', 5000

clients = []
clients_lock = threading.Lock()
bridge_q_west = queue.Queue() #separar solicitudes segun la direccion, una cola para cada dirección
bridge_q_east = queue.Queue()
current_dir = None        #  Estado del puente: Dirección actual del puente (WEST, EAST, o None si está libre)
cars_on_bridge = 0        # Número de coches actualmente en el puente en la misma dirección

MAX_CARS_SAME_DIRECTION = 2 # maximo de autos de una dirección
state_lock = threading.Lock() # Bloqueo para proteger las variables de estado global

next_preferred_dir = "EAST" # Para alternancia

def broadcast_status(): #notificar el estado del puente a todos los clientes
    msg = tpl["STATUS"].copy()
    msg.update({
        "busy": current_dir is not None,
        "dir": current_dir,
        "cars_on_bridge": cars_on_bridge
    })
    data = json.dumps(msg) + "\n"
    with clients_lock:
        for c in clients[:]:
            try:
                c.sendall(data.encode())
            except:
                clients.remove(c)

def try_grant(): #Decision de a quien conceder el cruce 
    global current_dir, cars_on_bridge, next_preferred_dir
    with state_lock: # Aseguramos que solo un hilo modifique el estado a la vez
        car_to_grant = None # Para almacenar el coche que se va a conceder
        
        # 1. Prioridad: Si el puente está OCUPADO y hay espacio, seguir concediendo a la MISMA dirección
        if current_dir == "WEST" and cars_on_bridge < MAX_CARS_SAME_DIRECTION:
            if not bridge_q_west.empty():
                car_to_grant = bridge_q_west.get()
                
        elif current_dir == "EAST" and cars_on_bridge < MAX_CARS_SAME_DIRECTION:
            if not bridge_q_east.empty():
                car_to_grant = bridge_q_east.get()
                

        # 2. Si el puente está LIBRE o la dirección actual está llena/no hay coches en esa dirección
        # entonces se decide la PRIMERA dirección que entrará.
        # Esto solo se ejecuta si car_to_grant aún es None 
        if car_to_grant is None and cars_on_bridge == 0: # <-- Importante: solo si el puente está realmente vacío
            # Intentar con la dirección preferida
            if next_preferred_dir == "WEST" and not bridge_q_west.empty():
                car_to_grant = bridge_q_west.get()
                next_preferred_dir = "EAST" # Alternar la preferencia para la próxima vez que el puente esté libre
            elif next_preferred_dir == "EAST" and not bridge_q_east.empty():
                car_to_grant = bridge_q_east.get()
                next_preferred_dir = "WEST" # Alternar la preferencia
            # Fallback: Si la dirección preferida está vacía, pero la OTRA dirección tiene coches
            elif not bridge_q_west.empty(): # Conceder a WEST (si EAST era preferido pero vacío)
                car_to_grant = bridge_q_west.get()
                next_preferred_dir = "EAST" # Si un coche WEST entra, la próxima preferencia es EAST
            elif not bridge_q_east.empty(): # Conceder a EAST si WEST era preferido pero vacío
                car_to_grant = bridge_q_east.get()
                next_preferred_dir = "WEST" # Si un coche EAST entra, la próxima preferencia es WEST
        
        # FINAL: Conceder el permiso si se encontró un coche.
        if car_to_grant:
            car_id, dirc, conn = car_to_grant
            
            # Si este es el primer coche que entra, establece la dirección del puente.
            # Si ya hay coches, la dirección del puente ya está establecida.
            if cars_on_bridge == 0: 
                current_dir = dirc 
            
            cars_on_bridge += 1 # Incrementar el contador de coches en el puente
            
            grant = tpl["GRANT"].copy()
            grant["id"] = car_id
            try:
                conn.sendall((json.dumps(grant) + "\n").encode())
                print(f"GRANT concedido a Coche {car_id} ({dirc}). Cars on bridge: {cars_on_bridge}, Current Dir: {current_dir}")
            except Exception as e:
                print(f"Error al enviar GRANT a {car_id} ({dirc}): {e}")
                # Si falla el envío, el coche no entró realmente al puente, revertir estado
                cars_on_bridge -= 1
                # Si al revertir se vacía el puente, liberarlo
                if cars_on_bridge == 0:
                    current_dir = None
        
        broadcast_status()


def handle_client(conn, addr): #Ciclo del cliente
    
    global current_dir, cars_on_bridge, clients 

    buffer = ""
    conn.settimeout(0.1)

    print(f"Conexión establecida con {addr}")

    try:
        # REGISTER
        # para añadir la conexión a la lista de clientes.
        while True:
            try:
                chunk = conn.recv(1024).decode()
                if not chunk:
                    raise ConnectionError
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = json.loads(line)
                    if msg.get("type") == tpl["REGISTER"]["type"]:
                        # Se añade la conexión del cliente a la lista global de clientes
                        # Esto es necesario para broadcast_status()
                        with clients_lock: # Proteger la lista clients
                            clients.append(conn)
                        car_id = msg.get("id", "N/A") # Obtener el ID del coche si existe
                        print(f"Coche {car_id} registrado desde {addr}. Clientes conectados: {len(clients)}")
                        broadcast_status() # Notificar a todos que un nuevo cliente se conecto
                        raise StopIteration # Sale del bucle de registro
            except StopIteration:
                break # Salir del bucle de registro
            except socket.timeout:
                continue # No hay datos, sigue esperando
            except (ConnectionError, json.JSONDecodeError) as e:
                print(f"Error durante el registro para {addr}: {e}")
                break # Rompe si hay un error de conexión o JSON

        # Mensajes subsecuentes REQUEST y FINISH
        while True:
            try:
                chunk = conn.recv(1024).decode()
                if not chunk:
                    print(f"Cliente {addr} desconectado.")
                    break # Cliente desconectado
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = json.loads(line)
                    t = msg.get("type")
                    car_id = msg.get("id", "N/A") # Obtener el ID para los logs

                    if t == tpl["REQUEST"]["type"]:
                        car_dir = msg["dir"]
                        print(f"Coche {car_id} ({car_dir}) solicita cruzar.")
                        # La adición a la cola también debería estar protegida si es parte del estado
                        # que try_grant() evalúa de forma crítica.
                        with state_lock: # Proteger la adición a la cola y la llamada a try_grant
                            if car_dir == "WEST":
                                bridge_q_west.put((msg["id"], msg["dir"], conn))
                            elif car_dir == "EAST":
                                bridge_q_east.put((msg["id"], msg["dir"], conn))
                        try_grant() # Llama a try_grant después de añadir a la cola

                    elif t == tpl["FINISH"]["type"]:
                        print(f"Coche {car_id} informa FINISH.")
                        with state_lock:
                            cars_on_bridge -= 1
                            if cars_on_bridge < 0: # Para evitar errores de conteo
                                cars_on_bridge = 0 
                            
                            # SI EL PUENTE SE VACÍA, REINICIAMOS SU DIRECCIÓN
                            if cars_on_bridge == 0:
                                current_dir = None #Libera el puente para la otra dirección
                                print(f"Coche {car_id} finalizó cruce. Puente LIBRE. cars_on_bridge: {cars_on_bridge}, current_dir: {current_dir}")
                            else:
                                print(f"Coche {car_id} finalizó cruce. Cars on bridge: {cars_on_bridge}, Current Dir: {current_dir}.")
                            
                        ack = tpl["ACK_FINISH"].copy()
                        ack["id"] = car_id
                        try:
                            conn.sendall((json.dumps(ack) + "\n").encode())
                        except Exception as send_err:
                            print(f"Error al enviar ACK_FINISH a {car_id}: {send_err}")
                        
                        broadcast_status() # Notificar a todos del cambio de estado
                        try_grant() 
                        
            except socket.timeout:
                continue # No hay datos disponibles de inmediato, sigue el bucle
            except (ConnectionError, json.JSONDecodeError) as e:
                print(f"Error de comunicación con {addr}: {e}")
                break # Rompe el bucle si hay un error de conexión o JSON

    finally:
        # Asegurarse de limpiar la conexión en caso de cualquier excepción o desconexión
        print(f"Cierre de conexión para {addr}.")
        with clients_lock:
            if conn in clients:
                clients.remove(conn)
        conn.close()

def server_loop():
    print(f"[SERVIDOR] Escuchando en {HOST}:{PORT}")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen()
    while True:
        try:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
        except KeyboardInterrupt:
            print ("[SERVIDOR] Servidor apagándose.")
            break

if __name__ == "__main__":
    server_loop()

