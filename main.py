from SX126x import SX126x, LoRaGpio, LoRaSpi
import time
import json
import random
import argparse
import inspect


parser = argparse.ArgumentParser()
parser.add_argument('-p', type=str, help=' : Lora Protocol', choices=[
    "lora",
    "meshtastic"
], required=True)
parser.add_argument('-m', type=str, help=' : Rx/Tx Mode', choices=[
    "receive",
    "receive_listen",
    "receive_continuous",
    "transmit_message",
    "transmit_broadcast",
], required=True)
parser.add_argument('-t', type=str, help=' : Tx Message')
parser.add_argument('-i', type=int, help=' : Tx Broadcast Interval', default=5)
args = parser.parse_args()


spi = LoRaSpi(1, 0)
# cs = LoRaGpio(0, 18)
reset = LoRaGpio(0, 14)
busy = LoRaGpio(0, 15)

LoRa = SX126x(spi, reset, busy)


print("Begin LoRa radio")
if not LoRa.begin() :
    raise Exception("Something wrong, can't begin LoRa radio")

print("Set RF module to use TCXO as clock reference")
LoRa.setDio3TcxoCtrl(LoRa.DIO3_OUTPUT_1_8, LoRa.TCXO_DELAY_10)

print("Set frequency to 921.625 Mhz")
LoRa.setFrequency(921625000)

print("Set TX power to +22 dBm")
LoRa.setTxPower(22, LoRa.TX_POWER_SX1262)

print("Set RX gain to power saving gain")
LoRa.setRxGain(LoRa.RX_GAIN_POWER_SAVING)

sf = 11                                                         # LoRa spreading factor: 11
bw = 250000                                                     # Bandwidth: 250 kHz
cr = 5                                                          # Coding rate: 4/5
print(f"Set modulation parameters:\n\tSpreading factor = {sf}\n\tBandwidth = {bw / 1000} kHz\n\tCoding rate = 4/{cr}")
LoRa.setLoRaModulation(sf, bw, cr)

headerType = LoRa.HEADER_EXPLICIT                               # Explicit header mode
preambleLength = 12                                             # Set preamble length to 12
payloadLength = 255                                              # Initialize payloadLength to 15
crcType = True                                                  # Set CRC enable
print(f"Set packet parameters:\n\tExplicit header type\n\tPreamble length = {preambleLength}\n\tPayload Length = {payloadLength}\n\tCRC {crcType}")
LoRa.setLoRaPacket(headerType, preambleLength, payloadLength, crcType)

print("Set syncronize word to 0x3444")
LoRa.setSyncWord(0x3444)


