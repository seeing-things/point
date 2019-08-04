from abc import *
import re
import collections
import sys
from point.gemini_exceptions import *


if not (sys.version_info[0] == 3 and sys.version_info[1] < 6):
    from enum import *
else:
    # backported Python 3.6 enum class (has Flags etc)
    from point.enum36 import *


# TODO: print command/response class name in exception messages more often / more consistently


####################################################################################################


_re_int       = re.compile(r'^([-+]?)(\d+)$',                             re.ASCII)
_re_ang_dbl   = re.compile(r'^([-+]?)(\d{1,3}\.\d{6})$',                  re.ASCII)
_re_ang_high  = re.compile(r'^([-+]?)(\d{1,2}):(\d{1,2}):(\d{1,2})$',     re.ASCII)
_re_ang_low   = re.compile(r'^([-+]?)(\d{1,2})' + '\xDF' + r'(\d{1,2})$', re.ASCII)
_re_time_dbl  = re.compile(r'^([-+]?)(\d+\.\d{6})$',                      re.ASCII)
_re_time_hilo = re.compile(r'^(\d{1,2}):(\d{1,2}):(\d{1,2})$',            re.ASCII)
_re_revisions = re.compile(r'^.{8}$',                                     re.ASCII)


def parse_int(string):
    match = _re_int.fullmatch(string)
    if match is None: raise G2ResponseIntegerParseError(string)
    return int(match.expand(r'\1\2'))

def parse_int_bounds(string, bound_min, bound_max):
    assert bound_min <= bound_max
    val = parse_int(string)
    if val < bound_min or val > bound_max: raise G2ResponseIntegerBoundsViolation(val, bound_min, bound_max)
    return val


def parse_ang_dbl(string):
    match = _re_ang_dbl.fullmatch(string)
    if match is None: raise G2ResponseAngleParseError(string, 'double')
    return float(match.expand(r'\1\2'))

def parse_ang_high(string):
    match = _re_ang_high.fullmatch(string)
    if match is None: raise G2ResponseAngleParseError(string, 'high')
    f_deg = float(match.expand(r'\1\2'))
    f_min = float(match.expand(r'\1\3'))
    f_sec = float(match.expand(r'\1\4'))
    return (f_deg + (f_min / 60.0) + (f_sec / 3600.0))

def parse_ang_low(string):
    match = _re_ang_low.fullmatch(string)
    if match is None: raise G2ResponseAngleParseError(string, 'low')
    f_deg = float(match.expand(r'\1\2'))
    f_min = float(match.expand(r'\1\3'))
    return (f_deg + (f_min / 60.0))

def parse_ang(string, precision):
    assert isinstance(precision, G2Precision)
    if   precision == G2Precision.DOUBLE: return parse_ang_dbl (string)
    elif precision == G2Precision.HIGH:   return parse_ang_high(string)
    elif precision == G2Precision.LOW:    return parse_ang_low (string)


def parse_time_dbl(string):
    match = _re_time_dbl.fullmatch(string)
    if match is None: raise G2ResponseTimeParseError(string, 'double')
    return float(match.expand(r'\1\2'))

def parse_time_hilo(string):
    match = _re_time_hilo.fullmatch(string)
    if match is None: raise G2ResponseTimeParseError(string, 'high/low')
    i_hour = int(match[1])
    i_min  = int(match[2])
    i_sec  = int(match[3])
    # TODO: bounds check on hour field...? and should we even be limiting the hour field to 2 digits in the RE?
    if i_min >= 60 or i_sec >= 60: raise G2ResponseTimeParseError(string, 'high/low')
    return float((i_hour * 3600) + (i_min * 60) + i_sec)

def parse_time(string, precision):
    assert isinstance(precision, G2Precision)
    if precision == G2Precision.DOUBLE: return parse_ang_dbl (string)
    else:                               return parse_ang_hilo(string)


