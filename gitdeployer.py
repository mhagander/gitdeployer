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
    s = subprocess.Popen(command, cwd=cfg.get(reponame, 'root'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    s.wait(10)
    if s.returncode != 0:
        raise Exception("Command {0} returned {1}".format(" ".join(command), s.returncode))
    return [l.decode('utf8', errors='ignore').rstrip() for l in s.stdout.readlines()]

def run_command_conditional(reponame, *command):
    s = subprocess.Popen(command, cwd=cfg.get(reponame, 'root'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    s.wait(10)
    out = "\n".join([l.decode('utf8', errors='ignore').rstrip() for l in s.stdout.readlines()])
    if cfg.has_option(reponame, 'hideoutput') and cfg.get(reponame, 'hideoutput') == '1':
        out=''

    return (s.returncode == 0, out)

def pipe_command(reponame, pipedata, *command):
    s = subprocess.Popen(command, cwd=cfg.get(reponame, 'root'), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    outs, errs = s.communicate(pipedata.encode('utf8'))
    if s.returncode != 0:
        raise Exception("Command {0} returned {1}".format(" ".join(command), s.returncode))
    return [l.decode('utf8', errors='ignore').rstrip() for l in outs.splitlines()]

# Regexp that matches the "fetched branch" lines in git output and captures the
# branch names and start/end revisions from it.
re_revs = re.compile('\s{3}([a-z0-9]+\.\.[a-z0-9]+)\s+(\S+)\s+->')
def git_operation(reponame, operation, branch=None):
    if operation == 'pull':
        operations = ['pull', '--rebase']
    elif operation == 'fetch':
        operations = ['fetch', ]
    else:
        raise Exception("Unknown operation")

    if not branch:
        branch = run_command(reponame, '/usr/bin/git', 'symbolic-ref', '--short', 'HEAD')[0].strip()

    lines = run_command(reponame, '/usr/bin/git', *operations)
    parsing_revs = False
    for l in lines:
        if parsing_revs:
            m = re_revs.match(l)
            if m:
                if m.group(2) == branch:
                    return m.group(1)
        elif l.startswith('From '):
            parsing_revs = True
    return ''

def get_files_for_rev(reponame, revs):
    if revs:
        return run_command(reponame, '/usr/bin/git', 'diff-tree', '--no-commit-id', '--name-only', '-r', revs)
    else:
        return []

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
        branch = None
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

    output = ""
    try:
        if cfg.get(repository, 'type') == 'django':
            # Basic django repository. For this repo type, we do a git pull. If something
            # has changed, we count on the uwsgi process to reload the app.
            # XXX: in the future, consider doing automatic migration?
            revs = git_operation(repository, 'pull')
        elif cfg.get(repository, 'type') == 'static':
            # This is just a pure static checkout
            revs = git_operation(repository, 'pull')
        elif cfg.get(repository, 'type') == 'pgeustatic':
            # For pgeu static, we pull the git repo and then deploy from there.
            # The correct branch has to be checked out.
            for k in 'target', :
                if not cfg.has_option(repository, k):
                    eprint("Repository {0} is missing key {1}".format(repository, k))
                    return "Repo misconfigured", 500

            revs = git_operation(repository, 'pull')
            (ok, out) = run_command_conditional(repository, deploystatic,
                                                cfg.get(repository, 'root'),
                                                cfg.get(repository, 'target'),
            )
            if ok:
                output += out
            else:
                eprint("Failed run deploystatic in {0}".format(repository))
                return out, 500

            if cfg.has_option(repository, 'templates'):
                (ok, out) = run_command_conditional(repository, deploystatic, '--templates',
                                                    cfg.get(repository, 'root'),
                                                    cfg.get(repository, 'templates'),
                )
                if ok:
                    output += out
                else:
                    eprint("Failed run deploystatic for templates in {0}".format(repository))
                    return out, 500
        elif cfg.get(repository, 'type') == 'pgeubranch':
            # For pgeu branch, we fetch the git repository and then deploy directly from
            # that using a tar export.
            for k in 'target', 'branch' :
                if not cfg.has_option(repository, k):
                    eprint("Repository {0} is missing key {1}".format(repository, k))
                    return "Repo misconfigured", 500

            # Branch will be set for wildcard deploys already, but for deploys
            # off a static branch we have to get it here.
            if not branch:
                branch = cfg.get(repository, 'branch')

            revs = git_operation(repository, 'fetch', branch)
            (ok, out) = run_command_conditional(repository, deploystatic,
                                                cfg.get(repository, 'root'),
                                                cfg.get(repository, 'target').replace('*', reporeplace),
                                                '--branch',
                                                cfg.get(repository, 'branch').replace('*', reporeplace),
            )
            if ok:
                output += out
            else:
                eprint("Failed run deploystatic in {0}".format(repository))
                return out, 500

            if cfg.has_option(repository, 'templates'):
                (ok, out) = run_command_conditional(repository, deploystatic, '--templates',
                                                    cfg.get(repository, 'root'),
                                                    cfg.get(repository, 'templates').replace('*', reporeplace),
                                                    '--branch',
                                                    cfg.get(repository, 'branch').replace('*', reporeplace),
                )
                if ok:
                    output += out
                else:
                    eprint("Failed run deploystatic for templates in {0}".format(repository))
                    return out, 500

        else:
            eprint("Repository {0} has an invalid type {1}".format(
                repository, cfg.get(repository, 'type')))
            return "Invalid git repo type", 500
    except Exception as e:
        eprint("Failed to update {0}: {1}".format(repository, e))
        return str(e), 500

    eprint("Deployed repository {0}".format(repository))

    if cfg.has_option(repository, 'notify') and revs:
        # There is a script to notify. Figure out affected files.
        files = get_files_for_rev(repository, revs)
        res = pipe_command(repository, "\n".join(files), cfg.get(repository, 'notify'), revs)
        eprint("\n".join(res))
        eprint("Completed trigger for {0}".format(repository))

    if not output:
        output = "OK"
    return output

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
