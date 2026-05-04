# Samuel_AI/core/led_controller.py
import serial
import time

class LEDController:
    def __init__(self, port="/dev/ttyUSB0", baud=115200):
        try:
            self.esp = serial.Serial(port, baud, timeout=1)
            time.sleep(2)
            self.set_idle()
            print("[LED] ESP32 connected.")
        except Exception as e:
            print(f"[LED] Not available: {e}")
            self.esp = None

    def _send(self, cmd):
        if self.esp:
            try:
                self.esp.write(f"{cmd}\n".encode())
            except Exception as e:
                print(f"[LED] Send error: {e}")

    def set_idle(self):      self._send("RED")
    def set_listening(self): self._send("GREEN")
    def set_thinking(self):  self._send("BLUE")
    def off(self):           self._send("OFF")