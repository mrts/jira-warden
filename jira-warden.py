# encoding: utf-8
"""
jira-warden: script for tending for JIRA Software issues and sprint boards.

Copy config-sample.py to config.py and edit according to your project needs
before running the script.

Features:

 - adding default subtasks to issues to make story-based swimlanes nice,
 - adding worklogs to issues automatically,
 - setting time-based estimates from points,
 - setting remaining to zero for issues when work is completed etc.

Run

 - `sprint_daily_update_worklogs_and_remaining` daily in the evening with a
    scheduled job,
 - `sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points` at
    the start of the sprint.
"""
from __future__ import print_function
import base64
import contextlib
import datetime
import inspect
import json
import pprint
import sys
import urllib2
import warnings
from decimal import Decimal

from config import JIRA, PERSON_WEEKLY_WORKDAYS


def _main():
    command = _get_command()
    command()


def issue_show_raw():
    message = "Showing raw data"

    def script():
        issue = _get_issue_from_args(message)
        pprint.pprint(issue)

    _run_with_exception_check(script, message)


def issue_add_default_subtask():
    message = "Adding default subtask"

    def script():
        issue = _get_issue_from_args(message)
        subtask = _add_default_subtask(issue)
        print('Subtask {subtask[key]} added to issue {issue[key]}'.format(**locals()))

    _run_with_exception_check(script, message)


def _add_default_subtask(issue):
    data = {"fields": {
        "parent": {"id": issue['id']},
        "project": {"id": issue['fields']['project']['id']},
        "issuetype": {"id": JIRA['subtask_issuetype_id']},
        "summary": issue['fields']['summary'],
        "description": issue['fields']['description'] or " ",
    }}
    if issue['fields'][JIRA['storypoints_field']]:
        data[JIRA['storypoints_field']] = issue['fields'][JIRA['storypoints_field']],
    return _request_jira('issue', 'POST', data)


def issue_add_worklog():
    message = "Adding worklog"

    def script():
        issue = _get_issue_from_args(message)
        hours = JIRA['daily_workhours'] if len(sys.argv) < 4 else sys.argv[3]
        _add_worklog(issue, hours)
        print('Worklog of {hours} added to issue {issue[key]}'.format(**locals()))

    _run_with_exception_check(script, message)


def _add_worklog(issue, hours):
    assignee = issue['fields']['assignee']['displayName']
    data = {
        'started': _10am_today(),
        'timeSpent': hours,
        'comment': 'Worklog added automatically by jira-warden '
                   'script for *{assignee}*'.format(**locals()),
    }
    return _request_jira('issue/{key}/worklog'.format(**issue), 'POST', data)


def _10am_today():
    today = datetime.date.today()
    ten_am = datetime.time(10, 0)
    timezone_offset = JIRA['timezone_offset']
    return '{today}T{ten_am}.000+{timezone_offset}'.format(**locals())


def issue_set_original_estimate_from_points():
    message = "Setting original estimate from points"

    def script():
        issue = _get_issue_from_args(message)
        points, hours = _set_original_estimate_from_points(issue)
        _print_set_estimate_from_points_message(points, hours, issue)

    _run_with_exception_check(script, message)


def _set_original_estimate_from_points(issue):
    points = issue['fields'][JIRA['storypoints_field']]
    if not points:
        warnings.warn("Issue {key} has no points, won't update estimates".format(**issue))
        return None, None
    points = Decimal(points)
    hours = points * JIRA['storypoints_to_hours_coefficient']
    data = {'update': {
        "timetracking": [{"edit": {"originalEstimate": "{}h".format(hours)}}],
    }}
    _request_jira('issue/{key}'.format(**issue), 'PUT', data, expect_response=False)
    return points, hours


def _print_set_estimate_from_points_message(points, hours, issue):
    message = ('Issue {issue[key]} original estimate set to {hours} hours from {points} points'
               if points is not None else
               'Issue {issue[key]} has no points, original estimate not updated')
    print(message.format(**locals()))

def sprint_set_estimates_from_points():
    message = 'Setting estimates from points'

    def script():
        sprint_issues = _get_issues_of_sprint_from_args(message, subtasks=False)
        issues_with_subtasks = [issue for issue in sprint_issues
                                if issue['fields']['subtasks']]
        _set_subtasks_original_estimate_from_points(issues_with_subtasks)
        issues_without_subtasks = [issue for issue in sprint_issues
                                if not issue['fields']['subtasks']]
        for issue in issues_without_subtasks:
            points, hours = _set_original_estimate_from_points(issue)
            _print_set_estimate_from_points_message(points, hours, issue)
        print('Estimate update completed')

    _run_with_exception_check(script, message)

def sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points():
    message = 'Verifying that subtasks exist and setting subtask estimates from points'

    def script():
        sprint_issues = _get_issues_of_sprint_from_args(message, subtasks=False)
        refetch = _verify_subtasks_exist(sprint_issues)
        if refetch:
            sprint_issues = _get_issues_of_sprint_from_args(message, subtasks=False)
        _set_subtasks_original_estimate_from_points(sprint_issues)
        print('Subtask verification and estimate update completed')

    _run_with_exception_check(script, message)


def _verify_subtasks_exist(issues):
    refetch = False
    for issue in issues:
        if not issue['fields']['subtasks']:
            warnings.warn('Issue {key} does not have subtasks, adding default'.format(**issue))
            _add_default_subtask(issue)
            refetch = True
        else:
            print('OK, issue {key} has subtasks'.format(**issue))
    return refetch


