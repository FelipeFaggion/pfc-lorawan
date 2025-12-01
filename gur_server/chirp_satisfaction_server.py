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

# === CONFIGURAÇÕES CHIRPSTACK ===
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
APPLICATION_ID = "50981d4c-9ebd-49fc-a7d4-f88ea8598ef2"
LOG_FILE = "dados_experimento_game_theory.csv"

def get_next_trial_id():
    """Lê o CSV para descobrir o próximo número de Trial sequencial."""
    if not os.path.exists(LOG_FILE):
        return 1
    
    try:
        with open(LOG_FILE, mode="r") as f:
            reader = csv.DictReader(f)
            # Extrai todos os Trial_IDs únicos que são números
            existing_ids = set()
            for row in reader:
                try:
                    val = int(row["Trial_ID"])
                    existing_ids.add(val)
                except ValueError:
                    continue # Pula cabeçalho ou lixo
            
            if not existing_ids:
                return 1
                
            return max(existing_ids) + 1
    except Exception as e:
        print(f"⚠️ Erro ao ler Trial ID anterior: {e}. Iniciando do 1.")
        return 1

# === PARÂMETROS DO EXPERIMENTO ===
WINDOW_SECONDS = 300        # 5 minutos
TARGET_MESSAGES = 30        # Objetivo (Setpoint)
TICK_INTERVAL = 60          # Log no console a cada 60s

# === CONTROLE DE TRIAL ===
START_TIME = time.time()
TRIAL_ID = get_next_trial_id()

# === ESTRUTURAS DE DADOS ===
message_log = []            # [(timestamp, device_id), ...]

# === FUNÇÕES AUXILIARES ===
def calc_satisfaction(recebido, n):
    """Calcula satisfação (0-100%) baseada no erro em relação ao alvo."""
    val = 20 + 80 * math.exp(-0.02 * (recebido - n) ** 2)
    return round(max(0.0, min(100.0, val)), 2)

