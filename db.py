import constants
import pandas as pd
import datetime


def get_locations():
    # In this function, we retrieve the data from postgres using pandas's read_sql method.

    # This data is periodically getting updated via a separate Celery Process in tasks.py.
    # "dataset_table" is the name of the table that we initialized in tasks.py.
    updated_df = pd.read_sql(
        "SELECT * FROM {};".format(constants.locations_table), constants.postgres_engine
    )
    return updated_df

def get_mission_locations(mission_id, dsg_id):
    # In this function, we retrieve the data from postgres using pandas's read_sql method.

    # This data is periodically getting updated via a separate Celery Process in tasks.py.
    # "dataset_table" is the name of the table that we initialized in tasks.py.
    updated_df = pd.read_sql(
        "SELECT * FROM {} WHERE MISSION_ID=\'{}\' ORDER BY TIME,{};".format(constants.locations_table, mission_id, dsg_id), constants.postgres_engine
    )
    return updated_df

def drop():
    "DROP {}".format(constants.locations_table)