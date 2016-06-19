# jira-warden

Python app for tending for JIRA Software issues and sprint boards.

Copy `config-sample.py` to `config.py`, edit according to your project needs and run the script:

    python jira-warden.py sprint_daily_update_worklogs_and_remaining

Features:

 - adding default subtasks to issues to make story-based swimlanes nice,
 - adding worklogs to issues automatically,
 - setting time-based estimates from points,
 - setting remaining to zero for issues when work is completed etc.

Available commands:

 - `issue_add_default_subtask`
 - `issue_add_worklog`
 - `issue_set_original_estimate_from_points`
 - `sprint_daily_update_worklogs_and_remaining`
 - `sprint_set_estimates_from_points`
 - `sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points`

Run

 - `sprint_daily_update_worklogs_and_remaining` daily in the evening with a scheduled job,
 - `sprint_verify_subtasks_exist_and_set_subtask_estimates_from_points` at the start of the sprint.

