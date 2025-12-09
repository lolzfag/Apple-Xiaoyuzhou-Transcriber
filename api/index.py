import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from vercel_serverless_wsgi import handle  # type: ignore
from app import app


def handler(event, context):
    return handle(app, event, context)
