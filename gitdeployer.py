#!/usr/bin/env python3
#
# gitdeployer.py - simple script that listens for triggering http calls and
#                  initiate git based deploys from it.
#

from flask import Flask, request, abort
import configparser
import netaddr
import os
import subprocess
import sys
import re

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

class ReloadingConfigParser(object):
    def __init__(self, filename):
        self.filename = filename
        self._load()

    def _load(self):
        self.loadtime = os.stat(self.filename).st_mtime
        self.parser = configparser.ConfigParser()
        self.parser.read(self.filename)

    def __getattr__(self, name):
        return getattr(self.parser, name)

    def refresh(self):
        if os.stat(self.filename).st_mtime != self.loadtime:
            eprint("Reloading configuration")
            self._load()

def run_command(reponame, *command):
    # We don't bother with the actual output
    s = subprocess.Popen(command, cwd=cfg.get(reponame, 'root'))
    s.wait(10)
    if s.returncode != 0:
        raise Exception("Command {0} returned {1}".format(command[0], s.returncode))

def git_operation(reponame, *operations):
    run_command(reponame, '/usr/bin/git', *operations)

cfg = ReloadingConfigParser('gitdeployer.ini')
app = Flask('gitdeployer')

deploystatic = cfg.get('global', 'deploystatic')


@app.route("/deploy/<repository>/<key>", methods=['GET', 'POST'])
def deploy(repository, key):
    cfg.refresh()

    if cfg.has_section(repository):
        # Change * back into * if for some reason it was used for a
        # non-branch repository
        reporeplace = '*'
    else:
        (base, branch) = repository.split('-', 1)
        if cfg.has_section('{0}-*'.format(base)):
            repository = '{0}-*'.format(base)
            reporeplace = branch

            # Verify this repo type can handle
            _replaceable_types = ['pgeubranch', ]
            if cfg.get(repository, 'type') not in _replaceable_types:
                return "Replacement paths only supported for {0}".format(', '.join(-replaceable_types))

            if not re.match('^[a-z0-9]+$', branch):
                return "Invalid character(s) in branch name '{0}'".format(branch)
        else:
            return "Repo not found", 404
    for k in 'key', 'type', 'root':
        if not cfg.has_option(repository, k):
            eprint("Repository {0} is missing key {1}".format(repository, k))
            return "Repo misconfigured", 500
    if not cfg.get(repository, 'key') == key:
        return "Invalid key", 401

    # We only do git, so verify that the root is a dictionary
    if not os.path.isdir("{0}/.git".format(cfg.get(repository, 'root'))):
        eprint("Repository {0} has a root {1} that is not a git repository".format(
            repository, cfg.get(repository, 'root')))
        return "Not a git repo", 500

    try:
        if cfg.get(repository, 'type') == 'django':
            # Basic django repository. For this repo type, we do a git pull. If something
            # has changed, we count on the uwsgi process to reload the app.
            # XXX: in the future, consider doing automatic migration?
            git_operation(repository, 'pull', '--rebase')
        elif cfg.get(repository, 'type') == 'static':
            # This is just a pure static checkout
            git_operation(repository, 'pull', '--rebase')
        elif cfg.get(repository, 'type') == 'pgeustatic':
            # For pgeu static, we pull the git repo and then deploy from there.
            # The correct branch has to be checked out.
            for k in 'target', :
                if not cfg.has_option(repository, k):
                    eprint("Repository {0} is missing key {1}".format(repository, k))
                    return "Repo misconfigured", 500

            git_operation(repository, 'pull', '--rebase')
            run_command(repository, deploystatic,
                        cfg.get(repository, 'root'),
                        cfg.get(repository, 'target'),
            )
            if cfg.has_option(repository, 'templates'):
                run_command(repository, deploystatic, '--templates',
                            cfg.get(repository, 'root'),
                            cfg.get(repository, 'templates'),
                )
        elif cfg.get(repository, 'type') == 'pgeubranch':
            # For pgeu branch, we fetch the git repository and then deploy directly from
            # that using a tar export.
            for k in 'target', 'branch' :
                if not cfg.has_option(repository, k):
                    eprint("Repository {0} is missing key {1}".format(repository, k))
                    return "Repo misconfigured", 500

            git_operation(repository, 'fetch')
            run_command(repository, deploystatic,
                        cfg.get(repository, 'root'),
                        cfg.get(repository, 'target').replace('*', reporeplace),
                        '--branch',
                        cfg.get(repository, 'branch').replace('*', reporeplace),
            )
            if cfg.has_option(repository, 'templates'):
                run_command(repository, deploystatic, '--templates',
                            cfg.get(repository, 'root'),
                            cfg.get(repository, 'templates').replace('*', reporeplace),
                            '--branch',
                            cfg.get(repository, 'branch').replace('*', reporeplace),
                )
        else:
            eprint("Repository {0} has an invalid type {1}".format(
                repository, cfg.get(repository, 'type')))
            return "Invalid git repo type", 500
    except Exception as e:
        eprint("Failed to update {0}: {1}".format(repository, e))
        return "Internal error", 500

    eprint("Deployed repository {0}".format(repository))
    return "OK"

@app.before_request
def limit_remote_addr():
    cfg.refresh()
    for a in cfg.get('global', 'sources').split():
        if netaddr.IPAddress(request.remote_addr) in netaddr.IPNetwork(a):
            return
    abort(403)

if __name__ == "__main__":
    addresses = [netaddr.IPNetwork(c) for c in cfg.get('global', 'sources').split()]

    app.run(debug=cfg.get("global", "debug", fallback=False),
            host=cfg.get("global", "bindhost", fallback="127.0.0.1"),
            port=cfg.getint('global', 'port'))
