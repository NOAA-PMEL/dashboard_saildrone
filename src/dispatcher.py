import app as saildrone
import wsm as wsm
import osites as oceansites
import index as index
from werkzeug.middleware.dispatcher import DispatcherMiddleware
import flask_app
from schedule import repeat, every


@repeat(every(60).seconds)
def do_work():
    saildrone.update_mission_metadata()


app = DispatcherMiddleware(flask_app, {
    '/dashboard/oceansites': oceansites.server,
    '/dashboard/saildrone': saildrone.server,
    '/dashboard/wsm': wsm.server,
    '/dashboard': index.server,
})
