#!/usr/bin/env python
from __future__ import print_function
import argparse
import os
import sys
import re
import webbrowser

import requests
import requests.exceptions

session = requests.Session()
adapter = requests.adapters.HTTPAdapter(max_retries = 20)
session.mount('http://', adapter)

# Python 2/3 compatibility
if sys.version_info[0] >= 3:
    import configparser
else:
    # Python 2, import modules with Python 3 names
    import ConfigParser as configparser

# End Python 2/3 compatibility

_DEFAULT_CONFIG = '/usr/local/etc/iic1103src'
_VERSION = 'Version: $Version: $'
_LANGUAGE_GUESS = {
    '.java': 'Java',
    '.c': 'C',
    '.cpp': 'C++',
    '.h': 'C++',
    '.cc': 'C++',
    '.cxx': 'C++',
    '.c++': 'C++',
    '.py': 'Python',
    '.cs': 'C#',
    '.c#': 'C#',
    '.go': 'Go',
    '.m': 'Objective-C',
    '.hs': 'Haskell',
    '.pl': 'Prolog',
    '.js': 'JavaScript',
    '.php': 'PHP',
    '.rb': 'Ruby'
}
_GUESS_MAINCLASS = {'Java', 'Python'}


_HEADERS = {'User-Agent': 'iic1103-cli-submit'}


class ConfigError(Exception):
    pass


def parseResults(results):
    print("+-----------------------------+")
    s = ""
    for str in results:
        str = str.replace("\"", "")
        s+=str

    s = s.replace("[", "")
    s = s.replace("]", "")
    results = s.split(',')

    for str in results:
        while(str and  str[0] == " "):
            str = str.strip()
        print(str)

    print("+-----------------------------+")

def get_url(cfg, option, default):
    if cfg.has_option('iic1103', option):
        return cfg.get('iic1103', option)
    else:
        return 'https://%s/%s' % (cfg.get('iic1103', 'hostname'), default)


def get_config():
    """Returns a ConfigParser object for the .iic1103src file(s)
    """
    cfg = configparser.ConfigParser()
    if os.path.exists(_DEFAULT_CONFIG):
        cfg.read(_DEFAULT_CONFIG)

    if not cfg.read([os.path.join(os.getenv('HOME'), '.iic1103src'),
                     os.path.join(os.path.dirname(sys.argv[0]), '.iic1103src')]):
        raise ConfigError('''\
I failed to read in a config file from your home directory or from the
same directory as this script. Please go to your iic1103 installation
to download a .iic1103src file.

The file should look something like this:
[user]
username: yourusername
token: *********

[iic1103]
loginurl: https://<iic1103>/login
submissionurl: https://<iic1103>/submit''')
    return cfg


def login(login_url, username, password=None, token=None):
    """Log in to iic1103.

    At least one of password or token needs to be provided.

    Returns a requests.Response with cookies needed to be able to submit
    """
    login_args = {'user': username, 'script': 'true'}
    if password:
        login_args['password'] = password
    if token:
        login_args['token'] = token

    return session.post(login_url, data=login_args, headers=_HEADERS)


def login_from_config(cfg):
    """Log in to iic1103 using the access information in a iic1103src file

    Returns a requests.Response with cookies needed to be able to submit
    """
    username = cfg.get('user', 'username')
    password = token = None
    try:
        password = cfg.get('user', 'password')
    except configparser.NoOptionError:
        pass
    try:
        token = cfg.get('user', 'token')
    except configparser.NoOptionError:
        pass
    if password is None and token is None:
        raise ConfigError('''\
Your .iic1103src file appears corrupted. It must provide a token (or a
iic1103 password).

Please download a new .iic1103src file''')

    loginurl = get_url(cfg, 'loginurl', 'login')
    return login(loginurl, username, password, token)


def submit(submit_url, cookies, problem, language, files, mainclass='', tag=''):
    """Make a submission.

    The url_opener argument is an OpenerDirector object to use (as
    returned by the login() function)

    Returns the requests.Result from the submission
    """

    data = {'submit': 'true',
            'submit_ctr': 2,
            'language': language,
            'mainclass': mainclass,
            'problem': problem,
            'tag': tag,
            'script': 'true'}
    _HEADERS = {'problem': problem}
    sub_files = []
    for f in files:
        with open(f) as sub_file:
            sub_files.append(('sub_file[]',
                              (os.path.basename(f),
                               sub_file.read(),
                               'application/octet-stream')))
    return session.post(submit_url, data=data, files=sub_files, headers=_HEADERS)
    #return session.post(submit_url, data=data, files=sub_files, cookies=cookies, headers=_HEADERS)


