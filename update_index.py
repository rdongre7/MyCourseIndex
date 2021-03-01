import logging
import os
from piazza_api import Piazza
from elasticsearch import Elasticsearch
from flask import Flask
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

p = Piazza()
p.user_login(email=app.config["PIAZZA_USER"],
             password=app.config["PIAZZA_PASS"])

coursePiazzaDict = {
    "CS 4300": p.course(app.config["PIAZZA_CS4300_NID"]),
    "INFO 1998": p.course(app.config["PIAZZA_INFO1998_NID"])
}

for course_name, course in coursePiazzaDict.items():
    es = Elasticsearch()
    for post_id, post in course.get_postings():
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
        res = es.index(index="course_name", id=post_id, body=info)
        resources = post["Resource"]
        for post_id, post in resources.items():
            info = {
                "title": post["doc_name"],
                "question": "",
                "text": post["raw"],
                "answer": "",
                "followups": [],
                "document_type": "Lecture Notes"
            }
            res = es.index(index="test_index", id=post_id, body=info)