def parse_revisions(string):
    match = _re_revisions.fullmatch(string)
    if match is None: raise G2ResponseRevisionsParseError(string)
    vals = []
    for char in string:
        val = ord(char)
        if val < 0x30 or val > 0x7E: raise G2ResponseRevisionsParseError(string)
        vals.append(val - 0x30)
    assert len(vals) == 8
    return vals


####################################################################################################


# returns tuple: (int:sign[-1|0|+1], int:deg, int:min, float:sec)
def ang_to_degminsec(ang):
    if   ang > 0.0: sign = +1.0
    elif ang < 0.0: sign = -1.0
    else:           sign =  0.0
    ang = abs(ang) * 3600.0
    f_sec = ang % 60.0
    ang /= 60.0
    i_min = int(ang % 60.0)
    ang /= 60.0
    i_deg = int(ang)
    return (sign, i_deg, i_min, f_sec)
# TODO: test this, in case I am dumb

# returns tuple: (int:sign[-1|0|+1], int:hour, int:min, float:sec)
def ang_to_hourminsec(ang):
    return ang_to_degminsec(ang * 24.0 / 360.0)


####################################################################################################


class Gemini2Command(ABC):
    # IMPLEMENTED AT THE PROTOCOL-SPECIFIC SUBCLASS LEVEL (LX200, Native, etc)
    # purpose: takes info from the command-specific subclass and turns it into a raw cmd string with
    #          prefix, postfix, checksum, etc that's completely ready to be shoved onto the backend
    # return: string containing fully encoded raw command with prefix, postfix, checksum, etc
    @abstractmethod
    def encode(self): pass

    # return: a Gemini2Response-derived object if this command expects a response
    # return: None if this command does not expect a response
    @abstractmethod
    def response(self): pass

    # return: False if this particular command is not valid for the given backend type
    def valid_for_serial(self): return True
    def valid_for_udp(self):    return True

# ==================================================================================================

class Gemini2Command_ACK(Gemini2Command):
    def encode(self):
        return '\x06'

# --------------------------------------------------------------------------------------------------

class Gemini2Command_Macro(Gemini2Command):
    def encode(self):
        return self.cmd_str()

    # return: the character(s) to send for this macro command
    @abstractmethod
    def cmd_str(self): pass

# --------------------------------------------------------------------------------------------------

class Gemini2Command_LX200(Gemini2Command):
    def encode(self):
        cmd_str = self.lx200_str()
        self._check_validity(cmd_str)
        return ':{:s}#'.format(cmd_str)

    # IMPLEMENTED AT THE COMMAND-SPECIFIC SUBCLASS LEVEL (Echo etc)
    # purpose: takes params supplied via the ctor or otherwise (if any) and builds the basic cmd str
    # return: string containing essential cmd info characters
    @abstractmethod
    def lx200_str(self): pass

    def _check_validity(self, cmd_str):
        # TODO: do a more rigorous valid-character-range check here
        assert not '#' in cmd_str
        assert not '\x00' in cmd_str
        assert not '\x06' in cmd_str

class Gemini2Command_LX200_NoReply(Gemini2Command_LX200):
    def response(self):
        return None

# --------------------------------------------------------------------------------------------------

class Gemini2Command_Native(Gemini2Command):
    def encode(self):
        assert isinstance(self.native_id(), int)
        params_str = self._make_params_str(self.native_params())
        cmd_str = '{:s}{:d}:{:s}'.format(self.native_prefix(), self.native_id(), params_str)
        return '{:s}{:s}#'.format(cmd_str, chr(self._compute_checksum(cmd_str)))

    # IMPLEMENTED AT THE COMMAND-SPECIFIC SUBCLASS LEVEL (GetMountType etc)
    # return: native command ID number
    @abstractmethod
    def native_id(self): pass

    # IMPLEMENTED AT THE COMMAND-SPECIFIC SUBCLASS LEVEL (GetMountType etc)
    # return: None if no parameters are to be sent along with the command
    # return: a parameter, or list-of-parameters, to be sent along with the command
    def native_params(self):
        return None

    @abstractmethod
    def native_prefix(self): pass

    def _make_params_str(self, params):
        assert sys.version_info[0] >= 3 # our string type check below is incompatible with Python 2
        if params is None:
            return ''
        elif isinstance(params, collections.Iterable) and (not isinstance(params, str)):
            for param in params:
                self._check_validity(str(param))
            return ':'.join(params)
        else:
            self._check_validity(str(params))
            return str(params)

    def _check_validity(self, param_str):
        # TODO: do a more rigorous valid-character-range check here
        assert not '<' in param_str
        assert not '>' in param_str
        assert not ':' in param_str
        assert not '#' in param_str
        assert not '\x00' in param_str
        assert not '\x06' in param_str

    # TODO: move this to somewhere common between cmd and response
    def _compute_checksum(self, cmd_str):
        csum = 0
        for char in cmd_str:
            csum = csum ^ ord(char)
        csum = (csum % 128) + 64
        assert csum >= 0x40 and csum < 0xC0
        return csum

