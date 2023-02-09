#!/bin/bash
export MISSIONS_JSON=/home/hazy/tomcat/saildrone/missions.json
eval "$(/home/hazy/tomcat/miniconda3/bin/conda shell.bash hook)"
conda activate dash
cd /usr/local/src/dash/saildrone
gunicorn app:server --workers 4 --preload --timeout 600 --bind hazy.pmel.noaa.gov:9018 1>>/home/hazy/tomcat/saildrone/gunicorn.log 2>&1 &
