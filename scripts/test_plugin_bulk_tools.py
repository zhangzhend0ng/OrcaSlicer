#!/usr/bin/env python3
"""Portable bulk-driver contracts, no native host or performance claims."""
import argparse
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

spec = importlib.util.spec_from_file_location('benchmark_plugin_bulk', Path(__file__).with_name('benchmark_plugin_bulk.py'))
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
ROOT = Path(__file__).resolve().parents[1]


def rows():
    return [{'cycle': cycle, 'warmup': cycle < 0, 'passed': True,
             'load_ms': 1, 'dispatch_execute_ms': 2, 'unload_ms': 3,
             'bulk': {'metrics_ns': {'read': 4}, 'passed': True},
             'memory': {'after_cleanup': {'rss_bytes': 100 + cycle * 4, 'phys_footprint_bytes': 200}},
             'python': {'python_allocated_blocks': 50, 'gc_tracked_objects': 60, 'alive_weakrefs': 0,
                        'plugin_module_count': 0, 'unload_calls': 1},
             'native_capability_expired': True, 'mesh_owners_after_cleanup': 1} for cycle in range(-1, 5)]


class Contracts(unittest.TestCase):
    def test_package_syntax(self):
        source = ROOT / 'tests/plugin_benchmark/bulk_package.py'
        compile(source.read_text(encoding='utf-8'), str(source), 'exec')

    def test_deterministic_wheel(self):
        with tempfile.TemporaryDirectory(prefix='bulk-中文-') as directory:
            a, c = Path(directory)/'a.whl', Path(directory)/'c.whl'
            source = ROOT/'tests/plugin_benchmark/bulk_package.py'
            b.fixture(source, a); b.fixture(source, c)
            self.assertEqual(a.read_bytes(), c.read_bytes())

    def test_real_dependency_and_record(self):
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory)/'bulk.whl'
            b.fixture(ROOT/'tests/plugin_benchmark/bulk_package.py', wheel)
            with zipfile.ZipFile(wheel) as z:
                self.assertIn(b'Requires-Dist: numpy==2.2.6', z.read('orca_benchmark_bulk-1.0.0.dist-info/METADATA'))
                records = csv.reader(io.StringIO(z.read('orca_benchmark_bulk-1.0.0.dist-info/RECORD').decode()))
                for name, checksum, size in records:
                    if not checksum: continue
                    value = z.read(name)
                    self.assertEqual(checksum, 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(value).digest()).rstrip(b'=').decode())
                    self.assertEqual(len(value), int(size))

    def test_warmups_excluded(self):
        result = b.aggregate(rows())
        self.assertEqual((result['warmup_cycles'], result['measured_cycles']), (1, 5))
        self.assertEqual(result['after_cleanup_current_memory']['rss_bytes']['first'], 100)

    def test_rss_trend(self):
        result = b.aggregate(rows())['after_cleanup_current_memory']['rss_bytes']
        self.assertEqual(result['ols_units_per_cycle'], 4)
        self.assertEqual((result['first'], result['last']), (100, 116))
        self.assertEqual((result['first_window_median'], result['last_window_median']), (100, 116))

    def test_bounded_owners(self):
        self.assertTrue(b.aggregate(rows())['all_observed_owners_released'])

    def test_each_owner_failure_is_detected(self):
        for scope, field, value in [('python','alive_weakrefs',1), ('python','plugin_module_count',1),
                                    ('python','unload_calls',0), (None,'native_capability_expired',False),
                                    (None,'mesh_owners_after_cleanup',2)]:
            with self.subTest(field=field):
                sample = rows()
                (sample[-1][scope] if scope else sample[-1])[field] = value
                self.assertFalse(b.aggregate(sample)['all_observed_owners_released'])

    def test_failed_sample_not_hidden(self):
        sample = rows(); sample[-1]['passed'] = False
        with self.assertRaises(ValueError): b.aggregate(sample)

    def test_empty_samples_rejected(self):
        with self.assertRaises(ValueError): b.aggregate([])
        with self.assertRaises(ValueError): b.trend([])

    def test_single_sample_slope_unavailable(self):
        self.assertIsNone(b.trend([1])['ols_units_per_cycle'])

    def test_memory_platform_schema(self):
        # Simulated platform schemas only. PrivateUsage is never relabelled as
        # resident footprint and unavailable fields are not filled with zero.
        for metric in (None, 'phys_footprint_bytes', 'private_commit_bytes'):
            sample = rows()
            for row in sample:
                memory = row['memory']['after_cleanup']
                memory.pop('phys_footprint_bytes')
                if metric: memory[metric] = 1024 + row['cycle']*8
            report = b.aggregate(sample)['after_cleanup_current_memory']
            self.assertEqual(set(report), {'rss_bytes'} | ({metric} if metric else set()))
            if metric: self.assertEqual(report[metric]['ols_units_per_cycle'], 8)

    def test_windows_source_and_link_contract(self):
        # Structure check, deliberately not represented as Windows compilation.
        source = (ROOT/'tests/plugin_benchmark/bulk_main.cpp').read_text(encoding='utf-8')
        memory = source.split('json memory()', 1)[1].split('std::shared_ptr<TriangleMesh> grid', 1)[0]
        win = memory.split('#if defined(_WIN32)', 1)[1].split('#elif defined(__APPLE__)', 1)[0]
        self.assertIn('GetProcessMemoryInfo(GetCurrentProcess()', win)
        self.assertIn('PROCESS_MEMORY_COUNTERS_EX', win)
        self.assertIn('{"rss_bytes", counters.WorkingSetSize}', win)
        self.assertIn('{"private_commit_bytes", counters.PrivateUsage}', win)
        self.assertNotIn('PeakWorkingSetSize', win)
        self.assertNotIn('PeakPagefileUsage', win)
        # ADAPTED: this tree wires the bulk target in tests/plugin_benchmark/CMakeLists.txt
        # (women keeps it in cmake/OrcaPluginBenchmark.cmake alongside its main.cpp harness).
        cmake = (ROOT/'tests/plugin_benchmark/CMakeLists.txt').read_text(encoding='utf-8')
        self.assertIn('target_link_libraries(orca_plugin_bulk_benchmark PRIVATE Psapi)', cmake)

    def test_sampling_requires_explicit_idle(self):
        args = argparse.Namespace(mode='sample', idle_confirmed=False)
        with self.assertRaisesRegex(ValueError, 'idle-confirmed'): b.run(args)

    def test_validation_resource_bound(self):
        for side, warmups, cycles in [(128, 1, 2), (32, 3, 2), (32, 1, 4)]:
            args = argparse.Namespace(mode='validate', idle_confirmed=False, side=side, warmups=warmups, cycles=cycles)
            with self.assertRaisesRegex(ValueError, 'bounded'): b.run(args)


if __name__ == '__main__': unittest.main()
