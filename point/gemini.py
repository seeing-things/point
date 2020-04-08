import datetime
import time
import calendar
import multiprocessing
import signal
from typing import Tuple
import point.gemini_backend
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

    def __init__(self, backend, rate_limit=3.0, rate_step_limit=0.25, accel_limit=10.0):
        """Constructs a Gemini2 object.

        Note on slew rate and acceleration limts: Limits are enforced when using high-level
        commands such as slew() and stop_motion(). Low-level commands that set the divisors do not
        respect limits. Acceleration and slew step size limits also depend on memory of the most
        recently commanded rates which are cached in this object. If the rates are changed by
        low-level commands or by means other than calls to slew() or stop_motion() these limits
        will not function as intended.

        Args:
            backend: A Gemini2Backend object. This can be a Gemini2BackendSerial
                instance (if using USB serial) or a Gemini2BackendUDP instance
                (if using UDP datagrams).
            max_rate: Maximum allowed slew rate in degrees per second. May be
                set to None to disable enforcement (not recommended).
            rate_step_limit: Maximum allowed change in slew rate per call to
                slew() in degrees per second. May be set to None to disable
                enforcement (not recommended).
            accel_limit: Acceleration limit in degrees per second squared. May
                be set to None to disable enforcement (not recommended).
        """
        self._backend = backend
        self._rate_limit = rate_limit
        self._rate_step_limit = rate_step_limit
        self._accel_limit = accel_limit
        self.set_double_precision()

        self._slew_rate_target = {
            'ra': multiprocessing.Value('f', 0.0),
            'dec': multiprocessing.Value('f', 0.0),
        }
        self._stop_motion = multiprocessing.Event()
        self._slew_rate_event = {
            'ra': multiprocessing.Event(),
            'dec': multiprocessing.Event(),
        }
        self._slew_rate_threads = {
            'ra': multiprocessing.Process(
                target=self._slew_rate_thread,
                name='Gemini RA slew rate thread',
                args=('ra',)),
            'dec': multiprocessing.Process(
                target=self._slew_rate_thread,
                name='Gemini DEC slew rate thread',
                args=('dec',)),
        }
        self._slew_rate_threads['ra'].start()
        self._slew_rate_threads['dec'].start()

    def __del__(self):
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
        which do not. To allow for enforcement of acceleration limits while providing smooth
        acceleration, the actual commands to the mount are sent rapidly in a separate thread until
        the desired rate is achieved. This method does not block, so the desired rate is not
        guaranteed to be achieved before it returns.

        Args:
            axis: Axis to which this applies, 'ra' or 'dec'.
            rate: Slew rate in degrees per second. For the RA axis, positive values move east,
                toward increasing right ascension.

        Returns:
            A tuple containing the actual slew rate target and a bool indicating whether the slew
            rate limit was exceeded. The actual slew rate target may differ slightly from the
            desired rate due to quantization error in the divisor setting.
        """

        if axis not in ['ra', 'dec']:
            raise ValueError("axis must be 'ra' or 'dec'")


        limits_exceeded = False

        # enforce slew rate limit if limit is enabled
        if self._rate_limit is not None:
            if abs(rate) > self._rate_limit:
                limits_exceeded = True
                rate = clamp(rate, self._rate_limit)

        # TODO: maybe change this to raise an exception rather than return a bool
        # raise ValueError(f'{rate:.2f} deg/s exceeds {self._rate_limit:.2f} deg/s limit')

        # quantize the rate
        rate = self.div_to_slew_rate(self.slew_rate_to_div(rate))

        self._slew_rate_target[axis].value = rate
        self._slew_rate_event[axis].set()

        return rate, limits_exceeded


    def _slew_rate_thread(self, axis: str):
        """Thread for sending slew rate commands continuously until a target rate is achieved.

        This thread helps the mount to accelerate smoothly, since this requires sending commands
        to the mount computer in rapid succession. Acceleration and slew rate step limits are
        enforced here. Commands are sent to the mount until the desired target slew rate is
        achieved, and then it will wait for an event to signal that a new target has been set.

        Args:
            axis: The mount axis to be controlled by this thread (one thread per axis).
        """

        # Ignore SIGINT in this process (will be handled in main process)
        signal.signal(signal.SIGINT, signal.SIG_IGN)

        # TODO: Read initial slew rate from Gemini rather than assuming it is zero
        # Commanded rate is cached along with the time of last command to enforce acceleration
        # limit
        last_commanded_rate = 0.0
        last_command_time = time.time() - 1e-3

        while True:
            if self._stop_motion.is_set():
                rate_desired = 0.0
            else:
                rate_desired = self._slew_rate_target[axis].value

            current_time = time.time()
            time_since_last = current_time - last_command_time

            # enforce acceleration limit if limit is enabled
            if self._accel_limit is not None:
                rate_change = rate_desired - last_commanded_rate
                if abs(rate_change) / time_since_last > self._accel_limit:
                    clamped_rate_change = clamp(rate_change, self._accel_limit * time_since_last)
                    accel = rate_change / time_since_last
                    rate_desired = last_commanded_rate + clamped_rate_change

            # enforce rate step limit if limit is enabled
            if self._rate_step_limit is not None:
                rate_change = rate_desired - last_commanded_rate
                if abs(rate_change) > self._rate_step_limit:
                    clamped_rate_change = clamp(rate_change, self._rate_step_limit)
                    rate_desired = last_commanded_rate + clamped_rate_change

            div = self.slew_rate_to_div(rate_desired)

            try:
                if axis == 'ra':
                    # Must use the start and stop movement commands on the RA axis because
                    # achieving zero motion when slew() is called repeatedly with a rate of zero
                    # can't be accomplished using set_ra_divisor alone.
                    if div == 0 and last_commanded_rate != 0.0:
                        self.ra_stop_movement()
                    elif div != 0 and last_commanded_rate == 0.0:
                        self.ra_start_movement()

                    # Only set the RA divisor to non-zero values. Setting the RA divisor to 0 will
                    # cause that axis to advance by exactly one servo step per command which is not
                    # the desired action.
                    if div != 0:
                        # the divisor is negated here to reverse the direction
                        self.set_ra_divisor(-div)
                else:
                    self.set_dec_divisor(div)
            except Gemini2Exception as e:
                # dangerous to give up because this thread is critical for stopping mount motion
                # safely; better to keep trying to send commands to the bitter end
                print(f'Ignoring exception in {axis} slew rate command thread: {str(e)}')
                continue

            # re-compute rate from divisor so that quantization error is accounted for
            actual_rate = self.div_to_slew_rate(div)

            # TODO: Do we *always* want to exit this thread when stop_motion() is called?
            if self._stop_motion.is_set() and actual_rate == 0.0:
                return

            last_commanded_rate = actual_rate
            last_command_time = current_time

            # No limits were enforced, so the target rate has been achieved. Wait for new target.
            if rate_desired == self._slew_rate_target[axis].value:
                self._slew_rate_event[axis].clear()
                self._slew_rate_event[axis].wait()


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

        This method will also attempt to recover if previous commands were interrupted mid-
        execution, leaving the backend in an inconsistent state. This is desired for this method
        specifically because it is often invoked in response to catching KeyboardInterrupt in the
        main thread.
        """

        # Throw-away command to clear out any inconsistent state in the backend
        # TODO: This should no longer be necessary, since the slew rate command thread ignores
        # exceptions raised by the back-end. Such exceptions *should* also be more rare with
        # CTRL-C since implementing code that protects the critical section of the back-end from
        # being interrupted by SIGINT.
        try:
            self.echo('a')
        except Exception:
            pass

        # informs slew command threads to bring rates to zero and then quit
        self._stop_motion.set()
        self._slew_rate_event['ra'].set()
        self._slew_rate_event['dec'].set()

        # TODO: Is this safe? Maybe we should re-start these threads in case they died unexpectedly?
        # wait for threads to end
        if self._slew_rate_threads['ra'].is_alive():
            self._slew_rate_threads['ra'].join()
        if self._slew_rate_threads['dec'].is_alive():
            self._slew_rate_threads['dec'].join()
