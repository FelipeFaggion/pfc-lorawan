import paho.mqtt.client as mqtt
import json
import time
import math
import base64
from threading import Timer

APP_ID = "pfc-game-theory"
TTN_REGION = "au1"
MQTT_BROKER = f"{TTN_REGION}.cloud.thethings.network"
API_KEY = "NNSXS.SH5KOVWVEZJGZIV4QAJRTO4CJAHTIGRIEP6H56Q.3ISS6RW2AFNXJQUOABTKV5PB46N7DQAP5AYL625WMUKIDEQROR7Q"

WINDOW_SECONDS = 900  
TARGET_MESSAGES = 30

nodes = {}
window_start = time.time()


def calc_satisfaction(recebido, n):
    """Cálculo gaussiano do grau de satisfação."""
    return round(20 + 80 * math.exp(-0.002 * (recebido - n)**2), 2)


def send_downlink(client, device_id, satisfaction):
    """Envia downlink com o grau de satisfação."""
    payload = {
        "downlinks": [{
            "f_port": 1,
            "frm_payload": base64.b64encode(bytes([int(satisfaction)])).decode(),
            "confirmed": False
        }]
    }

    topic = f"v3/{APP_ID}@ttn/devices/{device_id}/down/push"
    client.publish(topic, json.dumps(payload))
    print(f"[↓] Downlink enviado para {device_id}: satisfação={satisfaction}")


def reset_window():
    """Zera contadores a cada janela de tempo."""
    global nodes, window_start
    nodes = {}
    window_start = time.time()
    print(f"\n🕒 Nova janela iniciada às {time.strftime('%H:%M:%S')}\n")
    Timer(WINDOW_SECONDS, reset_window).start()


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

    print(f"[↑] Uplink de {device_id} | total={total_received} | satisfação={satisfaction}")

    send_downlink(client, device_id, satisfaction)

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)  # usa API moderna
client.username_pw_set(APP_ID, API_KEY)
client.tls_set()
client.tls_insecure_set(False)   # garante verificação TLS
client.on_connect = on_connect
client.on_message = on_message

print(f"🔗 Conectando a {MQTT_BROKER} ...")
client.connect(MQTT_BROKER, 8883, 60)
client.loop_start()

reset_window()
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Encerrando servidor...")
    client.loop_stop()
    client.disconnect()
