import paho.mqtt.client as mqtt
import json
import time
import base64
import requests

MQTT_SERVER = "au1.cloud.thethings.network"
MQTT_PORT = 1883
APPLICATION_ID = "pfc-game-theory"
API_KEY = "NNSXS.3XCBK3BPTOYYRDMGB3A7URS3ZNJOZ7HLOJ6IP2Y.LTDP5HV35N5AL7WM26NAHJGLH64CHEMHZ3XFDZYI4ON4MQY2FUTA"
API_URL_EU1 = "https://eu1.cloud.thethings.network"
API_URL_AU1 = "https://au1.cloud.thethings.network"


DEV_EUIs = ["70B3D57ED00717AE", "70B3D57ED0072A97"]
DEV_EUIS_1 = []

def get_all_dev_euis():
    """
    Recupera a lista de todos os DevEUIs registrados na aplicação TTN.
    """
    try:
        url = f"{API_URL_EU1}/api/v3/applications/{APPLICATION_ID}/devices"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        data = response.json()
        deveuis = [device['ids']['dev_eui'] for device in data['end_devices']]
        print(f"DevEUIs recuperados: {deveuis}")
        return deveuis
    except requests.exceptions.RequestException as e:
        print(f"Erro ao recuperar DevEUIs: {e}")
        return []

def reset_frame_counter(deveuis):
    """
    Reseta o contador de quadros de todos os dispositivos usando a API REST do TTN.
    """
    for dev_eui in deveuis:
        try:
            url = f"{API_URL_AU1}/api/v3/ns/applications/{APPLICATION_ID}/devices/{dev_eui}/mac-settings"
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "mac_settings": {
                    "reset_f_cnt_up": True,
                    "reset_f_cnt_down": True
                }
            }
            
            response = requests.put(url, headers=headers, json=data)
            response.raise_for_status()
            print(f"Contador de quadros resetado para o dispositivo {dev_eui}.")

        except requests.exceptions.RequestException as e:
            print(f"Erro ao resetar o contador de quadros para {dev_eui}: {e}")

def clear_downlink_queue(client, deveuis):
    """
    Limpa a fila de downlink de todos os dispositivos.
    """
    for dev_eui in deveuis:
        downlink_topic = f"v3/{APPLICATION_ID}@ttn/devices/{dev_eui}/down/replace"
        
        client.publish(downlink_topic, '{"downlinks": []}')
        print(f"Fila de downlink limpa para o dispositivo {dev_eui}.")

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Conectado ao servidor MQTT da TTN!")
        
        deveuis = get_all_dev_euis()
        client.subscribe(f"v3/{APPLICATION_ID}@ttn/devices/+/up")

        if deveuis:
            clear_downlink_queue(client, deveuis)
            reset_frame_counter(deveuis)

    else:
        print(f"Falha na conexão, código de retorno: {rc}")

def on_message(client, userdata, msg):
    print(f"Mensagem recebida no tópico: {msg.topic}")

    try:
        data = json.loads(msg.payload)
        dev_eui = data['end_device_ids']['dev_eui']
        
        print(f"Uplink do dispositivo {dev_eui} recebido.")
        if "uplink_message" in data:
            payload_data = data["uplink_message"].get("decoded_payload", {})
            temperature = payload_data.get("temperature", 0)

            if temperature > 20 and temperature <= 30:
                print(f"Temperatura alta ({temperature}). Agendando downlink para o dispositivo {dev_eui}.")
                
                downlink_payload_base64 = "GQ=="

                downlink = {
                    "downlinks": [{
                        "f_port": 1,
                        "frm_payload": downlink_payload_base64,
                        "confirmed": False
                    }]
                }

                downlink_topic = f"v3/{APPLICATION_ID}@ttn/devices/{dev_eui}/down/push"

                client.publish(downlink_topic, json.dumps(downlink))
                print("Downlink agendado.")
            else:
                 print(f"Temperatura ({temperature}) dentro do range. Nao agendando downlink.")

    except Exception as e:
        print(f"Erro ao processar mensagem: {e}")

client = mqtt.Client(client_id="mqtt-server", protocol=mqtt.MQTTv311)
client.username_pw_set(APPLICATION_ID, API_KEY)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_SERVER, MQTT_PORT, 60)
client.loop_forever()
