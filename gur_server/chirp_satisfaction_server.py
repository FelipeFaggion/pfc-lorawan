import paho.mqtt.client as mqtt
import json
import time
import math
import base64
import csv
from threading import Timer
from datetime import datetime

# === CONFIGURAÇÕES CHIRPSTACK ===
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
APPLICATION_ID = "50981d4c-9ebd-49fc-a7d4-f88ea8598ef2"
LOG_FILE = "gur_log.csv"

# === PARÂMETROS DO EXPERIMENTO ===
WINDOW_SECONDS = 300        # 5 minutos
TARGET_MESSAGES = 10        # 10 mensagens por janela de 5 min
TICK_INTERVAL = 60          # Atualiza estatísticas a cada 60 segundos

# === ESTRUTURAS DE DADOS ===
message_log = []            # [(timestamp, device_id), ...]
nodes_total = {}            # contagem total histórica por nodo


# === FUNÇÕES AUXILIARES ===
def calc_satisfaction(recebido, n):
    """Função de satisfação suave em torno do setpoint."""
    val = 20 + 80 * math.exp(-0.02 * (recebido - n) ** 2)
    return round(max(0.0, min(100.0, val)), 2)


def get_window_stats():
    """Retorna total de mensagens e nós ativos na janela móvel."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    recent = [(t, dev) for (t, dev) in message_log if t >= cutoff]
    active_nodes = len(set(dev for _, dev in recent))
    return len(recent), active_nodes


def log_event(event_type, device_id, total_received, satisfaction, active_nodes):
    """Registra evento (uplink/downlink) em CSV."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([
            timestamp, event_type, device_id, total_received,
            satisfaction, active_nodes
        ])
    print(f"📝 Log: {timestamp} | {event_type} | {device_id} | total={total_received} | sat={satisfaction} | ativos={active_nodes}")


def send_downlink(client, dev_eui, satisfaction):
    """Envia satisfação atual como downlink ao nodo que fez uplink."""
    payload = {
        "devEui": dev_eui,
        "confirmed": False,
        "f_port": 2,
        "data": base64.b64encode(bytes([int(satisfaction)])).decode(),
    }
    topic = f"application/{APPLICATION_ID}/device/{dev_eui}/command/down"
    client.publish(topic, json.dumps(payload))
    print(f"[↓] Downlink para {dev_eui}: satisfação={satisfaction}")


def periodic_status():
    """Exibe status global a cada minuto (janela móvel)."""
    total, active = get_window_stats()
    satisfaction = calc_satisfaction(total, TARGET_MESSAGES)
    print(
        f"\n🌐 STATUS (últimos {WINDOW_SECONDS//60} min)"
        f" | msgs={total}/{TARGET_MESSAGES}"
        f" | nós ativos={active}"
        f" | satisfação média={satisfaction:.2f}%\n"
    )
    Timer(TICK_INTERVAL, periodic_status).start()


# === CALLBACKS MQTT ===
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Conectado ao broker MQTT do ChirpStack")
        topic = f"application/{APPLICATION_ID}/device/+/event/up"
        client.subscribe(topic)
        print(f"📡 Subscrito em: {topic}")
    else:
        print(f"⚠️ Falha na conexão (rc={rc})")


def on_message(client, userdata, msg):
    """Processa uplinks, atualiza histórico e envia feedback."""
    global message_log

    data = json.loads(msg.payload.decode())
    dev_info = data.get("deviceInfo", {})
    dev_eui = dev_info.get("devEui", "unknown")
    device_id = dev_info.get("deviceName", dev_eui)

    now = time.time()
    message_log.append((now, device_id))
    nodes_total[device_id] = nodes_total.get(device_id, 0) + 1

    # Estatísticas da janela móvel
    total_window, active_nodes = get_window_stats()
    satisfaction = calc_satisfaction(total_window, TARGET_MESSAGES)

    print(f"[↑] Uplink de {device_id} | janela={total_window}/{TARGET_MESSAGES} | satisfação={satisfaction}")
    log_event("uplink", device_id, total_window, satisfaction, active_nodes)

    # Envia feedback apenas para o nodo que transmitiu
    send_downlink(client, dev_eui, satisfaction)
    log_event("downlink", device_id, total_window, satisfaction, active_nodes)


# === INICIALIZAÇÃO ===
with open(LOG_FILE, mode="a", newline="") as f:
    if f.tell() == 0:
        csv.writer(f).writerow([
            "timestamp", "event_type", "device_id",
            "messages_in_window", "satisfaction", "active_nodes"
        ])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()

# Inicia monitoramento periódico
periodic_status()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Encerrando servidor...")
    client.loop_stop()
    client.disconnect()
