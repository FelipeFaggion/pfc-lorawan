import paho.mqtt.client as mqtt
import base64
import json

APP_ID = "50981d4c-9ebd-49fc-a7d4-f88ea8598ef2"
DEV_EUIs = ["70b3d57ed00717ae", "70b3d57ed0072a97"]


BROKER = "localhost"
PORT = 1883

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Conectado ao broker MQTT!")

    for dev_eui in DEV_EUIs:
        uplink_topic = f"application/{APP_ID}/device/{dev_eui}/event/up"
        client.subscribe(uplink_topic)
        print(f"Assinado no tópico: {uplink_topic}")

def on_message(client, userdata, msg):
    print(f"Uplink recebido no tópico {msg.topic}")
    data = json.loads(msg.payload.decode())

    parts = msg.topic.split("/")
    dev_eui = parts[3]

    if "data" in data:
        payload_bytes = base64.b64decode(data["data"])
        print(f"Payload bruto de {dev_eui}: {payload_bytes}")

    down_payload = {
        "confirmed": False,
        "fPort": 1,
        "data": base64.b64encode(b"Hello world").decode()
    }

    downlink_topic = f"application/{APP_ID}/device/{dev_eui}/command/down"
    print(f"Enviando downlink para {dev_eui}: {down_payload}")
    client.publish(downlink_topic, json.dumps(down_payload))

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print("Servidor iniciado, aguardando uplinks...\n")

    client.loop_forever()

if __name__ == "__main__":
    main()