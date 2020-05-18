#!/usr/bin/env python
#
# Utility functions for UI automation with xdotool in a virtual framebuffer
# with XVFB. Also includes utilities for accessing the clipboard for easily
# and efficiently copy-pasting strings in the UI
# Based on splitflap/electronics/scripts/export_util.py by Scott Bezek
#
#   Copyright 2019 Productize SPRL
#   Copyright 2015-2016 Scott Bezek and the splitflap contributors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import os
from subprocess import (Popen, CalledProcessError, TimeoutExpired, call, check_output, STDOUT, DEVNULL)
import tempfile
import time
import shutil

from contextlib import contextmanager

# python3-xvfbwrapper
from xvfbwrapper import Xvfb


from kicad_auto import log
logger = log.get_logger(__name__)

wait_for_key = False


class PopenContext(Popen):

    def __exit__(self, type, value, traceback):
        # Note: currently we don't communicate with the child so these cases are never used.
        # I keep them in case they are needed, but excluded from the coverage.
        # Also note that closing stdin needs extra handling, implemented in the parent class
        # but not here.
        if self.stdout:
            self.stdout.close()  # pragma: no cover
        if self.stderr:
            self.stderr.close()  # pragma: no cover
        if self.stdin:
            self.stdin.close()   # pragma: no cover
        if type:
            self.terminate()
        # Wait for the process to terminate, to avoid zombies.
        try:
            # Wait for 3 seconds
            self.wait(3)
            retry = False
        except TimeoutExpired:  # pragma: no cover
            # The process still alive after 3 seconds
            retry = True
            pass
        if retry:  # pragma: no cover
            # We shouldn't get here. Kill the process and wait upto 10 seconds
            self.kill()
            self.wait(10)


def wait_xserver():
    timeout = 10
    DELAY = 0.5
    logger.debug('Waiting for virtual X server ...')
    logger.debug('Current DISPLAY is '+os.environ['DISPLAY'])
    if shutil.which('setxkbmap'):
        cmd = ['setxkbmap', '-query']
    elif shutil.which('setxkbmap'):  # pragma: no cover
        cmd = ['xset', 'q']
    else:  # pragma: no cover
        cmd = ['ls']
        logger.warning('No setxkbmap nor xset available, unable to verify if X is running')
    for i in range(int(timeout/DELAY)):
        with open(os.devnull, 'w') as fnull:
            logger.debug('Checking using '+str(cmd))
            ret = call(cmd, stdout=fnull, stderr=STDOUT, close_fds=True)
            # ret = call(['xset', 'q'])
        if not ret:
            return
        logger.debug('   Retry')
        time.sleep(DELAY)
    raise RuntimeError('Timed out waiting for virtual X server')


def wait_wm():
    timeout = 10
    DELAY = 0.5
    logger.debug('Waiting for Window Manager ...')
    if shutil.which('wmctrl'):
        cmd = ['wmctrl', '-m']
    else:  # pragma: no cover
        logger.warning('No wmctrl, unable to verify if WM is running')
        time.sleep(2)
        return
    logger.debug('Checking using '+str(cmd))
    for i in range(int(timeout/DELAY)):
        ret = call(cmd, stdout=DEVNULL, stderr=STDOUT, close_fds=True)
        if not ret:
            return
        logger.debug('   Retry')
        time.sleep(DELAY)
    raise RuntimeError('Timed out waiting for WM server')


@contextmanager
def start_wm(do_it):
    if do_it:
        cmd = ['fluxbox']
        logger.debug('Starting WM: '+str(cmd))
        with PopenContext(cmd, stdout=DEVNULL, stderr=DEVNULL, close_fds=True) as wm_proc:
            wait_wm()
            try:
                yield
            finally:
                logger.debug('Terminating the WM')
                # Fluxbox sometimes will ignore SIGTERM, we can just kill it
                wm_proc.kill()
    else:
        yield


@contextmanager
def start_record(video_dir, video_name):
    if video_dir:
        video_filename = os.path.join(video_dir, video_name)
        cmd = ['recordmydesktop', '--overwrite', '--no-sound', '--no-frame', '--on-the-fly-encoding',
               '-o', video_filename]
        logger.debug('Recording session with: '+str(cmd))
        with PopenContext(cmd, stdout=DEVNULL, stderr=DEVNULL, close_fds=True) as screencast_proc:
            try:
                yield
            finally:
                logger.debug('Terminating the session recorder')
                screencast_proc.terminate()
    else:
        yield


@contextmanager
def start_x11vnc(do_it, old_display):
    if do_it:
        cmd = ['x11vnc', '-display', os.environ['DISPLAY'], '-localhost']
        logger.debug('Starting VNC server: '+str(cmd))
        with PopenContext(cmd, stdout=DEVNULL, stderr=DEVNULL, close_fds=True) as x11vnc_proc:
            if old_display is None:
                old_display = ':0'
            logger.debug('To monitor the Xvfb now you can start: "ssvncviewer '+old_display+'"(or similar)')
            try:
                yield
            finally:
                logger.debug('Terminating the x11vnc server')
                x11vnc_proc.terminate()
    else:
        yield


