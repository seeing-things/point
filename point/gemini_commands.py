from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass
import re
import ipaddress
from curses.ascii import isgraph
import enum
from enum import Enum, Flag
from collections.abc import Iterable
from point.gemini_exceptions import (
    G2ResponseDecodeError,
    G2ResponseException,
    G2ResponseIntegerParseError,
    G2ResponseParseError,
    G2ResponseIntegerBoundsViolation,
    G2ResponseAngleParseError,
    G2ResponseTimeParseError,
    G2ResponseRevisionsParseError,
    G2ResponseIPv4AddressParseError,
    G2CommandBadCharacterError,
    G2ResponseChecksumMismatchError,
    G2ResponseTooShortError,
    G2ResponseMissingTerminatorError,
    G2CommandParameterTypeError,
    G2ResponseInterpretationFailure,
    G2CommandParameterValueError,
)


# TODO: print command/response class name in exception messages more often / more
# consistently


########################################################################################


_re_int = re.compile(r'^([-+]?)(\d+)$', re.ASCII)
_re_ang_dbl = re.compile(r'^([-+]?)(\d{1,3}\.\d{6})$', re.ASCII)
_re_ang_high = re.compile(r'^([-+]?)(\d{1,2}):(\d{1,2}):(\d{1,2})$', re.ASCII)
_re_ang_low = re.compile(r'^([-+]?)(\d{1,3})' + '\xdf' + r'(\d{1,2})$', re.ASCII)
_re_time_dbl = re.compile(r'^([-+]?)(\d+\.\d{6})$', re.ASCII)
_re_time_hilo = re.compile(r'^(\d{1,2}):(\d{1,2}):(\d{1,2})$', re.ASCII)
_re_ipv4addr = re.compile(r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$', re.ASCII)


def parse_int(string: str) -> int:
    match = _re_int.fullmatch(string)
    if match is None:
        raise G2ResponseIntegerParseError(string)
    return int(match.expand(r'\1\2'))


def parse_int_bounds(string: str, bound_min: int, bound_max: int) -> int:
    if bound_min > bound_max:
        raise G2ResponseParseError(f'bound_min {bound_min} > bound_max {bound_max})')
    val = parse_int(string)
    if val < bound_min or val > bound_max:
        raise G2ResponseIntegerBoundsViolation(val, bound_min, bound_max)
    return val


def parse_ang_dbl(string: str) -> float:
    match = _re_ang_dbl.fullmatch(string)
    if match is None:
        raise G2ResponseAngleParseError(string, 'double')
    return float(match.expand(r'\1\2'))


def parse_ang_high(string: str) -> float:
    match = _re_ang_high.fullmatch(string)
    if match is None:
        raise G2ResponseAngleParseError(string, 'high')
    f_deg = float(match.expand(r'\1\2'))
    f_min = float(match.expand(r'\1\3'))
    f_sec = float(match.expand(r'\1\4'))
    return f_deg + (f_min / 60.0) + (f_sec / 3600.0)


def parse_ang_low(string: str) -> float:
    match = _re_ang_low.fullmatch(string)
    if match is None:
        raise G2ResponseAngleParseError(string, 'low')
    f_deg = float(match.expand(r'\1\2'))
    f_min = float(match.expand(r'\1\3'))
    return f_deg + (f_min / 60.0)


def parse_ang(string: str, precision: G2Precision) -> float:
    if not isinstance(precision, G2Precision):
        raise G2ResponseParseError('parse_ang: not isinstance(precision, G2Precision)')
    if precision == G2Precision.DOUBLE:
        return parse_ang_dbl(string)
    elif precision == G2Precision.HIGH:
        return parse_ang_high(string)
    elif precision == G2Precision.LOW:
        return parse_ang_low(string)


def parse_time_dbl(string: str) -> float:
    match = _re_time_dbl.fullmatch(string)
    if match is None:
        raise G2ResponseTimeParseError(string, 'double')
    return float(match.expand(r'\1\2'))


def parse_time_hilo(string: str) -> float:
    match = _re_time_hilo.fullmatch(string)
    if match is None:
        raise G2ResponseTimeParseError(string, 'high/low')
    i_hour = int(match[1])
    i_min = int(match[2])
    i_sec = int(match[3])
    # TODO: Bounds check on hour field...?
    # And should we even be limiting the hour field to 2 digits in the RE?
    if i_min >= 60 or i_sec >= 60:
        raise G2ResponseTimeParseError(string, 'high/low')
    return float((i_hour * 3600) + (i_min * 60) + i_sec)


def parse_time(string: str, precision: G2Precision) -> float:
    if not isinstance(precision, G2Precision):
        raise G2ResponseParseError('parse_time: not isinstance(precision, G2Precision)')
    if precision == G2Precision.DOUBLE:
        return parse_time_dbl(string)
    else:
        return parse_time_hilo(string)


def parse_revisions(string: str) -> G2Revisions:
    """Parse revision characters in the 8-character response to native command 97."""
    vals = []
    if len(string) != 8:
        raise G2ResponseRevisionsParseError(string)
    for char in string:
        val = ord(char)
        if val < 0x30 or val > 0x7E:
            raise G2ResponseRevisionsParseError(string)
        vals.append(val - 0x30)
    return G2Revisions(*vals)


def parse_ip4vaddr(string: str) -> ipaddress.IPv4Address:
    match = _re_ipv4addr.fullmatch(string)
    if match is None:
        raise G2ResponseIPv4AddressParseError(string)
    if int(match[1]) < 0 or int(match[1]) > 255:
        raise G2ResponseIPv4AddressParseError(string)
    if int(match[2]) < 0 or int(match[2]) > 255:
        raise G2ResponseIPv4AddressParseError(string)
    if int(match[3]) < 0 or int(match[3]) > 255:
        raise G2ResponseIPv4AddressParseError(string)
    if int(match[4]) < 0 or int(match[4]) > 255:
        raise G2ResponseIPv4AddressParseError(string)
    return ipaddress.IPv4Address(string)


########################################################################################


# returns tuple: (int:sign[-1|0|+1], int:hour, int:min, int:sec)
def ang_to_hourminsec(ang: float) -> tuple[int, int, int, int]:
    """
    Args:
        ang: Angle in degrees.

    Returns:
        Tuple containing sign (-1, 0, or +1), hours, minutes, seconds.
    """
    return ang_to_degminsec(ang * 24.0 / 360.0)


def ang_to_degminsec(ang: float) -> tuple[int, int, int, int]:
    """
    Args:
        ang: Angle in degrees.

    Returns:
        Tuple containing sign (-1, 0, or +1), degrees, arcminutes, arcseconds.
    """
    if ang > 0.0:
        sign = +1
    elif ang < 0.0:
        sign = -1
    else:
        sign = 0
    ang = abs(ang) * 3600.0
    # TODO: change this to round(), if we can fix the round-up-to-60 issues
    i_sec = int(ang % 60.0)
    ang /= 60.0
    i_min = int(ang % 60.0)
    ang /= 60.0
    i_deg = int(ang)
    return (sign, i_deg, i_min, i_sec)


def ang_to_degmin(ang: float) -> tuple[int, int, int]:
    """
    Args:
        ang: Angle in degrees.

    Returns:
        Tuple containing sign (-1, 0, or +1), degrees, and arcminutes.
    """
    if ang > 0.0:
        sign = +1
    elif ang < 0.0:
        sign = -1
    else:
        sign = 0
    ang = abs(ang) * 60.0
    # TODO: change this to round(), if we can fix the round-up-to-60 issues
    i_min = int(ang % 60.0)
    ang /= 60.0
    i_deg = int(ang)
    return (sign, i_deg, i_min)


def compute_native_checksum(cmd_str: str) -> int:
    """Compute checksum for native commands and responses."""
    csum = 0
    for char in cmd_str:
        csum = csum ^ ord(char)
    csum = (csum % 128) + 64
    assert csum >= 0x40 and csum < 0xC0
    return csum


########################################################################################


class Backend(enum.Flag):
    """Used to indicate which backends are supported by commands."""

    SERIAL = enum.auto()
    UDP = enum.auto()


class Gemini2Command(ABC):
    """Abstract base class for Gemini 2 commands.

    Instances of child classes are passed to `Gemini2Backend.execute_one_command()` to
    execute commands. Most of the methods of this class are meant to be called by the
    backend. Command parameters are generally passed to child class constructors and
    response information can be retrieved by accessing the `raw_response` attribute or
    by other attributes and methods specific to individual commands.

    Attributes:
        supported_backends: Indicates which backends this command supports. Most
            commands support both backends but the ENQ macro command is only supported
            via UDP.
        response_expected: True if a response to this command is expected.
        response_type: Type of response expected (fixed length, hash-terminated, etc.)
            which determines how the response is interpreted.
        response_decoded: True after `decode()` has been called for commands expecting
            a response, False otherwise.
        response_length_expected: Expected length of response string for fixed-length
            response type.
        zero_len_hack: Whether to process possibly-zero-length responses. This may only
            be True if the `type` is FIXED_LENGTH.
        raw_response: The raw response string from Gemini. This attribute won't exist
            until `decode()` has been called.
    """

    class ResponseType(enum.Enum):
        FIXED_LENGTH = enum.auto()
        HASH_TERMINATED = enum.auto()
        SEMICOLON_DELIMITED = enum.auto()

    # Individual commands may override these default values.
    supported_backends: Backend = Backend.SERIAL | Backend.UDP
    response_expected: bool = False
    response_type: ResponseType = ResponseType.HASH_TERMINATED
    response_decoded: bool = False
    response_length_expected: int = 0
    zero_len_hack: bool = False
    raw_response: str

    @abstractmethod
    def encode(self) -> str:
        """Encode a command into a string ready for transmission on the backend.

        IMPLEMENTED AT THE PROTOCOL-SPECIFIC SUBCLASS LEVEL (LX200, Native, etc)

        Takes info from the command-specific subclass and turns it into a raw cmd string
        with prefix, postfix, checksum, etc that's completely ready to be shoved onto
        the backend.

        Returns:
            String containing fully encoded raw command with prefix, postfix, checksum,
            etc.
        """

    def _check_bad_chars(self, string: str, bad_chars: Iterable[str]) -> None:
        """Check for bad characters in the command string.

        Args:
            string: The string to check for bad characters.
            bad_chars: The bad characters to search for.

        Raises:
            G2CommandBadCharacterError if any bad characters are found.
        """
        for char in bad_chars:
            if char in string:
                if isgraph(char):  # Character has a graphical representation
                    raise G2CommandBadCharacterError(
                        f"Command {self.__class__.__name__:s}: contains '{char}'."
                    )
                else:
                    raise G2CommandBadCharacterError(
                        f"Command {self.__class__.__name__:s}: "
                        f"contains '\\x{ord(char):02X}'."
                    )

    def decode(self, chars: str) -> int:
        """Decode the command response.

        Args:
            chars: String containing this response, and potentially additional responses
                to other commands.

        Returns:
            Integer representing how many characters from the input were decoded for
            this response.
        """
        assert self.response_expected
        assert not self.response_decoded
        self.response_decoded = True

        if self.response_type == self.ResponseType.FIXED_LENGTH:
            idx = self.response_length_expected
            if len(chars) < idx:
                raise G2ResponseTooShortError(len(chars), idx)
            resp_data = chars[:idx]
            num_chars_processed = idx
        elif self.response_type == self.ResponseType.HASH_TERMINATED:
            idx = chars.find('#')
            if idx == -1:
                raise G2ResponseMissingTerminatorError(len(chars))
            resp_data = chars[:idx]
            num_chars_processed = idx + 1
        elif self.response_type == self.ResponseType.SEMICOLON_DELIMITED:
            # Individual commands are responsible for parsing fields out of the raw
            # response string. This is because presently there is only one command, the
            # ENQ macro command, that uses a semicolon-delimited response, and the
            # response to that command has one field that can also contain semicolons.
            # Command-specific parsing can handle that situation.
            resp_data = chars
            num_chars_processed = len(chars)
        else:
            raise G2ResponseException(
                f'Unsupported response type {self.response_type}.'
            )

        self.raw_response = self.post_decode(resp_data)
        self.interpret()
        return num_chars_processed

    def post_decode(self, chars: str) -> str:
        """Optionally implement to do some additional post-decode-step verification."""
        return chars

    def interpret(self) -> None:
        """Optionally implement to do cmd-specific interpretation of the response."""
        return None


# ======================================================================================


class Gemini2Command_LX200(Gemini2Command):
    """
    Attributes:
        lx200_cmd: The LX200 command string. The value is assigned by the command-
            specific subclasses and may contain encoded parameters.
    """

    response_type = Gemini2Command.ResponseType.HASH_TERMINATED
    lx200_cmd: str

    def encode(self) -> str:
        self._check_bad_chars(self.lx200_cmd, ['#', '\x00', '\x06'])
        return f':{self.lx200_cmd}#'


# --------------------------------------------------------------------------------------


class Gemini2Command_Native(Gemini2Command):
    """Abstract base class for all native Gemini 2 commands.

    Abstract because child classes must assign values to the attributes listed below.

    Attributes:
        native_prefix: A single character prefix, '<' for "get" commands and '>' for
            "set" commands.
        native_id: The native command ID.
        native_params: Set of parameters to be sent along with the command.
    """

    response_type = Gemini2Command.ResponseType.HASH_TERMINATED
    native_prefix: str
    native_id: int
    native_params: tuple[str, ...] = ()

    def encode(self) -> str:
        params_str = self._make_params_str(self.native_params)
        cmd_str = f'{self.native_prefix}{self.native_id}:{params_str}'
        return f'{cmd_str:s}{chr(compute_native_checksum(cmd_str)):s}#'

    def _make_params_str(self, params: tuple[str, ...]) -> str:
        for param in params:
            self._check_bad_chars(param, ['<', '>', ':', '#', '\x00', '\x06'])
        # The serial command reference says parameters are separated from each other and
        # from the ID by hyphens, but this probably is not correct because the example
        # commands show a colon between the ID and the parameter. See bottom of
        # https://gemini-2.com/web/L6V02serial.html. In practice it may not matter
        # because few commands take multiple parameters and those that do seem to each
        # use their own unique format.
        return ':'.join(params)

    def post_decode(self, chars: str) -> str:
        """Verify and strip native response checksum."""
        if len(chars) < 2:
            raise G2ResponseDecodeError('Native command response too short.')
        checksum_received = ord(chars[-1])
        checksum_computed = compute_native_checksum(chars[:-1])
        if checksum_received != checksum_computed:
            raise G2ResponseChecksumMismatchError(checksum_received, checksum_computed)
        return chars[:-1]

    # TODO: implement generic G2-Native response decoding


class Gemini2Command_Native_Get(Gemini2Command_Native):
    native_prefix = '<'


class Gemini2Command_Native_Set(Gemini2Command_Native):
    native_prefix = '>'


####################################################################################################


## Commands
# All commands in the following sections are placed in the same order as
# they appear in the serial command reference page:
# http://www.gemini-2.com/web/L5V2_1serial.html


### Enumerations, Constants, etc


class G2Precision(Enum):
    """Parameter for GetPrecision."""

    DOUBLE = 'DBL  PRECISION'
    HIGH = 'HIGH PRECISION'
    LOW = 'LOW  PRECISION'


class G2StartupStatus(Enum):
    """Parameter for StartupCheck."""

    INITIAL = 'B'
    MODE_SELECT = 'b'
    COLD_START = 'S'
    DONE_EQUATORIAL = 'G'
    DONE_ALTAZ = 'A'


class G2StartupMode(Enum):
    """Parameter for SelectStartupMode."""

    COLD_START = 'C'
    WARM_START = 'W'
    WARM_RESTART = 'R'


class G2AxisVelocity(Enum):
    """Parameter for MacroENQ fields 'vel_max', 'vel_x', and 'vel_y'."""

    STALL = '!'
    NO_MOVEMENT = 'N'
    SLEWING = 'S'
    CENTERING = 'C'
    TRACKING = 'T'
    GUIDING = 'G'
    UNDEFINED = '?'


class G2AxisSide(Enum):
    """Parameter for MacroENQ field 'ha_pos'."""

    LOWER_SIDE = 'W'
    HIGHER_SIDE = 'E'


class G2ParkStatus(Enum):
    """Parameter for MacroENQ field 'park_state'."""

    NOT_PARKED = 0
    PARKED = 1
    PARKING = 2


class G2PECStatus(Flag):
    """Periodic error correction (PEC) status.

    Used in:
    * MacroENQ field 'pec_state'.
    * PECStatus_Set
    * Response for PECStatus_Get
    """

    ACTIVE = 1 << 0
    FRESH_DATA_AVAILABLE = 1 << 1
    TRAINING_IN_PROGRESS = 1 << 2
    TRAINING_COMPLETED = 1 << 3
    TRAINING_STARTS_SOON = 1 << 4
    DATA_AVAILABLE = 1 << 5


class G2Status(Flag):
    """Parameter for MacroENQ field 'cmd99_state'."""

    SCOPE_IS_ALIGNED = 1 << 0
    MODELLING_IN_USE = 1 << 1
    OBJECT_IS_SELECTED = 1 << 2
    GOTO_OPERATION_ONGOING = 1 << 3
    RA_LIMIT_REACHED = 1 << 4
    ASSUMING_J2000_OBJ_COORDS = 1 << 5


# Parameter for MacroENQ fields 'servo_duty_x' and 'servo_duty_y'.
G2_SERVO_DUTY_MIN = -100
G2_SERVO_DUTY_MAX = 100


def parse_servo_duty(string: str) -> int:
    return parse_int_bounds(string, G2_SERVO_DUTY_MIN, G2_SERVO_DUTY_MAX)


class G2Valid(Enum):
    """Response for SetObjectRA and SetObjectDec."""

    INVALID = '0'
    VALID = '1'


class G2Stopped(Enum):
    """Parameter for RA_StartStop_Set and DEC_StartStop_Set."""

    STOPPED = 0
    NOT_STOPPED = 1


# Limits for signed 32-bit integer parameters.
SINT32_MIN = -((1 << 31) - 0)
SINT32_MAX = (1 << 31) - 1

# Limits for unsigned 32-bit integer parameters.
UINT32_MIN = 0
UINT32_MAX = (1 << 32) - 1


### Special Commands


# This command doesn't follow the conventions of all the other LX200 or native commands.
# It's a special snowflake. The command is a non-printable, single-byte value.
class G2Cmd_StartupCheck(Gemini2Command):
    response_expected = True
    response_type = Gemini2Command.ResponseType.HASH_TERMINATED
    status: G2StartupStatus

    def encode(self) -> str:
        return '\x06'

    def interpret(self) -> None:
        self.status = G2StartupStatus(self.raw_response)


class G2Cmd_SelectStartupMode(Gemini2Command_LX200):
    def __init__(self, mode: G2StartupMode):
        self.lx200_cmd = f'b{mode.value}'


### Macro Commands


@dataclass(frozen=True)
class G2Revisions:
    """Revisions from native command 97 "State Check" response.

    These are initialized to 0 and increment each time corresponding values in Gemini
    are updated. They each count up to a max value of 78 before rolling over back to 0.
    """

    site: int
    date_time: int
    mount_param: int
    display_content: int
    modelling_parameters: int
    speeds: int
    park: int
    reserved: int


# TODO: Document each of these fields, including what ordinary LX200 or native command
# they correspond to.
# TODO: Use more descriptive names. Some of these are a bit too terse.
# TODO: Consider using datetime or similar for the time fields rather than float.
@dataclass(frozen=True)
class G2MacroFields:
    """Response data from the ENQ macro command."""

    pra: int
    pdec: int
    ra: float
    dec: float
    ha: float
    az: float
    alt: float
    vel_max: G2AxisVelocity
    vel_x: G2AxisVelocity
    vel_y: G2AxisVelocity
    ha_pos: G2AxisSide
    t_sidereal: float
    park_state: G2ParkStatus
    pec_state: G2PECStatus
    t_wsl: float
    cmd99_state: G2Status
    revisions: G2Revisions
    servo_lag_x: int
    servo_lag_y: int
    servo_duty_x: int
    servo_duty_y: int


class G2Cmd_MacroENQ(Gemini2Command):
    supported_backends = Backend.UDP  # Not supported via serial.
    response_type = Gemini2Command.ResponseType.SEMICOLON_DELIMITED
    response_expected = True
    fields: G2MacroFields

    def encode(self):
        return '\x05'

    def interpret(self) -> None:
        # TODO: implement some range checking on most of the numerical fields here
        # (e.g. angle ranges:  [0,180) or [-90,+90] or [0,360)  etc)

        # The 'revisions' (native #97) field contains chars in the range of 0x30 ~ 0x7E,
        # inclusive; this happens to include the semicolon character. So if we split the
        # response string purely using semicolon characters we could end up spuriously
        # interpreting revision chars as field delimiters! To work around that, we use
        # additional information about the expected structure of the response to parse
        # fields out of it via a regular expression.
        fields = re.fullmatch(
            pattern=(
                # Angles and times are always double precision in ENQ macro response.
                r'(\d+);'  # 101 - RA encoder position
                r'(\d+);'  # 111 - DEC encoder position
                r'([-+]?\d{1,3}.\d{6});'  # GR - Right ascension in degrees
                r'([-+]?\d{1,3}.\d{6});'  # GD - Declination in degrees
                r'([-+]?\d{1,3}.\d{6});'  # GH - Hour angle in degrees
                r'([-+]?\d{1,3}.\d{6});'  # GZ - Azimuth in degrees
                r'([-+]?\d{1,3}.\d{6});'  # GA - Altitude in degrees
                r'([!NSCTG?]);'  # Gv - Max velocity of both axes
                r'([!NSCTG?]);'  # GW - Velocity of RA axis
                r'([!NSCTG?]);'  # Gw - Velogity of DEC axis
                r'([WE]);'  # Gm - RA axis mount side
                r'([-+]?\d+.\d{6});'  # GS - Sidereal time (double precision)
                r'([012]);'  # h? - Park state
                r'(\d+);'  # 509 - PEC status
                r'([-+]?\d+.\d{6});'  # 226 - Time to western safety limit
                r'(\d+);'  # 99 - Status inquiry native command
                r'([0-~]{8});'  # 97 - State check, which may contain semicolons
                r'([-+]?\d+);'  # 245 - RA servo lag
                r'([-+]?\d+);'  # 246 - DEC servo lag
                r'([-+]?\d+);'  # 247 - RA servo PWM duty cycle
                r'([-+]?\d+);'  # 248 - DEC servo PWM duty cycle
                r'([-+]?\d+);'  # Unknown, probably added recently (in Level 6?)
                r'([-+]?\d+);'  # Unknown, probably added recently (in Level 6?)
            ),
            string=self.raw_response,
            flags=re.ASCII,
        )

        if fields is None:
            raise G2ResponseParseError(
                f'Could not parse ENQ response "{self.raw_response}"'
            )

        self.fields = G2MacroFields(
            pra=int(fields[1]),
            pdec=int(fields[2]),
            ra=float(fields[3]),
            dec=float(fields[4]),
            ha=float(fields[5]),
            az=float(fields[6]),
            alt=float(fields[7]),
            vel_max=G2AxisVelocity(fields[8]),
            vel_x=G2AxisVelocity(fields[9]),
            vel_y=G2AxisVelocity(fields[10]),
            ha_pos=G2AxisSide(fields[11]),
            t_sidereal=float(fields[12]),
            park_state=G2ParkStatus(int(fields[13])),
            pec_state=G2PECStatus(int(fields[14])),
            t_wsl=float(fields[15]),
            cmd99_state=G2Status(int(fields[16])),
            revisions=parse_revisions(fields[17]),
            servo_lag_x=int(fields[18]),
            servo_lag_y=int(fields[19]),
            servo_duty_x=parse_servo_duty(fields[20]),
            servo_duty_y=parse_servo_duty(fields[21]),
        )


### Synchronization Commands


class G2Cmd_Echo(Gemini2Command_LX200):
    response_expected = True

    def __init__(self, char: str):
        if (not isinstance(char, str)) or (len(char) != 1):
            raise G2CommandParameterTypeError('char')
        self.lx200_cmd = f'CE{char}'


class G2Cmd_AlignToObject(Gemini2Command_LX200):
    response_expected = True
    lx200_cmd = 'Cm'

    def interpret(self) -> None:
        if self.raw_response == 'No object!':
            # TODO: This seems like the wrong response to this situation
            raise G2ResponseInterpretationFailure()


class G2Cmd_SyncToObject(Gemini2Command_LX200):
    response_expected = True
    lx200_cmd = 'CM'

    def interpret(self) -> None:
        if self.raw_response == 'No object!':
            # TODO: This seems like the wrong response to this situation
            raise G2ResponseInterpretationFailure()


# ...


### Focus Control Commands

# ...


### Get Information Commands

# ...


### Park Commands

# ...


### Move Commands

# ...


### Precision Guiding Commands

# ...


### Object/Observing/Output Commands


class G2Cmd_SetObjectName(Gemini2Command_LX200):
    def __init__(self, name: str):
        if name == '':
            raise G2CommandParameterValueError('name cannot be empty.')
        if '#' in name:
            raise G2CommandParameterValueError("name cannot contain '#' characters.")
        self.lx200_cmd = f'ON{name}'


# ...


### Precession and Refraction Commands

# ...


### Precision Commands


class G2Cmd_GetPrecision(Gemini2Command_LX200):
    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 14
    lx200_cmd = 'P'
    precision: G2Precision

    def interpret(self) -> None:
        self.precision = G2Precision(self.raw_response)


class G2Cmd_TogglePrecision(Gemini2Command_LX200):
    lx200_cmd = 'U'


class G2Cmd_SetDblPrecision(Gemini2Command_LX200):
    lx200_cmd = 'u'


### Quit Motion Commands

# ...


### Rate Commands

# ...


### Set Commands


class G2Cmd_SetObjectRA(Gemini2Command_LX200):
    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 1

    def __init__(self, ra: float):
        if ra < 0.0 or ra >= 360.0:
            raise G2CommandParameterValueError('ra must be >= 0.0 and < 360.0.')
        _, hour, min, sec = ang_to_hourminsec(ra)
        self.lx200_cmd = f'Sr{hour:02d}:{min:02d}:{sec:02d}'

    def interpret(self) -> None:
        validity = G2Valid(
            self.raw_response
        )  # raises ValueError if the response field value isn't in the enum
        if validity != G2Valid.VALID:
            raise G2ResponseInterpretationFailure()


class G2Cmd_SetObjectDec(Gemini2Command_LX200):
    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 1

    def __init__(self, dec: float):
        if dec < -90.0 or dec > 90.0:
            raise G2CommandParameterValueError('dec must be >= -90.0 and <= 90.0.')
        sign, deg, min, sec = ang_to_degminsec(dec)
        signchar = '+' if sign >= 0 else '-'
        self.lx200_cmd = f'Sd{signchar}{deg:02d}:{min:02d}:{sec:02d}'

    def interpret(self):
        # Raises ValueError if the response field value isn't in the enum.
        validity = G2Valid(self.raw_response)
        if validity != G2Valid.VALID:
            raise G2ResponseInterpretationFailure()
        # NOTE: only objects which are currently above the horizon are considered valid


class G2Cmd_SetSiteLongitude(Gemini2Command_LX200):
    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 1
    zero_len_hack = True

    def __init__(self, lon: float):
        if lon <= -360.0 or lon >= 360.0:
            raise G2CommandParameterValueError('lon must be > -360.0 and < 360.0.')
        sign, deg, min = ang_to_degmin(lon)
        # everyone else in the world uses positive to mean eastern longitudes; but not
        # LX200!
        signchar = '-' if sign >= 0 else '+'
        self.lx200_cmd = f'Sg{signchar}{deg:03d}*{min:02d}'

    def interpret(self):
        if len(self.raw_response) == 0:
            raise G2ResponseInterpretationFailure()  # invalid
        if self.raw_response != '1':
            raise G2ResponseInterpretationFailure()  # ???


class G2Cmd_SetSiteLatitude(Gemini2Command_LX200):
    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 1
    zero_len_hack = True

    def __init__(self, lat: float):
        if lat < -90.0 or lat > 90.0:
            raise G2CommandParameterValueError('lat must be >= -90.0 and <= 90.0.')
        sign, deg, min = ang_to_degmin(lat)
        signchar = '+' if sign >= 0.0 else '-'
        self.lx200_cmd = f'St{signchar}{deg:02d}*{min:02d}'

    def interpret(self):
        if len(self.raw_response) == 0:
            raise G2ResponseInterpretationFailure()  # invalid
        if self.raw_response != '1':
            raise G2ResponseInterpretationFailure()  # ???


# ...


### Site Selection Commands


class G2Cmd_SetStoredSite(Gemini2Command_LX200):
    def __init__(self, site: int):
        """
        Args:
            site: Integer in [0, 4] specifying which site to select. Note that the
                official Gemini 2 serial command documentation is wrong: the range for
                sites is 0-4 inclusive, not 0-3 inclusive.
        """
        if site < 0 or site > 4:
            raise G2CommandParameterValueError('site must be >= 0 and <= 4.')
        self.lx200_cmd = f'W{site:d}'


class G2Cmd_GetStoredSite(Gemini2Command_LX200):
    """Note that the official Gemini 2 serial command documentation is wrong: the range
    for sites is 0-4 inclusive, not 0-3 inclusive."""

    response_expected = True
    response_type = Gemini2Command.ResponseType.FIXED_LENGTH
    response_length_expected = 1
    lx200_cmd = 'W?'
    site: int

    def interpret(self) -> None:
        self.site = parse_int_bounds(self.raw_response, 0, 4)


# ...


### Native Commands

# class G2Cmd_TEST_Native_92_Get(Gemini2Command_Native_Get):
#    native_id = 92
#    def __init__(self, val):
#        if not isinstance(val, int):
#            raise G2CommandParameterTypeError('int')
#        self._val = val
#        self.native_params = (f'{val:d}',)
#    def response(self):      return None # TODO!


class G2Cmd_PECBootPlayback_Set(Gemini2Command_Native_Set):
    native_id = 508

    def __init__(self, enable: bool):
        if not isinstance(enable, bool):
            raise G2CommandParameterTypeError('bool')
        self.native_params = ('1',) if enable else ('0',)


class G2Cmd_PECBootPlayback_Get(Gemini2Command_Native_Get):
    response_expected = True
    native_id = 508
    enabled: bool

    def interpret(self):
        self.enabled = bool(parse_int_bounds(self.raw_response, 0, 1))


class G2Cmd_PECStatus_Set(Gemini2Command_Native_Set):
    native_id = 509

    def __init__(self, status: G2PECStatus):
        if not isinstance(status, G2PECStatus):
            raise G2CommandParameterTypeError('G2PECStatus')
        self.native_params = (str(status.value),)


class G2Cmd_PECStatus_Get(Gemini2Command_Native_Get):
    response_expected = True
    native_id = 509
    status: G2PECStatus

    def interpret(self):
        self.status = G2PECStatus(int(self.raw_response))


class G2Cmd_PECReplayOn_Set(Gemini2Command_Native_Set):
    native_id = 531


class G2Cmd_PECReplayOff_Set(Gemini2Command_Native_Set):
    native_id = 532


class G2Cmd_NTPServerAddr_Set(Gemini2Command_Native_Set):
    native_id = 816

    def __init__(self, addr: ipaddress.IPv4Address):
        if not isinstance(addr, ipaddress.IPv4Address):
            raise G2CommandParameterTypeError('IPv4Address')
        self.native_params = (str(addr),)


class G2Cmd_NTPServerAddr_Get(Gemini2Command_Native_Get):
    response_expected = True
    native_id = 816
    address: ipaddress.IPv4Address

    def interpret(self):
        self.address = parse_ip4vaddr(self.raw_response)


# ...


### Undocumented Commands


class G2CmdBase_Divisor_Set(Gemini2Command_Native_Set):
    def __init__(self, div: int):
        if not isinstance(div, int):
            raise G2CommandParameterTypeError('int')
        # clamp divisor into the allowable range
        if div < SINT32_MIN:
            div = SINT32_MIN
        if div > SINT32_MAX:
            div = SINT32_MAX
        self.native_params = (str(div),)


class G2Cmd_RA_Divisor_Set(G2CmdBase_Divisor_Set):
    native_id = 451


class G2Cmd_DEC_Divisor_Set(G2CmdBase_Divisor_Set):
    native_id = 452


class G2CmdBase_StartStop_Set(Gemini2Command_Native_Set):
    def __init__(self, val: G2Stopped):
        if not isinstance(val, G2Stopped):
            raise G2CommandParameterTypeError('G2Stopped')
        self.native_params = (f'{val.value:b}',)


class G2Cmd_RA_StartStop_Set(G2CmdBase_StartStop_Set):
    native_id = 453


class G2Cmd_DEC_StartStop_Set(G2CmdBase_StartStop_Set):
    native_id = 454


# TODO: implement GET cmds 451-454


"""
class G2Cmd_Undoc451_Get(Gemini2Command_Native_Get):
    def id(self):
        return 451
    def response(self):
        G2Rsp_Undoc451_Get()


class G2Rsp_Undoc451_Get(Gemini2Response_Native):
    # TODO
    pass


class G2Cmd_Undoc451_Set(Gemini2Command_Native_Set):
    def __init__(self, divisor):
        self._divisor = divisor

    def id(self):
        return 451

    def param(self):
        return f'{self._divisor:+d}'

    def response(self):
        G2Rsp_Undoc451_Set()


class G2Rsp_Undoc451_Set(Gemini2Response_Native):
    # TODO
    pass
"""

# TODO: 452
# TODO: 453
# TODO: 454


"""

HIGH PRIORITY COMMANDS TO IMPLEMENT
===================================
macro 0x05 (ENQ)
set double precision
undocumented native cmds (details omitted here)

LESS IMPORTANT ONES
===================
native 411-412 (do arcsec/sec conversions automagically)
native 21
get meridian side
native 130-137
get RA
get DEC
get AZ
get ALT
all the date+time shit (some of this is under 'Set' category for some idiotic reason)
all the site shit
get info buffer
velocities
park stuff
all move commands + quit-moving commands
native 120-122
native 190-192 (191 = "do not track at all")
native 220-223
native 826
native 65533-65535

BELOW THAT
==========
everything else in category/alphabetical order

"""