class Gemini2Command_Native_Get(Gemini2Command_Native):
    def native_prefix(self):
        return '<'

class Gemini2Command_Native_Set(Gemini2Command_Native):
    def native_prefix(self):
        return '>'

    # TODO: verify whether this is correct, or if SET's ever respond with stuff
    def response(self):
        return None


####################################################################################################


class Gemini2Response(ABC):
    DecoderType = Enum('DecoderType', ['FIXED_LENGTH', 'HASH_TERMINATED', 'SEMICOLON_DELIMITED'])

    class Decoder(ABC):
        @abstractmethod
        def type(self): pass

        # return: tuple: ([decoded_str OR list-of-decoded_strs], num_chars_processed)
        @abstractmethod
        def decode(self, chars): pass

    class FixedLengthDecoder(Decoder):
        def __init__(self, fixed_len):
            assert fixed_len >= 0
            self._fixed_len = fixed_len

        def fixed_len(self):
            return self._fixed_len

        def type(self): return DecoderType.FIXED_LENGTH

        def decode(self, chars):
            idx = self.fixed_len()
            if len(chars) < idx:
                raise G2ResponseTooShortError(len(chars), idx)
            return (chars[:idx], idx)

    class HashTerminatedDecoder(Decoder):
        def type(self): return DecoderType.HASH_TERMINATED

        def decode(self, chars):
            idx = chars.find('#')
            if idx == -1:
                raise G2ResponseMissingTerminatorError(len(chars))
            return (chars[:idx], idx + 1)

    # SERIOUS ISSUE: the 'revisions' (native #97) field contains chars in the range of 0x30 ~ 0x7E,
    # inclusive; this happens to include the semicolon character. so we end up spuriously
    # interpreting revision chars as field delimiters in those cases!
    # TEMPORARY WORKAROUND:
    # - SemicolonDelimitedDecoder.decode:
    #   - remove assertion for number of fields
    #   - replace total_len calculation with fake calculation
    # - G2Rsp_MacroENQ.interpret:
    #   - remove parsing of "later" fields, since we don't CURRENTLY need them
    # TODO: report this to Rene!
    class SemicolonDelimitedDecoder(Decoder):
        def __init__(self, num_fields):
            assert num_fields >= 0
            self._num_fields = num_fields

        def num_fields(self):
            return self._num_fields

        def type(self): return DecoderType.SEMICOLON_DELIMITED

        def decode(self, chars):
            fields = chars.split(';', self._num_fields)
            if len(fields) <= self._num_fields:
                raise G2ResponseTooFewDelimitersError(len(chars), len(fields), self._num_fields)
#            assert len(fields) == self._num_fields + 1
            fields = fields[:-1]
