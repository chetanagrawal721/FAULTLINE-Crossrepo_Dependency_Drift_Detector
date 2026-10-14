"""Replay a witness from its evidence bundle on another machine.

The bundle is verified first (a bad bundle is refused, never replayed). The artifact tree comes from the bundle and is checked
against its content hash. Wheels are fetched only by sha256 from the bundle's lock files. Nothing is ever fetched by branch,
tag or any other moving reference. The outcome is exactly one of:

  EXACT_REPRODUCTION   same package sets, same environment image, reference passes 3/3, consumer fails 3/3 with the same signature
  ENVIRONMENT_LIMITED  the failure reproduces but the environment differs, or a world could not be rebuilt for environmental reasons
  NON_REPRODUCIBLE     the worlds rebuilt as described but the outcomes differ, or the artifact does not match its hash
"""
import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from ..core.enums import WorldKind
from ..core.models import FailureSignature
from ..oracles.artifacts import content_hash as tree_hash
from ..oracles.o_import import run_o_import
from ..sandbox.client import SandboxClient
from ..storage.store import Store
from ..worlds.builder import WorldBuilder, WorldBuildError
from .bundle import verify_bundle
from .signature import signature_of


class ReplayOutcome(StrEnum):
    EXACT_REPRODUCTION = "EXACT_REPRODUCTION"
    ENVIRONMENT_LIMITED = "ENVIRONMENT_LIMITED"
    NON_REPRODUCIBLE = "NON_REPRODUCIBLE"


