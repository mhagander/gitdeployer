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

This repository type is almost as simple. It will just execute a `git
fetch --rebase` in the root directory and then it will be done.

### django

This repository type is almost as simple. It will just execute a `git
fetch --rebase` in the root directory and then it will be done.

A consideration for the future could be to run an automatic migration
on it, but that's not implemented yet.

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
