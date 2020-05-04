import datetime
import time
import calendar
from multiprocessing import Process, Event, Pipe, Value
from multiprocessing.connection import Connection
import signal
from typing import Tuple, Optional
from point.gemini_backend import Gemini2Backend
from point.gemini_commands import *
from point.gemini_exceptions import *


__all__ = ['Gemini2']


# TODO: Handle UDP response timeouts appropriately
# TODO: Restore "good" documentation to the classes and functions and stuff


def clamp(val, limit):
    """Limit value to symmetric range.

    Args:
        val: Value to be adjusted.
        limit: Absolute value of return value will not be greater than this.

    Returns:
        The input value limited to the range [-limit,+limit].
    """
    return max(min(limit, val), -limit)


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
    """

    class ResponseException(Exception):
        """Raised on bad command responses from Gemini."""

    class ReadTimeoutException(Exception):
        """Raised when read from Gemini times out"""

    def __init__(
            self,
            backend: Gemini2Backend,
            rate_limit: float = 4.0,
            rate_step_limit: float = 0.5,
            accel_limit: float = 20.0,
            use_multiprocessing: bool = False,
        ):
        """Constructs a Gemini2 object.

        Note on slew rate and acceleration limts: Limits are enforced when using high-level
        commands such as slew() and stop_motion(). Low-level commands that set the divisors do not
        respect limits. Acceleration and slew step size limits also depend on memory of the most
        recently commanded rates which are cached in this object. If the rates are changed by
        low-level commands or by means other than calls to slew() or stop_motion() these limits
        will not function as intended.

        Args:
            backend: This can be a Gemini2BackendSerial instance (if using USB serial) or a
                Gemini2BackendUDP instance (if using UDP datagrams).
            max_rate: Maximum allowed slew rate in degrees per second. May be set to None to
                disable enforcement (not recommended).
            rate_step_limit: Maximum allowed change in slew rate per call to slew() in degrees per
                second. May be set to None to disable enforcement (not recommended).
            accel_limit: Acceleration limit in degrees per second squared. May be set to None to
                disable enforcement (not recommended).
            use_multiprocessing: When True, two processes are started that send slew rate commands
                to the mount asynchronously such that the mount can accelerate and decelerate
                smoothly without the user needing to call `slew()` repeatedly until a target rate
                is achieved. When False, each call to `slew()` sends exactly one slew rate command
                to the mount synchronously and no additional processes are created.
        """
        self._backend = backend
        self._rate_limit = rate_limit
        self._rate_step_limit = rate_step_limit
        self._accel_limit = accel_limit
        self._use_multiprocessing = use_multiprocessing
        self.set_double_precision()

        if use_multiprocessing:
            self._slew_rate_processes = {}
            self._slew_rate_target = {}
            self._div_last_commanded = {}
            self._axis_safe_event = {}
            for axis in ['ra', 'dec']:
                self._axis_safe_event[axis] = Event()
                rate_target_pipe_recv, rate_target_pipe_send = Pipe(duplex=False)
                self._div_last_commanded[axis] = Value('l', 0)
                self._slew_rate_target[axis] = rate_target_pipe_send
                self._slew_rate_processes[axis] = Process(
                    target=self._slew_rate_process,
                    name='Gemini ' + axis.upper() + ' slew rate thread',
                    args=(
                        axis,
                        rate_target_pipe_recv,
                        self._axis_safe_event[axis],
                        self._div_last_commanded[axis],
                    ),
                )
                self._slew_rate_processes[axis].start()
        else:
            now = time.perf_counter()
            self._div_last_commanded = {'ra': 0, 'dec': 0}
            self._time_last_commanded = {'ra': now, 'dec': now}

    def __del__(self):
        """Shuts down both slew rate command processes."""
        if self._use_multiprocessing:
            for axis in ['ra', 'dec']:
                if self._slew_rate_processes[axis].is_alive():
                    # informs slew command process to bring rates to zero and then quit
                    self._slew_rate_target[axis].send(None)

            for axis in ['ra', 'dec']:
                self._slew_rate_processes[axis].join()
        else:
            self.stop_motion()

    def exec_cmd(self, cmd):
        return self._backend.execute_one_command(cmd)

    def exec_cmds(self, *cmds):
        return self._backend.execute_multiple_commands(*cmds)


    ## Commands
    # All commands in the following sections are placed in the same order as
    # they appear in the serial command reference page:
    # http://www.gemini-2.com/web/L5V2_1serial.html


    ### Special Commands

    def startup_check(self):
        """Check startup state and type of mount."""
        return self.exec_cmd(G2Cmd_StartupCheck()).get()

    def select_startup_mode(self, mode):
        self.exec_cmd(G2Cmd_SelectStartupMode(mode))


    ### Macro Commands

    def enq_macro(self):
        return self.exec_cmd(G2Cmd_MacroENQ()).get()


    ### Synchronization Commands

    def echo(self, char):
        """Test command. Should return the same character as the argument."""
        return self.exec_cmd(G2Cmd_Echo(char)).get()

    def align_to_object(self):
        """Add selected object to pointing model."""
        return self.exec_cmd(G2Cmd_AlignToObject()).get()

    def sync_to_object(self):
        """Synchronize to selected object."""
        return self.exec_cmd(G2Cmd_SyncToObject()).get()

    # TODO: reimplement this
#    def select_pointing_model(self, num):
#        """Select a pointing model (0 or 1)."""
#        return int(self.lx200_cmd('C' + chr(num), expect_reply=True))

    # TODO: reimplement this
#    def select_pointing_model_for_io(self):
#        """Selects the active pointing model for I/O access."""
#        return int(self.lx200_cmd('Cc', expect_reply=True))

    # TODO: reimplement this
#    def get_pointing_model(self):
#        """Get number of active pointing model (0 or 1)."""
#        return int(self.lx200_cmd('C?', expect_reply=True))

    # TODO: reimplement this
#    def init_align(self):
#        """Perform Initial Align with selected object."""
#        return self.lx200_cmd('CI', expect_reply=True)

    # TODO: reimplement this
#    def reset_model(self):
#        """Resets the currently selected model."""
#        return int(self.lx200_cmd('CR', expect_reply=True))

    # TODO: reimplement this
#    def reset_last_align(self):
#        """Resets the last alignment of currently selected model."""
#        return int(self.lx200_cmd('CU', expect_reply=True))


    ### Focus Control Commands

    # TODO: reimplement this
#    def focus_in(self):
#        self.lx200_cmd('F+')

    # TODO: reimplement this
#    def focus_out(self):
#        self.lx200_cmd('F-')

    # TODO: reimplement this
#    def focus_stop(self):
#        self.lx200_cmd('FQ')

    # TODO: reimplement this
#    def focus_fast(self):
#        self.lx200_cmd('FF')

    # TODO: reimplement this
#    def focus_medium(self):
#        self.lx200_cmd('FM')

    # TODO: reimplement this
#    def focus_slow(self):
#        self.lx200_cmd('FS')


    ### Get Information Commands

    # TODO: reimplement this
#    def get_alt(self):
#        """Altitude in signed degrees format [-90.0, +90.0]."""
#        return float(self.lx200_cmd('GA', expect_reply=True))

    # TODO: reimplement this
#    def get_led_brightness(self):
#        return int(self.lx200_cmd('GB', expect_reply=True))

    # TODO: reimplement this
#    def get_local_date(self):
#        """Date as a string in mm/dd/yy format."""
#        return self.lx200_cmd('GC', expect_reply=True)

    # TODO: reimplement this
#    def get_clock_format(self):
#        return self.lx200_cmd('Gc', expect_reply=True)

    # TODO: reimplement this
#    def get_dec(self):
#        """Apparent declination in signed degrees [-90.0,+90.0]."""
#        return float(self.lx200_cmd('GD', expect_reply=True))

    # TODO: reimplement this
#    def get_obj_dec(self):
#        """Selected object's declination in signed degrees."""
#        return float(self.lx200_cmd('Gd', expect_reply=True))

    # TODO: reimplement this
