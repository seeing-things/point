from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import re
import ipaddress
from curses.ascii import isgraph
import enum
from enum import Enum, Flag, IntEnum
from collections.abc import Iterable
from typing import Any
from point.gemini_exceptions import (
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
    G2ResponseTooFewDelimitersError,
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
_re_revisions = re.compile(r'^.{8}$', re.ASCII)
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


def parse_revisions(string: str) -> list[int]:
    match = _re_revisions.fullmatch(string)
    if match is None:
        raise G2ResponseRevisionsParseError(string)
    vals = []
    for char in string:
        val = ord(char)
        if val < 0x30 or val > 0x7E:
            raise G2ResponseRevisionsParseError(string)
        vals.append(val - 0x30)
    if len(vals) != 8:
        raise G2ResponseRevisionsParseError(string)
    return vals


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


class Gemini2Command(ABC):

    # Response from the command. Individual commands may set this to subclasses of
    # Gemini2Response. None means no response is expected.
    response: Gemini2Response | None = None

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

    def valid_for_serial(self) -> bool:
        """True if this command is valid on the serial backend.

        Specific commands can override this to return `False` if the particular command
        is not valid for the given backend type.
        """
        return True

    def valid_for_udp(self) -> bool:
        """True if this command is valid on the UDP backend.

        Specific commands can override this to return `False` if the particular command
        is not valid for the given backend type.
        """
        return True

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
                        f"command {self.__class__.__name__:s}: contains '{char}'"
                    )
                else:
                    raise G2CommandBadCharacterError(
                        f"command {self.__class__.__name__:s}: "
                        f"contains '\\x{ord(char):02X}'"
                    )


# ======================================================================================


class Gemini2Command_ACK(Gemini2Command):
    def encode(self) -> str:
        return '\x06'


# --------------------------------------------------------------------------------------


class Gemini2Command_Macro(Gemini2Command):
    def encode(self) -> str:
        return self.cmd_str()

    @abstractmethod
    def cmd_str(self) -> str:
        """The character(s) to send for this macro command."""


# --------------------------------------------------------------------------------------


class Gemini2Command_LX200(Gemini2Command):
    def encode(self) -> str:
        cmd_str = self.lx200_str()
        self._check_validity(cmd_str)
        return f':{cmd_str:s}#'

    @abstractmethod
    def lx200_str(self) -> str:
        """Build the LX200 command string.

        Takes params supplied via the constructor or otherwise (if any) and builds the
        basic command string.

        Implemented at the command-specific subclass level.

        Returns:
            String containing essential cmd info characters.
        """

    def _check_validity(self, cmd_str: str) -> None:
        # TODO: do a more rigorous valid-character-range check here
        self._check_bad_chars(cmd_str, ['#', '\x00', '\x06'])


# --------------------------------------------------------------------------------------


class Gemini2Command_Native(Gemini2Command):
    def encode(self) -> str:
        params_str = self._make_params_str(self.native_params())
        cmd_str = f'{self.native_prefix()}{self.native_id()}:{params_str}'
        return f'{cmd_str:s}{chr(compute_native_checksum(cmd_str)):s}#'

    @abstractmethod
    def native_id(self) -> int:
        """Get the native command ID number."""

    def native_params(self):
        """Get native command parameters.

        Overridden by specific command child classes that have parameters.

        Returns:
            None if no parameters are to be sent along with the command or a parameter
            or list of parameters to be sent along with the command.
        """
        return None

    @abstractmethod
    def native_prefix(self) -> str:
        pass

    # TODO: Make this less complicated by expecting `params` to always be an
    # iterable of strings, even if there are zero or one parameters.
    def _make_params_str(self, params) -> str:
        if params is None:
            return ''
        elif isinstance(params, Iterable) and (not isinstance(params, str)):
            for param in params:
                self._check_validity(str(param))
            return ':'.join(params)
        else:
            self._check_validity(str(params))
            return str(params)

    def _check_validity(self, param_str: str) -> None:
        # TODO: do a more rigorous valid-character-range check here
        self._check_bad_chars(param_str, ['<', '>', ':', '#', '\x00', '\x06'])


class Gemini2Command_Native_Get(Gemini2Command_Native):
    def native_prefix(self) -> str:
        return '<'


class Gemini2Command_Native_Set(Gemini2Command_Native):
    def native_prefix(self) -> str:
        return '>'


########################################################################################


