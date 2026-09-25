# bmp180.py - Driver simple para el sensor BMP180 en MicroPython
# Subir este archivo a la ESP32 junto con main.py

from machine import I2C
import time

class BMP180:
    def __init__(self, i2c, addr=0x77):
        self.i2c = i2c
        self.addr = addr
        self._load_calibration()
        self.oversample_setting = 3  # resolución máxima

    def _read_signed_16(self, reg):
        msb = self.i2c.readfrom_mem(self.addr, reg, 1)[0]
        lsb = self.i2c.readfrom_mem(self.addr, reg + 1, 1)[0]
        val = (msb << 8) + lsb
        if val > 32767:
            val -= 65536
        return val

    def _read_unsigned_16(self, reg):
        msb = self.i2c.readfrom_mem(self.addr, reg, 1)[0]
        lsb = self.i2c.readfrom_mem(self.addr, reg + 1, 1)[0]
        return (msb << 8) + lsb

    def _load_calibration(self):
        self.AC1 = self._read_signed_16(0xAA)
        self.AC2 = self._read_signed_16(0xAC)
        self.AC3 = self._read_signed_16(0xAE)
        self.AC4 = self._read_unsigned_16(0xB0)
        self.AC5 = self._read_unsigned_16(0xB2)
        self.AC6 = self._read_unsigned_16(0xB4)
        self.B1 = self._read_signed_16(0xB6)
        self.B2 = self._read_signed_16(0xB8)
        self.MB = self._read_signed_16(0xBA)
        self.MC = self._read_signed_16(0xBC)
        self.MD = self._read_signed_16(0xBE)

    def _read_raw_temp(self):
        self.i2c.writeto_mem(self.addr, 0xF4, b'\x2E')
        time.sleep_ms(5)
        msb = self.i2c.readfrom_mem(self.addr, 0xF6, 1)[0]
        lsb = self.i2c.readfrom_mem(self.addr, 0xF7, 1)[0]
        return (msb << 8) + lsb

    def _read_raw_pressure(self):
        self.i2c.writeto_mem(self.addr, 0xF4, bytes([0x34 + (self.oversample_setting << 6)]))
        time.sleep_ms(2 + (3 << self.oversample_setting))
        msb = self.i2c.readfrom_mem(self.addr, 0xF6, 1)[0]
        lsb = self.i2c.readfrom_mem(self.addr, 0xF7, 1)[0]
        xlsb = self.i2c.readfrom_mem(self.addr, 0xF8, 1)[0]
        raw = ((msb << 16) + (lsb << 8) + xlsb) >> (8 - self.oversample_setting)
        return raw

    def _get_b5(self, raw_temp):
        x1 = ((raw_temp - self.AC6) * self.AC5) >> 15
        x2 = (self.MC << 11) // (x1 + self.MD)
        return x1 + x2

    def read_temperature(self):
        raw_temp = self._read_raw_temp()
        b5 = self._get_b5(raw_temp)
        return ((b5 + 8) >> 4) / 10.0  # grados Celsius

    def read_pressure(self):
        raw_temp = self._read_raw_temp()
        raw_pressure = self._read_raw_pressure()
        b5 = self._get_b5(raw_temp)
        b6 = b5 - 4000
        x1 = (self.B2 * ((b6 * b6) >> 12)) >> 11
        x2 = (self.AC2 * b6) >> 11
        x3 = x1 + x2
        b3 = (((self.AC1 * 4 + x3) << self.oversample_setting) + 2) >> 2
        x1 = (self.AC3 * b6) >> 13
        x2 = (self.B1 * ((b6 * b6) >> 12)) >> 16
        x3 = ((x1 + x2) + 2) >> 2
        b4 = (self.AC4 * (x3 + 32768)) >> 15
        b7 = (raw_pressure - b3) * (50000 >> self.oversample_setting)
        if b7 < 0x80000000:
            p = (b7 * 2) // b4
        else:
            p = (b7 // b4) * 2
        x1 = (p >> 8) * (p >> 8)
        x1 = (x1 * 3038) >> 16
        x2 = (-7357 * p) >> 16
        p = p + ((x1 + x2 + 3791) >> 4)
        return p  # Pascales

    def read_altitude(self, sea_level_pa=101325):
        p = self.read_pressure()
        altitude = 44330.0 * (1.0 - (p / sea_level_pa) ** (1.0 / 5.255))
        return altitude