#    def get_alarm_time(self):
#        return self.lx200_cmd('GE', expect_reply=True)

    # TODO: reimplement this
#    def get_utc_offset(self):
#        return self.lx200_cmd('GG', expect_reply=True)

    # TODO: reimplement this
#    def get_site_lon(self):
#        return float(self.lx200_cmd('Gg', expect_reply=True))

    # TODO: reimplement this
#    def get_hour_angle(self):
#        """Hour angle in signed degrees."""
#        return float(self.lx200_cmd('GH', expect_reply=True))

    # TODO: reimplement this
#    def get_info_buffer(self):
#        return self.lx200_cmd('GI', expect_reply=True)

    # TODO: reimplement this
#    def get_local_time(self):
#        """Local time in hours as a float."""
#
#        # For some reason time is not very precise in double precision. It's
#        # worse than one second. High precision format has better resolution.
#        return float(self.lx200_cmd('GL', expect_reply=True))

    # TODO: reimplement this
#    def get_meridian_side(self):
#        """Returns 'E' or 'W' to indicate side of meridian."""
#        return self.lx200_cmd('Gm', expect_reply=True)

    # TODO: reimplement this
#    def get_site_name(self, site_num=0):
#        site_letters = ['M', 'N', 'O', 'P']
#        return self.lx200_cmd('G' + site_letters[site_num], expect_reply=True)

    # TODO: reimplement this
