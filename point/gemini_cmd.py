#!/usr/bin/env python3

"""
A simple script for sending raw serial commands to Gemini.
"""

import time
import serial
import readline

def main():

    ser = serial.Serial('/dev/ttyACM0', baudrate=9600)

    while True:
        cmd = input('> ')

        if len(cmd) == 0:
            continue

        # losmandy native commands -- add checksum
        if cmd[0] == '<' or cmd[0] == '>':

            if ':' not in cmd:
                print("Rejected: Native command must contain a ':' character")
                continue

            checksum = 0
            for c in cmd:
                checksum = checksum ^ ord(c)
            checksum %= 128
            checksum += 64
            cmd = cmd + chr(checksum) + '#'

            print('Native command: ' + cmd)

        # LX200 command format
        elif cmd[0] == ':':
            print('LX200 command: ' + cmd)
            pass
        else:
            print("Rejected: Must start with ':', '<', or '>'")
            continue

        ser.write(cmd.encode())
        time.sleep(0.1)
        reply = ser.read(ser.in_waiting).decode()
        if len(reply) > 0:
            print('reply: ' + reply)

if __name__ == "__main__":
    main()
