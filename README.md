# Sky cam peak-hold stacking using OpenCV

## Installation

Installing the require libraries is easiest done using Conda
(MiniForge3 distribution and `conda-forge` software channel are
preferred):

```bash
conda create -n sky-cam-cv \
    ephem \
	py-opencv \
	python=3.13 \
	pyyaml
```

## Configuration

See `etc/tapo.yaml`, which can be used as a template.

## Running

Below is an example script that can be used in crontab to start the
processing every minute.  If the file pointed by the `pid_file`
setting exists, the Python script will simply exit to prevent starting
up several instances.

```bash
#!/usr/bin/env bash

conda activate sky-cam-cv
sky-cam-cv.py /path/to/configs/tapo.yaml
```

## Watchdog

Occasionally, if the network connectivity is unstable, the Python
scipt may hang.  For this, there's a bash scipt in
`etc/sky-cam-cv_watchdog.sh` that will kill the stray process and
clean the PID file.  After this the cron script can restart the
process.