class Gemini2Response(ABC):
    """Decodes, processes, and stores the response from a Gemini command.

    Attributes:
        type: Type of response. This determines how the response is interpreted and
            informs the backend how to determine when it has received the full response.
        decoded: True after `decode()` has been called, False until then.
        zero_len_hack: Whether to process possibly-zero-length responses. This may only
            be True if the `type` is FIXED_LENGTH.
        length_expected: The expected number of characters in the response. Only
            relevant when the `type` is FIXED_LENGTH.
        num_fields_expected: The number of fields expected in the response. Only
            relevant when the `type` is SEMICOLON_DELIMITED.
    """

    class ResponseType(enum.Enum):
        FIXED_LENGTH = enum.auto()
        HASH_TERMINATED = enum.auto()
        SEMICOLON_DELIMITED = enum.auto()

    type: ResponseType = ResponseType.HASH_TERMINATED
    decoded: bool = False
    zero_len_hack: bool = False
    length_expected: int = 0
    num_fields_expected: int = 0

    def decode(self, chars: str) -> int:
        """Decode a command response.

        Args:
            chars: String containing this response, and potentially additional responses
                to other commands.

        Returns:
            Integer representing how many characters from the input were decoded for
            this response.
        """
        assert not self.decoded
        self.decoded = True

        if self.type == self.ResponseType.FIXED_LENGTH:
            idx = self.length_expected
            if len(chars) < idx:
                raise G2ResponseTooShortError(len(chars), idx)
            resp_data = chars[:idx]
            num_chars_processed = idx
        elif self.type == self.ResponseType.HASH_TERMINATED:
            idx = chars.find('#')
            if idx == -1:
                raise G2ResponseMissingTerminatorError(len(chars))
            resp_data = chars[:idx]
            num_chars_processed = idx + 1
        elif self.type == self.ResponseType.SEMICOLON_DELIMITED:
            # SERIOUS ISSUE: the 'revisions' (native #97) field contains chars in the
            # range of 0x30 ~ 0x7E, inclusive; this happens to include the semicolon
            # character. so we end up spuriously interpreting revision chars as field
            # delimiters in those cases!
            # TEMPORARY WORKAROUND:
            # - SemicolonDelimitedDecoder.decode:
            #   - remove assertion for number of fields
            #   - replace total_len calculation with fake calculation
            # - G2Rsp_MacroENQ.interpret:
            #   - remove parsing of "later" fields, since we don't CURRENTLY need them
            # TODO: report this to Rene!
            fields = chars.split(';', self.num_fields_expected)
            if len(fields) <= self.num_fields_expected:
                raise G2ResponseTooFewDelimitersError(
                    len(chars), len(fields), self.num_fields_expected
                )
            # assert len(fields) == self.num_fields + 1
            fields = fields[:-1]
            # total_len = (len(fields) + sum(len(field) for field in fields))
            total_len = len(chars)  # !!! REMOVE ME !!!
            resp_data = fields
            num_chars_processed = total_len
        else:
            raise G2ResponseException(f'Unsupported response type {self.type}')

        self._resp_data = self.post_decode(resp_data)
        self.interpret()
        return num_chars_processed

    def post_decode(self, chars: str | list[str]) -> str | list[str]:
        """Optionally implement to do some additional post-decode-step verification."""
        return chars

    def interpret(self) -> None:
        """Optionally implement to do cmd-specific interpretation of the response."""
        return None

    def get_raw(self) -> str | list[str]:
        """Raw response string (or list-of-strings, in the semicolon-delimited case)."""
        assert self.decoded
        return self._resp_data

    def get(self) -> Any:
        """Override this to return interpreted data instead of the raw response."""
        return self.get_raw()


# ======================================================================================


class Gemini2Response_ACK(Gemini2Response):
    type = Gemini2Response.ResponseType.HASH_TERMINATED


# --------------------------------------------------------------------------------------


class Gemini2Response_Macro(Gemini2Response):
    type = Gemini2Response.ResponseType.SEMICOLON_DELIMITED


# --------------------------------------------------------------------------------------


class Gemini2Response_LX200(Gemini2Response):
    type = Gemini2Response.ResponseType.HASH_TERMINATED


# --------------------------------------------------------------------------------------


class Gemini2Response_LX200_FixedLength(Gemini2Response_LX200):
    type = Gemini2Response.ResponseType.FIXED_LENGTH