def confirm_or_die(problem, language, files, mainclass, tag):
    print('Problem:', problem)
    print('Language:', language)
    print('Files:', ', '.join(files))
    if mainclass:
        print('Mainclass:', mainclass)
    if tag:
        print('Tag:', tag)
    print('Submit (y/N)?')
    if sys.stdin.readline().upper()[:-1] != 'Y':
        print('Cancelling')
        sys.exit(1)


def open_submission(submit_response, cfg):
    submissions_url = get_url(cfg, 'submissionsurl', 'submissions')

    m = re.search(r'Submission ID: (\d+)', submit_response)
    if m:
        submission_id = m.group(1)
        print('Open in browser (y/N)?')
        if sys.stdin.readline().upper()[:-1] == 'Y':
            url = '%s/%s' % (submissions_url, submission_id)
            webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(description='Submit a solution to iic1103')
    parser.add_argument('-p', '--problem',
                   help=''''Which problem to submit to.
Overrides default guess (first part of first filename)''')
    parser.add_argument('-m', '--mainclass',
                   help='''Sets mainclass.
Overrides default guess (first part of first filename)''')
    parser.add_argument('-l', '--language',
                   help='''Sets language.
Overrides default guess (based on suffix of first filename)''')
    parser.add_argument('-t', '--tag',
                   help=argparse.SUPPRESS)
    parser.add_argument('-f', '--force',
                   help='Force, no confirmation prompt before submission',
                   action='store_true')
    parser.add_argument('files', nargs='+')

    args = parser.parse_args()
    files = args.files

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(exc)
        sys.exit(1)

    submission_name, ext = os.path.splitext(os.path.basename(args.files[0]))
    language = _LANGUAGE_GUESS.get(ext, None)
    mainclass = submission_name if language in _GUESS_MAINCLASS else None
    tag = args.tag

    if args.problem:
        problem = args.problem

    if args.mainclass is not None:
        mainclass = args.mainclass

    if args.language:
        language = args.language
    elif language == 'Python':
        python_version = str(sys.version_info[0])
        try:
            python_version = cfg.get('defaults', 'python-version')
        except configparser.Error:
            pass

        if python_version not in ['2', '3']:
            print('python-version in .iic1103src must be 2 or 3')
            sys.exit(1)
        language = 'Python ' + python_version

    if language is None:
        print('''\
No language specified, and I failed to guess language from filename
extension "%s"''' % (ext,))
        sys.exit(1)

    files = list(set(args.files))

    try:
        login_reply = login_from_config(cfg)
    except ConfigError as exc:
        print(exc)
        sys.exit(1)
    except requests.exceptions.RequestException as err:
        print('Login connection failed:', err)
        sys.exit(1)

    if not login_reply.status_code == 200:
        print('Login failed.')
        if login_reply.status_code == 403:
            print('Incorrect username or password/token (403)')
        elif login_reply.status_code == 404:
            print('Incorrect login URL (404)')
        else:
            print('Status code:', login_reply.status_code)
        sys.exit(1)

    submit_url = get_url(cfg, 'submissionurl', 'submit')

    if not args.force:
        confirm_or_die(problem, language, files, mainclass, tag)

    try:
        result = submit(submit_url,
                        login_reply.cookies,
                        problem,
                        language,
                        files,
                        mainclass,
                        tag)
    except requests.exceptions.RequestException as err:
        print('Submit connection failed:', err)
        sys.exit(1)

    if result.status_code != 200:
        print('Submission failed.')
        if result.status_code == 403:
            print('Access denied (403)')
        elif result.status_code == 404:
            print('Incorrect submit URL (404)')
        else:
            print('Status code:', login_reply.status_code)
        sys.exit(1)

    # TODO: Decode results to readable thing
    parseResults(result)

    plain_result = result.content.decode('utf-8').replace('<br />', '\n')
    #print(plain_result)

    try:
        open_submission(plain_result, cfg)
    except configparser.NoOptionError:
        pass


if __name__ == '__main__':
    main()
