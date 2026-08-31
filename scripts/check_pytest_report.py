'''Decide a CI test step from pytest's own JUnit report.

Blender's exit code is unusable on Windows: it faults while unloading misuka
after every test has already run, so a fully passing suite still reports a
failure (issue #4). pytest writes this report before that teardown, so it
reflects what actually happened.

This is not a blanket "ignore Windows". A crash *during* the run leaves the
report missing or incomplete, and that still fails here.
'''
import sys
import xml.etree.ElementTree as ET


def main(path):
    try:
        root = ET.parse(path).getroot()
    except FileNotFoundError:
        sys.exit(f'FAIL: {path} was never written - the run did not reach the end')
    except ET.ParseError as e:
        sys.exit(f'FAIL: {path} is not parseable ({e}) - the run was cut short')

    suites = root.iter('testsuite')
    totals = {'tests': 0, 'failures': 0, 'errors': 0, 'skipped': 0}
    for suite in suites:
        for key in totals:
            totals[key] += int(suite.get(key, 0))

    print(f"{totals['tests']} tests, {totals['failures']} failures, "
          f"{totals['errors']} errors, {totals['skipped']} skipped")

    if totals['tests'] == 0:
        sys.exit('FAIL: no tests ran')
    if totals['failures'] or totals['errors']:
        sys.exit('FAIL: pytest reported failures')
    print('PASS')


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: check_pytest_report.py <report.xml>')
    main(sys.argv[1])
