import logging
import os
from elasticsearch import Elasticsearch
from flask import Flask
import json
import boto3
app = Flask(__name__)

if os.environ.get("deployment", False):
    app.config.from_pyfile('/etc/cs4300-volume-cfg/cs4300app.cfg')
else:
    app.config.from_pyfile(os.path.join(
        os.path.join(os.getcwd(), "secrets"), "cs4300app.cfg"))

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

key = app.config["AWS_ACCESS"]
secret = app.config["AWS_SECRET"]

s3 = boto3.client('s3', aws_access_key_id=key, aws_secret_access_key=secret)
s3.download_file('cs4300-data-models',
                 'P03Data_mod_concepts.json', 'P03Data.json')

with open("P03Data.json") as f:
    fromS3 = json.load(f)

coursePiazzaList = [
    "CS 4300", "INFO 1998"
]
es = Elasticsearch('http://18.222.65.250:9200/')

for course_name in coursePiazzaList:
    posts = fromS3[course_name]["Piazza"]
    resources = fromS3[course_name]["Resource"]
    index_name = course_name.replace(" ", "_").lower()

    for post_id, post in posts.items():
        content = post["raw"]["history"]
        children = post["raw"]["children"]
        try:
            answer = children[0]["history"][0]["content"]
        except:
            answer = ""
        followups = []
        if isinstance(children, dict):
            for child in children["children"]:
                followups.append(child)
        info = {
            "title": content[0]["subject"],
            "question": content[0]["content"],
            "text": "",
            "answer": answer,
            "followups": followups,
            "document_type": "Piazza"
        }
        res = es.index(index=index_name, id=post_id, body=info)

    for post_id, post in resources.items():
        info = {
            "title": post["doc_name"],
            "question": "",
            "text": post["raw"],
            "answer": "",
            "followups": [],
            "document_type": "Lecture Notes"
        }
        res = es.index(index=index_name, id=post_id, body=info)