class Gemini2Response_LX200_FixedLengthOrZero(Gemini2Response_LX200_FixedLength):
    type = Gemini2Response.ResponseType.FIXED_LENGTH
    zero_len_hack = True


# --------------------------------------------------------------------------------------


class Gemini2Response_Native(Gemini2Response):
    type = Gemini2Response.ResponseType.HASH_TERMINATED

    def post_decode(self, chars: str) -> str:
        if len(chars) < 1:
            # TODO: Is this a bug? Why return None instead of empty string?
            return
        csum_recv = ord(chars[-1])
        csum_comp = compute_native_checksum(chars[:-1])
        if csum_recv != csum_comp:
            raise G2ResponseChecksumMismatchError(csum_recv, csum_comp)
        return chars[:-1]


#    def get(self):
#        # TODO: need to return our post-processed string, not the raw string
#        pass

# TODO: implement generic G2-Native response decoding


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


class G2AxisPosition(Enum):
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


class G2Revision(IntEnum):
    """Indexes for MacroENQ field 'revisions'."""

    SITE = 0
    DATE_TIME = 1
    MOUNT_PARAM = 2
    DISPLAY_CONTENT = 3
    MODEL_PARAM = 4
    SPEEDS = 5
    PARK = 6
    RESERVED = 7


# Parameter for MacroENQ fields 'servo_lag_x' and 'servo_lag_y'.
G2_SERVO_LAG_MIN = -390
G2_SERVO_LAG_MAX = 390


def parse_servo_lag(string: str) -> int:
    return parse_int_bounds(string, G2_SERVO_LAG_MIN, G2_SERVO_LAG_MAX)


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


class G2Rsp_StartupCheck(Gemini2Response_ACK):
    def interpret(self) -> None:
        self._status = G2StartupStatus(
            self.get_raw()
        )  # raises ValueError if the response value isn't in the enum

    def get(self) -> G2StartupStatus:
        return self._status


@dataclass
class G2Cmd_StartupCheck(Gemini2Command_ACK):
    response: G2Rsp_StartupCheck = field(default_factory=G2Rsp_StartupCheck, init=False)


class G2Cmd_SelectStartupMode(Gemini2Command_LX200):
    def __init__(self, mode: G2StartupMode):
        if not isinstance(mode, G2StartupMode):
            raise G2CommandParameterTypeError('G2StartupMode')
        self._mode = mode

    def lx200_str(self):
        return f'b{G2StartupMode[self._mode]:s}'


### Macro Commands


class G2Rsp_MacroENQ(Gemini2Response_Macro):
    num_fields_expected = 21

    def interpret(self) -> None:
        # TODO: implement some range checking on most of the numerical fields here
        # (e.g. angle ranges:  [0,180) or [-90,+90] or [0,360)  etc)
        fields = self.get_raw()
        self._values = {}
        # raises G2ResponseIntegerParseError on failure
        # self._values['phys_x'] = parse_int(fields[0])
        # raises G2ResponseIntegerParseError on failure
        # self._values['phys_y'] = parse_int(fields[1])
        # raises G2ResponseIntegerParseError on failure
        self._values['pra'] = parse_int(fields[0])
        # raises G2ResponseIntegerParseError on failure
        self._values['pdec'] = parse_int(fields[1])
        # raises G2ResponseAngleParseError on failure
        self._values['ra'] = parse_ang_dbl(fields[2])
        # raises G2ResponseAngleParseError on failure
        self._values['dec'] = parse_ang_dbl(fields[3])
        # raises G2ResponseAngleParseError on failure
        self._values['ha'] = parse_ang_dbl(fields[4])
        # raises G2ResponseAngleParseError on failure
        self._values['az'] = parse_ang_dbl(fields[5])
        # raises G2ResponseAngleParseError on failure
        self._values['alt'] = parse_ang_dbl(fields[6])
        # raises ValueError if the response field value isn't in the enum
        self._values['vel_max'] = G2AxisVelocity(fields[7])
        # raises ValueError if the response field value isn't in the enum
        self._values['vel_x'] = G2AxisVelocity(fields[8])
        # raises ValueError if the response field value isn't in the enum
        self._values['vel_y'] = G2AxisVelocity(fields[9])
        # raises ValueError if the response field value isn't in the enum
        self._values['ha_pos'] = G2AxisPosition(fields[10])
        # raises G2ResponseTimeParseError on failure
        self._values['t_sidereal'] = parse_time_dbl(fields[11])
        # raises ValueError if the response field value isn't in the enum
        self._values['park_state'] = G2ParkStatus(int(fields[12]))
        # raises ValueError if the response field value isn't in the enum
        self._values['pec_state'] = G2PECStatus(int(fields[13]))
        # raises G2ResponseTimeParseError on failure
        self._values['t_wsl'] = parse_time_dbl(fields[14])
        # raises ValueError if the response field value isn't in the enum
        self._values['cmd99_state'] = G2Status(int(fields[15]))
        # raises G2ResponseRevisionsParseError on failure
        # self._values['revisions'] = parse_revisions(fields[16])
        # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on
        # failure
        # self._values['servo_lag_x'] = parse_servo_lag(fields[17])
        # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on
        # failure
        # self._values['servo_lag_y'] = parse_servo_lag(fields[18])
        # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on
        # failure
        # self._values['servo_duty_x'] = parse_servo_duty(fields[19])
        # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on
        # failure
        # self._values['servo_duty_y'] = parse_servo_duty(fields[20])

    def get(self) -> dict:
        return self._values


