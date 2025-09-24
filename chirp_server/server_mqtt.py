import paho.mqtt.client as mqtt
import base64
import json

APP_ID = "50981d4c-9ebd-49fc-a7d4-f88ea8598ef2"  # seu applicationId
DEV_EUI = "70b3d57ed00717ae"

UPLINK_TOPIC = f"application/{APP_ID}/device/{DEV_EUI}/event/up"
DOWNLINK_TOPIC = f"application/{APP_ID}/device/{DEV_EUI}/command/down"

BROKER = "localhost"
PORT = 1883

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Conectado ao broker MQTT!")
    client.subscribe(UPLINK_TOPIC)
    print(f"Assinado no tópico: {UPLINK_TOPIC}")

def on_message(client, userdata, msg):
    print(f"\n📡 Uplink recebido no tópico {msg.topic}")
    data = json.loads(msg.payload.decode())

    # Decodifica payload (caso exista)
    if "data" in data:
        payload_bytes = base64.b64decode(data["data"])
        print(f"Payload bruto: {payload_bytes}")

    # Monta o downlink "Hello world"
    down_payload = {
        "confirmed": False,
        "fPort": 1,
        "data": base64.b64encode(b"Hello world").decode()
    }

    print(f"🔽 Enviando downlink: {down_payload}")
    client.publish(DOWNLINK_TOPIC, json.dumps(down_payload))

def main():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message

    client.connect(BROKER, PORT, 60)
    print("Servidor iniciado, aguardando up links...\n")

    client.loop_forever()

if __name__ == "__main__":
    main()

