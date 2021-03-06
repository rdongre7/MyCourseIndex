from app.search import concept_modify_query_bool as concept_modify_query
import html2text
import logging
import app.utils.vectorizer as vecPy
from app.utils.signup_data import add_course
from app.search.boolean_search import *
from app.search.similarity import *
import os
import sys
import time
from flask import Flask, render_template, request, redirect, flash, url_for, send_from_directory, jsonify
# from db_setup import init_db, db_session
from urllib.parse import unquote
from piazza_api import Piazza
from app.auth import user_jwt_required, get_name, get_claims, can_add_course
from elasticsearch import Elasticsearch

start_import = time.time()
end_import = time.time()


app = Flask(__name__, template_folder="../client/build",
            static_folder="../client/build/static")

if os.environ.get("deployment", False):
    app.config.from_pyfile('/etc/cs4300-volume-cfg/cs4300app.cfg')
else:
    app.config.from_pyfile(os.path.join(
        os.path.join(os.getcwd(), "secrets"), "cs4300app.cfg"))

APP_ROOT = os.path.dirname(os.path.abspath(__file__))

gunicorn_logger = logging.getLogger('gunicorn.error')
app.logger.handlers = gunicorn_logger.handlers
app.logger.setLevel(gunicorn_logger.level)

app.logger.debug("Total import runtime: {} seconds".format(
    end_import - start_import))

p = Piazza()
p.user_login(email=app.config["PIAZZA_USER"],
             password=app.config["PIAZZA_PASS"])
coursePiazzaIDDict = {
    "CS 4300": app.config["PIAZZA_CS4300_NID"],
    "INFO 1998": app.config["PIAZZA_INFO1998_NID"]
}

coursePiazzaDict = {
    "CS 4300": p.course(app.config["PIAZZA_CS4300_NID"]),
    "INFO 1998": p.course(app.config["PIAZZA_INFO1998_NID"])
}


@app.route("/auth", methods=["POST"])
def auth():
    # app.logger.debug("Starting Auth")
    # access_token = request.get_json()["token"]
    # # app.logger.debug("My Token is: {}".format(access_token))
    # app.logger.critical("Should I have access? {}".format(user_jwt_required(access_token, app.config["APP_ID"])))
    # if user_jwt_required(access_token, app.config["APP_ID"]):
    #     return "OK"
    # else:
    #     return "NO"
    return "OK"


@app.route("/whoami", methods=["POST"])
def whoami():
    access_token = request.get_json()["token"]
    # app.logger.debug("My Token is: {}".format(access_token))
    name = get_name(access_token, app.config["APP_ID"])
    return name


@app.route('/search', methods=["POST"])
def search_results():
    access_token = request.get_json()["token"]
    if user_jwt_required(access_token, app.config["APP_ID"]):
        orig_query = unquote(request.get_json()["query"])
        app.logger.info("User queried: {}".format(orig_query))
        courseSelection = request.get_json()["course"]
        app.logger.info("User course: {}".format(courseSelection))
        es = Elasticsearch('http://18.191.198.23:9200/')
        index = courseSelection.replace(" ", "_").lower()
        # Search query
        res = es.search(index=index, body={
            "query": {
                "query_string": {
                    "query": "*" + orig_query + "*",
                    "fields": ["title", "question", "answer", "text", "followups"]
                }
            },
            "highlight": {
                "fields": {
                    "title": {},
                    "question": {},
                    "answer": {},
                    "text": {},
                    "followups": {}
                }
            }
        })
        print("Got %d Hits:" % res['hits']['total']['value'], file=sys.stderr)
        return res["hits"]

    else:
        return "Not Authorized"


@app.route("/addcourse", methods=["POST"])
def add_prof_course():
    access_token = request.get_json()["token"]
    validated = can_add_course(access_token, app.config["APP_ID"])
    if not validated:
        return "Denied"
    input_request = request.get_json()
    # h = html2text.HTML2Text()
    # h.ignore_links = True
    # TODO1: Validate Professor User Group
    # input_request.pop
    add_course(email=input_request["formEmail"], course_name=input_request["formCN"],
               piazza_link=input_request["formPL"], canvas_link=input_request["formCL"], csv=input_request["formCSV"])
    return "OK"


@app.route("/courses", methods=["POST"])
def get_user_courses():
    access_token = request.get_json()["token"]
    claims = get_claims(access_token, app.config["APP_ID"])
    if claims["scope"] == "Unauthorized":
        return jsonify([])
    else:
        to_json = []
        for claim in claims["scope"]:
            if app.config["COURSE_MAPPING"].get(claim, "") != "":
                to_json.append(app.config["COURSE_MAPPING"].get(claim))
        to_json = sorted(to_json, key=lambda x: x["courseName"])
        for d in to_json:
            d["add"] = False
        if "AddCourse" in claims["scope"]:
            to_json.append({"courseName": "Add Course",
                            "add": True, "protected": True})

        return jsonify(to_json)


@app.route("/isprof", methods=["POST"])
def is_professor():
    access_token = request.get_json()["token"]
    claims = can_add_course(access_token, app.config["APP_ID"])
    return claims


@app.route("/folders", methods=["POST"])
def getFolders():
    courseSelection = request.get_json()["courseSelection"]  # "CS 4300"
    # searchSelection = request.get_json()["courseSelection"]
    app.logger.critical("{}".format(vecPy.foldersDictionary[courseSelection]))
    return jsonify(vecPy.foldersDictionary[courseSelection])


@app.route("/tokeVerify", methods=["POST"])
def tokeVerify():
    access_token = request.get_json()["token"]
    course = request.get_json()["course"]
    their_token = request.get_json()["piazzaToken"]

    claims = get_claims(access_token, app.config["APP_ID"])
    if claims["scope"] == "Unauthorized":
        return "NO"
    else:
        auth_courses = [app.config["COURSE_MAPPING"].get(
            claim, {"courseName": ""}).get("courseName") for claim in claims["scope"]]
    # print("HELLOR: {}".format(course not in auth_courses))
    if course not in auth_courses:
        return "NO"
    if course == "CS 4300":
        if their_token == "4300":
            return "OK"
        else:
            return "NO"
    h = html2text.HTML2Text()
    h.ignore_links = True
    parsed_piazza = h.handle(coursePiazzaDict[course].get_post(
        app.config["PIAZZA_" + course.replace(" ", "") + "_TOKEN_POST"])["history"][0]["content"])
    split_piazza = parsed_piazza.split("\n")
    piazza_token = split_piazza[0]
    if piazza_token == their_token:
        return "OK"
    else:
        return "NO"


@app.route("/manifest.json")
def manifest():
    return send_from_directory(os.path.join(app.root_path, "../client/build"), 'manifest.json')


@app.route('/ColorMCIfavicon.ico')
def ColorMCIfavicon():
    return send_from_directory(os.path.join(app.root_path, "static"), "ColorMCIfavicon.ico")


@app.route('/oidc/callback', methods=['GET'])
def oidc_callback():
    return redirect(url_for("index"))


@app.route('/null', methods=['GET'])
def null_callback():
    return redirect(url_for("index"))


@app.route('/', methods=['GET'], defaults={'path': ''})
@app.route('/<path:path>')
def index(path):
    return render_template("index.html")


# application.add_api('spec.yml')
if __name__ == "__main__":
    app.run(port=5000, debug=True)
