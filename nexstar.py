#!/usr/bin/python

import serial
import io

class NexStar:
    
    def __init__(self, device):
        self.serial = serial.Serial(device, baudrate=9600, timeout=1)
        self.DIR_AZIMUTH = 0
        self.DIR_ELEVATION = 1

    def _validate_command(self, response):
        assert response == '#', 'Command failed'

    def _precise_to_degrees(self, string):
        return int(string, 16) / 2.**32 * 360.

    def _degrees_to_precise(self, degrees):
        return '%08X' % round(degrees / 360. * 2.**32)

    def _get_position(self, command):
        self.serial.write(command)
        response = self.serial.read(18)
        return (self._precise_to_degrees(response[:8]),
                self._precise_to_degrees(response[9:17]))

    def get_azel(self):
        return self._get_position('z')
        
    def get_radec(self):
        return self._get_position('e') 

    def _goto_command(self, char, values):
        command = (char + self._degrees_to_precise(values[0]) + ',' 
                   + self._degrees_to_precise(values[1]))
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)
        
    def goto_azel(self, az, el):
        self._goto_command('b', (az, el))
    
    def goto_radec(self, ra, dec):
        self._goto_command('r', (ra, dec))
        
    def sync(self, ra, dec):
        self._goto_command('s', (ra, dec))

    def get_tracking_mode(self):
        self.serial.write('t')
        response = self.serial.read(2)
        return ord(response[0])

    def set_tracking_mode(self, mode):
        command = 'T' + chr(mode)
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)

    def _var_slew_command(self, direction, rate):
        negative_rate = True if rate < 0 else False
        track_rate_high = (int(abs(rate)) * 4) / 256
        track_rate_low = (int(abs(rate)) * 4) % 256
        direction_char = chr(16) if direction == self.DIR_AZIMUTH else chr(17)
        sign_char = chr(7) if negative_rate == True else chr(6)
        command = ('P' + chr(3) + direction_char + sign_char 
                  + chr(track_rate_high) + chr(track_rate_low) + chr(0) 
                  + chr(0))
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)

    def slew_var(self, az_rate, el_rate):
       self._var_slew_command(self.DIR_AZIMUTH, az_rate)
       self._var_slew_command(self.DIR_ELEVATION, el_rate)

    def _fixed_slew_command(self, direction, rate):
        negative_rate = True if rate < 0 else False
        sign_char = chr(37) if negative_rate == True else chr(36)
        direction_char = chr(16) if direction == self.DIR_AZIMUTH else chr(17)
        rate_char = chr(int(abs(rate)))
        command = ('P' + chr(2) + direction_char + sign_char + rate_char
                   + chr(0) + chr(0) + chr(0))
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)

    def slew_fixed(self, az_rate, el_rate):
        assert (az_rate >= -9) and (az_rate <= 9), 'az_rate out of range'
        assert (el_rate >= -9) and (el_rate <= 9), 'az_rate out of range'
        self._fixed_slew_command(self.DIR_AZIMUTH, az_rate)
        self._fixed_slew_command(self.DIR_ELEVATION, el_rate)

    def get_location(self):
        self.serial.write('w')
        response = self.serial.read(9)
        lat = ()
        for char in response[:4]:
            lat = lat + (ord(char),)
        long = ()
        for char in response[4:-1]:
            long = long + (ord(char),)
        ns_char = 'N' if lat[3] == 0 else 'S'
        ew_char = 'E' if long[3] == 0 else 'W'
        print (str(lat[0]) + ' ' + str(lat[1]) + "'" + str(lat[2]) 
               + '" ' + ns_char + ', '
               + str(long[0]) + ' ' + str(long[1]) + "'" + str(long[2]) 
               + '" ' + ew_char)
        return (lat, long)

    def set_location(self, lat, long):
        command = 'W'
        for p in lat:
            command = command + chr(p)
        for p in long:
            command = command + chr(p)
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)

    def get_time(self):
        self.serial.write('h')
        response = self.serial.read(9)
        time = ()
        for char in response[:-1]:
            time = time + (ord(char),)
        return time

    def set_time(self, time):
        command = 'H'
        for p in time:
            command = command + str(p)
        self.serial.write(command)
        response = self.serial.read(1)
        self._validate_command(response)

    def get_version(self):
        self.serial.write('V')
        response = self.serial.read(3)
        return ord(response[0]) + ord(response[1]) / 10.0

    def get_model(self):
        self.serial.write('m')
        response = self.serial.read(2)
        return ord(response[0])

    def echo(self, x):
        command = 'K' + chr(x)
        self.serial.write(command)
        response = self.serial.read(2)
        return ord(response[0])

    def alignment_complete(self):
        self.serial.write('J')
        response = self.serial.read(2)
        return True if ord(response[0]) == 1 else False

    def goto_in_progress(self):
        self.serial.write('L')
        response = self.serial.read(2)
        return True if int(response[0]) == 1 else False

    def cancel_goto(self):
        self.serial.write('M')
        response = self.serial.read(1)
        self._validate_command(response)