#            total_len = (len(fields) + sum(len(field) for field in fields))
            total_len = len(chars) # !!! REMOVE ME !!!
            return (fields, total_len)


    def __init__(self, cmd):
        assert isinstance(cmd, Gemini2Command)
        self._cmd = cmd
        self._decoded = False

    # return: an instance of one of the Decoder subclasses
    @abstractmethod
    def decoder(self): pass

    # input: string containing this response, and potentially additional responses to other commands
    # return: integer representing how many characters from the input were decoded for this response
    def decode(self, chars):
        assert not self._decoded
        self._decoded = True
        (resp_data, num_chars_processed) = self.decoder().decode(chars)
        self._resp_data = self.post_decode(resp_data)
        self.interpret()
        return num_chars_processed

    # purpose: optionally implement this to do some additional post-decode-step verification
    def post_decode(self, chars):
        return chars

    # purpose: optionally implement this to do cmd-specific interpretation of the response string
    def interpret(self): pass

    def decoder_type(self):
        return self.decoder().type()

    def command(self):
        return self._cmd

    # return: raw response string (or list-of-strings, in the semicolon-delimited case)
    def get_raw(self):
        assert self._decoded
        return self._resp_data

    # purpose: optionally override this to return interpreted data instead of the raw response str(s)
    def get(self):
        return self.get_raw()

# ==================================================================================================

class Gemini2Response_ACK(Gemini2Response):
    def decoder(self):
        return self.HashTerminatedDecoder()

# --------------------------------------------------------------------------------------------------

class Gemini2Response_Macro(Gemini2Response):
    def decoder(self):
        return self.SemicolonDelimitedDecoder(self.field_count())

    # return: number of semicolon-separated fields expected from this macro response
    @abstractmethod
    def field_count(self): pass

# --------------------------------------------------------------------------------------------------

class Gemini2Response_LX200(Gemini2Response):
    def decoder(self):
        return self.HashTerminatedDecoder()

class Gemini2Response_LX200_FixedLength(Gemini2Response_LX200):
    def decoder(self):
        return self.FixedLengthDecoder(self.fixed_len())

    @abstractmethod
    def fixed_len(self): pass

# --------------------------------------------------------------------------------------------------

class Gemini2Response_Native(Gemini2Response):
    def decoder(self):
        return self.HashTerminatedDecoder()

    def post_decode(self, chars):
        if len(chars) < 1: return
        csum_recv = ord(chars[-1])
        csum_comp = self.command()._compute_checksum(chars[:-1])
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

# (used in a variety of locations)
# parameter for GetPrecision
class G2Precision(Enum):
    DOUBLE = 'DBL  PRECISION'
    HIGH   = 'HIGH PRECISION'
    LOW    = 'LOW  PRECISION'

# parameter for StartupCheck
class G2StartupStatus(Enum):
    INITIAL         = 'B'
    MODE_SELECT     = 'b'
    COLD_START      = 'S'
    DONE_EQUATORIAL = 'G'
    DONE_ALTAZ      = 'A'

# parameter for SelectStartupMode
class G2StartupMode(Enum):
    COLD_START   = 'C'
    WARM_START   = 'W'
    WARM_RESTART = 'R'

# parameter for MacroENQ [fields 'vel_max', 'vel_x', 'vel_y']
class G2AxisVelocity(Enum):
    STALL       = '!'
    NO_MOVEMENT = 'N'
    SLEWING     = 'S'
    CENTERING   = 'C'
    TRACKING    = 'T'
    GUIDING     = 'G'
    UNDEFINED   = '?'

# parameter for MacroENQ [field 'ha_pos']
class G2AxisPosition(Enum):
    LOWER_SIDE  = 'W'
    HIGHER_SIDE = 'E'

# parameter for MacroENQ [field 'park_state']
class G2ParkStatus(Enum):
    NOT_PARKED = 0
    PARKED     = 1
    PARKING    = 2

# parameter for MacroENQ [field 'pec_state']
class G2PECStatus(Flag):
    ACTIVE               = (1 << 0)
    FRESH_DATA_AVAILABLE = (1 << 1)
    TRAINING_IN_PROGRESS = (1 << 2)
    TRAINING_COMPLETED   = (1 << 3)
    TRAINING_STARTS_SOON = (1 << 4)
    DATA_AVAILABLE       = (1 << 5)

