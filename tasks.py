import os
import redis
import pandas as pd
import numpy as np
import json
from celery import Celery
from sdig.erddap.info import Info
import urllib.parse
import constants
import db
from celery.utils.log import get_task_logger
import ssl
import urllib.parse
import plotly.express as px

ssl._create_default_https_context = ssl._create_unverified_context
logger = get_task_logger(__name__)


def flush():
    constants.redis_instance.flushall()


def update_mission(mid, mission):
   
    logger.debug('Pulling locations for mission ' + str(mission['ui']['title']))
         
    start_dates = []
    end_dates = []
    long_names = {}
    units = {}
    dsg_ids = []
    drones = mission['drones']
    mission_dfs = []
    for dix, d in enumerate(sorted(drones)):
        color = px.colors.qualitative.Alphabet[dix]
        logger.debug('Reading drone ' + str(d))
        drone = drones[d]
        info = Info(drone['url']) 
        depth_name, dsg_var = info.get_dsg_info()
        dsg_id = dsg_var[info.get_dsg_type()]
        base_url = drone['url'] + '.csv?'
        time_url = base_url + urllib.parse.quote_plus('time&orderByMinMax("time")')
        print(time_url)
        tdf = pd.read_csv(time_url, skiprows=[1])
        print(tdf)
        start_date = tdf['time'].min()
        end_date = tdf['time'].max()
        req_vars = 'latitude,longitude,time,' + dsg_id
        query = '&orderByClosest("time,1day")&'+dsg_id+'="'+d+'"'
        q = urllib.parse.quote(query)
        url = base_url + req_vars + q
        print(url)
        df = pd.read_csv(url, skiprows=[1])
        # Don't drop, just take the rows where lat or lon is not NA:
        df = df[df['latitude'].notna()]
        df = df[df['longitude'].notna()]
        df['mission_id'] = mid
        df['title'] = mission['ui']['title']
        df[dsg_id] = df[dsg_id].astype(str)
        drone_vars, d_long_names, d_units, standard_names, var_types = info.get_variables()
        drones[d]['variables'] = drone_vars
        drones[d]['start_date'] = start_date
        drones[d]['color'] = color
        start_dates.append(start_date)
        drones[d]['end_date'] = end_date
        end_dates.append(end_date)
        depth_name, dsg_id = info.get_dsg_info()
        dsg_ids.append(dsg_id['trajectory'])
        long_names = {**long_names, **d_long_names}
        units = {**units, **d_units}
        mission_dfs.append(df)
    uids = list(set(dsg_ids))
    if len(uids) == 1:
        mission['dsg_id'] = uids[0]
    else:
        print('Mission has non-unique DSG ID names.')
    long_names = dict(sorted(long_names.items(), key=lambda item: item[1]))
    mission['long_names'] = long_names
    mission['units'] = units
    start_dates.sort()
    end_dates.sort()
    mission['start_date'] = start_dates[0]
    mission['end_date'] = end_dates[-1]
    constants.redis_instance.hset("mission", mid, json.dumps(mission)) 
    full_df = pd.concat(mission_dfs).reset_index()
    return full_df

# Run this once from the workspace before deploying the application

def load_missions():
    with open('config/missions.json') as missions_config:
        config_json = json.load(missions_config)
    collections = config_json['collections']
    outeridx = 0 
    for collection in collections:
        logger.info('Processing missions for ' + collection)
        member = collections[collection]     
        for idx, mid in enumerate(member['missions']):
            mission = member['missions'][mid]
            df = update_mission(mid, mission)
            if outeridx == 0:
                locations_df = df
            else:
                locations_df = pd.concat([locations_df, df])
            outeridx = outeridx + 1
                
    logger.info('Setting the mission locations...')
    locations_df.to_sql(constants.locations_table, constants.postgres_engine, if_exists='replace', index=False)  

