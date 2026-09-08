'''
Run each test in its own Blender process and record what killed the ones that die.

`scripts/run_tests.py` runs the whole suite in one process, and pytest writes its
JUnit report at the very end. A native fault therefore costs the whole run's
results rather than one test, so a suite that faults tells you nothing about
which test did it. This runs them one per process, so every test reports for
itself.

For each test it records:

  status   pass / fail / skip, read from that test's own JUnit report
  exit     Blender's exit code
  fault    the last faulthandler frame, which names where the process died

A test whose report says `pass` while Blender exits non-zero faulted during
teardown, after the work was done. A test with no report at all faulted during
the test itself, and that is the kind that takes a suite down.

    python scripts/audit_test_faults.py --blender path/to/blender [PATH ...]

Narrow it to the files worth asking about. Every Blender start costs seconds,
and a test that never reaches misuka cannot fault in it.
'''
import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET


# Blender's own exit code cannot distinguish a fault from a failure, so keep the
# codes Windows and POSIX use for a crash separate from pytest's own 1..5.
FAULT_CODES = {-1073741819: 'access violation (0xC0000005)',
               3221225477: 'access violation (0xC0000005)',
               -1073740791: 'stack buffer overrun (0xC0000409)',
               3221226505: 'stack buffer overrun (0xC0000409)',
               -11: 'SIGSEGV', 139: 'SIGSEGV',
               -6: 'SIGABRT', 134: 'SIGABRT'}


def collect(blender, paths=None, keyword=None):
    '''Every test id pytest would run, without running any of them.'''
    args = ['--collect-only', '-q'] + list(paths or [])
    if keyword:
        args += ['-k', keyword]

    result = run_blender(blender, args, timeout=300)

    ids = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if '::' in line and line.startswith('tests/'):
            ids.append(line.split(' ')[0])
    return ids


def run_blender(blender, pytest_args, timeout=600):
    command = [blender, '-b', '-noaudio', '--factory-startup',
               '--python', os.path.join('scripts', 'run_tests.py'), '--'] + pytest_args

    environment = dict(os.environ)
    # Without this the process dies silently and there is nothing to attribute
    # the fault to. With it, Python prints the C-level frame it died in.
    environment['PYTHONFAULTHANDLER'] = '1'
    # Let every test run, including the ones a Windows marker would skip: a
    # skipped test is exactly the thing this is trying to measure.
    environment['MISUKA_AUDIT_NO_SKIP'] = '1'

    return subprocess.run(command, capture_output=True, text=True,
                          timeout=timeout, env=environment, errors='replace')


def read_status(report_path):
    '''
    What that test's own JUnit report says, as (status, message).

    Status is None when the report was never written, which is the interesting
    case: it means the process died before pytest could record anything.
    '''
    try:
        root = ET.parse(report_path).getroot()
    except (FileNotFoundError, ET.ParseError):
        return None, ''

    case = next(root.iter('testcase'), None)
    if case is None:
        return None, ''
    for outcome, label in (('failure', 'fail'), ('error', 'error'), ('skipped', 'skip')):
        node = case.find(outcome)
        if node is not None:
            detail = (node.get('message') or node.text or '').strip()
            return label, ' '.join(detail.split())[:300]
    return 'pass', ''


def last_fault_frame(text):
    '''The deepest frame faulthandler printed, which is where it actually died.'''
    if 'Fatal Python error' not in text and 'fatal exception' not in text.lower():
        return ''

    frames = re.findall(r'^\s+File "(.+?)", line (\d+) in (.+)$', text, re.M)
    if not frames:
        # No Python frame means it died below Python, in the extension itself.
        marker = re.search(r'(Windows fatal exception: .+|Fatal Python error: .+)', text)
        return marker.group(1).strip() if marker else 'fault with no Python frame'

    path, line, function = frames[-1]
    return f'{os.path.basename(path)}:{line} in {function}'


def audit(blender, test_ids):
    results = []
    for index, test_id in enumerate(test_ids, 1):
        report = os.path.abspath(f'audit-{index}.xml')
        if os.path.exists(report):
            os.unlink(report)

        print(f'[{index}/{len(test_ids)}] {test_id}', flush=True)
        try:
            completed = run_blender(blender, [test_id, '-q', f'--junitxml={report}'])
            code, output = completed.returncode, completed.stdout + completed.stderr
        except subprocess.TimeoutExpired:
            code, output = None, 'timed out'

        status, message = read_status(report)
        results.append({
            'id': test_id,
            'status': status or 'NO REPORT',
            'message': message,
            'exit': code,
            'fault': FAULT_CODES.get(code, ''),
            'where': last_fault_frame(output),
        })
        print(f'    -> {results[-1]["status"]}, exit {code} '
              f'{results[-1]["fault"]} {results[-1]["where"]}', flush=True)
        if message:
            print(f'       {message}', flush=True)

    return results


def render_table(results):
    lines = ['| Test | Report | Exit | Fault | Died in | Message |',
             '|---|---|---|---|---|---|']
    for row in results:
        lines.append(
            '| `{id}` | {status} | {exit} | {fault} | {where} | {message} |'.format(
                id=row['id'].replace('tests/', ''), status=row['status'],
                exit=row['exit'], fault=row['fault'] or '-',
                where=row['where'] or '-',
                message=row['message'].replace('|', '\\|') or '-'))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', required=True, help='path to the Blender executable')
    parser.add_argument('paths', nargs='*',
                        help='test files to audit (default: the whole suite)')
    parser.add_argument('-k', dest='keyword', default=None,
                        help='pytest -k expression narrowing which tests are audited')
    parser.add_argument('--summary', default=None, help='write a markdown table here')
    args = parser.parse_args()

    test_ids = collect(args.blender, args.paths, args.keyword)
    if not test_ids:
        sys.exit('collected no tests')
    print(f'auditing {len(test_ids)} tests\n', flush=True)

    results = audit(args.blender, test_ids)
    table = render_table(results)
    print('\n' + table)

    if args.summary:
        with open(args.summary, 'a', encoding='utf-8') as handle:
            handle.write(table + '\n')

    # The audit reports; it does not judge. A test that fails here is data.
    lost = [r for r in results if r['status'] == 'NO REPORT']
    print(f'\n{len(lost)} of {len(results)} tests took their process down with them')


if __name__ == '__main__':
    main()