@dataclass
class G2Cmd_MacroENQ(Gemini2Command_Macro):
    response: G2Rsp_MacroENQ = field(default_factory=G2Rsp_MacroENQ, init=False)

    def cmd_str(self):
        return '\x05'

    def valid_for_serial(self):
        return False  # only valid on UDP backend


### Synchronization Commands


class G2Rsp_Echo(Gemini2Response_LX200):
    pass


class G2Cmd_Echo(Gemini2Command_LX200):
    response: G2Rsp_Echo

    def __init__(self, char: str):
        if (not isinstance(char, str)) or (len(char) != 1):
            raise G2CommandParameterTypeError('char')
        self._char = char
        self.response = G2Rsp_Echo()

    def lx200_str(self):
        return f'CE{self._char:s}'


class G2Rsp_AlignToObject(Gemini2Response_LX200):
    def interpret(self) -> None:
        if self.get_raw() == 'No object!':
            raise G2ResponseInterpretationFailure()


@dataclass
class G2Cmd_AlignToObject(Gemini2Command_LX200):
    response: G2Rsp_AlignToObject = field(
        default_factory=G2Rsp_AlignToObject, init=False
    )

    def lx200_str(self):
        return 'Cm'


class G2Rsp_SyncToObject(Gemini2Response_LX200):
    def interpret(self) -> None:
        if self.get_raw() == 'No object!':
            raise G2ResponseInterpretationFailure()


@dataclass
class G2Cmd_SyncToObject(Gemini2Command_LX200):
    response: G2Rsp_SyncToObject = field(default_factory=G2Rsp_SyncToObject, init=False)

    def lx200_str(self):
        return 'CM'


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
            raise G2CommandParameterValueError('name cannot be empty')
        if '#' in name:
            raise G2CommandParameterValueError('name cannot contain \'#\' characters')
        self._name = name

    def lx200_str(self):
        return f'ON{self._name:s}'


# ...


### Precession and Refraction Commands

# ...


### Precision Commands


class G2Rsp_GetPrecision(Gemini2Response_LX200_FixedLength):
    length_expected = 14

    def interpret(self) -> None:
        self._precision = G2Precision(
            self.get_raw()
        )  # raises ValueError if the response value isn't in the enum

    def get(self) -> G2Precision:
        return self._precision


@dataclass
class G2Cmd_GetPrecision(Gemini2Command_LX200):
    response: G2Rsp_GetPrecision = field(default_factory=G2Rsp_GetPrecision, init=False)

    def lx200_str(self):
        return 'P'


class G2Cmd_TogglePrecision(Gemini2Command_LX200):
    def lx200_str(self):
        return 'U'


class G2Cmd_SetDblPrecision(Gemini2Command_LX200):
    def lx200_str(self):
        return 'u'


### Quit Motion Commands

# ...


### Rate Commands

# ...


### Set Commands
class G2Rsp_SetObjectRA(Gemini2Response_LX200_FixedLength):
    length_expected = 1

    def interpret(self) -> None:
        validity = G2Valid(
            self.get_raw()
        )  # raises ValueError if the response field value isn't in the enum
        if validity != G2Valid.VALID:
            raise G2ResponseInterpretationFailure()


