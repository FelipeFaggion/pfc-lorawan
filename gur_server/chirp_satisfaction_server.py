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
LOG_FILE = "dados_experimento_game_theory_v3.csv" # Mudei para v3 para não misturar

# === PARÂMETROS FIXOS ===
WINDOW_SECONDS = 300
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

def get_dynamic_target(sim_time):
    """Define o objetivo de mensagens baseado no tempo de simulação."""
    if sim_time < 2500:
        return 45
    elif sim_time < 5000:
        return 30
    else:
        return 50

def calc_satisfaction(recebido, target):
    """Calcula a satisfação com base no target atual."""
    val = 20 + 80 * math.exp(-0.02 * (recebido - target) ** 2)
    return round(max(0.0, min(100.0, val)), 2)

def get_window_stats():
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    global message_log
    # Limpa mensagens antigas
    message_log = [(t, dev) for (t, dev) in message_log if t >= cutoff]
    active_nodes = len(set(dev for _, dev in message_log))
    return len(message_log), active_nodes

def unpack_node_data(b64_data):
    """Desempacota os 7 bytes enviados pelo nodo."""
    try:
        if not b64_data: return None
        raw = base64.b64decode(b64_data)
        if len(raw) != 7: return None
        # Formato: node_id(B), state(B), last_sat(B), p_rew(B), action(B), period(H)
        data = struct.unpack('<BBBBBH', raw)
        return {
            "node_id": data[0],
            "state": data[1],
            "last_sat": data[2],        # O que o nodo viu antes
            "p_rew": data[3]/100.0,     # Probabilidade usada
            "action": "REWARD" if data[4]==1 else "PUNISH",
            "period": data[5]
        }
    except: return None

def log_data(dev_eui, f_cnt, node_data, msgs_win, target, sat, status_flag, active):
    sim_time = round(time.time() - START_TIME, 2)
    
    # Valores padrão caso venha vazio
    n_data = node_data if node_data else {
        "node_id": "ERR", "state": -1, "action": "ERR", 
        "period": -1, "last_sat": -1, "p_rew": -1
    }
    
    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([
            TRIAL_ID, sim_time, dev_eui, 
            n_data["node_id"], f_cnt,
            msgs_win, target, sat, status_flag, 
            n_data["state"], n_data["action"], n_data["period"], 
            n_data["last_sat"], n_data["p_rew"], # Adicionado conforme pedido
            active
        ])
    
    # Log no terminal simplificado
    flag_str = 'OVER' if status_flag else 'UNDER'
    print(f"💾 T={int(sim_time)}s | Win={msgs_win}/{target} | Sat={sat:.0f}% | {flag_str} | Node={n_data['node_id']} St={n_data['state']}")

def send_downlink(client, dev_eui, satisfaction, is_overload):
    # Byte 0 = Satisfação, Byte 1 = Flag de Overload (0 ou 1)
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
    sim_time = time.time() - START_TIME
    target = get_dynamic_target(sim_time)
    
    total, active = get_window_stats()
    sat = calc_satisfaction(total, target)
    status = "OVERLOAD" if total > target else "UNDERLOAD"
    
    print(f"\n--- TRIAL {TRIAL_ID} ({int(sim_time)}s) ---")
    print(f"Target Atual: {target} msgs")
    print(f"Janela Real:  {total} msgs ({status})")
    print(f"Satisfação:   {sat:.1f}%")
    print("--------------------------------------------------\n")
    Timer(TICK_INTERVAL, periodic_status).start()

# === MQTT ===
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"✅ Conectado. Iniciando Trial {TRIAL_ID} com Setpoint Dinâmico.")
        client.subscribe(f"application/{APPLICATION_ID}/device/+/event/up")

def on_message(client, userdata, msg):
    global message_log
    try:
        data = json.loads(msg.payload.decode())
        if data.get("fPort") != 2: return
        
        dev_info = data.get("deviceInfo", {})
        dev_eui = dev_info.get("devEui", "unk")
        raw_payload = data.get("data", "")
        
        # 1. Obter tempo e Target atual
        now = time.time()
        sim_time = now - START_TIME
        current_target = get_dynamic_target(sim_time)

        # 2. Processa Payload do Nodo
        node_data = unpack_node_data(raw_payload)
        
        # 3. Atualiza Janela
        message_log.append((now, dev_eui))
        total_win, active = get_window_stats()
        
        # 4. Calcula Satisfação com o Target Dinâmico
        sat = calc_satisfaction(total_win, current_target)
        
        # 5. Lógica Direcional
        is_overload = total_win > current_target
        
        # 6. Log e Envio
        log_data(dev_eui, data.get("fCnt"), node_data, total_win, current_target, sat, 1 if is_overload else 0, active)
        send_downlink(client, dev_eui, sat, is_overload)
        
    except Exception as e:
        print(f"❌ Erro: {e}")

# === INIT ===
# Cria cabeçalho apenas se arquivo não existir
if not os.path.exists(LOG_FILE):
    with open(LOG_FILE, "w", newline="") as f:
        csv.writer(f).writerow([
            "Trial_ID", "Sim_Time", "Dev_EUI", "Node_ID", "F_Cnt", 
            "Msgs_Window", "Target", "Server_Sat", "Net_Status_Flag",
            "Node_State", "Node_Action", "Node_Period", 
            "Node_Last_Sat", "Node_P_Rew", # <--- Colunas Novas
            "Active_Nodes"
        ])

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