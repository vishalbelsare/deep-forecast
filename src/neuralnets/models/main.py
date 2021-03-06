import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.realpath(__file__), '..', '..', '..', '..')))

import subprocess
from itertools import product, chain
from src.utils.data_utils import VARIABLES
import psutil
import os
import argparse

RUN_SCRIPT = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'run_models.py'))

one_one = [([i], [i]) for i in VARIABLES]
many_one = [(VARIABLES, [i]) for i in VARIABLES]
many_many = [(VARIABLES, VARIABLES)]


def run_command(command):
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            print output.strip()
    rc = process.poll()
    return rc


def kill_others():
    for proc in psutil.process_iter():
        pinfo = proc.as_dict(attrs=['pid', 'name'])
        procname = str(pinfo['name'])
        procpid = str(pinfo['pid'])
        if "python" in procname and procpid != str(os.getpid()):
            print("Stopped Python Process ", proc)
            proc.kill()


def mlp_experiments(diff, vars):
    countries = ['EA', 'US']
    # vars = one_one_in + many_one + many_many

    for i, j in product(countries, vars):
        args = ['python', '-m', 'scoop', RUN_SCRIPT, '-m', 'mlp', '-c', i, '--in'] + j[0] + ['--out'] + j[1]

        if diff:
            args.append('-d')

        run_command(args)
        kill_others()


def lstm_experiments(diff):
    countries = ['EA', 'US']
    vars = one_one

    for i, j in product(countries, vars):
        print i, j
        args = ['python', '-m', 'scoop', RUN_SCRIPT, '-m', 'lstm', '-c', i, '--in'] + j[0] + ['--out'] + j[1]

        if diff:
            args.append('-d')

        run_command(args)
        kill_others()


MODELS = {'mlp': [mlp_experiments], 'lstm': [lstm_experiments], 'all': [lstm_experiments, mlp_experiments]}
DIFFS = {'no': [False], 'yes': [True], 'both': [True, False]}
SETS = {'one_to_one': one_one, 'many_to_one': many_one, 'many_to_many': many_many}


def run_experiments(args):
    models = MODELS[args['model']]
    diffs = DIFFS[args['diff']]
    mlp_sets = [SETS[i] for i, j in args.iteritems() if j and i in SETS.keys()]
    mlp_sets = list(chain.from_iterable(mlp_sets))

    print 'Experiment set up'
    print args

    for model, diff in product(models, diffs):
        if model == mlp_experiments:
            mlp_experiments(diff, mlp_sets)
        else:
            lstm_experiments(diff)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-m', '--model', choices=['mlp', 'lstm', 'all'], required=True, help='Which models to run.')
    parser.add_argument('-d', '--diff', choices=['yes', 'no', 'both'], required=True,
                        help='Weather or not to use first order differencing')
    parser.add_argument('-a', '--one-to-one', action='store_true',
                        help='This argument only applies to mlp. Run one-to-one architecture')
    parser.add_argument('-b', '--many-to-one', action='store_true',
                        help='This argument only applies to mlp. Run many-to-one architecture')
    parser.add_argument('-c', '--many-to-many', action='store_true',
                        help='This argument only applies to mlp. Run many-to-many architecture')

    args = parser.parse_args()
    args = vars(args)

    run_experiments(args)