# parameter for MacroENQ [field 'cmd99_state']
class G2Status(Flag):
    SCOPE_IS_ALIGNED          = (1 << 0)
    MODELLING_IN_USE          = (1 << 1)
    OBJECT_IS_SELECTED        = (1 << 2)
    GOTO_OPERATION_ONGOING    = (1 << 3)
    RA_LIMIT_REACHED          = (1 << 4)
    ASSUMING_J2000_OBJ_COORDS = (1 << 5)

# indexes for MacroENQ [field 'revisions']
class G2Revision(IntEnum):
    SITE            = 0
    DATE_TIME       = 1
    MOUNT_PARAM     = 2
    DISPLAY_CONTENT = 3
    MODEL_PARAM     = 4
    SPEEDS          = 5
    PARK            = 6
    RESERVED        = 7

# parameter for MacroENQ [fields 'servo_lag_x', 'servo_lag_y']
G2_SERVO_LAG_MIN = -390
G2_SERVO_LAG_MAX =  390
def parse_servo_lag(string): return parse_int_bounds(string, G2_SERVO_LAG_MIN, G2_SERVO_LAG_MAX)

# parameter for MacroENQ [fields 'servo_duty_x', 'servo_duty_y']
G2_SERVO_DUTY_MIN = -100
G2_SERVO_DUTY_MAX =  100
def parse_servo_duty(string): return parse_int_bounds(string, G2_SERVO_DUTY_MIN, G2_SERVO_DUTY_MAX)

# response for SetObjectRA and SetObjectDec
class G2Valid(Enum):
    INVALID = '0'
    VALID   = '1'

# parameter for RA_StartStop_Set
# parameter for DEC_StartStop_Set
class G2Stopped(Enum):
    STOPPED     = 0
    NOT_STOPPED = 1

# limits for signed 32-bit integer parameters
SINT32_MIN = -((1 << 31) - 0)
SINT32_MAX =  ((1 << 31) - 1)

# limits for unsigned 32-bit integer parameters
UINT32_MIN = 0
UINT32_MAX = ((1 << 32) - 1)


### Special Commands

class G2Cmd_StartupCheck(Gemini2Command_ACK):
    def response(self): return G2Rsp_StartupCheck(self)
class G2Rsp_StartupCheck(Gemini2Response_ACK):
    def interpret(self): self._status = G2StartupStatus(self.get_raw()) # raises ValueError if the response value isn't in the enum
    def get(self):       return self._status

class G2Cmd_SelectStartupMode(Gemini2Command_LX200_NoReply):
    def __init__(self, mode):
        if not isinstance(mode, G2StartupMode):
            raise G2CommandParameterTypeError('G2StartupMode')
        self._mode = mode
    def lx200_str(self): return 'b{:s}'.format(G2StartupMode[self._mode])


### Macro Commands

class G2Cmd_MacroENQ(Gemini2Command_Macro):
    def cmd_str(self):          return '\x05'
    def response(self):         return G2Rsp_MacroENQ(self)
    def valid_for_serial(self): return False # only valid on UDP backend
class G2Rsp_MacroENQ(Gemini2Response_Macro):
    def field_count(self): return 21
    def interpret(self):
        # TODO: implement some range checking on most of the numerical fields here
        # (e.g. angle ranges:  [0,180) or [-90,+90] or [0,360)  etc)
        fields = self.get_raw()
        self._values = dict()
