#encoding=utf-8

import os
import time
import serial
import struct
import binascii
import functools
import logging as log


class CAN(object):
    def __init__(self, device, baudrate=1000000):
        self.conn = serial.Serial(device, 3000000, timeout=0)
        self._read_handler = self._get_bytes_sync
        self.partial_message = ""
        self.baudrate = baudrate

    def _get_bytes_sync(self):
        return self.conn.read(1)

    def _get_bytes_async(self):
        return os.read(self.conn.fd, 1024)

    def _ioloop_event_handler(self, fd, events, callback=None):
        self.recv(callback=callback)

    def add_to_ioloop(self, ioloop, callback=None):
        self._read_handler = self._get_bytes_async
        ioloop.add_handler(
            self.conn.fd,
            functools.partial(self._ioloop_event_handler, callback=callback),
            ioloop.READ)

    def parse(self, message):
        try:
            if message[0] == "T":
                id_len = 8
            else:
                id_len = 3

            # Parse the message into a (message ID, data) tuple.
            packet_id = int(message[1:1 + id_len], 16)
            packet_len = int(message[1 + id_len])
            packet_data = binascii.a2b_hex(message[2 + id_len:
                                                   2 + id_len + packet_len * 2])

            # ID, data, extended
            return packet_id, packet_data, (id_len == 8)
        except Exception:
            return None

    def open(self, callback=None):
        self.close()
        speed_code = {
            1000000: 8,
            500000: 6,
            250000: 5,
            125000: 4
        }[self.baudrate]
        self.conn.write("S{0:d}\r".format(speed_code))
        self.conn.flush()
        self.recv()
        self.conn.write("O\r")
        self.conn.flush()
        self.recv()
        time.sleep(0.1)

    def close(self, callback=None):
        self.conn.write("C\r")
        self.conn.flush()
        time.sleep(0.1)

    def recv(self, callback=None):
        bytes = ""
        new_bytes = self._read_handler()
        while new_bytes:
            bytes += new_bytes
            new_bytes = self._read_handler()

        if not bytes:
            if callback:
                return
            else:
                return []

        # Split into messages
        messages = [self.partial_message]
        for byte in bytes:
            if byte in "tT":
                messages.append(byte)
            elif messages and byte in "0123456789ABCDEF":
                messages[-1] += byte
            elif byte in "\x07\r":
                messages.append("")

        if messages[-1]:
            self.partial_message = messages.pop()
        # Filter, parse and return the messages
        messages = list(self.parse(m) for m in messages
                        if m and m[0] in ("t", "T"))
        messages = filter(lambda x: x and x[0], messages)

        if callback:
            for message in messages:
                log.debug("CAN.recv(): {!r}".format(message))
                try:
                    callback(self, message)
                except Exception:
                    raise
        else:
            for message in messages:
                log.debug("CAN.recv(): {!r}".format(message))
            return messages

    def send(self, message_id, message, extended=False):
        log.debug("CAN.send({!r}, {!r}, {!r})".format(message_id, message,
                                                      extended))

        if extended:
            start = "T{0:8X}".format(message_id)
        else:
            start = "t{0:3X}".format(message_id)
        line = "{0:s}{1:1d}{2:s}\r".format(start, len(message),
                                           binascii.b2a_hex(message))
        self.conn.write(line)
        self.conn.flush()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: driver.py CAN_DEVICE")
        sys.exit()

    can = CAN(sys.argv[1])
    can.open()
    while True:
        messages = can.recv()
        for message in messages:
            print(message)

