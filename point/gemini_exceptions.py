"""Gemini2 Exception Inheritance Tree

Gemini2Exception
  G2BackendException
     G2BackendCommandNotSupportedError
     G2BackendFeatureNotSupportedError
     G2BackendFeatureNotImplementedYetError
     G2BackendCommandError
     G2BackendResponseError
     G2BackendReadTimeoutError
  G2CommandException
     G2CommandParameterError
        G2CommandParameterValueError
        G2CommandParameterTypeError
     G2CommandBadCharacterError
  G2ResponseException
     G2ResponseDecodeError
        G2ResponseTooShortError
        G2ResponseMissingTerminatorError
        G2ResponseTooFewDelimitersError
        G2ResponseChecksumMismatchError
     G2ResponseParseError
        G2ResponseIntegerParseError
        G2ResponseAngleParseError
        G2ResponseTimeParseError
        G2ResponseRevisionsParseError
        G2ResponseIPv4AddressParseError
     G2ResponseBoundsViolation
        G2ResponseIntegerBoundsViolation
     G2ResponseInterpretationFailure
"""


class Gemini2Exception(Exception):
    """Base class for ALL exceptions that may be raised by ANY Gemini2 code."""


class G2BackendException(Gemini2Exception):
    """Base class for exceptions raised by the Gemini2 serial or UDP backend code."""


class G2CommandException(Gemini2Exception):
    """Base class for exceptions raised when processing Gemini2 commands."""


class G2ResponseException(Gemini2Exception):
    """Base class for exceptions raised when processing Gemini2 responses."""


class G2BackendCommandNotSupportedError(G2BackendException):
    """Raised when a command is not supported."""


class G2BackendFeatureNotSupportedError(G2BackendException):
    """Raised when a feature is not supported."""


class G2BackendFeatureNotImplementedYetError(G2BackendException):
    """Raised when a feature is not implemented yet, but might be in the future."""


class G2BackendCommandError(G2BackendException):
    """Raised when a command error is encountered in the backend."""


class G2BackendResponseError(G2BackendException):
    """Raised when a response error is encountered in the backend."""


class G2BackendReadTimeoutError(G2BackendException):
    """Raised when a read operation times out."""


class G2CommandParameterError(G2CommandException):
    """These are raised when a Gemini2 command is created with invalid parameters."""


class G2CommandParameterValueError(G2CommandParameterError):
    """Raised when values of command parameters do not match expectations."""


class G2CommandParameterTypeError(G2CommandParameterError):
    """Raised when the types of command parameters do not match expectations."""

    def __init__(self, *types):
        if len(types) == 1:
            super().__init__(f'Command expects 1 parameter with type {types[0]:s}.')
        else:
            super().__init__(
                f'Command expects {len(types)} parameters with types: '
                f'{", ".join(types)}.'
            )


class G2CommandBadCharacterError(G2CommandException):
    """Raised when a Gemini2 constructed command string contains reserved characters."""


class G2ResponseDecodeError(G2ResponseException):
    """These are raised when a Gemini2 response cannot be decoded properly."""


class G2ResponseTooShortError(G2ResponseDecodeError):
    """Raised when a fixed-length response has fewer characters than expected."""

    def __init__(self, buf_len, expected):
        super().__init__(
            f'Response too short: length <= {buf_len}, expected {expected}.'
        )


class G2ResponseMissingTerminatorError(G2ResponseDecodeError):
    """Raised when a hash-terminated response is presented with no '#' character."""

    def __init__(self, buf_len: int):
        super().__init__(
            f"Response with length <= {buf_len} not terminated with a '#' character."
        )


class G2ResponseTooFewDelimitersError(G2ResponseDecodeError):
    """Raised when a semicolon-delimited response has fewer semicolons than expected."""

    def __init__(self, buf_len: int, actual: int, expected: int):
        super().__init__(
            f'Response contains too few delimiters: length <= {buf_len}; '
            f'{actual} fields, expected {expected}.'
        )


class G2ResponseChecksumMismatchError(G2ResponseDecodeError):
    """Raised when a native response has a checksum mismatch."""

    def __init__(self, actual: int, expected: int):
        super().__init__(
            f'Checksum mismatch in response to native command: {actual:02x}, '
            f'expected {expected:02x}.'
        )


class G2ResponseParseError(G2ResponseException):
    """These are raised when a Gemini2 response cannot be parsed properly."""


class G2ResponseIntegerParseError(G2ResponseParseError):
    """Raised when a response cannot be parsed as an integer."""

    def __init__(self, string: str):
        super().__init__(f'Failed to parse "{string}" as integer')


class G2ResponseAngleParseError(G2ResponseParseError):
    """Raised when a response cannot be parsed as an angle."""

    def __init__(self, string: str, precision: str):
        super().__init__(
            f'Failed to parse "{string}" as angle ({precision} precision).'
        )


class G2ResponseTimeParseError(G2ResponseParseError):
    """Raised when a response cannot be parsed as a time value."""

    def __init__(self, string: str, precision: str):
        super().__init__(f'Failed to parse "{string}" as time ({precision} precision).')


class G2ResponseRevisionsParseError(G2ResponseParseError):
    """Raised when a response cannot be parsed as an 8-character revision."""

    def __init__(self, string: str):
        super().__init__(
            f'Failed to parse "{string}" as G2 native command #97 eight-character '
            'revisions parameter.'
        )


class G2ResponseIPv4AddressParseError(G2ResponseParseError):
    """Raised when a response cannot be parsed as an IPv4 address."""

    def __init__(self, string: str):
        super().__init__(f'Failed to parse \'{string}\' as IPv4 address.')


class G2ResponseBoundsViolation(G2ResponseException):
    """Raised when a response contains a value which exceeds allowable bounds."""


class G2ResponseIntegerBoundsViolation(G2ResponseBoundsViolation):
    """Raised when an integer response value is out of bounds."""

    def __init__(self, val: int, bound_min: int, bound_max: int):
        super().__init__(
            f'Successfully-parsed integer {val} violates its prescribed bounds: '
            f'[{bound_min}, {bound_max}].'
        )


class G2ResponseInterpretationFailure(G2ResponseException):
    """Raised when a Gemini2 response cannot be interpreted properly."""
