#!/usr/bin/env bash

PID_FILE=$1
CPU_LIMIT=5

# Check the process status if it's running
if [ -e ${PID_FILE} ]; then
    pid=`cat ${PID_FILE}`
    cpu=`top -p $pid -b -n 1 | tail -1 | awk '{print $9;}' | awk -F ',' '{print $1;}'`
    cpu=${cpu%.*}
    # Kill the process if is not active
    if [ "$cpu" -lt "${CPU_LIMIT}" ]; then
		date
        kill ${pid}
		rm $PID_FILE
    fi
fi
