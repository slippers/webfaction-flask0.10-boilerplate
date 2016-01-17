"""Fabfile for webfaction-flask-boilerplate``.

Make sure to setup your ``fabric_settings.py`` first. As a start, just copy
``fabric_settings.py.sample``.

"""
# Adapted in part from https://github.com/bitmazk/webfaction-django1.4-boilerplate.git

from __future__ import with_statement

import sys
import xmlrpclib

from fabric.api import (
    cd,
    env,
    get,
    lcd,
    local,
    path,
    put,
    run,
    settings,
    )
import fabric_settings as fab_settings

env.hosts = fab_settings.ENV_HOSTS
env.user = fab_settings.ENV_USER

PROJECT_NAME = fab_settings.PROJECT_NAME


# ****************************************************************************
# HIGH LEVEL TASKS
# ****************************************************************************
def install_everything():
    install_server()
    install_local_repo()
    local_link_repo_with_remote_repo()
    first_deployment()


def onetime_setup():
    """ only has to be done one time ever """
    api_add_git_domain()


def first_deployment():
    run_install_requirements()
    run_deploy_website()
    run_prepare_local_settings()
    run_deploy_website()


def install_local_repo():
    local_create_virtualenv()
    local_create_new_repo()
    local_init_flask_project()
    local_create_fab_settings()
    local_initial_commit()


def install_server():
    run_delete_previous_attempts()
    api_add_applications()
    run_create_virtualenv()
    run_create_git_repo()
    run_delete_index_files()


# ****************************************************************************
# LOCAL TASKS
# ****************************************************************************
def local_link_repo_with_remote_repo():
    with lcd(fab_settings.PROJECT_ROOT):
        local('git config http.sslVerify false')
        local('git config http.postBuffer 524288000')
        with settings(warn_only=True):
            local('git remote rm origin')
        local('git remote add origin'
              ' {0}@{0}.webfactional.com:'
              '/home/{0}/webapps/git/repos/{1}'.format(
                    fab_settings.ENV_USER, fab_settings.GIT_REPO_NAME))
        local('git push -u origin master')


def local_create_fab_settings():
    # TODO make sure to remove the fabric gitignore lines when this
    # is updated to copy fabfile and fabric_settings files.
    # Right now I don't know what I'll need
    pass


def local_create_new_repo():
    with lcd(fab_settings.PROJECT_ROOT):
        local('rm -rf .git')
        local('git init')

        gitignore = """
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]

# Distribution / packaging
{0}/
""".format(fab_settings.VENV_NAME)
        local('printf "{0}" >> .gitignore'.format(gitignore))


def local_init_flask_project():
    with lcd(fab_settings.PROJECT_ROOT):
        # download remote default Apache .conf
        local('rm -rf apache2/conf')
        local('mkdir -p apache2/conf')
        with cd(fab_settings.REMOTE_APP_ROOT):
            get(remote_path='apache2/conf/httpd.conf',
                local_path ='apache2/conf/httpd.conf')
        # prepare httpd.conf
        local("sed -i -r -e 's/ENV_USER/{0}/g'"
              " apache2/conf/httpd.conf".format(fab_settings.ENV_USER))
        local("sed -i -r -e 's/VENV_NAME/{0}/g'"
              " apache2/conf/httpd.conf".format(fab_settings.VENV_NAME))
        local("sed -i -r -e 's/APP_NAME/{0}/g'"
              " apache2/conf/httpd.conf".format(fab_settings.APP_NAME))

        # initialize local Flask project
        with path('{0}/bin'.format(fab_settings.VENV_NAME), behavior='prepend'):
            local('pip install Flask')
            local('pip freeze > requirements.txt')


def local_initial_commit():
    with lcd(fab_settings.PROJECT_ROOT):
        local('git add .')
        local('git commit -am "Initial commit."')

def local_create_virtualenv():
    with lcd(fab_settings.PROJECT_ROOT):
        local(fab_settings.VENV_COMMAND)


# ****************************************************************************
# REMOTE TASKS
# ****************************************************************************
def run_create_git_repo():
    run('rm -rf $HOME/webapps/git/repos/{0}'.format(
        fab_settings.GIT_REPO_NAME))
    with cd('$HOME/webapps/git'):
        run('git init --bare ./repos/{0}'.format(fab_settings.GIT_REPO_NAME))
    with cd('$HOME/webapps/git/repos/{0}'.format(fab_settings.GIT_REPO_NAME)):
        run('git config http.receivepack true')


def run_create_ssh_dir():
    with cd('$HOME'):
        with settings(warn_only=True):
            run('mkdir .ssh')
            run('touch .ssh/authorized_keys')
            run('chmod 600 .ssh/authorized_keys')
            run('chmod 700 .ssh')


def run_delete_index_files():
    run('rm -f $HOME/webapps/{0}/index.html'.format(
        fab_settings.STATIC_NAME))


