import serial
import datetime
import time
import calendar


__all__ = ['Gemini2']


# TODO: Modifiy the Gemini2 class to support both serial and network interfaces
# TODO: Create an abstract class for transporting serial commands, make
#       Gemini2UDP inherit from this. Make a corresponding Gemini2Serial class
#       that also inherits from this.
# TODO: Handle UDP response timeouts appropriately


class Gemini2UDP(object):
    """Implements the Gemini 2 UDP protocol.

    This class implements the UDP protocol for Gemini 2 as documented here:
    http://gemini-2.com/Gemini2_drivers/UPD_Protocol/Gemini_UDP_Protocol_Specification_1.0.pdf

    Attributes:
        seqnum: packet sequence number
        sendaddr: send address tuple
        sock: socket.socket object
    """

    def __init__(self, hostname, port=11110):
        """Constructs a Gemini2UDP object.

        Args:
            hostname: The hostname or IP address of Gemini 2 as a string.
            port: UDP protocol port number for Gemini 2.
        """
        self.seqnum = 0
        self.sendaddr = (hostname, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.25)
        self.sock.bind(('0.0.0.0', port))

    def send_cmd(self, serial_cmds):
        """Sends one or more serial commands and gets a response.

        This method sends one or more serial commands and waits to receive
        the corresponding response from Gemini 2.

        Args:
            serial_cmds: A string containing the serial command(s) to send.
                The string should include the entire command including the
                termination character. If multiple commands are to be sent
                they should be concatenated back-to-back with no additional
                delimiting characters or spaces.

        Returns:
            A string with the response to the command or commands that were
            sent. If the serial command has no response (not even a #
            character) then None is returned. Note that even when None is
            returned this method has still confirmed that the command was
            acknowledged.

        Raises:
            ValueError: When serial_cmds is too long.
            RuntimeError: When there is a mismatch in the sequence number.
        """
        if len(serial_cmds) > 254:
            raise ValueError('serial command string is too long!')
        msg = struct.pack('!II', self.seqnum, 0)
        msg += serial_cmds + '\0'
        self.sock.sendto(msg, self.sendaddr)
        try:
            response = self.sock.recv(255)
        except socket.timeout:
            # TODO: Handle this exception by sending NACKs
            print('timeout on recv')
            return
        seqnum, = struct.unpack('!I', response[0:4])
        if seqnum != self.seqnum:
            raise RuntimeError('sequence number mismatch')
        self.seqnum += 1
        serial_reply = response[8:].split('\0')[0]
        if serial_reply[0] == chr(0x06):
            return None
        else:
            return response[8:].split('\0')[0]