class G2Cmd_SetObjectRA(Gemini2Command_LX200):
    response: G2Rsp_SetObjectRA

    def __init__(self, ra: float):
        if ra < 0.0 or ra >= 360.0:
            raise G2CommandParameterValueError('ra must be >= 0.0 and < 360.0')
        _, self._hour, self._min, self._sec = ang_to_hourminsec(ra)
        self.response = G2Rsp_SetObjectRA()

    def lx200_str(self):
        return f'Sr{self._hour:02d}:{self._min:02d}:{self._sec:02d}'


class G2Rsp_SetObjectDec(Gemini2Response_LX200_FixedLength):
    length_expected = 1

    def interpret(self):
        # Raises ValueError if the response field value isn't in the enum.
        validity = G2Valid(self.get_raw())
        if validity != G2Valid.VALID:
            raise G2ResponseInterpretationFailure()
        # NOTE: only objects which are currently above the horizon are considered valid


class G2Cmd_SetObjectDec(Gemini2Command_LX200):
    response: G2Rsp_SetObjectDec

    def __init__(self, dec: float):
        if dec < -90.0 or dec > 90.0:
            raise G2CommandParameterValueError('dec must be >= -90.0 and <= 90.0')
        sign, self._deg, self._min, self._sec = ang_to_degminsec(dec)
        self._signchar = '+' if sign >= 0 else '-'
        self.response = G2Rsp_SetObjectDec()

    def lx200_str(self):
        return f'Sd{self._signchar}{self._deg:02d}:{self._min:02d}:{self._sec:02d}'


class G2Rsp_SetSiteLongitude(Gemini2Response_LX200_FixedLengthOrZero):
    length_expected = 1

    def interpret(self):
        if len(self.get_raw()) == 0:
            raise G2ResponseInterpretationFailure()  # invalid
        if self.get_raw() != '1':
            raise G2ResponseInterpretationFailure()  # ???


class G2Cmd_SetSiteLongitude(Gemini2Command_LX200):
    response: G2Rsp_SetSiteLongitude

    def __init__(self, lon: float):
        if lon <= -360.0 or lon >= 360.0:
            raise G2CommandParameterValueError('lon must be > -360.0 and < 360.0')
        sign, self._deg, self._min = ang_to_degmin(lon)
        # everyone else in the world uses positive to mean eastern longitudes; but not
        # LX200!
        self._signchar = '-' if sign >= 0 else '+'
        self.response = G2Rsp_SetSiteLongitude()

    def lx200_str(self):
        return f'Sg{self._signchar:s}{self._deg:03d}*{self._min:02d}'


class G2Rsp_SetSiteLatitude(Gemini2Response_LX200_FixedLengthOrZero):
    length_expected = 1

    def interpret(self):
        if len(self.get_raw()) == 0:
            raise G2ResponseInterpretationFailure()  # invalid
        if self.get_raw() != '1':
            raise G2ResponseInterpretationFailure()  # ???


class G2Cmd_SetSiteLatitude(Gemini2Command_LX200):
    response: G2Rsp_SetSiteLatitude

    def __init__(self, lat: float):
        if lat < -90.0 or lat > 90.0:
            raise G2CommandParameterValueError('lat must be >= -90.0 and <= 90.0')
        sign, self._deg, self._min = ang_to_degmin(lat)
        self._signchar = '+' if sign >= 0.0 else '-'
        self.response = G2Rsp_SetSiteLatitude()

    def lx200_str(self):
        return f'St{self._signchar:s}{self._deg:02d}*{self._min:02d}'


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
            raise G2CommandParameterValueError('site must be >= 0 and <= 4')
        self._site = site

    def lx200_str(self):
        return f'W{self._site:d}'


class G2Rsp_GetStoredSite(Gemini2Response_LX200_FixedLength):
    length_expected = 1

    def interpret(self) -> None:
        self._site = parse_int_bounds(self.get_raw(), 0, 4)

    def get(self) -> int:
        return self._site


@dataclass
class G2Cmd_GetStoredSite(Gemini2Command_LX200):
    """Note that the official Gemini 2 serial command documentation is wrong: the range
    for sites is 0-4 inclusive, not 0-3 inclusive."""

    response: G2Rsp_GetStoredSite = field(
        default_factory=G2Rsp_GetStoredSite, init=False
    )

    def lx200_str(self):
        return 'W?'


# ...


### Native Commands

# class G2Cmd_TEST_Native_92_Get(Gemini2Command_Native_Get):
#    def __init__(self, val):
#        if not isinstance(val, int):
#            raise G2CommandParameterTypeError('int')
#        self._val = val
#    def native_id(self):     return 92
##    def native_params(self): return '{:d}'.format(self._val)
#    def response(self):      return None # TODO!