@contextmanager
def recorded_xvfb(video_dir, video_name, do_x11vnc, do_wm, **xvfb_args):
    try:
        old_display = os.environ['DISPLAY']
    except KeyError:
        old_display = None
        pass
    with Xvfb(**xvfb_args):
        wait_xserver()
        with start_x11vnc(do_x11vnc, old_display):
            with start_wm(do_wm):
                with start_record(video_dir, video_name):
                    yield


def xdotool(command):
    return check_output(['xdotool'] + command, stderr=DEVNULL)


def clipboard_store(string):
    # I don't know how to use Popen/run to make it run with pipes without
    # either blocking or losing the messages.
    # Using files works really well.
    logger.debug('Clipboard store "'+string+'"')
    # Write the text to a file
    fd_in, temp_in = tempfile.mkstemp(text=True)
    os.write(fd_in, string.encode())
    os.close(fd_in)
    # Capture output
    fd_out, temp_out = tempfile.mkstemp(text=True)
    process = Popen(['xclip', '-selection', 'clipboard', temp_in], stdout=fd_out, stderr=STDOUT)
    ret_code = process.wait()
    os.remove(temp_in)
    os.lseek(fd_out, 0, os.SEEK_SET)
    ret_text = os.read(fd_out, 1000)
    os.close(fd_out)
    os.remove(temp_out)
    ret_text = ret_text.decode()
    if ret_text:  # pragma: no cover
        logger.error('Failed to store string in clipboard')
        logger.error(ret_text)
        raise
    if ret_code:  # pragma: no cover
        logger.error('Failed to store string in clipboard')
        logger.error('xclip returned %d' % ret_code)
        raise


# def clipboard_retrieve():
#     p = Popen(['xclip', '-o', '-selection', 'clipboard'], stdout=PIPE)
#     output = ''
#     for line in p.stdout:
#         output += line.decode()
#     logger.debug('Clipboard retrieve "'+output+'"')
#     return output


def debug_window(id=None):  # pragma: no cover
    if shutil.which('xprop'):
        if id is None:
            try:
                id = xdotool(['getwindowfocus']).rstrip()
            except CalledProcessError:
                logger.debug('xdotool getwindowfocus failed!')
                pass
        if id:
            call(['xprop', '-id', id])


def wait_focused(id, timeout=10):
    DELAY = 0.5
    logger.debug('Waiting for %s window to get focus...', id)
    for i in range(int(timeout/DELAY)):
        cur_id = xdotool(['getwindowfocus']).rstrip()
        logger.debug('Currently focused id: %s', cur_id)
        if cur_id == id:
            return
        time.sleep(DELAY)
    debug_window(cur_id)  # pragma: no cover
    raise RuntimeError('Timed out waiting for %s window to get focus' % id)


def wait_not_focused(id, timeout=10):
    DELAY = 0.5
    logger.debug('Waiting for %s window to lose focus...', id)
    for i in range(int(timeout/DELAY)):
        cur_id = xdotool(['getwindowfocus']).rstrip()
        logger.debug('Currently focused id: %s', cur_id)
        if cur_id != id:
            return
        time.sleep(DELAY)
    debug_window(cur_id)  # pragma: no cover
    raise RuntimeError('Timed out waiting for %s window to lose focus' % id)


def wait_for_window(name, window_regex, timeout=10, focus=True, skip_id=0, others=None):
    DELAY = 0.5
    logger.info('Waiting for "%s" ...', name)
    if skip_id:
        logger.debug('Will skip %s', skip_id)
    xdotool_command = ['search', '--onlyvisible', '--name', window_regex]

    for i in range(int(timeout/DELAY)):
        try:
            window_id = xdotool(xdotool_command).splitlines()
            logger.debug('Found %s window (%d)', name, len(window_id))
            if len(window_id) == 1:
                id = window_id[0]
            if len(window_id) > 1:
                id = window_id[1]
            logger.debug('Window id: %s', id)
            if id != skip_id:
                if focus:
                    xdotool_command = ['windowfocus', '--sync', id]
                    xdotool(xdotool_command)
                    wait_focused(id, timeout)
                return window_id
            else:
                logger.debug('Skipped')
        except CalledProcessError:
            pass
        # Check if we have a list of alternative windows
        if others:
            for other in others:
                cmd = ['search', '--onlyvisible', '--name', other]
                try:
                    xdotool(cmd)
                    raise ValueError(other)
                except CalledProcessError:
                    pass
        time.sleep(DELAY)
    debug_window()  # pragma: no cover
    raise RuntimeError('Timed out waiting for %s window' % name)


def set_wait(state):
    global wait_for_key
    wait_for_key = state


def wait_point():
    if wait_for_key:
        input('Press a key')