#        self._values['phys_x']       = parse_int           (fields[ 0])  # raises G2ResponseIntegerParseError on failure
#        self._values['phys_y']       = parse_int           (fields[ 1])  # raises G2ResponseIntegerParseError on failure
        self._values['pra']          = parse_int           (fields[ 0])  # raises G2ResponseIntegerParseError on failure
        self._values['pdec']         = parse_int           (fields[ 1])  # raises G2ResponseIntegerParseError on failure
        self._values['ra']           = parse_ang_dbl       (fields[ 2])  # raises G2ResponseAngleParseError on failure
        self._values['dec']          = parse_ang_dbl       (fields[ 3])  # raises G2ResponseAngleParseError on failure
        self._values['ha']           = parse_ang_dbl       (fields[ 4])  # raises G2ResponseAngleParseError on failure
        self._values['az']           = parse_ang_dbl       (fields[ 5])  # raises G2ResponseAngleParseError on failure
        self._values['alt']          = parse_ang_dbl       (fields[ 6])  # raises G2ResponseAngleParseError on failure
        self._values['vel_max']      = G2AxisVelocity      (fields[ 7])  # raises ValueError if the response field value isn't in the enum
        self._values['vel_x']        = G2AxisVelocity      (fields[ 8])  # raises ValueError if the response field value isn't in the enum
        self._values['vel_y']        = G2AxisVelocity      (fields[ 9])  # raises ValueError if the response field value isn't in the enum
        self._values['ha_pos']       = G2AxisPosition      (fields[10])  # raises ValueError if the response field value isn't in the enum
        self._values['t_sidereal']   = parse_time_dbl      (fields[11])  # raises G2ResponseTimeParseError on failure
        self._values['park_state']   = G2ParkStatus    (int(fields[12])) # raises ValueError if the response field value isn't in the enum
        self._values['pec_state']    = G2PECStatus     (int(fields[13])) # raises ValueError if the response field value isn't in the enum
        self._values['t_wsl']        = parse_time_dbl      (fields[14])  # raises G2ResponseTimeParseError on failure
        self._values['cmd99_state']  = G2Status        (int(fields[15])) # raises ValueError if the response field value isn't in the enum
#        self._values['revisions']    = parse_revisions     (fields[16])  # raises G2ResponseRevisionsParseError on failure
#        self._values['servo_lag_x']  = parse_servo_lag     (fields[17])  # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on failure
#        self._values['servo_lag_y']  = parse_servo_lag     (fields[18])  # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on failure
#        self._values['servo_duty_x'] = parse_servo_duty    (fields[19])  # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on failure
#        self._values['servo_duty_y'] = parse_servo_duty    (fields[20])  # raises G2ResponseIntegerParseError or G2ResponseIntegerBoundsViolation on failure
    def get(self): return self._values


### Synchronization Commands

class G2Cmd_Echo(Gemini2Command_LX200):
    def __init__(self, char):
        assert sys.version_info[0] >= 3 # our string type check below is incompatible with Python 2
        if (not isinstance(char, str)) or (len(char) != 1):
            raise G2CommandParameterTypeError('char')
        self._char = char
    def lx200_str(self): return 'CE{:s}'.format(self._char)
    def response(self):  return G2Rsp_Echo(self)
class G2Rsp_Echo(Gemini2Response_LX200): pass

class G2Cmd_AlignToObject(Gemini2Command_LX200):
    def lx200_str(self): return 'Cm'
    def response(self):  return G2Rsp_AlignToObject(self)
class G2Rsp_AlignToObject(Gemini2Response_LX200):
    def interpret(self):
        assert self.get_raw() != 'No object!'

class G2Cmd_SyncToObject(Gemini2Command_LX200):
    def lx200_str(self): return 'CM'
    def response(self):  return G2Rsp_SyncToObject(self)
class G2Rsp_SyncToObject(Gemini2Response_LX200):
    def interpret(self):
        assert self.get_raw() != 'No object!'


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

class G2Cmd_SetObjectName(Gemini2Command_LX200_NoReply):
    def __init__(self, name):
        assert name != ''
        assert '#' not in name
        self._name = name
    def lx200_str(self): return 'ON{:s}'.format(self._name)


### Precession and Refraction Commands

# ...


### Precision Commands

class G2Cmd_GetPrecision(Gemini2Command_LX200):
    def lx200_str(self): return 'P'
    def response(self):  return G2Rsp_GetPrecision(self)
class G2Rsp_GetPrecision(Gemini2Response_LX200_FixedLength):
    def fixed_len(self): return 14
    def interpret(self): self._precision = G2Precision(self.get_raw()) # raises ValueError if the response value isn't in the enum
    def get(self):       return self._precision

class G2Cmd_TogglePrecision(Gemini2Command_LX200_NoReply):
    def lx200_str(self): return 'U'

class G2Cmd_SetDblPrecision(Gemini2Command_LX200_NoReply):
    def lx200_str(self): return 'u'


