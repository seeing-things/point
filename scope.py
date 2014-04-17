#!/usr/bin/python

import serial
import io

class NexStar:
    
    def __init__(self, device):
        self.serial = serial.Serial(device, baudrate=9600, timeout=1)

    def _precise_to_degrees(self, string):
        return int(string, 16) / 2.**32 * 360.

    def _degrees_to_precise(self, degrees):
        return '%08X' % round(degrees / 360. * 2.**32)

    def _get_position(self, command):
        self.serial.write(command)
        response = self.serial.read(18)
        return (self._precise_to_degrees(response[:8]),
                self._precise_to_degrees(response[9:16]))

    def get_azel(self):
        return self._get_position('z')
        
    def get_radec(self):
        return self._get_position('e') 

    def _goto_command(self, char, values):
        command = (char + self._degrees_to_precise(values[0]) + ',' 
                   + self._degrees_to_precise(values[1]))
        self.serial.write(command)
        response = self.serial.read(1)
        print response
        
    def goto_azel(self, az, el):
        self._goto_command('b', (az, el))
    
    def goto_radec(self, ra, dec):
        self._goto_command('r', (ra, dec))
