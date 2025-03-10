import spidev
import time
import gpiod

# GPIO 칩 및 라인 설정
CHIP = "gpiochip0"
RST_PIN = 14
BUSY_PIN = 15

# SX1262 레지스터 및 명령어
RADIO_SET_STANDBY = 0x80
RADIO_SET_DIO2_AS_RF_SWITCH_CTRL = 0x9D
RADIO_SET_DIO3_AS_TCXO_CTRL = 0x97
RADIO_SET_PACKET_TYPE = 0x8A
RADIO_SET_RF_FREQUENCY = 0x86
RADIO_SET_BUFFER_BASE_ADDRESS = 0x8F
RADIO_SET_TX_PARAMS = 0x8E
RADIO_SET_MODULATION_PARAMS = 0x8B
RADIO_WRITE_BUFFER = 0x0E
RADIO_SET_TX = 0x83
RADIO_SET_RX = 0x82
RADIO_READ_REGISTER = 0x1D


class SX1262:
    def __init__(self, spi_bus=1, spi_device=0):
        # SPI 초기화
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_device)
        self.spi.max_speed_hz = 1000000
        self.spi.mode = 0b00

        # GPIO 초기화 (gpiod)
        self.chip = gpiod.Chip(CHIP)
        self.rst_line = self.chip.get_line(RST_PIN)
        self.busy_line = self.chip.get_line(BUSY_PIN)

        # RST는 출력, BUSY는 입력으로 설정
        self.rst_line.request(consumer="sx1262_rst", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])
        self.busy_line.request(consumer="sx1262_busy", type=gpiod.LINE_REQ_DIR_IN)

        self.reset()
        self.init_radio()

    def test_spi(self):
        """ SX1262 SPI 통신 테스트 (Version ID 확인) """
        version = self.read_register(0x89, 1)[0]  # 0x89 = SX1262 버전 레지스터
        print(f"SX1262 Version: {version:02X}", flush=True)
        
        if version == 0x00 or version == 0xFF:
            print("⚠️ SPI 통신 실패! SX1262가 응답하지 않음.", flush=True)
        else:
            print("✅ SPI 통신 정상", flush=True)

    def reset(self):
        """ SX1262 하드웨어 리셋 """
        self.rst_line.set_value(0)
        time.sleep(0.1)
        self.rst_line.set_value(1)
        time.sleep(0.1)

    def wait_for_ready(self, timeout=2.0):
        """ BUSY 핀이 LOW가 될 때까지 대기 (타임아웃 추가) """
        start_time = time.time()
        while self.busy_line.get_value() == 1:
            if time.time() - start_time > timeout:
                raise TimeoutError("SX1262 is stuck in BUSY state!")
            time.sleep(0.001)

    def spi_write(self, command, data=[]):
        """ SPI 쓰기 """
        self.wait_for_ready()
        self.spi.xfer2([command] + data)

    def set_tcxo_voltage(self, voltage=0x02):
        """ DIO3을 TCXO 컨트롤로 설정 (기본값: 1.8V) """
        print(f"Setting TCXO to {voltage} (1.8V)...", flush=True)
        self.spi_write(RADIO_SET_DIO3_AS_TCXO_CTRL, [voltage, 0x64])  # 100ms 대기
        time.sleep(0.1)  # TCXO 안정화 대기
        self.reset()  # TCXO 설정 후 SX1262 리셋

    def init_radio(self):
        """ SX1262 기본 설정 """
        self.spi_write(RADIO_SET_STANDBY, [0x00])  # Standby 모드
        
        # ✅ SX1262 모드 상태 확인
        status = self.read_register(0xC0, 1)[0]
        print(f"After Standby, Status: {status:02X}", flush=True)

        # ✅ SetDIO3AsTCXOCtrl 설정 (TCXO 전압: 1.8V)
        self.set_tcxo_voltage(0x02)

        self.spi_write(RADIO_SET_DIO2_AS_RF_SWITCH_CTRL, [0x01])  # DIO2 TX/RX 자동 스위칭 활성화
        self.spi_write(RADIO_SET_PACKET_TYPE, [0x01])  # LoRa 모드 설정
        self.spi_write(RADIO_SET_RF_FREQUENCY, [0xE6, 0x66, 0x66])  # 920.9 MHz
        self.spi_write(RADIO_SET_BUFFER_BASE_ADDRESS, [0x00, 0x00])  # TX, RX 버퍼 설정
        self.spi_write(RADIO_SET_TX_PARAMS, [0x16, 0x01])  # 22 dBm 출력
        self.spi_write(RADIO_SET_MODULATION_PARAMS, [0x07, 0xC0, 0x04])  # SF7, 125kHz BW, CR 4/5

        self.set_rx_mode()

    def set_rx_mode(self):
        """ RX 모드로 전환 후 안정화 대기 """
        self.spi_write(RADIO_SET_RX, [0x00, 0x00])  # RX 모드 설정
        time.sleep(0.05)  # RX 모드 안정화 대기
        print("Switched to RX mode.", flush=True)

    def send_packet(self, data):
        """ 문자열을 바이트로 변환 후 패킷 송신 """
        if isinstance(data, str):
            data = data.encode("utf-8")  # UTF-8 바이트 변환

        if len(data) > 255:
            raise ValueError("Packet size cannot exceed 255 bytes.")

        print(f"Sending packet: {data}", flush=True)

        # TX 전환 전에 현재 모드 확인
        status = self.read_register(0xC0, 1)[0]
        print(f"Before TX, Status: {status:02X}", flush=True)

        self.spi_write(RADIO_WRITE_BUFFER, [0x00] + list(data))  # TX 버퍼에 데이터 기록
        self.spi_write(RADIO_SET_TX, [0x00, 0x00])  # 즉시 전송

        while self.busy_line.get_value() == 1:
            time.sleep(0.001)

        time.sleep(0.05)

        # TX 후 현재 상태 확인
        status = self.read_register(0xC0, 1)[0]
        print(f"After TX, Status: {status:02X}", flush=True)

        print("Packet sent. SX1262 will auto-switch back to RX mode.", flush=True)

    def read_register(self, address, length=1):
        """ 특정 레지스터 값 읽기 """
        self.wait_for_ready()
        response = self.spi.xfer2([RADIO_READ_REGISTER, (address >> 8) & 0xFF, address & 0xFF, 0x00] + [0x00] * length)
        return response[4:]  # 첫 번째 4바이트는 헤더이므로 제외


if __name__ == "__main__":
    lora = SX1262()
    lora.reset()
    lora.test_spi()
    # print("Waiting for incoming packets...", flush=True)

    # while True:
    #     lora.send_packet("Bello, Banana!")  # 5초 간격으로 전송
    #     time.sleep(5)
