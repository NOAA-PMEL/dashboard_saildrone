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

celery_app = Celery('tasks', broker=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379"))

@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    sender.add_periodic_task(
         crontab(hour='1'),
         update_locations.s(),
         name='Update the locations database'
    )

@celery_app.task
def update_locations():
    with open('config/missions.json') as missions_config:
        config_json = json.load(missions_config)
    years = config_json['config']['collections']
    outeridx = 0
    for year in years:
        print('missions for ' + year)
        member = years[year]
        
        for idx, mid in enumerate(member['missions']):
            mission = member['missions'][mid]
            print('Pulling locations for mission ' + str(mid))
            for d in mission['drones']:
                logger.info('Reading drone ' + str(d))
                drone = mission['drones'][d]
                info = Info(drone['url'])
                print('getting info from ' + info.get_info_url(drone['url']))
                depth_name, dsg_var = info.get_dsg_info()
                dsg_id = dsg_var[info.get_dsg_type()]
                url = drone['url'] + '.csv?latitude,longitude,time,' + dsg_id +'&orderByClosest("time,1day")&'+dsg_id+'="'+d+'"'
                print(url)
                df = pd.read_csv(url, skiprows=[1])
                # Don't drop, just take the rows where EPS is not NA:
                df = df[df['latitude'].notna()]
                df = df[df['longitude'].notna()]
                df['mission_id'] = mid
                df['title'] = mission['ui']['title']
                df[dsg_id] = df[dsg_id].astype(str)
                if outeridx == 0:
                    locations_df = df
                else:
                    locations_df = pd.concat([locations_df, df])
                outeridx = outeridx + 1
    
    logger.info('Updating locations...')
    locations_df.to_sql(constants.locations_table, constants.postgres_engine, if_exists='replace', index=False)