### Quit Motion Commands

# ...


### Rate Commands

# ...


### Set Commands

class G2Cmd_SetObjectRA(Gemini2Command_LX200):
    def __init__(self, ra):
        assert ra >= 0.0 and ra < 360.0
        _, self._hour, self._min, self._sec = ang_to_hourminsec(ra)
    def lx200_str(self): return 'Sr{:02d}:{:02d}:{:02d}'.format(self._hour, self._min, int(self._sec))
    def response(self):  return G2Rsp_SetObjectRA(self)
class G2Rsp_SetObjectRA(Gemini2Response_LX200_FixedLength):
    def fixed_len(self): return 1
    def interpret(self):
        validity = G2Valid(self.get_raw())  # raises ValueError if the response field value isn't in the enum
        assert validity == G2Valid.VALID

class G2Cmd_SetObjectDec(Gemini2Command_LX200):
    def __init__(self, dec):
        assert dec >= -90.0 and dec <= 90.0
        sign, self._deg, self._min, self._sec = ang_to_degminsec(dec)
        self._signchar = '+' if sign >= 0.0 else '-'
    def lx200_str(self): return 'Sd{:s}{:02d}:{:02d}:{:02d}'.format(self._signchar, self._deg, self._min, int(self._sec))
    def response(self):  return G2Rsp_SetObjectDec(self)
class G2Rsp_SetObjectDec(Gemini2Response_LX200_FixedLength):
    def fixed_len(self): return 1
    def interpret(self):
        validity = G2Valid(self.get_raw())  # raises ValueError if the response field value isn't in the enum
        assert validity == G2Valid.VALID
        # NOTE: only objects which are currently above the horizon are considered valid


### Site Selection Commands

# ...


### Native Commands

#class G2Cmd_TEST_Native_92_Get(Gemini2Command_Native_Get):
#    def __init__(self, val):
#        if not isinstance(val, int):
#            raise G2CommandParameterTypeError('int')
#        self._val = val
#    def native_id(self):     return 92
##    def native_params(self): return '{:d}'.format(self._val)
#    def response(self):      return None # TODO!

### Undocumented Commands

class G2CmdBase_Divisor_Set(Gemini2Command_Native_Set):
    def __init__(self, div):
        if not isinstance(div, int):
            raise G2CommandParameterTypeError('int')
        # clamp divisor into the allowable range
        if div < self._div_min(): div = self._div_min()
        if div > self._div_max(): div = self._div_max()
        self._div = div
    def native_params(self): return self._div
    def _div_min(self): return SINT32_MIN
    def _div_max(self): return SINT32_MAX
class G2Cmd_RA_Divisor_Set(G2CmdBase_Divisor_Set):
    def native_id(self): return 451
class G2Cmd_DEC_Divisor_Set(G2CmdBase_Divisor_Set):
    def native_id(self): return 452

class G2CmdBase_StartStop_Set(Gemini2Command_Native_Set):
    def __init__(self, val):
        if not isinstance(val, G2Stopped):
            raise G2CommandParameterTypeError('G2Stopped')
        self._val = val
    def native_params(self): return '{:b}'.format(self._val.value)
class G2Cmd_RA_StartStop_Set(G2CmdBase_StartStop_Set):
    def native_id(self): return 453
class G2Cmd_DEC_StartStop_Set(G2CmdBase_StartStop_Set):
    def native_id(self): return 454

# TODO: implement GET cmds 451-454


"""
class G2Cmd_Undoc451_Get(Gemini2Command_Native_Get):
    def id(self): return 451
    def response(self): G2Rsp_Undoc451_Get()
class G2Rsp_Undoc451_Get(Gemini2Response_Native):
    # TODO
    pass

class G2Cmd_Undoc451_Set(Gemini2Command_Native_Set):
    def __init__(self, divisor):
        self._divisor = divisor
    def id(self): return 451
    def param(self): return '{:+d}'.format(self._divisor)
    def response(self): G2Rsp_Undoc451_Set()
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
