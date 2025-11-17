#!/usr/bin/env python

import datetime as dt
import sys
import threading
import time
import queue

import cv2
import ephem
import numpy as np
import yaml
from numba import njit, prange
from PIL import Image


def read_config(fname):
    """Read the config file."""
    with open(fname, "r") as fid:
        config = yaml.safe_load(fid)

    return config


class StreamCapture:
    """Video capturing class."""
    
    def __init__(self, url):
        """Start the video capture."""
        self.cap = cv2.VideoCapture(url)
        self.q = queue.Queue()
        self.running = False

    def _reader(self):
        while self.running:
            ret, frame = self.cap.read()
            frame_time = time.time()
            if not ret:
                break
            self.q.put((ret, frame, frame_time))

    def read(self):
        """Read and return a frame from the queue."""
        return self.q.get()

    def run(self):
        """Start the capture."""
        self.running = True
        self.t = threading.Thread(target=self._reader)
        self.t.daemon = True
        self.t.start()

    def stop(self):
        """Stop the capture."""
        self.running = False
        self.t.join()
        self.cap.release()


class Saver:
    """Class for saving images."""

    def __init__(self, config):
        """Initialize saving thread."""
        self._fname_fmt = config["fname_fmt"]
        self._date_fmt = config.get("fname_date_fmt")
        self.q = queue.Queue()
        self.running = True
        self.t = threading.Thread(target=self._save)
        self.t.daemon = True
        self.t.start()

    def _save(self):
        while self.running:
            try:
                start_time, data, stack_type, stack_length = self.q.get()
            except queue.Empty:
                continue
            if stack_type == "max":
                self._save_max_stack(start_time, data, stack_type, stack_length)

    def _save_max_stack(self, start_time, data, stack_type, stack_length):
        # OpenCV uses BGR channel order, adjust them to RGB
        img = Image.fromarray(data[:, :, ::-1])
        if self._date_fmt is not None:
            start_time = dt.datetime.fromtimestamp(
                start_time, dt.timezone.utc)
            start_time = start_time.strftime(self._date_fmt)
        fname = self._fname_fmt.format(**locals())
        print("Saving", fname)
        img.save(fname)

    def stop(self):
        self.running = False
        self.t.join()


class VideoStacker:
    """Manage video stacking."""

    def __init__(self, config, stream, saver):
        """Initialize stacker."""
        self._stack_length = config["stack_length"]
        self._stack_period = config["stack_period"]
        self._saturation_limit = config.get("saturation_limit", 255)
        self._saver = saver
        self._start_time = None
        self._end_time = time.time() + self._stack_period
        self._stream = stream
        self._max_stack = None
        self._stack_sum = None
        self._num_frames = 0

    def run(self):
        """Run the stacker."""
        self._stream.run()

        self._num_frames = 0

        self._running = True
        times = []
        while self._keep_running():
            success, frame, frame_time = self._stream.read()
            if not success:
                continue

            if self._max_stack is None:
                self._start_time = frame_time
                self._max_stack = frame
                save_at = frame_time + self._stack_length
                self._stack_sum = np.zeros(frame.shape[:2], dtype=np.uint16)
                continue

            tic = time.time()
            self._update_stacks(frame, frame_time)
            t = time.time() - tic
            times.append(t)

            if frame_time > save_at:
                print(sum(times) / self._num_frames)
                times = []
                self.save()
            else:
                self._num_frames += 1

    def _update_stacks(self, frame, frame_time):
        _update_max_stack_numba(self._max_stack, frame, self._stack_sum)

    def save(self):
        """Save the images."""
        self._saver.q.put(
            (self._start_time, self._max_stack, "max",
             self._stack_length))
        self._start_time = None
        self._max_stack = None
        self._num_frames = 0

    def stop(self):
        """Stop the processing."""
        self.save()
        self._stream.stop()
        self._saver.stop()

    def _keep_running(self):
        if time.time() < self._end_time:
            return True
        self.stop()
        return False


@njit(parallel=True)
def _update_max_stack_numba(max_stack, frame, stack_sum):
    frame_sum = np.sum(frame, axis=-1, dtype=np.uint16)
    y, x = frame_sum.shape
    for i in prange(x):
        for j in range(y):
            if frame_sum[j, i] > stack_sum[j, i]:
                max_stack[j, i, :] = frame[j, i, :]
                stack_sum[j, i] = frame_sum[j, i]


def _get_stream_url(config):
    url = (config.get("protocol", "rtsp") + "://"
           + config["username"] + ":"
           + config["password"] + "@"
           + config["camera_ip"] + ":"
           + str(config.get("port", 554)) + "/"
           + config["stream"])
    return url


def _set_stack_period_to_config(config):
    if "stack_period" in config:
        return
    config["stacks"]["stack_period"] = _calculate_stack_period(
        config["location"])


def _calculate_stack_period(config):
    now = dt.datetime.now(dt.timezone.utc)
    place = _get_place(config, now)
    sun = ephem.Sun()
    sun.compute(place)
    if np.rad2deg(sun.alt) >= config["sun_limit"]:
        return -1
    next_rise = place.next_rising(sun).datetime().replace(tzinfo=dt.timezone.utc)
    stack_period = next_rise - now
    return int(stack_period.total_seconds())


def _get_place(config, now):
    lon = config["longitude"]
    lat = config["latitude"]
    elevation = config["elevation"]
    sun_limit = config.get("sun_limit", 0)
    place = ephem.Observer()
    place.lon = "%f" % lon
    place.lat = "%f" % lat
    #place.pressure = 0
    place.horizon = "%f" % sun_limit
    place.elevation = elevation
    place.date = now

    return place


def main():
    """Main."""
    config = read_config(sys.argv[1])
    _set_stack_period_to_config(config)
    if config["stacks"]["stack_period"] < 0:
        return
    stream = StreamCapture(_get_stream_url(config["stream"]))
    saver = Saver(config["saving"])
    stacker = VideoStacker(config["stacks"], stream, saver)
    stacker.run()


if __name__ == "__main__":
    main()
