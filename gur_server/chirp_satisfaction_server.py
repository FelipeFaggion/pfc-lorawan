import paho.mqtt.client as mqtt
import json
import time
import math
import base64
import csv
import struct
import os
from threading import Timer
from datetime import datetime

# === CONFIGURAÇÕES ===
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
APPLICATION_ID = "50981d4c-9ebd-49fc-a7d4-f88ea8598ef2"
LOG_FILE = "dados_experimento_game_theory_v2.csv"

# === PARÂMETROS ===
WINDOW_SECONDS = 300
TARGET_MESSAGES = 30
TICK_INTERVAL = 60

# === CONTROLE DE TRIAL ===
def get_next_trial_id():
    if not os.path.exists(LOG_FILE): return 1
    try:
        with open(LOG_FILE, mode="r") as f:
            reader = csv.DictReader(f)
            existing_ids = {int(row["Trial_ID"]) for row in reader if row["Trial_ID"].isdigit()}
            return max(existing_ids) + 1 if existing_ids else 1
    except: return 1

TRIAL_ID = get_next_trial_id()
START_TIME = time.time()
message_log = []

# === FUNÇÕES ===
def calc_satisfaction(recebido, n):
    val = 20 + 80 * math.exp(-0.02 * (recebido - n) ** 2)
    return round(max(0.0, min(100.0, val)), 2)

def get_window_stats():
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    global message_log
    message_log = [(t, dev) for (t, dev) in message_log if t >= cutoff]
    active_nodes = len(set(dev for _, dev in message_log))
    return len(message_log), active_nodes

def unpack_node_data(b64_data):
    try:
        if not b64_data: return None
        raw = base64.b64decode(b64_data)
        if len(raw) != 7: return None
        data = struct.unpack('<BBBBBH', raw)
        return {
            "node_id": data[0], "state": data[1], "last_sat": data[2],
            "p_rew": data[3]/100.0, "action": "REWARD" if data[4]==1 else "PUNISH",
            "period": data[5]
        }
    except: return None

def log_data(dev_eui, f_cnt, node_data, msgs_win, sat, status_flag, active):
    sim_time = round(time.time() - START_TIME, 2)
    n_data = node_data if node_data else {"node_id": "ERR", "state": -1, "action": "ERR", "period": -1}
    
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([
            TRIAL_ID, sim_time, dev_eui, n_data["node_id"], f_cnt,
            msgs_win, TARGET_MESSAGES, sat, status_flag, 
            n_data["state"], n_data["action"], n_data["period"], active
        ])
    print(f"💾 T={sim_time}s | Win={msgs_win} | Sat={sat}% | Flag={'OVER' if status_flag else 'UNDER'} | {dev_eui[-4:]}")

def send_downlink(client, dev_eui, satisfaction, is_overload):
    # EMPACOTAMENTO: Byte 0 = Satisfação, Byte 1 = Flag de Overload (0 ou 1)
    flag_byte = 1 if is_overload else 0
    payload_bytes = bytes([int(satisfaction), flag_byte])
    
    payload = {
        "devEui": dev_eui,
        "confirmed": False,
        "f_port": 2,
        "data": base64.b64encode(payload_bytes).decode()
    }
    topic = f"application/{APPLICATION_ID}/device/{dev_eui}/command/down"
    client.publish(topic, json.dumps(payload))

def periodic_status():
    total, active = get_window_stats()
    sat = calc_satisfaction(total, TARGET_MESSAGES)
    # Define se está em Overload (Excesso) ou Underload (Falta)
    status = "OVERLOAD" if total > TARGET_MESSAGES else "UNDERLOAD"
    
    print(f"\n--- TRIAL {TRIAL_ID} ({int(time.time()-START_TIME)}s) ---")
    print(f"Window: {total}/{TARGET_MESSAGES} | Sat: {sat:.1f}% | Status: {status}")
    print("--------------------------------------------------\n")
    Timer(TICK_INTERVAL, periodic_status).start()

# === MQTT ===
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ Conectado. Trial {TRIAL_ID}")
        client.subscribe(f"application/{APPLICATION_ID}/device/+/event/up")

def on_message(client, userdata, msg):
    global message_log
    try:
        data = json.loads(msg.payload.decode())
        if data.get("fPort") != 2: return
        
        dev_info = data.get("deviceInfo", {})
        dev_eui = dev_info.get("devEui", "unk")
        raw_payload = data.get("data", "")
        
        # 1. Processa
        node_data = unpack_node_data(raw_payload)
        now = time.time()
        message_log.append((now, dev_eui))
        
        # 2. Calcula Estado da Rede
        total_win, active = get_window_stats()
        sat = calc_satisfaction(total_win, TARGET_MESSAGES)
        
        # 3. Lógica Direcional: Se msg > target, ativa flag de Overload
        is_overload = total_win > TARGET_MESSAGES
        
        # 4. Log e Envio
        log_data(dev_eui, data.get("fCnt"), node_data, total_win, sat, 1 if is_overload else 0, active)
        send_downlink(client, dev_eui, sat, is_overload)
        
    except Exception as e:
        print(f"❌ Erro: {e}")

# === INIT ===
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow(["Trial_ID", "Sim_Time", "Dev_EUI", "Node_ID", "F_Cnt", 
                                "Msgs_Window", "Target", "Server_Sat", "Net_Status_Flag",
                                "Node_State", "Node_Action", "Node_Period", "Active_Nodes"])

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_start()
periodic_status()

try:
    while True: time.sleep(1)
except KeyboardInterrupt:
    client.loop_stop()