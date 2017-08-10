import serial
import io
import datetime
import time


# Reference for NexStar commands: 
# http://www.nexstarsite.com/download/manuals/NexStarCommunicationProtocolV1.2.zip
class NexStar(object):

    # The constructor argument is a string giving the serial device connected to the 
    # NexStar hand controller. For example, '/dev/ttyUSB0'.
    def __init__(self, device):
        self.serial = serial.Serial(device, baudrate=9600, timeout=1)
        garbage_bytes = self.serial.inWaiting()
        self.serial.read(garbage_bytes)

    # stop any active slewing on destruct
    def __del__(self):
        self.cancel_goto()
        self.slew_fixed('az', 0)
        self.slew_fixed('alt', 0)

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

    # Helper function to convert precise angular values in command responses
    # to degrees. See NexStar command reference for details. Return value
    # will be in range [0,360).
    def _precise_to_degrees(self, string):
        return int(string, 16) / 2.**32 * 360.

    # Helper function to convert degrees to precise angular values for commands.
    # There are no restrictions on the range of the input. Both positive and
    # negative angles are supported.
    def _degrees_to_precise(self, degrees):
        return '%08X' % round((degrees % 360.) / 360. * 2.**32)

    # Generic get position helper function. Expects the precise version of 
    # these commands.
    def _get_position(self, command):
        assert command in ['e', 'z']
        response = self._send_command(command, 17)
        return (self._precise_to_degrees(response[:8]),
                self._precise_to_degrees(response[9:17]))

    # Returns a tuple with current (azimuth, altitude) in degrees
    # Azimuth range is [0,360) and altitude range is [-180,180)
    def get_azalt(self):
        (az, alt) = self._get_position('z')
        # adjust range of altitude from [0,360) to [-180,180)
        alt = (alt + 180.0) % 360.0 - 180.0
        return (az, alt)
        
    # Returns a tuple with current (right ascension, declination) in degrees
    def get_radec(self):
        return self._get_position('e') 

    # Generic goto helper function. Expects the precise version of these 
    # commands.
    def _goto_command(self, char, values):
        assert char in ['b', 'r', 's'] 
        command = (char + self._degrees_to_precise(values[0]) + ',' 
                   + self._degrees_to_precise(values[1]))
        self._send_command(command)
        
    # Commands the telescope to slew to the provided azimuth/altitude 
    # coordinates in degrees
    def goto_azalt(self, az, alt):
        self._goto_command('b', (az, alt))
    
    # Commands the telescope to slew to the provided right ascension and 
    # declination coordinates in degrees
    def goto_radec(self, ra, dec):
        self._goto_command('r', (ra, dec))
        
    # Informs the hand controller that the telescope is currently pointed at
    # the provided right ascension and declination coordinates to improve 
    # accuracy of future goto commands. See command reference for details. 
    def sync(self, ra, dec):
        self._goto_command('s', (ra, dec))

    # Returns the current tracking mode as an integer:
    # 0 = Off
    # 1 = Alt/Az
    # 2 = EQ North
    # 3 = EQ South
    def get_tracking_mode(self):
        response = self._send_command('t', 1)
        return ord(response[0])

    # Sets the tracking mode, 0-3, as a integer. See list in comments for 
    # get_tracking_mode.
    def set_tracking_mode(self, mode):
        assert mode in [0,1,2,3]
        command = 'T' + chr(mode)
        self._send_command(command)

    # Variable-rate slew command. Variable-rate simply means that
    # the angular rate can be specified precisely in arcseconds per second,
    # in contrast to the small number of fixed rates available on the hand-
    # controller. The axis argument may be set to 'az' or 'alt'. Rate 
    # has units of arcseconds per second and may be positive or negative.
    # Max advertised rate is 3 deg/s, max commandable rate is 16319 
    # arcseconds per second or ~4.5 deg/s.
    def slew_var(self, axis, rate):
        assert axis in ['az', 'alt']
        negative_rate = True if rate < 0 else False
        track_rate_high = (int(abs(rate)) * 4) / 256
        track_rate_low = (int(abs(rate)) * 4) % 256
        axis_char = chr(16) if axis == 'az' else chr(17)
        sign_char = chr(7) if negative_rate == True else chr(6)
        command = ('P' + chr(3) + axis_char + sign_char 
                  + chr(track_rate_high) + chr(track_rate_low) + chr(0) 
                  + chr(0))
        self._send_command(command)

    # Fixed-rate slew command. Fixed-rate means that only the nine
    # rates supported on the hand controller are available. The axis argument
    # may be set to 'az' or 'alt'. Rate is an integer from -9 to +9, 
    # where 0 is stop and +/-9 is the maximum slew rate.
    def slew_fixed(self, axis, rate):
        assert axis in ['az', 'alt']
        assert (rate >= -9) and (rate <= 9), 'fixed slew rate out of range'
        negative_rate = True if rate < 0 else False
        sign_char = chr(37) if negative_rate == True else chr(36)
        axis_char = chr(16) if axis == 'az' else chr(17)
        rate_char = chr(int(abs(rate)))
        command = ('P' + chr(2) + axis_char + sign_char + rate_char
                   + chr(0) + chr(0) + chr(0))
        self._send_command(command)

    # Returns the location of the telescope as a tuple of (latitude, 
    # longitude) in signed degrees format. 
    def get_location(self):
        response = self._send_command('w', 8)
        lat_deg = ord(response[0])
        lat_min = ord(response[1])
        lat_sec = ord(response[2])
        lat_north = True if ord(response[3]) == 0 else False
        lat = lat_deg + lat_min / 60.0 + lat_sec / 3600.0
        if lat_north == False:
            lat = -lat
        lon_deg = ord(response[4])
        lon_min = ord(response[5])
        lon_sec = ord(response[6])
        lon_east = True if ord(response[7]) == 0 else False
        lon = lon_deg + lon_min / 60.0 + lon_sec / 3600.0
        if lon_east == False:
            lon = -lon
        return (lat, lon)

    # Set the location of the telescope with latitude and longitude coordinates
    # in signed degrees format.
    def set_location(self, lat, lon):
        lat_deg = int(abs(lat))
        lat_min = int((abs(lat) - lat_deg) * 60.0)
        lat_sec = int((abs(lat) - lat_deg - lat_min / 60.0) * 3600.0)
        lon_deg = int(abs(lon))
        lon_min = int((abs(lon) - lon_deg) * 60.0)
        lon_sec = int((abs(lon) - lon_deg - lon_min / 60.0) * 3600.0)
        command = ('W' 
            + chr(lat_deg) 
            + chr(lat_min) 
            + chr(lat_sec)
            + chr(lat < 0)
            + chr(lon_deg)
            + chr(lon_min)
            + chr(lon_sec)
            + chr(lon < 0))
        self._send_command(command)

    # Returns the telescope current time in seconds since the Unix epoch
    # (1 Jan 1970). Timezone information and daylight savings time are not
    # currently supported.
    def get_time(self):
        response = self._send_command('h', 8)
        t = datetime.datetime(
            2000 + ord(response[5]), # year
            ord(response[3]),        # month
            ord(response[4]),        # day
            ord(response[0]),        # hour
            ord(response[1]),        # minute
            ord(response[2]),        # second
            0,                       # microseconds
        ) 
        return time.mktime(t.timetuple())

    # Set the time on the telescope. The timestamp argument is given in seconds
    # since the Unix epoch (1 Jan 1970). Timezone information and daylight 
    # savings time are not currently supported, so the GMT/UTC offset will be
    # set to zero and Daylight Savings will be disabled (Standard Time).
    def set_time(self, timestamp):
        t = datetime.datetime.fromtimestamp(timestamp)
        command = ('H'
            + chr(t.hour)
            + chr(t.minute)
            + chr(t.second)
            + chr(t.month)
            + chr(t.day)
            + chr(t.year - 2000)
            + chr(0)
            + chr(0)
        ) 
        self._send_command(command)

    # Returns version as a floating point value.
    def get_version(self):
        response = self._send_command('V', 2)
        return ord(response[0]) + ord(response[1]) / 10.0

    # Returns model as an integer. See NexStar command reference for decoding
    # table.
    def get_model(self):
        response = self._send_command('m', 1)
        return ord(response)

    # Returns device version as a floating point value.
    def get_device_version(self, dev):
        command = (
            'P'
            + chr(1)
            + chr(dev)
            + chr(254)
            + chr(0)
            + chr(0)
            + chr(0)
            + chr(2)
        )
        response = self._send_command(command, 2)
        return ord(response[0]) + ord(response[1]) / 10.0

    # Sends a character to the telescope hand controller, which the hand 
    # controller will echo back in response. The argument to the function 
    # is an integer in the range 0 to 255. If the command is successful, the 
    # return value will match the argument.
    def echo(self, x):
        command = 'K' + chr(x)
        response = self._send_command(command, 1)
        assert ord(response) == x, 'echo failed to return sent character'
        return ord(response)

    # Returns True if alignment has been performed, False otherwise.
    def alignment_complete(self):
        response = self._send_command('J', 1)
        return True if ord(response) == 1 else False

    # Returns True if the telescope is slewing to execute a goto command. Note
    # that this will return False if the telescope is slewing for any other
    # reason.
    def goto_in_progress(self):
        response = self._send_command('L', 1)
        return True if int(response) == 1 else False

    # Cancels a goto command that is in progress.
    def cancel_goto(self):
        self._send_command('M')
