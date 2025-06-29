# server.py
import socket, threading, json, queue, time, os

# ——— Carga de plantillas JSON ——————————————————————————————————————
BASE      = os.path.dirname(__file__)
tpl       = json.load(open(os.path.join(BASE, "messages.json")))
HOST, PORT= '0.0.0.0', 5000

clients      = []
clients_lock = threading.Lock()
bridge_q     = queue.Queue()
current_dir  = None
state_lock   = threading.Lock()

def broadcast_status():
    msg = tpl["STATUS"].copy()
    msg.update({
        "busy": current_dir is not None,
        "dir":  current_dir
    })
    data = json.dumps(msg) + "\n"
    with clients_lock:
        for c in clients[:]:
            try:
                c.sendall(data.encode())
            except:
                clients.remove(c)

def try_grant():
    global current_dir
    with state_lock:
        if current_dir or bridge_q.empty():
            return
        car_id, dirc, conn = bridge_q.get()
        current_dir = dirc
        grant = tpl["GRANT"].copy()
        grant["id"] = car_id
        try:
            conn.sendall((json.dumps(grant) + "\n").encode())
        except:
            current_dir = None
    broadcast_status()

def handle_client(conn, addr):
    global current_dir
    buffer = ""
    conn.settimeout(0.1)

    try:
        # REGISTER
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
                        with clients_lock:
                            clients.append(conn)
                        broadcast_status()
                        raise StopIteration
            except StopIteration:
                break
            except socket.timeout:
                continue

        # Mensajes subsecuentes
        while True:
            try:
                chunk = conn.recv(1024).decode()
                if not chunk:
                    break
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    msg = json.loads(line)
                    t   = msg.get("type")

                    if t == tpl["REQUEST"]["type"]:
                        bridge_q.put((msg["id"], msg["dir"], conn))
                        try_grant()

                    elif t == tpl["FINISH"]["type"]:
                        with state_lock:
                            current_dir = None
                        ack = tpl["ACK_FINISH"].copy(); ack["id"] = msg["id"]
                        try:
                            conn.sendall((json.dumps(ack) + "\n").encode())
                        except:
                            pass
                        broadcast_status()
                        try_grant()
            except socket.timeout:
                continue
            except (ConnectionError, json.JSONDecodeError):
                break

    finally:
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
            break

if __name__ == "__main__":
    server_loop()