#!/usr/bin/env python3
"""Real Manager/Python wheel-cache regression; no GUI, network, or mocked imports."""
from pathlib import Path
import argparse,base64,csv,hashlib,io,json,platform,shutil,struct,subprocess,sys,time,warnings,zipfile

CASES = tuple(f"{kind}_{fault}" for kind in ("entry", "dependency")
              for fault in ("crc", "unsafe", "duplicate", "conflict", "legacy")) + ("entry_case_alias",)

HEADER='''# /// script
# requires-python = ">=3.12"
# dependencies = []
# [tool.orcaslicer.plugin]
# name = "Wheel cache consumer"
# version = "1.0.0"
# ///
'''
MAIN='''import orca, pathlib
class Probe(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Wheel cache probe"
    def execute(self):
        root=pathlib.Path(__file__).parent
        path=root/"resource.txt"
        return orca.ExecutionResult.success("real callback", path.read_text() if path.exists() else "MISSING")
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Probe)
'''
CONSUMER=HEADER+'''import orca, cachedep
class Probe(orca.script.ScriptPluginCapabilityBase):
    def get_name(self): return "Wheel cache probe"
    def execute(self): return orca.ExecutionResult.success("real dependency callback", cachedep.read_resource())
@orca.plugin
class Package(orca.base):
    def register_capabilities(self): orca.register_capability(Probe)
'''
DEP='''import pathlib
def read_resource():
    path=pathlib.Path(__file__).parent/"resource.txt"
    return path.read_text() if path.exists() else "MISSING"
'''
def wheel(path,name,code,resource,fault=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    info=name+'-1.0.0.dist-info'
    entries=[(name+'/__init__.py',code.encode()),(name+'/resource.txt',resource.encode()),
      (info+'/METADATA',f'Metadata-Version: 2.1\nName: {name}\nVersion: 1.0.0\nRequires-Python: >=3.12\n\n'.encode()),
      (info+'/WHEEL',b'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n'),(info+'/top_level.txt',(name+'\n').encode())]
    if fault=='unsafe':entries.append(('../escaped.txt',b'never escape'))
    elif fault=='case_alias':entries.append((name+'/RESOURCE.TXT',b'COLLISION'))
    elif fault=='duplicate':entries.append((name+'/resource.txt',b'duplicate'))
    elif fault=='conflict':entries.extend([(name+'/block',b'file'),(name+'/block/child',b'impossible directory')])
    else:entries.append((name+'/tail.bin',b'tail bytes whose CRC will be checked'))
    record=io.StringIO();writer=csv.writer(record,lineterminator="\n")
    for key,data in entries:writer.writerow([key,"sha256="+base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode(),len(data)])
    writer.writerow([info+"/RECORD","",""]);entries.append((info+"/RECORD",record.getvalue().encode()))
    with warnings.catch_warnings():
      warnings.simplefilter('ignore',UserWarning)
      with zipfile.ZipFile(path,'w',zipfile.ZIP_STORED) as archive:
        for key,data in entries:
          entry=zipfile.ZipInfo(key,(2026,1,1,0,0,0));entry.compress_type=zipfile.ZIP_STORED;entry.create_system=3;entry.external_attr=0o100644<<16
          archive.writestr(entry,data)
    if fault=='crc':
      with zipfile.ZipFile(path) as archive:i=archive.getinfo(name+'/tail.bin');offset=i.header_offset
      data=bytearray(path.read_bytes());name_size,extra_size=struct.unpack_from('<HH',data,offset+26)
      data[offset+30+name_size+extra_size]^=0x01;path.write_bytes(data)

def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def create_fixtures(out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=False)
    for kind, name, code in [("entry", "cacheprobe", MAIN), ("dependency", "cachedep", DEP)]:
        for fault in (("crc", "unsafe", "duplicate", "conflict", "legacy", "case_alias") if kind == "entry" else ("crc", "unsafe", "duplicate", "conflict", "legacy")):
            folder = out / (kind + "_" + fault)
            folder.mkdir()
            (folder / "consumer.py").write_text(CONSUMER, encoding="utf-8")
            filename = name + "-1.0.0-py3-none-any.whl"
            wheel(folder / "bad" / filename, name, code, "ORIGINAL", None if fault == "legacy" else fault)
            wheel(folder / "good" / filename, name, code, "COMPLETE")
            wheel(folder / "updated" / filename, name, code, "UPDATED")
    manifest = [{"path": file.relative_to(out).as_posix(), "sha256": sha256(file), "bytes": file.stat().st_size}
                for file in sorted(out.rglob("*")) if file.is_file()]
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_observation(scenario, data):
    if data.get("scenario") != scenario or data.get("passed") is not True or data.get("interpreter_stopped") is not True:
        raise ValueError("Native pass/scenario/interpreter shutdown evidence missing")
    if data.get("failures") != [] or "fatal_error" in data:
        raise ValueError("Native recovery assertions failed")
    observations = data.get("observations", [])
    phases = {item["phase"]: item for item in observations}
    if len(phases) != len(observations):
        raise ValueError("Duplicate observation phase")
    if scenario == "entry_restart":
        expected = {"cross_process_complete_cache_reuse": "UPDATED"}
        rejected = []
    else:
        legacy = scenario.endswith("_legacy")
        payload = "ORIGINAL" if legacy else "COMPLETE"
        expected = {"legacy_unmarked_cache_recovery" if legacy else "good_archive_repair": payload,
                    "complete_cache_reuse": payload, "truncated_cached_resource_recovery": payload,
                    "invalid_completion_record_recovery": payload, "missing_cached_resource_recovery": payload,
                    "changed_archive_recovery": "UPDATED"}
        case_alias = scenario == "entry_case_alias"
        if case_alias and not isinstance(data.get("filesystem_case_insensitive"), bool):
            raise ValueError("Missing actual filesystem case-sensitivity probe")
        distinct_case = case_alias and data["filesystem_case_insensitive"] is False
        rejected = [] if legacy or distinct_case else ["first_corrupt_load", "same_corrupt_retry", "corrupt_replacement_rejected"]
        if distinct_case:
            expected["distinct_case_sensitive_entries"] = "ORIGINAL"
        if rejected:
            expected["restored_archive_reuse"] = payload
    if set(phases) != set(expected) | set(rejected):
        raise ValueError("Incomplete or unexpected real loading phases")
    for phase, payload in expected.items():
        item = phases[phase]
        if item.get("loaded") is not True or item.get("actual_callback_data") != payload or item.get("error"):
            raise ValueError("Real Script callback mismatch: " + phase)
        if item.get("cache_exists") is not True or ".orca-wheel-cache.json" not in item.get("cache_files", {}):
            raise ValueError("Successful import has no published completion record")
    for phase in rejected:
        item = phases[phase]
        if item.get("loaded") is not False or not item.get("error") or "actual_callback_data" in item:
            raise ValueError("Corrupt archive reached a real callback: " + phase)
        if phase != "corrupt_replacement_rejected" and item.get("cache_exists") is not False:
            raise ValueError("Failed extraction published a partial final directory")


def run(native, output, timeout=60):
    native, output = Path(native).resolve(), Path(output).resolve()
    if not native.is_file():
        raise ValueError("Native target does not exist")
    # ADAPTED (port): ctest reruns land on the same report path; wipe stale
    # reports instead of refusing, keeping every scenario's fixtures fresh.
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True, exist_ok=False)
    fixtures = output / "fixtures"
    create_fixtures(fixtures)
    report = {"schema": 1, "ok": False, "platform": platform.platform(),
              "scope": "real PluginManager loads, actual Python Script callbacks, filesystem recovery; no GUI",
              "native": str(native), "native_sha256": sha256(native),
              "fixture_manifest_sha256": sha256(fixtures / "manifest.json"), "cases": []}
    for scenario in (*CASES, "entry_restart"):
        # Only the explicit restart case reuses an earlier entry-wheel profile.
        profile = output / (("entry_crc" if scenario == "entry_restart" else scenario) + "-profile-中文")
        result_path = output / (scenario + ".json")
        start = time.monotonic()
        row = {"scenario": scenario, "ok": False, "profile": str(profile), "result": str(result_path)}
        try:
            process = subprocess.run([str(native), scenario, str(fixtures), str(profile), str(result_path)],
                                     capture_output=True, timeout=timeout)
            (output / (scenario + ".log")).write_bytes(process.stdout + process.stderr)
            row["returncode"] = process.returncode
            if process.returncode:
                raise ValueError("Native process failed")
            data = json.loads(result_path.read_text(encoding="utf-8"))
            verify_observation(scenario, data)
            row["result_sha256"] = sha256(result_path)
            row["ok"] = True
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            row["error"] = str(error)
        row["seconds"] = round(time.monotonic() - start, 4)
        report["cases"].append(row)
        (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["ok"] = all(row["ok"] for row in report["cases"])
    (output / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory; failures and original fixtures are retained")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    result = run(args.native, args.output, args.timeout)
    print(json.dumps({"ok": result["ok"], "passed": sum(row["ok"] for row in result["cases"]),
                      "total": len(result["cases"]), "results": str(args.output / "results.json")}, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