#    def get_ra(self):
#        """Apparent right ascension in hours [0.0,24.0)."""
#        return float(self.lx200_cmd('GR', expect_reply=True))

    # TODO: reimplement this
#    def get_obj_ra(self):
#        """Selected object's right ascension in signed degrees."""
#        return float(self.lx200_cmd('Gr', expect_reply=True))

    # TODO: reimplement this
#    def get_sidereal_time(self):
#        return float(self.lx200_cmd('GS', expect_reply=True))

    # TODO: reimplement this
#    def get_site_lat(self):
#        return float(self.lx200_cmd('Gt', expect_reply=True))

    # Omitting command 'GV' which is redundant with 'GVN'.

    # TODO: reimplement this
#    def get_software_build_date(self):
#        return self.lx200_cmd('GVD', expect_reply=True)

    # TODO: reimplement this
#    def get_software_level(self):
#        return self.lx200_cmd('GVN', expect_reply=True)

    # TODO: reimplement this
#    def get_product_string(self):
#        return self.lx200_cmd('GVP', expect_reply=True)

    # TODO: reimplement this
#    def get_software_build_time(self):
#        return self.lx200_cmd('GVT', expect_reply=True)

    # TODO: reimplement this
#    def get_max_velocity(self):
#        """Maximum velocity of both axes."""
#        return self.lx200_cmd('Gv', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity_ra(self):
#        return self.lx200_cmd('GW', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity_dec(self):
#        return self.lx200_cmd('Gw', expect_reply=True, reply_len=1)

    # TODO: reimplement this
#    def get_velocity(self):
#        """Velocity of both axes: RA, DEC (2 characters)."""
#        return self.lx200_cmd('Gu', expect_reply=True, reply_len=2)

    # TODO: reimplement this
#    def get_az(self):
#        """Azimuth in signed degrees format [0.0, 360.0)."""
#        return float(self.lx200_cmd('GZ', expect_reply=True))


    ### Park Commands

    # TODO: reimplement this
#    def park_home(self):
#        self.lx200_cmd('hP')

    # TODO: reimplement this
#    def park_startup(self):
#        self.lx200_cmd('hC')

    # TODO: reimplement this
#    def park_zenith(self):
#        self.lx200_cmd('hZ')

    # TODO: reimplement this
#    def sleep(self):
#        self.lx200_cmd('hN')

    # TODO: reimplement this
#    def wake(self):
#        self.lx200_cmd('hW')


    ### Move Commands

    # TODO: reimplement this
#    def goto_object_horiz(self):
#        """Goto object selected with horizontal coordinates."""
#        return self.lx200_cmd('MA', expect_reply=True)

    # TODO: reimplement this
#    def search_pattern(self, arcmins):
#        """Move at find speed in a meander search pattern."""
#        self.lx200_cmd('MF' + str(arcmins), expect_reply=True)

    # TODO: reimplement this
#    def move_lock(self):
#        self.lx200_cmd('ML', expect_reply=True)

    # TODO: reimplement this
#    def move_unlock(self):
#        self.lx200_cmd('Ml', expect_reply=True)

    # TODO: reimplement this
#    def meridian_flip(self):
#        return self.lx200_cmd('Mf', expect_reply=True)

    # TODO: reimplement this
