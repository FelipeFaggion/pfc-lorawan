import paho.mqtt.client as mqtt
import json
import time
import math
import base64
import csv
from threading import Timer
from datetime import datetime

APP_ID = "pfc-game-theory"
TTN_REGION = "au1"
MQTT_BROKER = f"{TTN_REGION}.cloud.thethings.network"
API_KEY = "NNSXS.S3YLGCMJFMONQOHBRJ665U4ZSJNSJN7KOKS2VAA.HROWPD2TPDVW4IEY2FI2E4VT4DPUTQDLOXHDQNJXLP6H4BV7MDHA"

WINDOW_SECONDS = 900  # 15 min
LOG_FILE = "gur_log.csv"

# === capacidade física (2 nós, 6/min cada) ===
MAX_RATE_PER_MIN = 12
WINDOW_CAPACITY = MAX_RATE_PER_MIN * (WINDOW_SECONDS // 60)  # = 180

# === cronograma de alvos (em segundos desde o início do experimento) ===
TARGET_SCHEDULE = [
    (0,   40),   # fase 1: fácil
    (600, 60),   # fase 2: médio
    (1200, 90),  # fase 3: agressivo
    (1800, 40)   # fase 4: relaxa
]

nodes = {}
window_start = time.time()
experiment_start = time.time()
TARGET_MESSAGES = TARGET_SCHEDULE[0][1]  # inicial

def calc_satisfaction(recebido, n):
    """Grau de satisfação (0–100), com saturação."""
    val = 20 + 80 * math.exp(-0.002 * (recebido - n)**2)
    return round(max(0.0, min(100.0, val)), 2)

def log_event(device_id, total, satisfaction):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([timestamp, device_id, total, satisfaction])
    print(f"📝 Log salvo: {timestamp} | {device_id} | total={total} | sat={satisfaction}")

def send_downlink(client, device_id, satisfaction):
    payload = {
        "downlinks": [{
            "f_port": 2,
            "frm_payload": base64.b64encode(bytes([int(satisfaction)])).decode(),
            "confirmed": False
        }]
    }
    topic = f"v3/{APP_ID}@ttn/devices/{device_id}/down/push"
    client.publish(topic, json.dumps(payload))
    print(f"[↓] Downlink enviado para {device_id}: satisfação={satisfaction}")

def reset_window():
    global nodes, window_start
    nodes = {}
    window_start = time.time()
    print(f"\n🕒 Nova janela iniciada às {time.strftime('%H:%M:%S')}\n")
    Timer(WINDOW_SECONDS, reset_window).start()

def status_global_tick():
    total_received = sum(nodes.values())
    elapsed_min = (time.time() - window_start) / 60.0
    sat = calc_satisfaction(total_received, TARGET_MESSAGES)

    print(
        f"\n🌐 STATUS | janela {elapsed_min:.1f} min"
        f" | recebido={total_received}/{TARGET_MESSAGES}"
        f" | capacidade={WINDOW_CAPACITY}"
        f" | satisfação={sat:.2f}%"
    )
    Timer(60, status_global_tick).start()  # atualiza a cada 60 s

def update_target_tick():
    global TARGET_MESSAGES
    elapsed = time.time() - experiment_start
    # acha o último target cujo tempo <= elapsed
    new_target = TARGET_MESSAGES
    for t, v in TARGET_SCHEDULE:
        if elapsed >= t:
            new_target = v
        else:
            break

    if new_target != TARGET_MESSAGES:
        TARGET_MESSAGES = new_target
        warn = " ⚠️(maior que capacidade!)" if TARGET_MESSAGES > WINDOW_CAPACITY else ""
        print(f"\n🎯 Novo setpoint de janela: TARGET_MESSAGES={TARGET_MESSAGES}{warn}\n")

    Timer(5, update_target_tick).start()  # checa a cada 5 s

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Conectado ao TTN MQTT Broker")
        topic = f"v3/{APP_ID}@ttn/devices/+/up"
        client.subscribe(topic)
        print(f"📡 Subscrito em: {topic}")
    else:
        print(f"⚠️ Falha na conexão (rc={rc})")

def on_message(client, userdata, msg):
    global nodes
    data = json.loads(msg.payload.decode())
    device_id = data["end_device_ids"]["device_id"]

    nodes[device_id] = nodes.get(device_id, 0) + 1
    total_received = sum(nodes.values())
    satisfaction = calc_satisfaction(total_received, TARGET_MESSAGES)

    print(f"[↑] Uplink de {device_id} | total={total_received} | alvo={TARGET_MESSAGES} | satisfação={satisfaction}")
    log_event(device_id, total_received, satisfaction)
    send_downlink(client, device_id, satisfaction)

# header CSV
with open(LOG_FILE, mode="a", newline="") as f:
    if f.tell() == 0:
        csv.writer(f).writerow(["timestamp", "device_id", "total_received", "satisfaction"])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.username_pw_set(APP_ID, API_KEY)
client.tls_set()
client.tls_insecure_set(False)
client.on_connect = on_connect
client.on_message = on_message

print(f"🔗 Conectando a {MQTT_BROKER} ...")
client.connect(MQTT_BROKER, 8883, 60)
client.loop_start()

reset_window()
status_global_tick()
update_target_tick()

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Encerrando servidor...")
    client.loop_stop()
    client.disconnect()
