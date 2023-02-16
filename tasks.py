import os
import redis
import pandas as pd
import numpy as np
import json
from celery import Celery
from celery.schedules import crontab
from sdig.erddap.info import Info

from celery.utils.log import get_task_logger

from random import randrange

import constants
import db

logger = get_task_logger(__name__)

def update_locations():
    with open('config/missions.json') as missions_config:
        config_json = json.load(missions_config)
    
    for idx, mission in enumerate(config_json['config']['missions']):
        mid = mission['mission_id']
        print('Pulling locations for mission ' + str(mid))
        for d in mission['drones']:
            logger.info('Reading drone ' + str(d))
            drone = mission['drones'][d]
            info = Info(drone['url'])
            depth_name, dsg_var = info.get_dsg_info()
            dsg_id = dsg_var[info.get_dsg_type()]
            url = drone['url'] + '.csv?latitude,longitude,time,' + str(dsg_id) +'&orderByClosest("time,1day")'
            df = pd.read_csv(url, skiprows=[1])
            # Don't drop, just take the rows where EPS is not NA:
            df = df[df['latitude'].notna()]
            df = df[df['longitude'].notna()]
            df['mission_id'] = mission['mission_id']
            df['title'] = mission['ui']['title']
            df[dsg_id] = df[dsg_id].astype(str)
            if idx == 0:
                locations_df = df
            else:
               locations_df = pd.concat([locations_df, df])
    logger.info('Updating locations...')
    locations_df.to_sql(constants.locations_table, constants.postgres_engine, if_exists='replace', index=False)