class G2Cmd_PECBootPlayback_Set(Gemini2Command_Native_Set):
    def __init__(self, enable: bool):
        if not isinstance(enable, bool):
            raise G2CommandParameterTypeError('bool')
        self._enable = enable

    def native_id(self):
        return 508

    def native_params(self):
        return '1' if self._enable else '0'


class G2Rsp_PECBootPlayback_Get(Gemini2Response_Native):
    def interpret(self):
        self._enabled = parse_int_bounds(self.get_raw(), 0, 1)

    def get(self) -> bool:
        return self._enabled != 0


@dataclass
class G2Cmd_PECBootPlayback_Get(Gemini2Command_Native_Get):
    response: G2Rsp_PECBootPlayback_Get = field(
        default_factory=G2Rsp_PECBootPlayback_Get, init=False
    )

    def native_id(self):
        return 508


class G2Cmd_PECStatus_Set(Gemini2Command_Native_Set):
    def __init__(self, status: G2PECStatus):
        if not isinstance(status, G2PECStatus):
            raise G2CommandParameterTypeError('G2PECStatus')
        self._status = status

    def native_id(self):
        return 509

    def native_params(self):
        return str(self._status.value)


class G2Rsp_PECStatus_Get(Gemini2Response_Native):
    def interpret(self):
        # Raises ValueError if the response field value isn't in the enum.
        self._status = G2PECStatus(int(self.get_raw()))

    def get(self):
        return self._status


@dataclass
class G2Cmd_PECStatus_Get(Gemini2Command_Native_Get):
    response: G2Rsp_PECStatus_Get = field(
        default_factory=G2Rsp_PECStatus_Get, init=False
    )

    def native_id(self):
        return 509


class G2Cmd_PECReplayOn_Set(Gemini2Command_Native_Set):
    def native_id(self):
        return 531


class G2Cmd_PECReplayOff_Set(Gemini2Command_Native_Set):
    def native_id(self):
        return 532


class G2Cmd_NTPServerAddr_Set(Gemini2Command_Native_Set):
    def __init__(self, addr: ipaddress.IPv4Address):
        if not isinstance(addr, ipaddress.IPv4Address):
            raise G2CommandParameterTypeError('IPv4Address')
        self._addr = addr

    def native_id(self):
        return 816

    def native_params(self):
        return str(self._addr)


class G2Rsp_NTPServerAddr_Get(Gemini2Response_Native):
    def interpret(self):
        self._addr = parse_ip4vaddr(self.get_raw())

    def get(self) -> ipaddress.IPv4Address:
        return self._addr


@dataclass
class G2Cmd_NTPServerAddr_Get(Gemini2Command_Native_Get):
    response: G2Rsp_NTPServerAddr_Get = field(
        default_factory=G2Rsp_NTPServerAddr_Get, init=False
    )

    def native_id(self):
        return 816


# ...


### Undocumented Commands


class G2CmdBase_Divisor_Set(Gemini2Command_Native_Set):
    def __init__(self, div: int):
        if not isinstance(div, int):
            raise G2CommandParameterTypeError('int')
        # clamp divisor into the allowable range
        if div < self._div_min():
            div = self._div_min()
        if div > self._div_max():
            div = self._div_max()
        self._div = div

    def native_params(self):
        return self._div

    def _div_min(self):
        return SINT32_MIN

    def _div_max(self):
        return SINT32_MAX


class G2Cmd_RA_Divisor_Set(G2CmdBase_Divisor_Set):
    def native_id(self):
        return 451


class G2Cmd_DEC_Divisor_Set(G2CmdBase_Divisor_Set):
    def native_id(self):
        return 452


class G2CmdBase_StartStop_Set(Gemini2Command_Native_Set):
    def __init__(self, val: G2Stopped):
        if not isinstance(val, G2Stopped):
            raise G2CommandParameterTypeError('G2Stopped')
        self._val = val

    def native_params(self):
        return f'{self._val.value:b}'


class G2Cmd_RA_StartStop_Set(G2CmdBase_StartStop_Set):
    def native_id(self):
        return 453


class G2Cmd_DEC_StartStop_Set(G2CmdBase_StartStop_Set):
    def native_id(self):
        return 454


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
        return '{:+d}'.format(self._divisor)

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
