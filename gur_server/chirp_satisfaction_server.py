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

# === Parâmetros do Gur Game ===
WINDOW_SECONDS = 1800  # 30 min
MAX_RATE_PER_MIN = 12
WINDOW_CAPACITY = MAX_RATE_PER_MIN * (WINDOW_SECONDS // 60)
TARGET_SCHEDULE = [
    (0, 40),
    (1800, 60),
    (2400, 90),
    (3000, 40)
]

nodes = {}
window_start = time.time()
experiment_start = time.time()
TARGET_MESSAGES = TARGET_SCHEDULE[0][1]


def calc_satisfaction(recebido, n):
    val = 20 + 80 * math.exp(-0.002 * (recebido - n) ** 2)
    return round(max(0.0, min(100.0, val)), 2)


def log_event(device_id, total, satisfaction):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([timestamp, device_id, total, satisfaction])
    print(f"📝 Log salvo: {timestamp} | {device_id} | total={total} | sat={satisfaction}")


def send_downlink(client, dev_eui, satisfaction):
    payload = {
        "confirmed": False,
        "f_port": 2,
        "data": base64.b64encode(bytes([int(satisfaction)])).decode(),
    }
    topic = f"application/{APPLICATION_ID}/device/{dev_eui}/command/down"
    client.publish(topic, json.dumps(payload))
    print(f"[↓] Downlink enviado para {dev_eui}: satisfação={satisfaction}")


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
    Timer(60, status_global_tick).start()


def update_target_tick():
    global TARGET_MESSAGES
    elapsed = time.time() - experiment_start
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
    Timer(5, update_target_tick).start()


def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print("✅ Conectado ao broker MQTT do ChirpStack")
        topic = f"application/{APPLICATION_ID}/device/+/event/up"
        client.subscribe(topic)
        print(f"📡 Subscrito em: {topic}")
    else:
        print(f"⚠️ Falha na conexão (rc={rc})")


def on_message(client, userdata, msg):
    global nodes
    data = json.loads(msg.payload.decode())

    dev_info = data.get("deviceInfo", {})
    dev_eui = dev_info.get("devEui", "unknown")
    device_id = dev_info.get("deviceName", dev_eui)

    nodes[device_id] = nodes.get(device_id, 0) + 1
    total_received = sum(nodes.values())
    satisfaction = calc_satisfaction(total_received, TARGET_MESSAGES)

    print(f"[↑] Uplink de {device_id} | total={total_received} | alvo={TARGET_MESSAGES} | satisfação={satisfaction}")
    log_event(device_id, total_received, satisfaction)
    send_downlink(client, dev_eui, satisfaction)


with open(LOG_FILE, mode="a", newline="") as f:
    if f.tell() == 0:
        csv.writer(f).writerow(["timestamp", "device_id", "total_received", "satisfaction"])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
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