def _set_subtasks_original_estimate_from_points(issues):
    for issue in issues:
        if issue['fields']['subtasks']:
            for subtask in issue['fields']['subtasks']:
                subissue = _request_jira('issue/{key}'.format(**subtask))
                points, hours = _set_original_estimate_from_points(subissue)
                _print_set_estimate_from_points_message(points, hours, subissue)
        else:
            raise RuntimeError("Issue {key} does not have subtasks".format(**issue))


def sprint_daily_update_worklogs_and_remaining():
    message = 'Updating worklogs and remaining'

    def script():
        sprint_tasks = _get_issues_of_sprint_from_args(message, subtasks=True)
        in_progress = [issue for issue in sprint_tasks
                       if issue['fields']['status']['name'] in JIRA['status_in_progress']]
        issue = None
        for issue in in_progress:
            if not issue['fields']['assignee']:
                warnings.warn('Issue {key} is in progress but has no assignee'.format(**issue))
                continue
            if _person_works_today(issue['fields']['assignee']['displayName']):
                print('Adding worklog to {key}'.format(**issue))
                _add_worklog(issue, JIRA['daily_workhours'])
            else:
                print('Not adding worklog to {key}, developer away today'.format(**issue))
        if issue is None:
            print('No issues in progress')
        work_done = [issue for issue in sprint_tasks
                     if issue['fields']['status']['name'] in JIRA['status_work_done']]
        issue = None
        for issue in work_done:
            print('Issue {key} work is done, setting remaining to zero'.format(**issue))
            _set_remaining_to_zero(issue)
        if issue is None:
            print('No issues are done')
        print('Worklog and remaining update completed')

    _run_with_exception_check(script, message)


def _person_works_today(name):
    if name not in PERSON_WEEKLY_WORKDAYS:
        warnings.warn("'{}' is not listed in weekly workday list".format(name))
        return False
    return datetime.date.today().isoweekday() in PERSON_WEEKLY_WORKDAYS[name]


def _set_remaining_to_zero(issue):
    data = {'update': {
        "timetracking": [{"edit": {"remainingEstimate": "0"}}],
    }}
    _request_jira('issue/{key}'.format(**issue), 'PUT', data, expect_response=False)


def _get_issue_from_args(message):
    if len(sys.argv) < 3:
        print("Issue key argument required", file=sys.stderr)
        exit(1)
    issue_key = sys.argv[2]
    print(message + ' to issue {}'.format(issue_key))
    return _request_jira('issue/{}'.format(issue_key))


def _get_issues_of_sprint_from_args(message, subtasks):
    sprint = 'openSprints()' if len(sys.argv) < 3 else '"{}"'.format(sys.argv[2])
    print(message + ' in sprint {}'.format(sprint))
    sprint_tasks = _get_sprint_issues(sprint, subtasks)['issues']
    if not sprint_tasks:
        print("No issues in sprint, nothing to do")
        exit(1)
    return sprint_tasks


def _get_sprint_issues(sprint, subtasks):
    jql = 'project = {project} AND sprint IN ({sprint}) AND issuetype {maybe_not}in subTaskIssueTypes()'
    jql = jql.format(project=JIRA['project'], sprint=sprint, maybe_not='' if subtasks else 'not ')
    jql = urllib2.quote(jql)
    max_results = 500  # arbitrary limit
    # fields = "summary,description" etc?
    return _request_jira('search?jql={jql}&maxResults={max_results}'.format(**locals()))


def _request_jira(api_endpoint, method=None, data=None, expect_response=True):
    url = '{server}/rest/api/2/{api_endpoint}'.format(api_endpoint=api_endpoint, **JIRA)
    if data:
        data = json.dumps(data)
    encoded_credentials = base64.encodestring('{user}:{password}'.format(**JIRA)).strip()
    headers = {
        'Authorization': 'Basic {0}'.format(encoded_credentials),
        'Content-Type': 'application/json'
    }
    request = urllib2.Request(url, data, headers)
    if method:
        request.get_method = lambda: method
    with contextlib.closing(urllib2.urlopen(request)) as response:
        return json.load(response) if expect_response else None


def _run_with_exception_check(script, errormessage):
    try:
        script()
    except urllib2.HTTPError as e:
        print(errormessage + ' failed:')
        print(e)
        print(e.read())


def _get_command():
    if len(sys.argv) < 2:
        _print_help_and_exit()
    command = sys.argv[1]
    if not command[0].isalpha():
        _print_help_and_exit()
    if command not in globals():
        print("Invalid command: {0}\n".format(command), file=sys.stderr)
        _print_help_and_exit()
    command = globals()[command]
    return command


def _print_help_and_exit():
    print(__doc__)
    print('Available commands:\n\n - {}'.format(_list_commands()))
    sys.exit(1)


def _list_commands():
    sorted_globals = globals().items()
    sorted_globals.sort()
    commands = [var for var, obj in sorted_globals
                if not var.startswith('_')
                and inspect.isfunction(obj)]
    # commands = [(var, obj.__doc__) for var, obj in sorted_globals ...
    # "\n".join("'{0}': {1}".format(name, doc) for name, doc in commands)
    return "\n - ".join(commands)


if __name__ == '__main__':
    _main()
