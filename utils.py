"""Helper utilities and decorators."""
import json
import os

import yaml
import markdown as md
import ast
from flask import abort, flash, request, url_for
from flask_login import current_user
from jwt.jwk import OctetJWK, jwk_from_dict
from markupsafe import Markup

from edurange_refactored.extensions import db

from .user.models import Scenarios, User, Responses

path_to_key = os.path.dirname(os.path.abspath(__file__))


def load_key_data(name, mode="rb"):
    abspath = os.path.normpath(os.path.join(path_to_key, "templates/utils/.keys", name))
    with open(abspath, mode=mode) as fh:
        return fh.read()


class TokenHelper:
    def __init__(self):
        self.data = jwk_from_dict(json.loads(load_key_data("oct.json", "r")))
        self.octet_obj = OctetJWK(self.data.key, self.data.kid)

    def get_JWK(self):
        return self.octet_obj

    def get_data(self):
        return self.data

    def verify(self, token):
        self.octet_obj.verify()


def flash_errors(form, category="warning"):
    """Flash all errors for a form."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{getattr(form, field).label.text} - {error}", category)


def check_role_view(mode):  # check if view mode compatible with role (admin/inst/student)
    number = current_user.id
    user = User.query.filter_by(id=number).first()
    if not user.is_admin and not user.is_instructor:
        abort(403)  # student's don't need their role checked
        return None  # a student has no applicable role. does abort stop the calling/parent function?
    else:
        mode = request.args["mode"]
        if mode not in ["studentView", "instructorView", "adminView"]:
            abort(400)  # only supported views
        elif user.is_instructor and not user.is_admin:  # instructor only
            if mode == "studentView":
                return True  # return true since viewMode should be set
            elif mode == "adminView":
                abort(403)  # instructors can't choose adminView
            else:
                return False  # return false since viewMode should be dropped
        elif user.is_admin:
            if mode in ["studentView", "instructorView"]:
                return True
            else:
                return False
        else:
            abort(403)  # who are you?!
            return None


# --------

def generateNavElements(role, view): # generate all navigational elements
    """Makes decisions and calls correct generators for navigational links based on role."""
    views = None
    links = None
    if role is None: # user not logged in
        return {'views': views, 'links': links}

    if role in ['a', 'a/i', 'i']:
        viewSwitch = {
            'a': genAdminViews,   #
            'a/i': genAdminViews, # ^ call generator for admins view links
            'i': genInstructorViews # call generator for instructors view links
        }
        views = viewSwitch[role]() # call view link generator function based on role

    linkSwitch = {
        'a': genAdminLinks,    # call generator for admin links,
        'a/i': genAdminLinks,  # ^ pass view so function can redirect to correct link generator
        'i': genInstructorLinks, # call generator for instructor links
        's': genStudentLinks # call generator for student links
    }
    links = linkSwitch[role](view) # call link generator function based on role

    return {'views': views, 'links': links} # views: dropdown list items for view change, to render in navbar
                                            # links: redirecting links, to render in sidebar


def create_link(route, icon, text):
    """Create html element for a sidebar link (requires route, icon class (font-awesome), and text to label link)."""
    html = '''<a class="list-group-item list-group-item-action bg-secondary text-white" href="{0}">
                <i class="fa {1}" aria-hidden="true"></i>&nbsp;&nbsp;{2}
              </a>'''
    html = html.format(url_for(route), icon, text)
    return Markup(html)


def create_view(route, text):
    """Create html element for dropdown link items."""
    html = '<a class="dropdown-item" href="{0}{1}">{2}</a>'.format(url_for('dashboard.set_view'), route, text)
    return Markup(html)


def genAdminViews():
    """Generate 'select view' elements for admin users."""
    views = [create_view('?mode=adminView', 'Admin View'),
             create_view('?mode=instructorView', 'Instructor View'),
             create_view('?mode=studentView', 'Student View')]

    return views


def genInstructorViews():
    """Generate 'select view' elements for instructors."""
    views = [create_view('?mode=instructorView', 'Instructor View'),
             create_view('?mode=studentView', 'Student View')]

    return views


def genAdminLinks(view):
    """Generate links for admin users based on selected view."""
    if not view:
        dashboard = create_link('dashboard.admin', 'fa-desktop', 'Admin Dashboard')
        scenarios = create_link('dashboard.scenarios', 'fa-align-justify', 'Scenarios')
        notification = create_link('dashboard.notification', 'fa-bell', 'Notifications')
        # return [dashboard, scenarios]
        return [dashboard, scenarios, notification]
    elif view == 'instructorView':
        return genInstructorLinks(None)
    elif view == 'studentView':
        return genStudentLinks()
    else:
        return None


def genInstructorLinks(view):
    """Generate links for instructors based on selected view."""
    if view == 'studentView':
        return genStudentLinks()
    elif not view:
        dashboard = create_link('dashboard.instructor', 'fa-desktop', 'Instructor Dashboard')
        scenarios = create_link('dashboard.scenarios', 'fa-align-justify', 'Scenarios')
        return [dashboard, scenarios]
    else:
        return None


def genStudentLinks(view=None): # needs common arg for switch statement
    """Generate links for students."""
    dashboard = create_link('dashboard.student', 'fa-desktop', 'Dashboard')
    # testing = create_link('public.testing', *icon*, *name*)
    return [dashboard] # return array to avoid character print in template's for loop


def checkAuth(d):
    number = current_user.id
    user = User.query.filter_by(id=number).first()
    if not user.is_instructor and not user.is_admin:
        return False
    else:
        return True


def format_datetime(value, format="%d %b %Y %I:%M %p"):
    """Format a date time to (Default): d Mon YYYY HH:MM P"""
    if value is None:
        return ""
    return value.strftime(format)


def statReader(s):
    statSwitch = {
        0: "Stopped",
        1: "Started",
        2: "Something went very wrong",
        3: "Starting",
        4: "Stopping",
        5: "ERROR",
        7: "Building"
    }
    return statSwitch[s]


def getDesc(t):
    t = t.lower().replace(" ", "_")
    with open(
            "./scenarios/prod/" + t + "/" + t + ".yml", "r"
    ) as yml:  # edurange_refactored/scenarios/prod
        document = yaml.full_load(yml)
        for item, doc in document.items():
            if item == "Description":
                d = doc
    return d


def getGuide2(t):
    # g = "No Codelab for this Scenario"
    t = t.lower().replace(" ", "_")
    with open(
            "./scenarios/prod/" + t + "/" + t + ".yml", "r"
    ) as yml:  # edurange_refactored/scenarios/prod
        document = yaml.full_load(yml)
        for item, doc in document.items():
            if item == "Codelab":
                g = doc
                # print(g)
                # return g
    # g = "No Codelab for this Scenario"
    return g


#
# host = os.getenv('HOST_EXTERN_ADDRESS', '127.0.0.1')
# g = host + "/tutorials/" + t + "/" + t + ".md"  # "#0"
# f = "./edurange_refactored/templates/tutorials/" + t + "/" + t + ".html"
# file = open(f, mode="r", encoding="utf-8")
# m = file.read()
# ht = m.replace('127.0.0.1', host)
# ht = md.markdown(m)


def getGuide(t):
    t = t.title().replace(" ", "_")
    f = "./edurange_refactored/templates/tutorials/" + t + "/" + t + ".md"
    lines = guideHelp1(f)
    htL = guideHelp2(lines)
    sections = []
    for lines in htL:
        lines = guideHelp3(lines)
        sections.append(lines)
    guide = guideHelp5(sections)
    # test
    #test = guideHelp3(htL[9])
    #test = guideHelp4(test, 4)
    return guide


def guideHelp1(f):
    # reads a md file into a list of lists divided by ---
    lines = []
    with open(f, mode="r", encoding="utf-8") as file:
        for line in file:
            lines.append(line)
    tmp = []
    lines2 = []
    for line in lines:
        if line == '---\n':
            # tmp.append(line)
            lines2.append(tmp)
            tmp = []
        else:
            tmp.append(line)
    return lines2


def guideHelp2(ls):
    # reads a list of lists of md and converts it to a list of lists of html
    new = []
    tmp = []
    for section in ls:
        for line in section:
            line = md.markdown(line)
            tmp.append(line)
        new.append(tmp)
        tmp = []
    return new


def guideHelp3(ls):
    # reads a list of html and separates it into a list of a head string and a content string
    h1 = '<h1>'
    h2 = '<h2>'
    h3 = '<h3>'
    col3 = 'class="colH3"'
    colSec = []
    section_head = ''
    hd = False
    c3 = False
    content = ''
    for line in ls:
        if not hd:
            if col3 in line:
                line = line.replace('<h2 class="colH3">', '').replace('</h2>', '')
                colSec.append(line)
                c3 = True
                hd = True
            if (h1 in line) or (h2 in line):
                section_head = line
                hd = True
        elif c3:
            if h3 in line:
                colSec.append(content)
                colSec.append(line)
                content = ''
            else:
                content = content + line
        else:
            content = content + line
    if c3:
        colSec.append(content)
        return colSec
    # section_head = section_head.replace('<h1>', '').replace('</h1>', '')
    section_head = section_head.replace('<h2>', '').replace('</h2>', '')
    return [section_head, content]


def guideHelp4(sec, num):
    # reads a list of section head and section content and creates a html card using the information
    head = sec[0]
    content = sec[1]
    if len(sec) > 2:
        content = guideHelp6(sec[1:], num)
    h_id = 'H' + str(num)
    b_id = 'B' + str(num)
    card = str("""