#    def goto_object(self, allow_meridian_flip=False):
#        """Goto object selected from database or equatorial coordinates."""
#        cmd = 'MM' if allow_meridian_flip else 'MS'
#        return lx200_cmd(cmd, expect_reply=True)

    # TODO: reimplement this
#    def move(self, direction):
#        """Move in a direction: 'east', 'west', 'north', or 'south'."""
#        if direction not in ['east', 'west', 'north', 'south']:
#            raise ValueError('invalid direction for move command') # TODO: consider using an exception derived from Gemini2Exception!
#        self.lx200_cmd('M' + direction[0])

    # TODO: reimplement this
#    def move_ticks(self, ra_steps, dec_steps):
#        self.lx200_cmd('mi' + str(ra_steps) + ';' + str(dec_steps))

    # TODO: reimplement this
#    def set_step_multiplier(self, multiplier):
#        self.lx200_cmd('mm' + str(multiplier))


    ### Precision Guiding Commands


    ### Object/Observing/Output Commands

    def set_object_name(self, name):
        self.exec_cmd(G2Cmd_SetObjectName(name))


    ### Precession and Refraction Commands


    ### Precision Commands

    def get_precision(self):
        return self.exec_cmd(G2Cmd_GetPrecision()).get()

    def toggle_precision(self):
        self.exec_cmd(G2Cmd_TogglePrecision())

    def set_double_precision(self):
        self.exec_cmd(G2Cmd_SetDblPrecision())


    ### Quit Motion Commands


    ### Rate Commands


    ### Set Commands

    def set_object_ra(self, ra):
        self.exec_cmd(G2Cmd_SetObjectRA(ra))

    def set_object_dec(self, dec):
        self.exec_cmd(G2Cmd_SetObjectDec(dec))

    def set_site_longitude(self, lon):
        self.exec_cmd(G2Cmd_SetSiteLongitude(lon))

    def set_site_latitude(self, lat):
        self.exec_cmd(G2Cmd_SetSiteLatitude(lat))


    ### Site Selection Commands

    def set_stored_site(self, site):
        self.exec_cmd(G2Cmd_SetStoredSite(site))

    def get_stored_site(self):
        return self.exec_cmd(G2Cmd_GetStoredSite()).get()


    ### Native Commands

    def set_pec_boot_playback(self, enable):
        self.exec_cmd(G2Cmd_PECBootPlayback_Set(enable))

    def get_pec_boot_playback(self):
        return self.exec_cmd(G2Cmd_PECBootPlayback_Get()).get()

    def set_pec_status(self, status):
        """See G2PECStatus in gemini_commands.py for the possible status values."""
        self.exec_cmd(G2Cmd_PECStatus_Set(status))

    def get_pec_status(self):
        """See G2PECStatus in gemini_commands.py for the possible status values."""
        return self.exec_cmd(G2Cmd_PECStatus_Get()).get()

    def set_pec_replay(self, enable):
        if enable:
            self.exec_cmd(G2Cmd_PECReplayOn_Set())
        else:
            self.exec_cmd(G2Cmd_PECReplayOff_Set())

    def set_ntp_server_addr(self, addr):
        if isinstance(addr, str):
            addr = ipaddress.IPv4Address(addr)
        self.exec_cmd(G2Cmd_NTPServerAddr_Set(addr))

    def get_ntp_server_addr(self):
        return self.exec_cmd(G2Cmd_NTPServerAddr_Get()).get()


    ### Undocumented Commands

    def set_ra_divisor(self, div):
        self.exec_cmd(G2Cmd_RA_Divisor_Set(div))

    def set_dec_divisor(self, div):
        self.exec_cmd(G2Cmd_DEC_Divisor_Set(div))

    def ra_start_movement(self):
        self.exec_cmd(G2Cmd_RA_StartStop_Set(G2Stopped.NOT_STOPPED))
    def ra_stop_movement(self):
        self.exec_cmd(G2Cmd_RA_StartStop_Set(G2Stopped.STOPPED))

    def dec_start_movement(self):
        self.exec_cmd(G2Cmd_DEC_StartStop_Set(G2Stopped.NOT_STOPPED))
    def dec_stop_movement(self):
        self.exec_cmd(G2Cmd_DEC_StartStop_Set(G2Stopped.STOPPED))












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

    def set_user_object_equatorial(self, ra, dec, name=''):
        self.set_object_ra(ra)
        if name != '':
            self.set_object_name(name)
        self.set_object_dec(dec)

    def slew(self, axis: str, rate: float) -> Tuple[float, bool]:
        """Set slew rate for one mount axis.

        This slew command allows changes to the slew rate on the fly, in contrast to move commands
        which do not.

        When multiprocessing is enabled the actual commands to the mount are sent rapidly in a
        separate process until the desired rate is achieved to allow for enforcement of
        acceleration limits while providing smooth acceleration. In multiprocessing mode this
        method does not block, so the desired rate may not be achieved until some time after this
        method returns.

        When multiprocessing is disabled this method is blocking and will not return until the
        command to the mount has been sent. For all but the smallest rate changes acceleration
        limits will likely prevent achieving the desired slew rate in a single call so multiple
        calls may be required until the desired rate is achieved.

        Args:
            axis: Axis to which this applies, 'ra' or 'dec'.
            rate: Slew rate target in degrees per second. When multiprocessing is enabled the mount
                will accelerate until this rate is achieved as long as the rate does not exceed the
                rate limit. When multiprocessing is disabled this method will send a slew rate
                command that is as close as possible to this value subject to acceleration and
                rate step limits. For the RA axis, positive values move east, toward increasing
                right ascension.

        Returns:
            A tuple containing the actual slew rate target and a bool indicating whether the slew
            rate limit was exceeded. The actual slew rate may differ slightly from the desired rate
            due to quantization error in the divisor setting or limits that were enforced.
        """

        if axis not in ['ra', 'dec']:
            raise ValueError("axis must be 'ra' or 'dec'")

        limits_exceeded = False

        # enforce slew rate limit if limit is enabled
        if self._rate_limit is not None:
            if abs(rate) > self._rate_limit:
                limits_exceeded = True
                rate = clamp(rate, self._rate_limit)

        if self._use_multiprocessing:
            # quantize the rate and send to the process
            rate = self.div_to_slew_rate(self.slew_rate_to_div(rate))
            self._slew_rate_target[axis].send(rate)
        else:
            rate, additional_limits_exceeded = self._slew_rate_single(axis, rate)
            limits_exceeded |= additional_limits_exceeded

        return rate, limits_exceeded


    def get_slew_rate(self, axis: str) -> float:
        """Get current slew rate for a mount axis.

        This method gets the current slew rate for one mount axis. The slew rate cannot be queried
        from the mount directly, so the implementation returns the cached value from the last
        slew rate divisor commands that were sent to the mount.

        Args:
            axis: Axis to which this applies, 'ra' or 'dec'.

        Returns:
            The current slew rate of the mount axis in degrees per second.
        """
        if self._use_multiprocessing == True:
            div = self._div_last_commanded[axis].value
        else:
            div = self._div_last_commanded[axis]
        return self.div_to_slew_rate(div)


    def _slew_rate_single(self, axis: str, rate_desired: float) -> Tuple[float, bool]:
        """Send a single slew-rate command to the specified axis.

        This method is used when multiprocessing is disabled.

        Args:
            axis: 'ra' or 'dec'
            rate_desired: The slew rate to set in degrees per second. Actual rate commanded may
                differ if limits are enforced.

        Returns:
            The actual rate commanded.
        """
        time_current = time.perf_counter()
        rate_last_commanded = self.div_to_slew_rate(self._div_last_commanded[axis])
        rate_to_command = self._apply_rate_accel_limit(
            rate_desired,
            time_current,
            rate_last_commanded,
            self._time_last_commanded[axis]
        )
        rate_to_command = self._apply_rate_step_limit(rate_to_command, rate_last_commanded)
        div = self.slew_rate_to_div(rate_to_command)
        self._set_divisor(axis, div, self._div_last_commanded[axis])
        self._div_last_commanded[axis] = div
        self._time_last_commanded[axis] = time_current
        return self.div_to_slew_rate(div), rate_to_command != rate_desired


    def _slew_rate_process(
            self,
            axis: str,
            rate_target_pipe: Connection,
            axis_safe_event: Event,
            div_last_commanded_shared: Value,
        ):
        """Process for sending slew rate commands continuously until a target rate is achieved.

        This process helps the mount to accelerate smoothly, since this requires sending commands
        to the mount computer in rapid succession. Acceleration and slew rate step limits are
        enforced here. Commands are sent to the mount until the desired target slew rate is
        achieved, and then it will wait for a new rate target before sending further commands.

        Args:
            axis: The mount axis to be controlled by this process (one process per axis).
            rate_target_pipe: The receiving end connection to a multiprocessing pipe over which
                slew rate target values are sent. Rates are in degrees per second.
            axis_safe_event: When the axis is safed, meaning that motion is stopped, this event
                will be set. Otherwise, it will be cleared.
            div_last_commanded_shared: Shared memory storing the divisor value most recently
                commanded for this mount axis.
        """

        # Ignore SIGINT in this process (will be handled in main process)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # Last commanded rate is cached along with the time of last command to enforce acceleration
        # limit. Keep local copy of last commanded divisor to avoid accessing shared memory more
        # than necessary.
        axis_safe_event.set()
        div_target = 0
        div_last_commanded = div_last_commanded_shared.value
        time_last_commanded = time.perf_counter() - 1e-3
        shutdown = False

        while True:
            if shutdown == True:
                if div_last_commanded == 0:
                    return
            # only try to receive from the pipe if a new rate target is waiting or if the last-
            # received rate target has been achieved, in which case we want to block
            elif rate_target_pipe.poll() or div_last_commanded == div_target:
                rate_target = rate_target_pipe.recv()
                # None is a special value indicating that it is time to shut down this process
                if rate_target is None:
                    div_target = 0
                    shutdown = True
                else:
                    div_target = self.slew_rate_to_div(rate_target)
                    if div_target == div_last_commanded:
                        continue

            time_current = time.perf_counter()

            # may not be able to achieve div_target if it exceeds rate accel or step limits
            rate_target = self.div_to_slew_rate(div_target)
            rate_last_commanded = self.div_to_slew_rate(div_last_commanded)

            rate_to_command = self._apply_rate_accel_limit(
                rate_target,
                time_current,
                rate_last_commanded,
                time_last_commanded
            )
            rate_to_command = self._apply_rate_step_limit(rate_to_command, rate_last_commanded)

            div = self.slew_rate_to_div(rate_to_command)

            # Clear this event before sending the actual commands since the state of the mount
            # is about to change and because if the commands fail for some reason the state of
            # the mount will be unknown and cannot be assumed to be safe.
            if div != 0:
                axis_safe_event.clear()

            try:
                self._set_divisor(axis, div, div_last_commanded)
            except Gemini2Exception as e:
                # dangerous to give up because this thread is critical for stopping mount motion
                # safely; better to keep trying to send commands to the bitter end
                print(f'Ignoring exception in {axis} slew rate command thread: {str(e)}')
                continue

            div_last_commanded_shared.value = div
            div_last_commanded = div
            time_last_commanded = time_current

            if div_last_commanded == 0:
                axis_safe_event.set()


    def _apply_rate_accel_limit(
            self,
            rate_desired: float,
            time_current: float,
            rate_last_commanded: float,
            time_last_commanded: float
        ) -> float:
        """Apply the slew acceleration limit to the desired rate, if enabled.

        Note that the acceleration limit is only effective if slew rate commands are sent to the
        mount at a fairly fast and steady rate (~10 Hz or higher).

        Args:
            rate_desired: The desired slew rate in degrees per second.
            time_current: The time of the current command as a Unix timestamp.
            rate_last_commanded: The slew rate that was commanded most recently.
            time_last_commanded: The time the last commanded slew rate was sent as a Unix
                timestamp.

        Returns:
            A slew rate that does not exceed the acceleration limit. If the rate_desired is already
            within this limit, or if the limit is disabled, rate_desired is returned unmodified.
            Otherwise the closest rate that complies with the limit is returned.
        """
        if self._accel_limit is None:
            return rate_desired

        time_since_last = time_current - time_last_commanded
        rate_change_desired = rate_desired - rate_last_commanded
        if abs(rate_change_desired) / time_since_last > self._accel_limit:
            rate_change_clamped = clamp(rate_change_desired, self._accel_limit * time_since_last)
            return rate_last_commanded + rate_change_clamped

        return rate_desired


    def _apply_rate_step_limit(self, rate_desired: float, rate_last_commanded: float) -> float:
        """Apply the slew rate step limit to the desired rate, if enabled.

        Args:
            rate_desired: The desired slew rate in degrees per second.
            rate_last_commanded: The slew rate that was commanded most recently.

        Returns:
            A slew rate that is within the rate step limit of the last commanded rate. If the
            rate_desired is already within this limit, or if the limit is disabled, rate_desired
            is returned unmodified. Otherwise the closest rate that complies with the limit is
            returned.
        """
        if self._rate_step_limit is None:
            return rate_desired

        rate_change_desired = rate_desired - rate_last_commanded
        if abs(rate_change_desired) > self._rate_step_limit:
            rate_change_clamped = clamp(rate_change_desired, self._rate_step_limit)
            return rate_last_commanded + rate_change_clamped

        return rate_desired


    def _set_divisor(self, axis: str, div: int, div_last_commanded: Optional[int] = None):
        """Set the divisor value for one mount axis to control slew rate.

        For the RA axis this also handles sending the stop/start movement commands if needed.

        Args:
            axis: 'ra' or 'dec'
            div: Divisor value to set
            div_last_commanded: For RA axis, this is used to avoid sending stop/start movement
                commands if they are not necessary.
        """
        if axis == 'ra':
            # Must use the start and stop movement commands on the RA axis because achieving zero
            # motion when slew() is called repeatedly with a rate of zero can't be accomplished
            # using set_ra_divisor alone.
            if div == 0 and (div_last_commanded is None or div_last_commanded != 0):
                self.ra_stop_movement()
            elif div != 0 and (div_last_commanded is None or div_last_commanded == 0):
                self.ra_start_movement()

            # Only set the RA divisor to non-zero values. Setting the RA divisor to 0 will cause
            # that axis to advance by exactly one servo step per command which is not the desired
            # action.
            if div != 0:
                # the divisor is negated here to reverse the direction
                self.set_ra_divisor(-div)
        else:
            self.set_dec_divisor(div)


    def slew_rate_to_div(self, rate: float) -> int:
        """Convert a slew rate to divisor setting.

        Args:
            rate: Slew rate in degrees per second.

        Returns:
            Divisor setting that is as close to the desired slew rate as possible.
        """
        if rate == 0.0:
            return 0
        # TODO: Replace hard-coded constants with values read from Gemini in constructor
        return int(12e6 / (6400.0 * rate))


    def div_to_slew_rate(self, div: int) -> float:
        """Convert a divisor setting to corresponding slew rate.

        Args:
            div: Divisor setting.

        Returns:
            The corresponding slew rate in degrees per second.
        """
        if div == 0:
            return 0.0
        # TODO: Replace hard-coded constants with values read from Gemini in constructor
        return 12e6 / (6400.0 * div)


    def stop_motion(self):
        """Stops motion on both axes.

        Stops motion on both axes. Blocks until slew rates have reached zero, which may take some
        time depending on the slew rates at the time this is invoked and acceleration limits.

        There is a possibility of a race condition here with multiprocessing enabled due to nuances
        of multiprocess communication. If the "safe" events are already set when this is called,
        but the process is just about to send commands to a non-zero slew rate (from previous calls
        to slew() that are sitting in the pipe), this method could return immediately even though
        the mount is about to be (briefly) in motion. However this edge case is expected to be
        relatively unlikely to happen in practice.
        """
        if self._use_multiprocessing == True:
            self.slew('ra', 0.0)
            self.slew('dec', 0.0)
            self._axis_safe_event['ra'].wait()
            self._axis_safe_event['dec'].wait()
        else:
            while True:
                try:
                    (actual_rate_ra, limits_exceeded) = self.slew('ra', 0.0)
                    (actual_rate_dec, limits_exceeded) = self.slew('dec', 0.0)
                except Gemini2Exception as e:
                    # dangerous to give up because this is critical for stopping mount motion
                    # safely; better to keep trying to send commands to the bitter end
                    print(f'Ignoring exception in stop_motion: {str(e)}')
                    continue
                if actual_rate_ra == 0.0 and actual_rate_dec == 0.0:
                    return
