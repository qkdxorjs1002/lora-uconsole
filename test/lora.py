#!/usr/bin/env python3
import spidev
import time
import gpiod
import signal
import sys

class SX1262:
    def __init__(self, spi_bus=1, spi_cs=0, reset_pin=14, busy_pin=15, spi_speed_hz=8 * 1000 * 1000):
        # SPI 설정 (SPI1, CS0 사용)
        self.spi = spidev.SpiDev()
        self.spi.open(spi_bus, spi_cs)
        self.spi.max_speed_hz = spi_speed_hz
        self.spi.mode = 0b00

        # libgpiod를 사용하여 Reset 및 Busy 핀 초기화
        self.chip = gpiod.Chip("gpiochip0")
        self.reset_line = self.chip.get_line(reset_pin)
        self.busy_line = self.chip.get_line(busy_pin)
        
        # Reset은 출력, Busy는 입력으로 요청 (출력 핀은 기본 HIGH)
        self.reset_line.request(consumer="sx1262", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1])
        self.busy_line.request(consumer="sx1262", type=gpiod.LINE_REQ_DIR_IN)
    
    def wait_for_busy(self, timeout=10.0):
        """Busy 핀이 LOW로 전환될 때까지 대기 (타임아웃: 초 단위)"""
        start = time.time()
        while self.busy_line.get_value() == 1:
            if time.time() - start > timeout:
                raise TimeoutError("Busy 핀 대기 시간 초과")
            time.sleep(0.001)
    
    def spi_transfer(self, data):
        """SPI 전송 (하드웨어 CS 사용)"""
        return self.spi.xfer2(data)
    
    def send_command(self, opcode, parameters):
        """명령어 전송 전후로 Busy 상태 체크"""
        self.wait_for_busy()
        self.spi_transfer([opcode] + parameters)
        self.wait_for_busy()
    
    def get_status(self):
        """GetStatus 명령(0xC0)을 통해 상태값 읽기"""
        self.wait_for_busy()
        ret = self.spi_transfer([0xC0, 0x00])
        self.wait_for_busy()
        return ret[1]
    
    def reset_module(self):
        """하드웨어 Reset 수행 (Reset 핀 LOW->HIGH)"""
        self.reset_line.set_value(0)
        time.sleep(0.1)
        self.reset_line.set_value(1)
        time.sleep(0.1)
        self.wait_for_busy()
    
    def write_buffer(self, offset, data_bytes):
        """버퍼 쓰기 명령 (opcode 0x0E)로 데이터를 전송"""
        self.send_command(0x0E, [offset] + list(data_bytes))
    
    def send_packet(self, payload):
        """패킷 송신: 버퍼에 payload 기록 후 TX 명령 전송"""
        self.write_buffer(0x00, payload)
        # TX 명령: opcode 0x83, 이후 2바이트 타임아웃 (0x0000: 즉시 TX)
        self.send_command(0x83, [0x00, 0x00])
        # 송신 후 continuous RX 모드로 복귀 (opcode 0x82, 타임아웃: 0xFFFFFF)
        self.send_command(0x82, [0x04, 0xE2, 0x00])
    
    def initialize_module(self):
        """SX1262 초기화 시퀀스 수행"""
        self.reset_module()
        # TCXO 모드 활성화: DIO3 제어 (opcode 0x97, 파라미터 예: 0x02 => 1.8V)
        self.send_command(0x97, [0x02, 0x04, 0xE2, 0x00])
        # DIO2를 RF 스위치로 사용 (opcode 0x9D, 파라미터 0x01: RF 스위치 모드)
        self.send_command(0x9D, [0x01])
        # 패킷 타입 설정 (opcode 0x8A, 파라미터 0x01: LoRa 모드)
        self.send_command(0x8A, [0x01])
        # RF 주파수 설정 (opcode 0x86, 4바이트: 921MHz 예제값)
        self.send_command(0x86, [0x39, 0x90, 0x00, 0x00])
        # RF 변조 방식 설정 (opcode 0x8B, SF7, 125kHz BW, CR 4/5)
        self.send_command(0x8B, [0x07, 0xC0, 0x04])
        # TX 파라미터 설정 (opcode 0x8E, [TX power, ramp time] 예: +22dBm, ramp time 0x04)
        self.send_command(0x8E, [0x16, 0x04])
        # 수신 모드 진입 (opcode 0x82, 3바이트 타임아웃: 0xFFFFFF => continuous RX)
        self.send_command(0x82, [0x04, 0xE2, 0x00])
    
    def spi_test(self):
        """SPI 테스트: GetStatus 명령을 통해 모듈 상태 읽기"""
        status = self.get_status()
        print("모듈 상태 (GetStatus): 0x{:02X}".format(status))
    
    def close(self):
        """자원 정리: SPI 닫기 및 GPIO 핀을 no 상태로 돌려놓음"""
        try:
            self.spi.close()
        except Exception as e:
            print("SPI close 오류:", e)
        try:
            self.reset_line.release()
        except Exception as e:
            print("Reset 라인 release 오류:", e)
        try:
            self.busy_line.release()
        except Exception as e:
            print("Busy 라인 release 오류:", e)

def signal_handler(sig, frame):
    print("\n종료 신호 수신, 프로그램 종료 중...")
    sys.exit(0)

def main():
    # SIGINT, SIGTERM 신호를 핸들링하여 종료 시 cleanup이 동작하도록 함
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    sx = None
    try:
        sx = SX1262()
        print("모듈 초기화 중...")
        sx.initialize_module()
        print("SPI 테스트 중...")
        sx.spi_test()
        print("초기화 완료, continuous RX 모드 진입")
        while True:
            time.sleep(5)
            msg = b"Bello, Banana"
            print("메시지 송신: {}".format(msg.decode()))
            sx.send_packet(msg)
    except KeyboardInterrupt:
        print("키보드 인터럽트 발생, 종료합니다.")
    except Exception as e:
        print("오류 발생:", e)
    finally:
        if sx is not None:
            sx.close()
        print("GPIO 핀을 no 상태로 돌려놓았습니다.")

if __name__ == "__main__":
    main()