<div class="card">
    <div class="card-header" id="[HEADER_ID]">
        <div class="row">
            <h2> [SECTION_HEADER] <button class="btn btn-dark btn-sm ml-2" type="button" data-toggle="collapse" data-target="#[BODY_ID]" aria-expanded="false" aria-controls="[BODY_ID]">
                <i class="fa fa-caret-down"></i> </button></h2>
        </div>
    </div>
    <div id="[BODY_ID]" class="collapse" aria-labelledby="[HEADER_ID]" data-parent="#acc">
        <div class="card-body">
            [SECTION_CONTENT]
        </div>
    </div>
</div>

<hr>
""")
    card = card.replace('[SECTION_HEADER]', head).replace('[SECTION_CONTENT]', content)
    card = card.replace('[HEADER_ID]', h_id).replace('[BODY_ID]', b_id)
    return card


def guideHelp5(sections):
    #
    guide = ''
    accOpen = str("""
<div class="container" id="acc">
""")
    accClose = str("""
</div>
""")
    titleSec = '' + sections[0][0] + sections[0][1] + "<hr>"
    guide += titleSec + accOpen
    sections = sections[1:]
    num = 0
    for sec in sections:
        guide = guide + guideHelp4(sec, num)
        num += 1
    guide += accClose
    return guide


def guideHelp6(sec, num):
    h3 = '<h3>'
    count = 0
    h_id = 'H' + str(num) + '-'
    b_id = 'B' + str(num) + '-'
    content = ''
    secAcc = 'acc' + str(num)
    secAccOpen = str("""