def run_delete_previous_attempts():
    api_remove_applications()


def run_create_virtualenv():
    with cd(fab_settings.REMOTE_APP_ROOT):
        run(fab_settings.VENV_COMMAND)


def run_deploy_website():
    with cd(fab_settings.REMOTE_APP_ROOT):
        with path('{0}/bin'.format(fab_settings.VENV_NAME), behavior='prepend'):
            pass
            # TODO
            #run('deploy-website-{1}.sh{2}'.format(PROJECT_NAME, args))


def run_install_requirements():
    with cd(fab_settings.REMOTE_APP_ROOT):
        # site isn't deployed yet, so copy requirements.txt as one-off
        with lcd(fab_settings.PROJECT_ROOT):
            put(local_path='requirements.txt',
                remote_path ='requirements.txt')
        with path('{0}/bin'.format(fab_settings.VENV_NAME), behavior='prepend'):
            run('pip install -r requirements.txt')


def run_prepare_local_settings():
    # TODO update flask local settings file when I get that far
    pass


# ****************************************************************************
# WEBFACTION API TASKS
# ****************************************************************************

# a class to automatically add the session_id to Webfaction API calls 
# and provide related convenience methods
class _Webfaction:
    def __init__(self):
        self.server = None
        self.session_id = None


    def _add_session_id(self, fn):
        def wrap(*args):
            return fn(self.session_id, *args)
        return wrap


    def __getattr__(self, attr):
        # connect to server here instead of init to avoid connecting until necessary
        if self.session_id is None:
            self.server = xmlrpclib.ServerProxy('https://api.webfaction.com/')
            self.session_id, _ = self.server.login(fab_settings.ENV_USER, fab_settings.ENV_PASS)

        # hasattr(xmlrpclib_obj, X) returns True for any X, so is not useful here
        if attr in self.server.system.listMethods():
            return self._add_session_id(getattr(self.server, attr))
        else:
            raise AttributeError("class %s has no attribute '%s'" % (self.__class__.__name__, attr))


    def get_app(self, appname):
        return filter(lambda d: d['name'] == appname, self.list_apps())


    def app_exists(self, appname):
        return len(self.get_app(appname)) == 1


def api_add_applications():
    _webfaction_create_app(fab_settings.APP_NAME, fab_settings.APP_TYPE)
    _webfaction_create_app(fab_settings.STATIC_NAME, fab_settings.STATIC_TYPE)


def api_remove_applications():
    _webfaction_delete_app(fab_settings.APP_NAME)
    _webfaction_delete_app(fab_settings.STATIC_NAME)


def _webfaction_init(f):
    if not 'wf' in f.func_globals:
        f.func_globals['wf'] = _Webfaction() 

    return f


@_webfaction_init
def api_add_git_domain():
    """ add git.username.webfactional.com to username.webfactional.com """
    # get a list of sites that have the username site in subdomains
    username_site = '{0}.webfactional.com'.format(env.user)
    site = filter(lambda s: username_site in s['subdomains'], wf.list_websites())

    # if there is one, add git.username.webfactional.com to the subdomains
    if site:
        site = site[0]
        git_site = 'git.{0}'.format(username_site)

        if git_site not in site['subdomains']:
            # create domain
            wf.create_domain(username_site, 'git')

            # create app
            _webfaction_create_app('git', fab_settings.GIT_TYPE, 
                    app_extra=fab_settings.ENV_PASS)

            # create website with new domain and app
            site['subdomains'].append(git_site)
            wf.create_website('git', site['ip'], True,
                    ['git.{}'.format(username_site)], ['git', '/'])
    else:
        print "Could not add {0} to webfaction {1}".format(git_site, username_site)
        sys.exit(1)


@_webfaction_init
def _webfaction_create_app(app_name,app_type,app_extra=''):
    """creates a app on webfaction of the named type using the webfaction public API."""
    try:
        if not wf.app_exists(app_name):
            response = wf.create_app(app_name, app_type, False, app_extra)
            print "App on webfaction created: %s" % response
            return response
        else:
            print("App name {0} already in use".format(app_name))

    except xmlrpclib.Fault:
        print "could not create app %s on webfaction, app name maybe already in use" % app_name
        sys.exit(1)

@_webfaction_init
def _webfaction_delete_app(app_name):
    """deletes a named app on webfaction using the webfaction public API."""
    try:
        if wf.app_exists(app_name):
            with cd(fab_settings.REMOTE_APP_BASE.format(app_name)):
                run("if test -x apache2/bin/stop; then apache2/bin/stop; fi")
            response = wf.delete_app(app_name)
            print "App on webfaction deleted: %s" % response
            return response

    except xmlrpclib.Fault:
        print "could not delete app on webfaction %s" % app_name
        return False