class Gemini2(object):
    """Implements serial and UDP command interfaces for Gemini 2.

    This class implements the command interface supported by the Gemini 2
    astronomical positioning system. The Gemini command set has evolved
    over time with the software. This class supports commands from the Level 5
    command interface. These commands are documented on this webpage:
    http://www.gemini-2.com/web/L5V2_1serial.html Both LX200 and Gemini Native
    command formats are supported.

    For numeric commands only the double-precision format is supported. Errors
    will occur if the precision is changed to HIGH or LOW precision.

    Attributes:
        serial: A serial.Serial object for exchanging serial commands
    """

    class ResponseException(Exception):
        """Raised on bad command responses from Gemini."""

    class ReadTimeoutException(Exception):
        """Raised when read from Gemini times out"""

    def __init__(self, device):
        """Constructs a Gemini2 object.

        Args:
            device: The name of the serial device. For example, '/dev/ttyACM0'.
        """
        self.serial = serial.Serial(device, timeout=1)
        self._flush_read_buffer()
        self._set_double_precision()

    def _flush_read_buffer(self):
        """Clears any characters waiting in the serial receive buffer."""
        garbage_bytes = self.serial.inWaiting()
        self.serial.read(garbage_bytes)

    def lx200_cmd(self, cmd, expect_reply=False, reply_len=None):
        """Sends a LX200 format command.

        Commands of this type are formatted to be largely compatible with the
        Meade LX200 command set.

        Args:
            cmd: The command string excluding the prefix ':' character and the
                terminating '#' character.
            expect_reply: A boolean indicating whether to expect a response to
                this command. When True this method will wait for a reply from
                Gemini.
            reply_len: Length of expected response. This must be set when
                expect_reply is true and the command response does not include
                a terminating '#' character. If set to None and expect_reply is
                True this method will continue reading until reaching a
                terminating '#' character.

        Returns:
            The Gemini response as a string if expect_reply is True, otherwise
            None is returned. Any terminating characters ('#') are stripped.

        Raises:
            ReadTimeoutException: When read attempt times out.
        """
        self._flush_read_buffer()
        self.serial.write(':' + cmd + '#')
        if expect_reply:
            response = ''
            while True:
                new_char = self.serial.read(1)
                if len(new_char) == 0:
                    raise self.ReadTimeoutException('LX200 command read timeout')
                elif new_char != '#':
                    response += new_char
                if reply_len is None and new_char == '#':
                    break
                elif reply_len is not None and len(response) >= reply_len:
                    break
            return response

    def native_cmd(self, id, set_param=''):
        """Sends a native Gemini 2 command.

        Native commands use a different syntax from the LX200-style commands.
        This method will construct the serial command string including the
        required checksum and send the command to Gemini.

        Args:
            id: The command ID as an integer.
            set_param: The parameter for set commands. When supplied, a set
                command is issued. If omitted a get command is sent.

        Returns:
            The Gemini response for get commands as a string. The checksum and
            termination # characters are omitted. For set commands None is
            returned.

        Raises:
            ReadTimeoutException: When read attempt times out.
            ResponseException: When a get response from Gemini 2 is malformed.
        """
        write = True if len(set_param) > 0 else False
        prefix = '>' if write else '<'
        cmd = prefix + str(id) + ':' + set_param
        cmd += chr(self.checksum(cmd)) + '#'
        self._flush_read_buffer()
        self.serial.write(cmd)
        if not write:
            response = ''
            while True:
                new_char = self.serial.read(1)
                if len(new_char) == 0:
                    raise self.ReadTimeoutException('Native command read timeout')
                response += new_char
                if response[-1] == '#':
                    break
            if len(response) <= 2:
                raise self.ResponseException('Native command response too short')
            elif self.checksum(response[:-2]) != ord(response[-2]):
                raise self.ResponseException('Native command checksum failure')
            return response[:-2]

    @staticmethod
    def checksum(cmd):
        """Computes checksum for Gemini native commands.

        Args:
            cmd: A string containing command characters up to but excluding the
                checksum (which this function computes) and the termination #
                character.

        Returns:
            The checksum as an integer.
        """
        checksum = 0
        for c in cmd:
            checksum = checksum ^ ord(c)
        return (checksum % 128) + 64


    ## Commands
    # All commands in the following sections are placed in the same order as
    # they appear in the serial command reference page:
    # http://www.gemini-2.com/web/L5V2_1serial.html


    ### Special Commands

    def startup_check(self):
        """Check startup state and type of mount."""
        self._flush_read_buffer()
        self.serial.write(chr(0x06))
        return self.serial.read(2)[0]


    ### Synchronization Commands

    def echo(self, char):
        """Test command. Should return the same character as the argument."""
        return self.lx200_cmd('CE' + char, expect_reply=True)

    def align_to_object(self):
        """Add selected object to pointing model."""
        return self.lx200_cmd('Cm', expect_reply=True)

    def sync_to_object(self):
        """Synchronize to selected object."""
        return self.lx200_cmd('CM', expect_reply=True)

    def select_pointing_model(self, num):
        """Select a pointing model (0 or 1)."""
        return int(self.lx200_cmd('C' + chr(num), expect_reply=True))

    def select_pointing_model_for_io(self):
        """Selects the active pointing model for I/O access."""
        return int(self.lx200_cmd('Cc', expect_reply=True))

    def get_pointing_model(self):
        """Get number of active pointing model (0 or 1)."""
        return int(self.lx200_cmd('C?', expect_reply=True))

    def init_align(self):
        """Perform Initial Align with selected object."""
        return self.lx200_cmd('CI', expect_reply=True)

    def reset_model(self):
        """Resets the currently selected model."""
        return int(self.lx200_cmd('CR', expect_reply=True))

    def reset_last_align(self):
        """Resets the last alignment of currently selected model."""
        return int(self.lx200_cmd('CU', expect_reply=True))


    ### Focus Control Commands

    def focus_in(self):
        self.lx200_cmd('F+')

    def focus_out(self):
        self.lx200_cmd('F-')

    def focus_stop(self):
        self.lx200_cmd('FQ')

    def focus_fast(self):
        self.lx200_cmd('FF')

    def focus_medium(self):
        self.lx200_cmd('FM')

    def focus_slow(self):
        self.lx200_cmd('FS')


    ### Get Information Commands

    def get_alt(self):
        """Altitude in signed degrees format [-90.0, +90.0]."""
        return float(self.lx200_cmd('GA', expect_reply=True))

    def get_led_brightness(self):
        return int(self.lx200_cmd('GB', expect_reply=True))

    def get_local_date(self):
        """Date as a string in mm/dd/yy format."""
        return self.lx200_cmd('GC', expect_reply=True)

    def get_clock_format(self):
        return self.lx200_cmd('Gc', expect_reply=True)

    def get_dec(self):
        """Apparent declination in signed degrees [-90.0,+90.0]."""
        return float(self.lx200_cmd('GD', expect_reply=True))

    def get_obj_dec(self):
        """Selected object's declination in signed degrees."""
        return float(self.lx200_cmd('Gd', expect_reply=True))

    def get_alarm_time(self):
        return self.lx200_cmd('GE', expect_reply=True)

    def get_utc_offset(self):
        return self.lx200_cmd('GG', expect_reply=True)

    def get_site_lon(self):
        return float(self.lx200_cmd('Gg', expect_reply=True))

    def get_hour_angle(self):
        """Hour angle in signed degrees."""
        return float(self.lx200_cmd('GH', expect_reply=True))

    def get_info_buffer(self):
        return self.lx200_cmd('GI', expect_reply=True)

    def get_local_time(self):
        """Local time in hours as a float."""

        # For some reason time is not very precise in double precision. It's
        # worse than one second. High precision format has better resolution.
        return float(self.lx200_cmd('GL', expect_reply=True))

    def get_meridian_side(self):
        """Returns 'E' or 'W' to indicate side of meridian."""
        return self.lx200_cmd('Gm', expect_reply=True)

    def get_site_name(self, site_num=0):
        site_letters = ['M', 'N', 'O', 'P']
        return self.lx200_cmd('G' + site_letters[site_num], expect_reply=True)

    def get_ra(self):
        """Apparent right ascension in hours [0.0,24.0)."""
        return float(self.lx200_cmd('GR', expect_reply=True))

    def get_obj_ra(self):
        """Selected object's right ascension in signed degrees."""
        return float(self.lx200_cmd('Gr', expect_reply=True))

    def get_sidereal_time(self):
        return float(self.lx200_cmd('GS', expect_reply=True))

    def get_site_lat(self):
        return float(self.lx200_cmd('Gt', expect_reply=True))

    # Omitting command 'GV' which is redundant with 'GVN'.

    def get_software_build_date(self):
        return self.lx200_cmd('GVD', expect_reply=True)

    def get_software_level(self):
        return self.lx200_cmd('GVN', expect_reply=True)

    def get_product_string(self):
        return self.lx200_cmd('GVP', expect_reply=True)

    def get_software_build_time(self):
        return self.lx200_cmd('GVT', expect_reply=True)

    def get_max_velocity(self):
        """Maximum velocity of both axes."""
        return self.lx200_cmd('Gv', expect_reply=True, reply_len=1)

    def get_velocity_ra(self):
        return self.lx200_cmd('GW', expect_reply=True, reply_len=1)

    def get_velocity_dec(self):
        return self.lx200_cmd('Gw', expect_reply=True, reply_len=1)

    def get_velocity(self):
        """Velocity of both axes: RA, DEC (2 characters)."""
        return self.lx200_cmd('Gu', expect_reply=True, reply_len=2)

    def get_az(self):
        """Azimuth in signed degrees format [0.0, 360.0)."""
        return float(self.lx200_cmd('GZ', expect_reply=True))


    ### Park Commands

    def park_home(self):
        self.lx200_cmd('hP')

    def park_startup(self):
        self.lx200_cmd('hC')

    def park_zenith(self):
        self.lx200_cmd('hZ')

    def sleep(self):
        self.lx200_cmd('hN')

    def wake(self):
        self.lx200_cmd('hW')


    ### Move Commands

    def goto_object_horiz(self):
        """Goto object selected with horizontal coordinates."""
        return self.lx200_cmd('MA', expect_reply=True)

    def search_pattern(self, arcmins):
        """Move at find speed in a meander search pattern."""
        self.lx200_cmd('MF' + str(arcmins), expect_reply=True)

    def move_lock(self):
        self.lx200_cmd('ML', expect_reply=True)

    def move_unlock(self):
        self.lx200_cmd('Ml', expect_reply=True)

    def meridian_flip(self):
        return self.lx200_cmd('Mf', expect_reply=True)

    def goto_object(self, allow_meridian_flip=False):
        """Goto object selected from database or equatorial coordinates."""
        cmd = 'MM' if allow_meridian_flip else 'MS'
        return lx200_cmd(cmd, expect_reply=True)

    def move(self, direction):
        """Move in a direction: 'east', 'west', 'north', or 'south'."""
        if direction not in ['east', 'west', 'north', 'south']:
            raise ValueError('invalid direction for move command')
        self.lx200_cmd('M' + direction[0])

    def move_ticks(self, ra_steps, dec_steps):
        self.lx200_cmd('mi' + str(ra_steps) + ';' + str(dec_steps))

    def set_step_multiplier(self, multiplier):
        self.lx200_cmd('mm' + str(multiplier))


    ### Precision Guiding Commands


    ### Object/Observing/Output Commands


    ### Precession and Refraction Commands


    ### Precision Commands


    ### Quit Motion Commands


    ### Rate Commands


    ### Set Commands


    ### Site Selection Commands


















    ### Wrapper Methods
    # These are methods that wrap one or more of the low-level interface
    # commands to provide extra functionality, abstration, or programming
    # convenience.

    def get_unix_time(self):
        """Get UNIX time (seconds since 00:00:00 UTC on 1 Jan 1970)"""

        # Slight risk that date and time commands will be inconsistent if
        # one is called just before UTC midnight and the other is called just
        # after midnight but there is no single command to retrieve the date
        # and time in one atomic operation so this is the best we can do.
        date = self.get_local_date()
        time = self.get_local_time() * 3600.0  # seconds since 00:00:00
        hours = int(time / 3600.0)
        time -= hours * 3600.0
        minutes = int(time / 60.0)
        time -= minutes * 60.0
        seconds = int(time)
        time -= seconds
        microseconds = int(time * 1e6)
        t = datetime.datetime(
            2000 + int(date[6:8]), # year
            int(date[0:2]),        # month
            int(date[3:5]),        # day
            hours,
            minutes,
            seconds,
            microseconds,
        )
        return calendar.timegm(t.timetuple())









    def get_precision(self):
        return self.lx200_cmd('P', expect_reply=True, reply_len=14)

    def _set_double_precision(self):
        """Private because only double precision is supported."""
        self.lx200_cmd('u')

    def _toggle_precision(self):
        """Private because only double precision is supported."""
        self.lx200_cmd('U')