<div class="container" id="[SEC_ACC]">
""")
    secAccClose = str("""
</div>
""")
    subCard = str("""
<div class="card">
    <div class="card-header" id="[HEADER_ID]">
        <div class="row">
            <h3> [SUBSECTION_HEADER] <button class="btn btn-dark btn-sm ml-2" type="button" data-toggle="collapse" data-target="#[BODY_ID]" aria-expanded="false" aria-controls="[BODY_ID]">
                <i class="fa fa-caret-down"></i> </button> </h3>
        </div>
    </div>
    <div id="[BODY_ID]" class="collapse" aria-labelledby="[HEADER_ID]" data-parent="#[SEC_ACC]">
        <div class="card-body">
            [SUBSECTION_CONTENT]
        </div>
    </div>
</div>
""")
    if h3 not in sec[0]:
        content += sec[0]
        sec = sec[1:]
    content += secAccOpen.replace('[SEC_ACC]', secAcc)
    for i in range(0, len(sec)):
        if h3 in sec[i]:
            tHd = sec[i].replace('<h3>', '').replace('</h3>', '')
            tmp = subCard
            tmp = tmp.replace('[HEADER_ID]', (h_id + str(count))).replace('[BODY_ID]', (b_id + str(count)))
            tmp = tmp.replace('[SUBSECTION_HEADER]', tHd).replace('[SUBSECTION_CONTENT]', sec[i+1])
            tmp = tmp.replace('[SEC_ACC]', secAcc)
            content += tmp
            count += 1
    content += secAccClose
    return content


def getPass(sn, un):
    sn = "".join(e for e in sn if e.isalnum())
    with open('./data/tmp/' + sn + '/students.json', 'r') as f:
        data = json.load(f)
        d1 = data.get(un)[0]
        p = d1.get('password')
    return p


def getQuestions(t):
    questions = {}
    t = t.lower().replace(" ", "_")
    with open(
            "./scenarios/prod/" + t + "/" + "questions.yml", "r"
    ) as yml:  # edurange_refactored/scenarios/prod
        document = yaml.full_load(yml)
        for item in document:
            #questions.append(item['Text'])
            questions[item['Order']] = item['Text']
    return questions


def getPort(n):
    n = 0  # [WIP]
    return n


def tempMaker(d, i):
    db_ses = db.session
    # status
    stat = db_ses.query(Scenarios.status).filter(Scenarios.id == d).first()
    stat = statReader(stat[0])
    # owner name
    oName = (
        db_ses.query(User.username).filter(Scenarios.id == d).filter(Scenarios.owner_id == User.id).first()
    )
    oName = oName[0]
    # description
    ty = db_ses.query(Scenarios.description).filter(Scenarios.id == d).first()
    ty = ty[0]
    desc = getDesc(ty)
    guide = getGuide(ty)
    questions = getQuestions(ty)
    # current_app.logger.info(questions) #--
    # scenario name
    sNom = db_ses.query(Scenarios.name).filter(Scenarios.id == d).first()
    sNom = sNom[0]
    if i == "ins":
        # creation time
        bTime = db_ses.query(Scenarios.created_at).filter(Scenarios.id == d).first()
        bTime = bTime[0]
        return stat, oName, bTime, desc, ty, sNom, guide, questions
    elif i == "stu":
        # username
        ud = current_user.id
        usr = db_ses.query(User.username).filter(User.id == ud).first()[0]
        usr = "".join(e for e in usr if e.isalnum())
        # password
        pw = getPass(sNom, usr)
        return stat, oName, desc, ty, sNom, usr, pw, guide, questions


# --


# def responseCheck(qnum, sid, resp):
#    # read correct response from yaml file
#    db_ses = db.session
#    s_name = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()
#    questions = questionReader(s_name[0])
#    for text in questions:
#        order = int(text['Order'])
#        if order == qnum:
#            ans = str(text['Values'][0]['Value'])
#    if resp == ans:
#        return True
#    else:
#        return False


def responseCheck(qnum, sid, resp, uid):
    # read correct response from yaml file
    db_ses = db.session
    s_name = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()
    questions = questionReader(s_name[0])
    for text in questions:
        order = int(text['Order'])  # get question number from yml file
        if order == qnum:
            if len(text['Values']) == 1:  # if there's only one correct answer in the yml file
                ans = str(text['Values'][0]['Value'])
                if "${" in ans:
                    ans = bashAnswer(sid, uid, ans)
                if resp == ans:
                    return int(text['Points'])
                elif ans == 'ESSAY':
                    return int(text['Points'])
                else:
                    return 0
            elif len(text['Values']) > 1:  # if there's multiple correct answers in the yml file
                yes = False
                for i in text['Values']:
                    ans = i['Value']
                    if "${" in ans:
                        ans = bashAnswer(sid, uid, ans)
                    if resp == ans:
                        yes = True
                if yes:
                    return int(i['Points'])
                else:
                    return 0


def bashAnswer(sid, uid, ans):
    db_ses = db.session
    uName = db_ses.query(User.username).filter(User.id == uid).first()[0]
    uName = "".join(e for e in uName if e.isalnum())
    sName = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()[0]
    if "${player.login}" in ans:
        students = open("./data/tmp/" + sName + "/students.json", "r")
        user = ast.literal_eval(students.read())
        username = user[uName][0]["username"]
        ansFormat = ans[0:6]
        newAns = ansFormat + username
        return newAns
    elif "${scenario.instances" in ans:
        wordIndex = ans[21:-1].index(".")
        containerName = ans[21:21+wordIndex]
        containerFile = open("./data/tmp/" + sName + "/" + containerName + ".tf.json", "r")
        content = ast.literal_eval(containerFile.read())
        index = content["resource"][0]["docker_container"][0][sName + "_" + containerName][0]["networks_advanced"]
        ans = ""
        for d in index:
            if d["name"] == (sName + "_PLAYER"):
                ans = d["ipv4_address"]
        return ans
    else:
        return ans


# --


def responseQuery(uid, att, query, questions):
    tableList = []
    tmpList = []
    for entry in query:
        if entry.user_id == uid and entry.attempt == att:
            tmpList.append(entry)

    for response in tmpList:
        qNum = response.question
        pts = response.points
        for text in questions:
            order = int(text['Order'])
            if order == qNum:
                quest = text['Text']
                poi = text['Points']
                val = text['Values'][0]['Value']
                sR = response.student_response
                dictionary = {'number': qNum, 'question': quest, 'answer': val, 'points': poi, 'student_response': sR, 'earned': pts}
                tableList.append(dictionary)
    return tableList


def responseSelector(resp):
    # response selector
    db_ses = db.session
    query = db_ses.query(Responses.id, Responses.user_id, Responses.scenario_id, Responses.attempt).all()
    for entry in query:
        if entry.id == int(resp):
            data = entry
            break
    return data


# -----

# scoring functions used in functions such as queryPolish()
# used as:
# scr = score(getScore(uid, att, query), questionReader(sName))

# required query entries:
# user_id, attempt, question, correct, student_response

'''
def getScore(usr, att, query):
    sL = []  # student response list
    for resp in query:
        if usr == resp.user_id and att == resp.attempt:
            sL.append({'question': resp.question, 'correct': resp.correct, 'response': resp.student_response})  # qnum, correct, student response
    return sL
'''


def totalScore(questions):
    tS = 0  # total number of possible points
    for text in questions:
        tS += int(text['Points'])
    return tS

'''
def score(scrLst, questions):
    sS = 0  # student score
    checkList = scoreSetup(questions)  # questions scored checklist
    for sR in scrLst:  # response in list of student responses
        if sR['correct']:
            num = int(sR['question'])  # question number
            for text in questions:
                if int(text['Order']) == num:
                    check, checkList = scoreCheck(num, checkList)
                    if not check:
                        if str(text['Type']) == "Multi String":
                            for i in text['Values']:
                                if i['Value'] == sR['response']:
                                    sS += int(text['Values'][i]['Points'])
                        else:
                            sS += int(text['Points'])
    scr = '' + str(sS) + ' / ' + str(totalScore(questions))
    return scr
'''


def scoreSetup(questions):
    checkList = {}  # list of question to be answered so duplicates are not scored
    for text in questions:
        if str(text['Type']) == "Multi String":
            # count = 1
            tmp = []
            for d in text['Values']:  # d is not used  # it's probably fine (possibly bad practice though)
                tmp.append(False)
                # k = str(text['Order']) + '.' + str(count)
                # checkList[k] = False
                # count += 1
            k = str(text['Order'])
            checkList[k] = tmp
        else:
            checkList[str(text['Order'])] = False
    # bloop()
    return checkList


# {'1': True, '2': False, ... , '6': [True, False, False, ...], '7': False}
#                                       0    1      2     ...

# if multi string, take student response into account to find the index within '6': [...] and mark true or false as normal


def scoreCheck(qnum, checkList):
    keys = list(checkList.keys())
    for k in keys:
        if k == str(qnum):
            if checkList[k]:
                return True, checkList  # answer has already been checked
            elif not checkList[k]:
                checkList[k] = True
                return False, checkList  # answer has not been checked before but is now checked
        elif str(qnum) in k and '.' in k:  # if multi string
            if checkList[k]:
                return True, checkList  # answer was already checked
            elif not checkList[k]:
                checkList[k] = True
                return False, checkList  # answer was not checked before but is now
        #elif str(qnum) in k:
            #flash("Could not check question {0} with key {1}".format(qnum, k))

    return False, checkList


def scoreCheck2(qnum, checkList, resp, quest):
    keys = list(checkList.keys())
    for k in keys:
        if k == str(qnum):
            if type(checkList[k]) == list:  # if multi string
                return False
                # check stu_resp against q.yml
                #   if stu_resp in q.yml
                #       if i in q.yml = false in checkList[k][i]
                #           return true
                #       else
            elif type(checkList[k]) == bool:    # if NOT a multi string
                if checkList[k]:
                    return True, checkList  # answer has already been checked
            elif not checkList[k]:
                checkList[k] = True
                return False, checkList  # answer has not been checked before but is now checked


# query(Responses.user_id, Responses.attempt, Responses.question, Responses.points, Responses.student_response)
# .filter(Responses.scenario_id == sid).filter(Responses.user_id == uid).filter(Responses.attempt == att).all()
#     |
#     V


def score(uid, att, query, questions):
    stuScore = 0
    checkList = scoreSetup(questions)
    for resp in query:
        if resp.user_id == uid and resp.attempt == att:     # if response entry matches uid and attempt number
            if resp.points > 0:                             # if the student has points i.e. if the student answered correctly
                qNum = int(resp.question)
                check, checkList = scoreCheck(qNum, checkList)      # check against checkList with question number
                if not check:
                    stuScore += resp.points
    scr = '' + str(stuScore) + ' / ' + str(totalScore(questions))
    return scr
# -----


def questionReader(name):
    name = "".join(e for e in name if e.isalnum())
    with open(
            "./data/tmp/" + name + "/questions.yml", "r"
    ) as yml:
        document = yaml.full_load(yml)
    return document


def queryPolish(query, sName):
    qList = []
    for entry in query:
        i = entry.id
        uid = entry.user_id
        att = entry.attempt
        usr = entry.username
        if qList is None:
            scr = score(uid, att, query, questionReader(sName))  # score(getScore(uid, att, query), questionReader(sName))
            d = {'id': i, 'user_id': uid, 'username': usr, 'score': scr, 'attempt': att}
            qList.append(d)
        else:
            error = 0
            for lst in qList:
                if uid == lst['user_id'] and att == lst['attempt']:
                    error += 1
            if error == 0:
                scr = score(uid, att, query, questionReader(sName))  # score(getScore(uid, att, query), questionReader(sName))
                d = {'id': i, 'user_id': uid, 'username': usr, 'score': scr, 'attempt': att}
                qList.append(d)
    return qList


def responseProcessing(data):
    # response info getter
    db_ses = db.session
    # user info
    uid = data.user_id
    uname = db_ses.query(User.username).filter(User.id == uid).first()
    uname = uname[0]
    # scenario info
    sid = data.scenario_id
    sname = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()
    sname = sname[0]
    # response info
    att = data.attempt
    return uid, uname, sid, sname, att


def setAttempt(sid):
    db_ses = db.session
    currAtt = db_ses.query(Scenarios.attempt).filter(Scenarios.id == sid).first()
    if currAtt[0] == 0:
        att = 1
    else:
        att = int(currAtt[0]) + 1
    return att


def getAttempt(sid):
    db_ses = db.session
    query = db_ses.query(Scenarios.attempt).filter(Scenarios.id == sid)
    return query


# returns dictionary of lines with common keyIndex values


def readScenario():
    scenarios = [
        dI
        for dI in os.listdir("./scenarios/prod/")
        if os.path.isdir(os.path.join("./scenarios/prod/", dI))
    ]
    desc = []
    for s in scenarios:
        desc.append(getDesc(s))
    return 0


def recentCorrect(uid, qnum, sid):
    db_ses = db.session
    recent = db_ses.query(Responses.points).filter(Responses.user_id == uid).filter(Responses.scenario_id == sid)\
        .filter(Responses.question == qnum).order_by(Responses.response_time.desc()).first()
    return recent


def displayCorrect(sName, uName):
    db_ses = db.session
    uid = db_ses.query(User.id).filter(User.username == uName).first()
    sid = db_ses.query(Scenarios.id).filter(Scenarios.name == sName).first()
    questions = questionReader(sName)
    ques = {}
    for text in questions:
        order = int(text['Order'])
        rec = recentCorrect(uid, order, sid)
        if rec is not None:
            rec = rec[0]
        ques[order] = rec
    return ques


def displayProgress(sid, uid):
    db_ses = db.session
    att = getAttempt(sid)
    sName = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()
    query = db_ses.query(Responses.attempt, Responses.question, Responses.points, Responses.student_response, Responses.scenario_id, Responses.user_id)\
        .filter(Responses.scenario_id == sid).filter(Responses.user_id == uid).all()
    questions = questionReader(sName.name)
    answered, tQuest = getProgress(query, questions)
    scr, tScr = calcScr(uid, sid, att)  # score(uid, att, query, questionReader(sName))  # score(getScore(uid, att, query), questionReader(sName))
    progress = {'questions': answered, 'total_questions': tQuest, 'score': scr, 'total_score': tScr}
    return progress


def calcScr(uid, sid, att):
    score = 0
    db_ses = db.session
    sName = db_ses.query(Scenarios.name).filter(Scenarios.id == sid).first()
    query = db_ses.query(Responses.points, Responses.question).filter(Responses.scenario_id == sid).filter(Responses.user_id == uid)\
        .filter(Responses.attempt == att).order_by(Responses.response_time.desc()).all()
    checkList = scoreSetup(questionReader(sName.name))
    for r in query:
        check, checkList = scoreCheck(r.question, checkList)
        if not check:
            score += int(r.points)
    # score = '' + str(score) + ' / ' + str(totalScore(questionReader(sName)))
    tScore = totalScore(questionReader(sName.name))
    return score, tScore


def getProgress(query, questions):
    checkList = scoreSetup(questions)
    corr = 0
    total = list(checkList.keys())[-1]
    for resp in query:
        if int(resp.points) > 0:
            q = int(resp.question)
            check, checkList = scoreCheck(q, checkList)
            if not check:
                corr += 1
    # progress = "" + str(corr) + " / " + str(total)
    return corr, total