class ReplayRefused(Exception):
    """The bundle failed verification, so nothing was executed."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


@dataclass
class ReplayResult:
    outcome: ReplayOutcome
    reasons: list[str]
    reference_passes: int = 0
    consumer_failures: int = 0
    signature_matches: bool = False
    fetched_by_moving_ref: bool = False                       # always False: asserted by tests
    details: dict = field(default_factory=dict)


def _entries(world_json: dict) -> set[tuple[str, str, str | None]]:
    return {(e["name"], e["version"], e["artifact_sha256"]) for e in world_json["entries"]}


def replay(bundle_path: str | Path, sbx: SandboxClient, image: str, store: Store, *, workdir: Path | None = None) -> ReplayResult:
    v = verify_bundle(bundle_path)
    if not v.ok:
        raise ReplayRefused(v.errors)
    manifest = v.manifest
    reasons: list[str] = []
    tmp = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="faultline-replay-"))
    try:
        with zipfile.ZipFile(bundle_path) as z:
            read = {n: z.read(n) for n in z.namelist() if n != "manifest.json"}
        ref_json, test_json = json.loads(read["worlds/reference.world.json"]), json.loads(read["worlds/consumer.world.json"])
        plan = json.loads(read["plan/oracle_plan.json"])
        sig = FailureSignature.model_validate(json.loads(read["witness.json"])["signature"])
        env = json.loads(read["env/env_profile.json"])
        if plan.get("oracle", "o_import") != "o_import":
            raise ReplayRefused([f"replay supports import witnesses; this bundle comes from {plan['oracle']}, so nothing was executed"])
        entry = plan["entry_point"]
        args = plan.get("args", {})
        modules = args.get("modules") or [entry]
        pythonpath = args.get("pythonpath") or "/artifact/src"
        top_level = modules[0]

        # 1. the artifact: restored from the bundle only, and it must match its content hash
        tree = tmp / "artifact"
        for name, data in read.items():
            if name.startswith("artifact/tree/"):
                t = tree / name.removeprefix("artifact/tree/")
                t.parent.mkdir(parents=True, exist_ok=True)
                t.write_bytes(data)
        want = manifest["artifact"]["content_hash"]
        if not tree.exists() or tree_hash(tree) != want:
            return ReplayResult(ReplayOutcome.NON_REPRODUCIBLE, [f"the artifact source in the bundle does not match its content hash {want}; "
                                                                 "it is not fetched from any branch or tag"])
        dest = store.artifact_dir(want)
        if not dest.exists():
            shutil.copytree(tree, dest)
            reasons.append(f"artifact {want} was missing from this machine's store and was restored from the bundle (hash verified)")

        # 2. the worlds: wheels by sha256 only
        builder = WorldBuilder(sbx, image)
        worlds = {}
        for side, wj in (("reference", ref_json), ("consumer", test_json)):
            lock = read[f"worlds/{side}.lock.txt"].decode()
            try:
                w = builder.materialize(lock, WorldKind.REFERENCE if side == "reference" else WorldKind.PROJECTED)
                if builder.build(w, lock).status == "FAILED":
                    return ReplayResult(ReplayOutcome.ENVIRONMENT_LIMITED, reasons + [f"the {side} world could not be built offline on this machine"])
            except WorldBuildError as e:
                return ReplayResult(ReplayOutcome.ENVIRONMENT_LIMITED,
                                    reasons + [f"the {side} world could not be rebuilt ({e.message}); a pinned wheel may no longer be available"])
            worlds[side] = w
            if _entries(wj) != {(x.name, x.version, x.artifact_sha256) for x in w.entries}:
                return ReplayResult(ReplayOutcome.NON_REPRODUCIBLE, reasons + [f"the rebuilt {side} world differs from the bundle's package set"])

        # 3. three runs per side
        ref_runs = [run_o_import(sbx, image, world_hash=worlds["reference"].world_hash, artifact_hash=want, top_level=top_level, modules=modules,
                                 pythonpath=(pythonpath,)) for _ in range(3)]
        test_runs = [run_o_import(sbx, image, world_hash=worlds["consumer"].world_hash, artifact_hash=want, top_level=top_level, modules=modules,
                                  pythonpath=(pythonpath,)) for _ in range(3)]

        def outcome_of(r):
            return next((e for e in r.entries if e.entry == entry), None)
        ref_pass = sum(1 for r in ref_runs if (o := outcome_of(r)) is not None and o.passed)
        fails = [o for r in test_runs if (o := outcome_of(r)) is not None and not o.passed and not o.not_applicable]
        same_sig = len(fails) == 3 and all(signature_of(o, entry) == sig for o in fails)
        res = ReplayResult(ReplayOutcome.NON_REPRODUCIBLE, reasons, ref_pass, len(fails), same_sig)
        if ref_pass == 3 and same_sig:
            same_env = image == env.get("image_ref")
            if same_env:
                res.outcome = ReplayOutcome.EXACT_REPRODUCTION
                res.reasons.append("same package sets, same execution image, reference passed 3/3 and the consumer failed 3/3 with the identical signature")
            else:
                res.outcome = ReplayOutcome.ENVIRONMENT_LIMITED
                res.reasons.append(f"the failure reproduced with the identical signature, but the execution image differs (bundle {env.get('image_ref')}, "
                                   f"here {image})")
        else:
            if ref_pass != 3:
                res.reasons.append(f"the reference world passed only {ref_pass} of 3 runs")
            if not same_sig:
                res.reasons.append(f"the consumer failed {len(fails)} of 3 runs, and not all with the bundle's signature")
        return res
    finally:
        if workdir is None:
            shutil.rmtree(tmp, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    import sys

    from ..core.config import Settings
    from ..sandbox.images import default_image
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m faultline.witnesses.replay <bundle.zip>")
        return 2
    try:
        res = replay(args[0], SandboxClient(), default_image(), Store(Settings.from_env().store_path))
    except ReplayRefused as e:
        print("REFUSED: nothing was executed")
        for err in e.errors:
            print("  -", err)
        return 1
    print(res.outcome.value)
    for r in res.reasons:
        print("  -", r)
    return 0 if res.outcome != ReplayOutcome.NON_REPRODUCIBLE else 1


if __name__ == "__main__":
    raise SystemExit(main())
