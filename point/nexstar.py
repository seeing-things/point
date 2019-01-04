import datetime
import time
import calendar
import serial


__all__ = ['NexStar']


# Reference for NexStar commands:
# http://www.nexstarsite.com/download/manuals/NexStarCommunicationProtocolV1.2.zip
class NexStar:

    class ResponseException(Exception):
        """Raised on bad command responses from NexStar."""

    class ReadTimeoutException(Exception):
        """Raised when read from NexStar times out."""

    # The constructor argument is a string giving the serial device connected to the
    # NexStar hand controller. For example, '/dev/ttyUSB0'.
    def __init__(self, device, read_timeout=1.0):
        self.serial = serial.Serial(device, baudrate=9600, timeout=read_timeout)

    # stop any active slewing on destruct
    def __del__(self):
        # Destructor could be called when a command was already in progress.
        # Wait for any commands to complete and flush the read buffer before
        # proceeding.
        time.sleep(0.1)
        self.cancel_goto()
        self.slew_fixed('az', 0)
        self.slew_fixed('alt', 0)

    def _send_command(self, command, response_len=None):
        """Sends a command to the NexStar hand controller and reads back the response.

        Args:
            command: A byte array containing the ASCII command to send.
            response_len: An integer giving the expected length of the response to this command,
                not counting the terminating '#' character. If set, a ResponseException will be
                raised if the actual response string does not have this length. If None, no length
                validation is performed.

        Returns:
            A byte array containing the response from the hand controller, excluding the
            termination character.

        Raises:
            ReadTimeoutException: When a timeout occurs during the attempt to read from the serial
                device.
            ResponseException: When the response length does not match the value of the
                response_len argument.
        """

        # eliminate any stale data sitting in the read buffer
        self.serial.read(self.serial.in_waiting)

        self.serial.write(command)

        # all valid mount responses are terminated with a '#' character
        response = self.serial.read_until(terminator=b'#')

        # if the byte array does not end with '#' the read timed out
        if response[-1:] != b'#':
            raise NexStar.ReadTimeoutException()

        # strip off the terminator
        response = response[:-1]

        # trim away any leading bytes from previous responses
        response = response.rsplit(b'#', 1)[-1]

        # validate length of response if a length was provided
        if response_len is not None:
            if len(response) != response_len:
                raise NexStar.ResponseException()

        return response

    # Helper function to convert precise angular values in command responses
    # to degrees. See NexStar command reference for details. Return value
    # will be in range [0,360).
    @staticmethod
    def _precise_to_degrees(string):
        return int(string, 16) / 2.**32 * 360.

    # Helper function to convert degrees to precise angular values for commands.
    # There are no restrictions on the range of the input. Both positive and
    # negative angles are supported.
    @staticmethod
    def _degrees_to_precise(degrees):
        return b'%08X' % round((degrees % 360.) / 360. * 2.**32)

    # Generic get position helper function. Expects the precise version of
    # these commands.
    def _get_position(self, command):
        assert command in [b'e', b'z']
        response = self._send_command(command, 17)
        return (self._precise_to_degrees(response[0: 8]),
                self._precise_to_degrees(response[9:17]))

    # Returns a tuple with current (azimuth, altitude) in degrees
    # Azimuth range is [0,360) and altitude range is [-180,180)
    def get_azalt(self):
        (az, alt) = self._get_position(b'z')
        # adjust range of altitude from [0,360) to [-180,180)
        alt = (alt + 180.0) % 360.0 - 180.0
        return (az, alt)

    # Returns a tuple with current (right ascension, declination) in degrees
    def get_radec(self):
        return self._get_position(b'e')

    # Generic goto helper function. Expects the precise version of these
    # commands.
    def _goto_command(self, char, values):
        assert char in [b'b', b'r', b's']
        command = (char
                   + self._degrees_to_precise(values[0])
                   + b','
                   + self._degrees_to_precise(values[1]))
        self._send_command(command)

    # Commands the telescope to slew to the provided azimuth/altitude
    # coordinates in degrees
    def goto_azalt(self, az, alt):
        self._goto_command(b'b', (az, alt))

    # Commands the telescope to slew to the provided right ascension and
    # declination coordinates in degrees
    def goto_radec(self, ra, dec):
        self._goto_command(b'r', (ra, dec))

    # Informs the hand controller that the telescope is currently pointed at
    # the provided right ascension and declination coordinates to improve
    # accuracy of future goto commands. See command reference for details.
    def sync(self, ra, dec):
        self._goto_command(b's', (ra, dec))

    # Returns the current tracking mode as an integer:
    # 0 = Off
    # 1 = Alt/Az
    # 2 = EQ North
    # 3 = EQ South
    def get_tracking_mode(self):
        response = self._send_command(b't', 1)
        return response[0]

    # Sets the tracking mode, 0-3, as a integer. See list in comments for
    # get_tracking_mode.
    def set_tracking_mode(self, mode):
        assert mode in range(0, 4)
        command = b'T' + bytes([mode])
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
        negative_rate = (rate < 0)
        axis_char = 17 if axis != 'az'  else 16
        sign_char =  7 if negative_rate else  6
        track_rate_high = (int(abs(rate)) * 4) // 256
        track_rate_low  = (int(abs(rate)) * 4)  % 256
        command = b'P' + bytes([
            3,
            axis_char,
            sign_char,
            track_rate_high,
            track_rate_low,
            0,
            0,
        ])
        self._send_command(command)

    # Fixed-rate slew command. Fixed-rate means that only the nine
    # rates supported on the hand controller are available. The axis argument
    # may be set to 'az' or 'alt'. Rate is an integer from -9 to +9,
    # where 0 is stop and +/-9 is the maximum slew rate.
    def slew_fixed(self, axis, rate):
        assert axis in ['az', 'alt']
        assert -9 <= rate <= 9, 'fixed slew rate out of range'
        negative_rate = (rate < 0)
        axis_char = 17 if axis != 'az'  else 16
        sign_char = 37 if negative_rate else 36
        rate_char = int(abs(rate))
        command = b'P' + bytes([
            2,
            axis_char,
            sign_char,
            rate_char,
            0,
            0,
            0,
        ])
        self._send_command(command)

    # Returns the location of the telescope as a tuple of (latitude,
    # longitude) in signed degrees format.
    def get_location(self):
        response = self._send_command(b'w', 8)
        lat_deg = response[0]
        lat_min = response[1]
        lat_sec = response[2]
        lat_north = (response[3] == 0)
        lat = lat_deg + lat_min / 60.0 + lat_sec / 3600.0
        if not lat_north:
            lat = -lat
        lon_deg = response[4]
        lon_min = response[5]
        lon_sec = response[6]
        lon_east = (response[7] == 0)
        lon = lon_deg + lon_min / 60.0 + lon_sec / 3600.0
        if not lon_east:
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
        command = b'W' + bytes([
            lat_deg,
            lat_min,
            lat_sec,
            lat < 0,
            lon_deg,
            lon_min,
            lon_sec,
            lon < 0,
        ])
        self._send_command(command)

    # Returns the telescope current time in seconds since the Unix epoch
    # (1 Jan 1970). Timezone information and daylight savings time are not
    # currently supported.
    def get_time(self):
        response = self._send_command(b'h', 8)
        t = datetime.datetime(
            response[5] + 2000, # year
            response[3],        # month
            response[4],        # day
            response[0],        # hour
            response[1],        # minute
            response[2],        # second
            0,                  # microseconds
        )
        return calendar.timegm(t.timetuple())

    # Set the time on the telescope. The timestamp argument is given in seconds
    # since the Unix epoch (1 Jan 1970). Timezone information and daylight
    # savings time are not currently supported, so the GMT/UTC offset will be
    # set to zero and Daylight Savings will be disabled (Standard Time).
    def set_time(self, timestamp):
        t = datetime.datetime.utcfromtimestamp(timestamp)
        command = b'H' + bytes([
            t.hour,
            t.minute,
            t.second,
            t.month,
            t.day,
            t.year - 2000,
            0,
            0,
        ])
        self._send_command(command)

    # Returns version as a floating point value.
    def get_version(self):
        response = self._send_command(b'V', 2)
        return response[0] + response[1] / 10.0

    # Returns model as an integer. See NexStar command reference for decoding
    # table.
    def get_model(self):
        response = self._send_command(b'm', 1)
        return response[0]

    # Returns device version as a floating point value.
    def get_device_version(self, dev):
        command = b'P' + bytes([
            1,
            dev,
            254,
            0,
            0,
            0,
            2,
        ])
        response = self._send_command(command, 2)
        return response[0] + response[1] / 10.0

    # Sends a character to the telescope hand controller, which the hand
    # controller will echo back in response. The argument to the function
    # is an integer in the range 0 to 255. If the command is successful, the
    # return value will match the argument.
    def echo(self, x):
        command = b'K' + bytes([x])
        response = self._send_command(command, 1)
        assert response[0] == x, 'echo failed to return sent character'
        return response[0]

    # Returns True if alignment has been performed, False otherwise.
    def alignment_complete(self):
        response = self._send_command(b'J', 1)
        return response[0] == 1

    # Returns True if the telescope is slewing to execute a goto command. Note
    # that this will return False if the telescope is slewing for any other
    # reason.
    def goto_in_progress(self):
        response = self._send_command(b'L', 1)
        return response == b'1'

    # Cancels a goto command that is in progress.
    def cancel_goto(self):
        self._send_command(b'M')