def get_window_stats():
    """Limpa log antigo e retorna contagem atual da janela."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    global message_log
    message_log = [(t, dev) for (t, dev) in message_log if t >= cutoff]
    active_nodes = len(set(dev for _, dev in message_log))
    return len(message_log), active_nodes

def unpack_node_data(b64_data):
    """
    Desempacota a struct binária enviada pelo Pico 2.
    Struct C: node_id(u8), state(u8), sat(u8), p_rew(u8), flag(u8), period(u16)
    Total: 7 bytes
    """
    try:
        if not b64_data: return None
        
        # 1. Decodifica Base64 para bytes brutos
        raw_bytes = base64.b64decode(b64_data)
        
        # 2. Verifica tamanho (deve ser 7 bytes conforme sua struct)
        if len(raw_bytes) != 7:
            print(f"Tamanho de payload inesperado: {len(raw_bytes)} bytes")
            return None

        # 3. Unpack usando struct
        # < : Little Endian (Padrão do Pico/ARM)
        # B : unsigned char (1 byte)
        # H : unsigned short (2 bytes)
        # Formato: BBBBBH
        data = struct.unpack('<BBBBBH', raw_bytes)
        
        return {
            "node_id_int": data[0],
            "state": data[1],
            "last_sat_seen": data[2],
            "p_reward": data[3] / 100.0, # Convertendo de volta para float 0.0-1.0
            "action": "REWARD" if data[4] == 1 else "PUNISH",
            "period_s": data[5]
        }
    except Exception as e:
        print(f"Erro ao desempacotar: {e}")
        return None

def log_data(dev_eui, f_cnt, node_data, total_window, server_sat, active_nodes):
    """Salva linha no CSV com dados decodificados do nodo + dados do servidor."""
    current_time = time.time()
    sim_time = round(current_time - START_TIME, 2)
    
    # Prepara valores padrão caso o decode tenha falhado
    if node_data:
        n_id = node_data["node_id_int"]
        state = node_data["state"]
        action = node_data["action"]
        p_rew = node_data["p_reward"]
        per_s = node_data["period_s"]
        last_sat = node_data["last_sat_seen"]
    else:
        n_id = state = action = p_rew = per_s = last_sat = "ERR"

    with open(LOG_FILE, mode="a", newline="") as f:
        csv.writer(f).writerow([
            TRIAL_ID,
            sim_time,
            dev_eui,
            n_id,               # ID interno do firmware
            f_cnt,
            total_window,       # Carga da Rede
            TARGET_MESSAGES,    # Setpoint
            server_sat,         # Satisfação calculada AGORA pelo servidor
            last_sat,           # Satisfação que o NODO tinha quando enviou
            state,              # Estado da FSM (0-5)
            action,             # Decisão tomada (Reward/Punish)
            p_rew,              # Probabilidade usada
            per_s,              # Período atual do nodo
            active_nodes
        ])
    
    print(f"💾 Log: T={sim_time}s | State={state} | Act={action} | Period={per_s}s | ServerSat={server_sat}%")

def send_downlink(client, dev_eui, satisfaction):
    """Envia Feedback (Satisfação) de volta ao nodo."""
    # O nodo espera receber 1 byte. Base64 encode desse byte.
    payload = {
        "devEui": dev_eui,
        "confirmed": False,
        "f_port": 2,
        "data": base64.b64encode(bytes([int(satisfaction)])).decode(),
    }
    topic = f"application/{APPLICATION_ID}/device/{dev_eui}/command/down"
    client.publish(topic, json.dumps(payload))

def periodic_status():
    """Monitoramento no terminal."""
    total, active = get_window_stats()
    sat = calc_satisfaction(total, TARGET_MESSAGES)
    print(f"\n--- TRIAL {TRIAL_ID} ({int(time.time()-START_TIME)}s) ---")
    print(f"Window: {total}/{TARGET_MESSAGES} msgs | Active Nodes: {active} | Global Sat: {sat:.1f}%")
    print("--------------------------------------------------\n")
    Timer(TICK_INTERVAL, periodic_status).start()

# === CALLBACKS MQTT ===
def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        print(f"Conectado ao Chirpstack. Trial: {TRIAL_ID}")
        client.subscribe(f"application/{APPLICATION_ID}/device/+/event/up")
    else:
        print(f"Erro conexão: rc={rc}")

def on_message(client, userdata, msg):
    global message_log
    try:
        data = json.loads(msg.payload.decode())
        
        # Filtra porta (fPort 2 = Telemetria)
        if data.get("fPort") != 2: return

        # Extração de dados básicos
        dev_info = data.get("deviceInfo", {})
        dev_eui = dev_info.get("devEui", "unknown")
        device_name = dev_info.get("deviceName", dev_eui)
        f_cnt = data.get("fCnt", -1)
        raw_payload = data.get("data", "")

        # 1. Desempacota a struct binária do nodo
        node_data = unpack_node_data(raw_payload)

        # 2. Atualiza estatísticas do servidor
        now = time.time()
        message_log.append((now, device_name))
        total_window, active = get_window_stats()
        
        # 3. Calcula nova satisfação (O Servidor é a "Environment" do jogo)
        server_satisfaction = calc_satisfaction(total_window, TARGET_MESSAGES)

        # 4. Salva no CSV
        log_data(dev_eui, f_cnt, node_data, total_window, server_satisfaction, active)

        # 5. Envia feedback (Downlink)
        send_downlink(client, dev_eui, server_satisfaction)

    except Exception as e:
        print(f"Erro processamento: {e}")

# === SETUP INICIAL ===
# Cabeçalho do CSV
if not os.path.isfile(LOG_FILE):
    with open(LOG_FILE, mode="w", newline="") as f:
        csv.writer(f).writerow([
            "Trial_ID", "Sim_Time", "Dev_EUI", "Node_Internal_ID", "F_Cnt", 
            "Msgs_Window", "Target", "Server_Calc_Sat", "Node_Last_Sat",
            "FSM_State", "Action", "P_Reward", "Period_Sec", "Active_Nodes"
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
    client.disconnect()