def flush_rx_buffer(timeout=0.5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        while LoRa.available():
            LoRa.read()
        time.sleep(0.01)  # 짧은 시간 대기


def lora_receive():
    flush_rx_buffer()
    print("\n-- LoRa Receiver --\n")

    while True :
        LoRa.request()
        LoRa.wait()

        message = ""

        while LoRa.available() > 1 :
            message += chr(LoRa.read())
        counter = LoRa.read()

        print(f"{message}  {counter}")

        print("Packet status: RSSI = {0:0.2f} dBm | SNR = {1:0.2f} dB".format(LoRa.packetRssi(), LoRa.snr()))

        status = LoRa.status()
        if status == LoRa.STATUS_CRC_ERR : print("CRC error")
        elif status == LoRa.STATUS_HEADER_ERR : print("Packet header error")


def lora_receive_listen():
    flush_rx_buffer()
    print("\n-- LoRa Receiver Listen --\n")

    while True :
        rxPeriod = 10
        sleepPeriod = 10
        LoRa.listen(rxPeriod, sleepPeriod)

        if LoRa.available() :
            message = ""
            
            while LoRa.available() > 1 :
                message += chr(LoRa.read())
            counter = LoRa.read()

            print(f"{message}  {counter}")

            print("Packet status: RSSI = {0:0.2f} dBm | SNR = {1:0.2f} dB".format(LoRa.packetRssi(), LoRa.snr()))

            status = LoRa.status()
            if status == LoRa.STATUS_CRC_ERR : print("CRC error")
            elif status == LoRa.STATUS_HEADER_ERR : print("Packet header error")


def lora_receive_continuous():
    flush_rx_buffer()
    print("\n-- LoRa Receiver Continuous --\n")
    LoRa.request(LoRa.RX_CONTINUOUS)

    while True :
        if LoRa.available() :
            message = ""

            while LoRa.available() > 1 :
                message += chr(LoRa.read())
            counter = LoRa.read()

            print(f"{message}  {counter}")

            print("Packet status: RSSI = {0:0.2f} dBm | SNR = {1:0.2f} dB".format(LoRa.packetRssi(), LoRa.snr()))

            status = LoRa.status()
            if status == LoRa.STATUS_CRC_ERR : print("CRC error")
            if status == LoRa.STATUS_HEADER_ERR : print("Packet header error")


def lora_transmit_message(text):
    print("\n-- LoRa Transmitter --\n")

    message = f"{text}\0"
    messageList = list(message)
    for i in range(len(messageList)) : messageList[i] = ord(messageList[i])

    LoRa.beginPacket()
    LoRa.write(messageList, len(messageList))
    LoRa.endPacket()

    print(message)

    LoRa.wait()

    print("Transmit time: {0:0.2f} ms | Data rate: {1:0.2f} byte/s".format(LoRa.transmitTime(), LoRa.dataRate()))


def lora_transmit_broadcast(text, interval = 5):
    print("\n-- LoRa Transmitter Broadcast--\n")

    message = f"{text}\0"
    messageList = list(message)
    for i in range(len(messageList)) : messageList[i] = ord(messageList[i])
    counter = 0

    while True :
        LoRa.beginPacket()
        LoRa.write(messageList, len(messageList))
        LoRa.write([counter], 1)
        LoRa.endPacket()

        print(f"{message}  {counter}")

        LoRa.wait()

        print("Transmit time: {0:0.2f} ms | Data rate: {1:0.2f} byte/s".format(LoRa.transmitTime(), LoRa.dataRate()))

        time.sleep(interval)
        counter = (counter + 1) % 256


# Meshtastic 노드 고유 ID (각 노드마다 고유해야 함)
NODE_ID = "paragonnov"  


def _create_meshtastic_packet(payload, destination="*", ttl=10, seq=None):
    if seq is None:
        seq = random.randint(0, 255)
    packet = {
        "from": NODE_ID,
        "to": destination,
        "payload": payload,
        "ttl": ttl,
        "seq": seq,
        "timestamp": int(time.time())
    }
    return json.dumps(packet)


def _process_received_meshtastic_packet(packet_str):
    try:
        packet = json.loads(packet_str)
    except json.JSONDecodeError:
        print("Received non-Meshtastic message:", packet_str)
        return

    sender = packet.get("from", "")
    destination = packet.get("to", "")
    payload = packet.get("payload", "")
    ttl = packet.get("ttl", 0)
    seq = packet.get("seq", 0)
    timestamp = packet.get("timestamp", 0)

    print(f"Received from {sender} -> to {destination}: {payload} (TTL: {ttl}, seq: {seq}, time: {timestamp})")

    if destination != "*" and destination != NODE_ID:
        if ttl > 0:
            packet["ttl"] = ttl - 1
            forward_packet_str = json.dumps(packet)
            print("Forwarding message:", forward_packet_str)
            forward_packet_bytes = [ord(c) for c in forward_packet_str]
            LoRa.beginPacket()
            LoRa.write(forward_packet_bytes, len(forward_packet_bytes))
            LoRa.endPacket()
            LoRa.wait()


def meshtastic_transmit_message(payload, destination="*", ttl=10):
    packet_str = _create_meshtastic_packet(payload, destination, ttl)
    packet_bytes = [ord(c) for c in packet_str]
    
    LoRa.beginPacket()
    LoRa.write(packet_bytes, len(packet_bytes))
    LoRa.endPacket()
    LoRa.wait()
    
    print("Sent:", packet_str)


def meshtastic_receive_continuous():
    flush_rx_buffer()
    print("\n-- Meshtastic Node Receiver Continuous --\n")
    LoRa.request(LoRa.RX_CONTINUOUS)

    while True:
        if LoRa.available():
            packet_str = ""
            while LoRa.available():
                packet_str += chr(LoRa.read())
            _process_received_meshtastic_packet(packet_str)


if __name__ == "__main__":
    try:
        func = locals()[f"{args.p}_{args.m}"]
        args_count = len(inspect.getfullargspec(func).args)
        
        if args_count == 0:
            func()
        elif args_count == 1:
            func(args.t)
        elif args_count == 2:
            func(args.t, args.i)
        else:
            raise
    except:
        print("Invalid argument")
    

