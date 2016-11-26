#!/usr/bin/python

import serial
import io

# Reference for NexStar commands: 
# http://www.nexstarsite.com/download/manuals/NexStarCommunicationProtocolV1.2.zip
class NexStar:
    
    def __init__(self, device):
        self.serial = serial.Serial(device, baudrate=9600, timeout=1)
        self.DIR_AZIMUTH = 0
        self.DIR_ELEVATION = 1

    # Send a command to the hand controller and get a response. The command
    # argument gives the ASCII command to send. The response_len is an integer
    # giving the number of characters expected in the response, excluding the
    # the terminating '#' character. The response received from the hand 
    # controller is validated and returned, excluding the termination character.
    def _send_command(self, command, response_len = 0):
        self.serial.write(command)
        response = self.serial.read(response_len + 1)
        assert response[-1] == '#', 'Command failed'
        return response[0:-1]

    def _precise_to_degrees(self, string):
        return int(string, 16) / 2.**32 * 360.

    def _degrees_to_precise(self, degrees):
        return '%08X' % round(degrees / 360. * 2.**32)

    # expects the precise version of the get position commands
    def _get_position(self, command):
        assert command in ['e', 'z']
        response = self._send_command(command, 17)
        return (self._precise_to_degrees(response[:8]),
                self._precise_to_degrees(response[9:17]))

    def get_azel(self):
        return self._get_position('z')
        
    def get_radec(self):
        return self._get_position('e') 

    def _goto_command(self, char, values):
        command = (char + self._degrees_to_precise(values[0]) + ',' 
                   + self._degrees_to_precise(values[1]))
        self._send_command(command)
        
    def goto_azel(self, az, el):
        self._goto_command('b', (az, el))
    
    def goto_radec(self, ra, dec):
        self._goto_command('r', (ra, dec))
        
    def sync(self, ra, dec):
        self._goto_command('s', (ra, dec))

    def get_tracking_mode(self):
        response = self._send_command('t', 1)
        return ord(response[0])

    def set_tracking_mode(self, mode):
        command = 'T' + chr(mode)
        self._send_command(command)

    def _var_slew_command(self, direction, rate):
        negative_rate = True if rate < 0 else False
        track_rate_high = (int(abs(rate)) * 4) / 256
        track_rate_low = (int(abs(rate)) * 4) % 256
        direction_char = chr(16) if direction == self.DIR_AZIMUTH else chr(17)
        sign_char = chr(7) if negative_rate == True else chr(6)
        command = ('P' + chr(3) + direction_char + sign_char 
                  + chr(track_rate_high) + chr(track_rate_low) + chr(0) 
                  + chr(0))
        self._send_command(command)

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
        self._send_command(command)

    def slew_fixed(self, az_rate, el_rate):
        assert (az_rate >= -9) and (az_rate <= 9), 'az_rate out of range'
        assert (el_rate >= -9) and (el_rate <= 9), 'el_rate out of range'
        self._fixed_slew_command(self.DIR_AZIMUTH, az_rate)
        self._fixed_slew_command(self.DIR_ELEVATION, el_rate)

    def get_location(self):
        response = self._send_command('w', 8)
        lat = ()
        for char in response[:4]:
            lat = lat + (ord(char),)
        long = ()
        for char in response[4:]:
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
        self._send_command(command)

    def get_time(self):
        response = self._send_command('h', 8)
        time = ()
        for char in response:
            time = time + (ord(char),)
        return time

    def set_time(self, time):
        command = 'H'
        for p in time:
            command = command + str(p)
        self._send_command(command)

    def get_version(self):
        response = self._send_command('V', 2)
        return ord(response[0]) + ord(response[1]) / 10.0

    def get_model(self):
        response = self._send_command('m', 1)
        return ord(response)

    def echo(self, x):
        command = 'K' + chr(x)
        response = self._send_command(command, 1)
        return ord(response)

    def alignment_complete(self):
        response = self._send_command('J', 1)
        return True if ord(response) == 1 else False

    def goto_in_progress(self):
        response = self._send_command('L', 1)
        return True if int(response) == 1 else False

    def cancel_goto(self):
        self._send_command('M')

