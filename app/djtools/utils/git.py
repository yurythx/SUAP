import os
import subprocess

from django.conf import settings

__all__ = [
    'diff',
    'diff2',
    'modified_apps',
    'modified_files',
]


def diff(branch):
    cmd = f'git merge-base origin/master {branch}'
    previous_commit = subprocess.run(cmd.split(' '), capture_output=True, check=False).stdout.decode('utf-8').strip()
    cmd = f'git diff {previous_commit} --name-only'
    return subprocess.run(cmd.split(' '), capture_output=True, check=False).stdout.decode('utf-8').strip()


def diff2(branch):
    cmd = f'git diff origin/master origin/{branch} --name-only'
    result = subprocess.run(cmd.split(' '), capture_output=True, check=False)
    stdout = result.stdout.decode('utf-8')
    return stdout


def modified_files(branch, pattern=None, exists_only=False):
    diff_content = diff(branch).strip()
    files = diff_content.split('\n') if diff_content else []
    if pattern:
        files = [f for f in files if pattern in f]
    if exists_only:
        files = [f for f in files if os.path.exists(f)]
    return files


def modified_apps(branch, pattern=None, exists_only=False):
    apps = []
    tokens = set()
    for file_path in modified_files(branch, pattern=pattern, exists_only=exists_only):
        tokens.add(file_path.split('/')[0])
    for token in tokens:
        if token in settings.INSTALLED_APPS:
            apps.append(token)
    return apps
