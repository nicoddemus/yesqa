from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import argparse
import collections
import os.path
import re
import subprocess
import sys
import tempfile

import tokenize_rt

NOQA_FILE_RE = re.compile('^# flake8[:=]\s*noqa', re.I)
NOQA_RE = re.compile('# noqa(: ([a-z][0-9]+([,\s]+)?)+)?', re.I)
SEP_RE = re.compile('[,\s]+')


def _run_flake8(filename):
    cmd = (sys.executable, '-mflake8', '--format=%(row)d\t%(code)s', filename)
    out, _ = subprocess.Popen(cmd, stdout=subprocess.PIPE).communicate()
    ret = collections.defaultdict(set)
    for line in out.decode().splitlines():
        lineno, code = line.split('\t')
        ret[int(lineno)].add(code)
    return ret


def _remove_comment(tokens, i):
    if i > 0 and tokens[i - 1].name == tokenize_rt.UNIMPORTANT_WS:
        del tokens[i - 1:i + 1]
    else:
        del tokens[i]


def _remove_comments(tokens):
    tokens = list(tokens)
    for i, token in reversed(tuple(enumerate(tokens))):
        if token.name == 'COMMENT':
            _remove_comment(tokens, i)
    return tokens


def _rewrite_noqa_comment(tokens, i, flake8_results):
    token = tokens[i]
    match = NOQA_RE.match(token.src)
    # exclude all lints on the line but no lints
    if token.line not in flake8_results:
        _remove_comment(tokens, i)
    elif match.group().lower() != '# noqa':
        codes = set(SEP_RE.split(match.group(1)[2:]))
        expected_codes = codes & flake8_results[token.line]
        if expected_codes != codes:
            comment = '# noqa: {}'.format(','.join(sorted(expected_codes)))
            tokens[i] = token._replace(src=NOQA_RE.sub(comment, token.src))


def fix_file(filename):
    with open(filename, 'rb') as f:
        contents_bytes = f.read()

    try:
        contents_text = contents_bytes.decode('UTF-8')
    except UnicodeDecodeError:
        print('{} is non-utf8 (not supported)'.format(filename))
        return 1

    tokens = tokenize_rt.src_to_tokens(contents_text)

    tokens_no_comments = _remove_comments(tokens)
    src_no_comments = tokenize_rt.tokens_to_src(tokens_no_comments)
    with tempfile.NamedTemporaryFile(
        dir=os.path.dirname(filename),
        prefix=os.path.basename(filename),
        suffix='.py',
    ) as tmpfile:
        tmpfile.write(src_no_comments.encode('UTF-8'))
        tmpfile.flush()
        flake8_results = _run_flake8(tmpfile.name)

    for i, token in reversed(tuple(enumerate(tokens))):
        if token.name != 'COMMENT':
            continue

        if NOQA_RE.search(token.src):
            _rewrite_noqa_comment(tokens, i, flake8_results)
        elif NOQA_FILE_RE.match(token.src) and not flake8_results:
            if i == 0 or tokens[i - 1].name == 'NEWLINE':
                del tokens[i: i + 2]
            else:
                _remove_comment(tokens, i)

    newsrc = tokenize_rt.tokens_to_src(tokens)
    if newsrc != contents_text:
        print('Rewriting {}'.format(filename))
        with open(filename, 'wb') as f:
            f.write(newsrc.encode('UTF-8'))
        return 1
    else:
        return 0


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('filenames', nargs='*')
    args = parser.parse_args(argv)

    retv = 0
    for filename in args.filenames:
        retv |= fix_file(filename)
    return retv


if __name__ == '__main__':
    exit(main())
