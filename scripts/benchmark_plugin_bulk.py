#!/usr/bin/env python3
"""Separate NumPy bulk / sustained-lifecycle observations; prior benchmark samples stay untouched."""
from __future__ import annotations
import argparse
import base64
import csv
import hashlib
import io
import json
import math
import os
from pathlib import Path
import platform
import signal
import statistics
import subprocess
import time
import zipfile


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''): value.update(chunk)
    return value.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def fixture(source, output):
    name, info = 'orca_benchmark_bulk', 'orca_benchmark_bulk-1.0.0.dist-info'
    files = {name + '/__init__.py': source.read_bytes(),
             info + '/METADATA': b'Metadata-Version: 2.1\nName: orca-benchmark-bulk\nVersion: 1.0.0\nRequires-Python: >=3.12\nRequires-Dist: numpy==2.2.6\n\n',
             info + '/WHEEL': b'Wheel-Version: 1.0\nGenerator: Orca-bulk-benchmark\nRoot-Is-Purelib: true\nTag: py3-none-any\n',
             info + '/top_level.txt': (name + '\n').encode()}
    record = io.StringIO(); writer = csv.writer(record, lineterminator='\n')
    for key, value in sorted(files.items()):
        writer.writerow([key, 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=').decode(), len(value)])
    writer.writerow([info + '/RECORD', '', '']); files[info + '/RECORD'] = record.getvalue().encode()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for key, value in sorted(files.items()):
            item = zipfile.ZipInfo(key, (2020, 1, 1, 0, 0, 0)); item.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(item, value)
    return {'path': str(output), 'sha256': digest(output), 'source_sha256': digest(source)}


def stats(values):
    if not values: raise ValueError('Missing samples')
    return {'n': len(values), 'min': min(values), 'median': statistics.median(values),
            'p95_nearest_rank': sorted(values)[math.ceil(len(values) * .95) - 1], 'max': max(values)}


def trend(values):
    if not values: raise ValueError('Missing observations')
    window = min(10, max(1, len(values) // 5))
    center = (len(values) - 1) / 2
    denom = sum((i-center)**2 for i in range(len(values)))
    slope = sum((i-center) * value for i, value in enumerate(values)) / denom if denom else None
    return {**stats(values), 'first': values[0], 'last': values[-1], 'last_minus_first': values[-1]-values[0],
            'window_size': window, 'first_window_median': statistics.median(values[:window]),
            'last_window_median': statistics.median(values[-window:]), 'ols_units_per_cycle': slope}


def aggregate(rows):
    measured = [row for row in rows if not row['warmup']]
    if not measured or not all(row['passed'] for row in rows): raise ValueError('Missing or failed lifecycle samples')
    timings = {key: stats([row[key] for row in measured]) for key in ('load_ms', 'dispatch_execute_ms', 'unload_ms')}
    timings.update({'bulk_ns/' + key: stats([row['bulk']['metrics_ns'][key] for row in measured])
                    for key in measured[0]['bulk']['metrics_ns']})
    memory = {key: trend([row['memory']['after_cleanup'][key] for row in measured])
              for key in ('rss_bytes', 'phys_footprint_bytes', 'private_commit_bytes') if key in measured[0]['memory']['after_cleanup']}
    python = {key: trend([row['python'][key] for row in measured])
              for key in ('python_allocated_blocks', 'gc_tracked_objects', 'alive_weakrefs', 'plugin_module_count')}
    owned_pass = all(row['python']['alive_weakrefs'] == 0 and row['python']['plugin_module_count'] == 0 and
                     row['python']['unload_calls'] == 1 and row['native_capability_expired'] and
                     row['mesh_owners_after_cleanup'] == 1 for row in rows)
    return {'warmup_cycles': len(rows)-len(measured), 'measured_cycles': len(measured), 'timings': timings,
            'after_cleanup_current_memory': memory, 'after_gc_python_counts': python,
            'all_observed_owners_released': owned_pass, 'all_correctness_checks_passed': all(row['bulk']['passed'] for row in rows),
            'limits': ['Same-process ordered cycles are correlated; timing percentiles are descriptive.',
                       'Current RSS and footprint include allocator/runtime retention; no arbitrary slope threshold or leak-free claim.',
                       'Weakrefs/registry/shared ownership cover this fixture only, not all host state.',
                       'NumPy stays imported for the full session; package module/capability and geometry views are unloaded each cycle.',
                       'No GUI, slicer, device, WebView, cold filesystem-cache or platform comparison is measured.']}


def run_child(binary, plan, output, timeout):
    env = os.environ.copy()
    for key in list(env):
        if key.startswith('ORCA_LOCAL_PLUGIN_SMOKE'): del env[key]
    env.update(UV_OFFLINE='1', PYTHONNOUSERSITE='1', SLIC3R_LOGLEVEL='0')
    start = time.perf_counter()
    with output.with_suffix('.log').open('wb') as log:
        process = subprocess.Popen([str(binary), str(plan), str(output)], env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != 'nt')
        try: status = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name != 'nt': os.killpg(process.pid, signal.SIGKILL)
            else: process.kill()
            process.wait(); raise RuntimeError('Bulk host timed out; partial evidence retained')
    if status or not output.exists(): raise RuntimeError('Bulk host failed; inspect ' + str(output.with_suffix('.log')))
    report = json.loads(output.read_text())
    if not report['passed']: raise RuntimeError('Bulk host reported failure')
    return {'wall_seconds_including_overhead': time.perf_counter()-start, 'host': report}


def run(args):
    if args.mode == 'sample' and not args.idle_confirmed:
        raise ValueError('Formal sampling requires --idle-confirmed after explicit quiet-window authorization')
    if args.mode == 'validate' and (args.side > 64 or args.cycles > 3 or args.warmups > 2):
        raise ValueError('Functional validation is bounded to side <= 64, <= 3 cycles, <= 2 warmups')
    if not 4 <= args.side <= 1024 or args.side % 2 or not 0 <= args.warmups <= 100 or not 1 <= args.cycles <= 1000:
        raise ValueError('Unsupported workload dimensions')
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=False)
    binary = args.binary.resolve(strict=True); wheelhouse = args.wheelhouse.resolve(strict=True)
    np_wheels = sorted(wheelhouse.glob('numpy-2.2.6-*.whl'))
    if not np_wheels: raise ValueError('Offline NumPy 2.2.6 wheel is required')
    source = args.package.resolve(strict=True)
    package = fixture(source, output / 'orca_benchmark_bulk-1.0.0-py3-none-any.whl')
    base_plan = {'schema': 1, 'profile': str(output / 'isolated-profile'), 'wheelhouse': str(wheelhouse),
                 'wheel': package['path'], 'side': args.side, 'warmups': args.warmups, 'cycles': args.cycles,
                 'validation_only': args.mode == 'validate', 'idle_confirmed': args.idle_confirmed}
    for mode in ('prepare', 'run'): save(output / (mode + '-plan.json'), {**base_plan, 'mode': mode})
    report = {'schema': 1, 'mode': args.mode, 'passed': False, 'started_unix': time.time(),
              'binary': {'file': str(binary), 'sha256': digest(binary)}, 'package': package,
              'numpy_wheels': [{'name': p.name, 'sha256': digest(p)} for p in np_wheels],
              'system': {'os': platform.system(), 'release': platform.release(), 'machine': platform.machine(),
                         'logical_cpus': os.cpu_count(), 'load_average': os.getloadavg() if hasattr(os, 'getloadavg') else None},
              'plan': base_plan, 'baseline_eligible': args.mode == 'sample',
              'scope': 'Independent benchmark: no previous benchmark artifacts, samples or normalization changed.'}
    try:
        if args.mode == 'plan':
            report['planned_only'] = True; return 0
        report['prepare'] = run_child(binary, output / 'prepare-plan.json', output / 'prepare-host.json', args.timeout)
        report['run'] = run_child(binary, output / 'run-plan.json', output / 'run-host.json', args.timeout)
        rows = [json.loads(line) for line in Path(report['run']['host']['samples_file']).read_text().splitlines()]
        if len(rows) != args.warmups + args.cycles: raise ValueError('Unexpected sample count')
        if [row['cycle'] for row in rows] != list(range(-args.warmups, args.cycles)): raise ValueError('Missing or reordered cycle')
        report['summary'] = aggregate(rows); report['passed'] = report['summary']['all_observed_owners_released']
        if digest(binary) != report['binary']['sha256']: raise ValueError('Binary changed during the run')
        if not report['passed']: raise ValueError('Fixture owners survived cleanup')
        print('PASS NumPy bulk functional validation' if args.mode == 'validate' else 'PASS NumPy bulk bounded sample')
        return 0
    except Exception as error:
        report['passed'] = False; report['error'] = str(error); raise
    finally:
        report['finished_unix'] = time.time(); save(output / 'results.json', report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['plan', 'validate', 'sample'], required=True)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--wheelhouse', type=Path, required=True)
    parser.add_argument('--package', type=Path, default=Path(__file__).resolve().parents[1] / 'tests/plugin_benchmark/bulk_package.py')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--side', type=int, default=512)
    parser.add_argument('--warmups', type=int, default=10)
    parser.add_argument('--cycles', type=int, default=100)
    parser.add_argument('--timeout', type=float, default=600)
    parser.add_argument('--idle-confirmed', action='store_true')
    args = parser.parse_args()
    try: return run(args)
    except Exception as error: print('FAIL: ' + str(error)); return 1

if __name__ == '__main__': raise SystemExit(main())
