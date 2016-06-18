#!/bin/bash

echo '--------------------'
echo 'Checking success cases'

python jira-warden.py issue_add_worklog AIAFT-1
python jira-warden.py issue_add_worklog AIAFT-1 5h

python jira-warden.py issue_add_default_subtask AIAFT-1

python jira-warden.py sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points 'AIAFT Sprint 1'

python jira-warden.py sprint_daily_update_worklogs_and_remaining

echo '--------------------'
echo 'Checking error cases'

python jira-warden.py issue_add_worklog INVALID
python jira-warden.py issue_add_worklog AIAFT-1 INVALID
python jira-warden.py issue_add_default_subtask INVALID
python jira-warden.py sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points INVALID
python jira-warden.py sprint_daily_update_worklogs_and_remaining INVALID
