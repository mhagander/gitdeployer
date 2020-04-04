gitdeployer
===========

`gitdeployer` is a trivial tool to implement a git "ping hook" and
initiate a deployment of a typical application.

Configure using `gitdeployer.ini` (see sample file), don't forget to
set up a firewall, and deploy using the systemd unit file.

Security
--------

There is expected to be a firewall that prevents bad guys from calling
the URL. There is no attempt to do rate limiting or anything like
that.

Each repository is assigned a name and a key. The url format is
`/deploy/<reponame>/<key>/`, and any `GET` to this url will initiate a
deployment.


Repository types
----------------

For each repository, a type is specified. All repositories include a
git repository root, but some types also need more information.

### static

This repository type is the simplest possible. It will just execute a `git
pull --rebase` in the root directory and then it will be done.

### django

This repository type is almost as simple. It will first execute a `git
pull --rebase` in the root directory.

If a symlink called `python` and a file called `manage.py` exists in
the root directory, it will also execute `./python manage.py migrate`
in this directory.

If there are any files named `*.pyc` in the checkout (recursively),
these are removed before doing the pull, to ensure there are not any
left for modules where the python source file has been removed. They
will usually be recreated by the migrate step, if it is run.

### pgeustatic

This repository type deploys a repository using the `deploystatic`
method from pgeu. It starts by running `git pull --rebase`, and then
executes `deploystatic`. It needs the following configuration
variables set:

`target` specifies the directory to deploy the website to.
`templates` specifies the directory to deploy raw templates into.

## pgeubranch

This repository type deploys a repository using the `deploystatic`
method from pgeu, but instead of working from a checkout of an
individual branch, it can directly deploy a branch. It will run a `git
fetch` to update the repository, and then immediately work from the
branch specified. It needs the following configuration
variables set:

`target` specifies the directory to deploy the website to.
`templates` specifies the directory to deploy raw templates into.

`branch` specifies the branch name, usually including the remote, for
example `origin/master`.


Branch name substitution
------------------------

When using the `pgeubranch` type, branch name substitution can be
used to avoid a lot of reptition. By ending a repository name with -*,
it will be enabled, and the * will be replaced with the branch name.
For example:

```
[somerepo-*]
key=secret
type=pgeubranch
root=/some/where/gitrepo
target=/some/web/root/*
templates=/some/web/templates/*
branch=origin/*
```

In this example, a ping to `/deploy/somerepo-branch1/secret` will
cause the branch `origin/branch1` to be deployed to
`/some/web/root/branch1` and templates to `/some/web/templates/*`.

Deploying specific commits
--------------------------
In normal mode, for any type except `pgeubranch` the existing branch
in the checked out directory will be rebased on it's own master using
`git pull --rebase`.

It is also possible to check out an individual commit. To do that,
the "ping" that's sent should be a POST and include the variable
`commit` as part of the submit (with normal form encoding). When
found, this commit will be checked out, instead of a rebase. This will
normally result in a detached head, but if it's moved to the tip of
the branch again it will "reattach".

For this to be allowed, the parameter `allowcommit` must be set in the
configuration for the repository.

Notification
------------
If the key `notify` is set for a repository, then whenever this
repository is updated in a way that changes any files (so not if a
deploy is triggered but there was no update), the script/program
defined in `notify` gets called. This scripts gets the list of git
revisions in the format `abc123abc..def345def` on the command line and
a list of modified files on standard input, one file per line.

Notification currently does not work when checking out an individual
commit, only when a branch is being followed.
