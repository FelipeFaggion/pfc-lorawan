import paho.mqtt.client as mqtt
import json
import time

MQTT_SERVER = "au1.cloud.thethings.network"
MQTT_PORT = 1883
APPLICATION_ID = "pfc-game-theory"
API_KEY = "NNSXS.3XCBK3BPTOYYRDMGB3A7URS3ZNJOZ7HLOJ6IP2Y.LTDP5HV35N5AL7WM26NAHJGLH64CHEMHZ3XFDZYI4ON4MQY2FUTA"


DEV_EUIs = ["70B3D57ED00717AE", "70B3D57ED0072A97"]

def clear_downlink_queue(client):
  for dev_eui in DEV_EUIs:
    downlink_topic = f"v3/{APPLICATION_ID}@ttn/devices/{dev_eui}/down/replace"

    client.publish(downlink_topic, '{"downlinks": []}')
    print(f"Fila de downlink limpa para o dispositivo {dev_eui}.")

def on_connect(client, userdata, flags, rc):
  if rc == 0:
    print("Conectado ao servidor MQTT da TTN!")
    client.subscribe(f"v3/{APPLICATION_ID}@ttn/devices/+/up")

    clear_downlink_queue(client)

  else:
    print(f"Falha na conexão, código de retorno: {rc}")

def on_message(client, userdata, msg):
  print(f"Mensagem recebida no tópico: {msg.topic}")

  try:
    data = json.loads(msg.payload)
    dev_eui = data['end_device_ids']['dev_eui']


    print(f"Uplink do dispositivo {dev_eui} recebido.")
    if "uplink_message" in data:
      if data["uplink_message"].get("decoded_payload", {}).get("temperature") > 20:
        print(f"Temperatura alta ({data['uplink_message']['decoded_payload']['temperature']}). Agendando downlink para o dispositivo {dev_eui}.")
        downlink_payload_hex = "1900"
        downlink_payload_bytes = bytes.fromhex(downlink_payload_hex)
        downlink_payload_base64 = downlink_payload_bytes.hex()

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
  except Exception as e:
    print(f"Erro ao processar mensagem: {e}")


client = mqtt.Client(client_id="mqtt-server", protocol=mqtt.MQTTv311)
client.username_pw_set(APPLICATION_ID, API_KEY)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_SERVER, MQTT_PORT, 60)
client.loop_forever()
