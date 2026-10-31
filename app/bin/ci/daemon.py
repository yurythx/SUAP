#!python3
import datetime
import os
import subprocess
import sys
import time
import traceback

import requests

PROJECT_ID = os.environ.get('PROJECT_ID', '8')
GITLAB_URL = os.environ.get('GITLAB_URL', 'https://gitlab.ifrn.edu.br/')
ACCESS_TOKEN = os.environ.get('GITLAB_ACCESS_TOKEN')
REMOTE_RUNNERS = os.environ.get('REMOTE_RUNNERS', '')
CHECK_CODE_JOB_NAME = 'checagem-codigo'
CLOSE_MRS_GROUP = os.environ.get('CLOSE_MRS_GROUP', 'cosinf-devops')


def log(text, indent=0):
    if indent:
        print('{}{}'.format('    ' * indent, text))
    else:
        print(datetime.datetime.now().strftime('%d/%m/%Y %H:%M'), text)


def main():
    headers = {'PRIVATE-TOKEN': ACCESS_TOKEN}
    # get last merge time of "master" branch
    url = f'{GITLAB_URL}api/v4/projects/{PROJECT_ID}/merge_requests?state=merged&target_branch=master&per_page=1'
    response = requests.get(
        url,
        headers=headers,
        timeout=240,
    )
    last_merge = response.json()[0]
    merged_at = last_merge['merged_at'][0:16] if last_merge['merged_at'] else last_merge['updated_at'][0:16]
    last_merge['merged_at'] = datetime.datetime.fromisoformat(merged_at)
    log('Last merge occurred at {}'.format(last_merge['merged_at'].strftime('%d/%m/%Y %H:%M')))
    # list running test containers
    running_containers = {}
    for remote in REMOTE_RUNNERS.split(','):
        cmd = 'docker ps -a --format {{.Names}} --filter ancestor=suap-test'
        output = subprocess.check_output(['ssh', remote, f'{cmd}'] if remote else cmd.split()).decode().strip()
        running_containers[remote] = output.split('\n') if output else []
        log('Containers running in {}: {}'.format(remote or 'local computer', ', '.join(running_containers[remote])))
    # list open merge requests
    url = f'{GITLAB_URL}api/v4/projects/{PROJECT_ID}/merge_requests?state=opened&per_page=20'
    response = requests.get(
        url,
        headers=headers,
        timeout=240,
    )
    mrs = response.json()
    log(f'There are {len(mrs)} MRs waiting to be merged.')

    # retrieve members of group cosinf-devops
    url = f'{GITLAB_URL}api/v4/groups/{CLOSE_MRS_GROUP}/members/?per_page=50'
    response = requests.get(
        url,
        headers=headers,
        timeout=240,
    )
    close_mrs_group_members = [member['username'] for member in response.json()]
    log(f'Users of {CLOSE_MRS_GROUP} group: "{close_mrs_group_members}"')

    # retrieve jobs of open merge requests
    active_job_ids = []
    for mr in mrs:
        updated_at = datetime.datetime.strptime(mr['updated_at'], '%Y-%m-%dT%H:%M:%S.%f%z').replace(tzinfo=None)
        # close mr if older than 7 days and authors
        if updated_at < datetime.datetime.now() - datetime.timedelta(days=7):
            url = '{}api/v4/projects/{}/merge_requests/{}/notes'.format(GITLAB_URL, PROJECT_ID, mr['iid'])
            requests.post(
                url,
                data={'body': 'Automatically closing because the last update was more then 7 days ago...'},
                headers=headers,
                timeout=240,
            )
            url = '{}api/v4/projects/{}/merge_requests/{}'.format(GITLAB_URL, PROJECT_ID, mr['iid'])
            requests.put(
                url,
                data={'state_event': 'close'},
                headers=headers,
                timeout=240,
            )
            log('Closing #{} because the last update was 7 days ago...'.format(mr['iid']))
        # get last pipeline of the merge request
        url = '{}api/v4/projects/{}/merge_requests/{}/pipelines?per_page=1'.format(GITLAB_URL, PROJECT_ID, mr['iid'])
        response = requests.get(
            url,
            headers=headers,
            timeout=240,
        )
        if response.json():
            mr['pipeline'] = response.json()[0]
            # get the jobs of the last pipeline
            url = '{}api/v4/projects/{}/pipelines/{}/jobs'.format(GITLAB_URL, PROJECT_ID, mr['pipeline']['id'])
            response = requests.get(
                url,
                headers=headers,
                timeout=240,
            )
            mr['jobs'] = response.json()
            ids = []
            for job in mr['jobs']:
                ids.append(str(job['id']))
                active_job_ids.append(job['id'])
            log('- {}: {}'.format(mr['iid'], mr['title']), indent=1)
            log('- Upvotes: {}'.format(mr['upvotes']), indent=2)
            log('- Pipeline: {}'.format(mr['pipeline']['id']), indent=2)
            log('- Jobs: {}'.format(' '.join(ids)), indent=2)
    # stop and remove unnecessary containers
    for remote, container_names in running_containers.items():
        for container_name in container_names:
            job_id = container_name.split('-')[-1]
            if job_id.isdigit() and int(job_id) not in active_job_ids:
                cmd = f'docker rm -f {container_name}'
                log('Stopping and removing container "{}" associated to job {} in {}.'.format(container_name, job_id, remote or 'local computer'))
                if '--preview' not in sys.argv:
                    url = f'{GITLAB_URL}api/v4/projects/{PROJECT_ID}/jobs/{job_id}/cancel'
                    requests.post(
                        url,
                        headers=headers,
                        timeout=240,
                    )
                    subprocess.check_output(['ssh', remote, f'{cmd}'] if remote else cmd.split())
    # sorte merge requests by when succeeds and upvotes
    mrs = sorted(mrs, key=lambda mr: (-mr['merge_when_pipeline_succeeds'], -mr['upvotes']))
    # proccess every upvoted merge request
    for mr in mrs:
        if mr['draft']:
            log('Skipping "{}" because its a draft.'.format(mr['title']))
        elif mr['work_in_progress']:
            log('Skipping "{}" because it is in progress.'.format(mr['title']))
        elif mr['merge_when_pipeline_succeeds'] or mr['upvotes']:
            url = '{}api/v4/projects/{}/repository/branches/{}'.format(GITLAB_URL, PROJECT_ID, mr['source_branch'])
            response = requests.get(
                url,
                headers=headers,
                timeout=240,
            )
            branch = response.json()
            last_update = datetime.datetime.fromisoformat(branch['commit']['committed_date'][0:16])
            log(
                'Monitoring MR "{}" to branch "{}" last updated at {}.'.format(
                    mr['title'],
                    mr['target_branch'],
                    last_update.strftime('%d/%m/%Y %H:%M'),
                )
            )
            check_code_status = None
            for job in mr['jobs']:
                if job['name'] == CHECK_CODE_JOB_NAME:
                    check_code_status = job['status']
            if check_code_status == 'success':
                pending = [job['name'] for job in mr['jobs']]
                for job in mr['jobs']:
                    log(
                        '- Job "{}" with id {} of pipeline {} is with "{}" status.'.format(
                            job['name'], job['id'], job['pipeline']['id'], job['status']
                        ),
                        indent=1,
                    )
                    if job['status'] == 'created' or job['status'] == 'manual':
                        action = 'play'
                        log(
                            'Starting "{}" for the first time.'.format(job['name']),
                            indent=2,
                        )
                    elif job['status'] == 'pending':
                        action = None
                        log(
                            'Waiting "{}" to start execution.'.format(job['name']),
                            indent=2,
                        )
                    elif job['status'] == 'running':
                        action = None
                        log(
                            'Waiting "{}" to finish execution.'.format(job['name']),
                            indent=2,
                        )
                    else:
                        started_at = datetime.datetime.fromisoformat(job['started_at'][0:-1])
                        if started_at < last_update:
                            action = 'retry'
                            log(
                                'Retrying {} executed at {} due to branch update at {}.'.format(
                                    job['name'],
                                    started_at.strftime('%d/%m/%Y %H:%M'),
                                    last_update.strftime('%d/%m/%Y %H:%M'),
                                ),
                                indent=2,
                            )
                        elif started_at < last_merge['merged_at']:
                            action = 'retry'
                            log(
                                'Retrying {} executed at {} due to merge in master at {}.'.format(
                                    job['name'],
                                    started_at.strftime('%d/%m/%Y %H:%M'),
                                    last_merge['merged_at'].strftime('%d/%m/%Y %H:%M'),
                                ),
                                indent=2,
                            )
                        elif job['status'] != 'success':
                            action = 'retry'
                            log(
                                'Retrying {} because its status is {}'.format(job['name'], job['status']),
                                indent=2,
                            )
                        else:
                            action = None
                            pending.remove(job['name'])
                            log(
                                'Skipping "{}" because it is successfully executed and up-to-date.'.format(job['name']),
                                indent=2,
                            )
                    if action:
                        url = '{}api/v4/projects/{}/jobs/{}/{}'.format(GITLAB_URL, PROJECT_ID, job['id'], action)
                        if '--preview' not in sys.argv:
                            requests.post(
                                url,
                                headers=headers,
                                timeout=240,
                            )
                if pending:
                    break
                else:
                    log('Monitoring next MR because "{}" has no pending job.'.format(mr['title']))
            elif check_code_status == 'running':
                log(f'Waiting "{CHECK_CODE_JOB_NAME}" to succeed.', indent=1)
                break
            else:
                log(f'Waiting "{CHECK_CODE_JOB_NAME}" to (re)-execute.', indent=1)
                break


if __name__ == '__main__':
    if '--loop' in sys.argv:
        try:
            log('Starting infinite looping...')
            while True:
                hour = datetime.datetime.now().hour
                if 7 < hour < 22:
                    try:
                        main()
                    except Exception:
                        print(traceback.format_exc())
                time.sleep(5 * 60)
        except KeyboardInterrupt:
            print('Bye! :)')
    else:
        main()
