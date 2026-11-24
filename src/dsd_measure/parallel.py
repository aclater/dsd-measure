"""Parallel runner: the tests of a suite on several CPU cores, with the result of a serial run.

Every test of every device is an independent piece of work (its own stimuli, its own device
calls), so each runs in its own worker process and the pieces are put back together in the run
order of the tests. Three things tie tests together in a serial run, and each is kept:

* the device delay, measured once and used by the impulse, polarity and overload tests: it is
  measured once here too (a job of its own) and handed to those tests;
* the adapter's provenance log and the list of reference-modulator designs: the pieces are joined
  in run order, the delay probe where a serial run makes it;
* what follows the last test (``measure.finish_result``): run once on the joined result.

The numbers do not depend on the number of jobs: a worker runs the same code on the same inputs
as a serial run, and nothing is shared but the stimulus cache, whose entries are checked by hash.
A device with a work folder named in the suite keeps its numbered files, so its tests stay in
one worker, in order.
"""

import multiprocessing as mp
import os
import signal
import time
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait

from . import stimcache
from .measure import Chain, finish_result, measure_device

#: Tests that use the device delay (``Chain.latency``).
LATENCY_TESTS = ("impulse", "polarity", "overload")
#: Adapter attributes the pre-flight may change (the file type it settled on, the number of the next
#: work file); a worker's own adapter gets the same values.
SYNC_ATTRS = ("input_ext", "_n")
MAX_DEFAULT_JOBS = 16


CGROUP_ROOT = "/sys/fs/cgroup"
#: Share of a control group's memory headroom that the jobs may plan to use. The limit is a hard one
#: (the kernel kills a process that crosses it) and a run's peak is a little above the plan.
CGROUP_HEADROOM = 0.8


def _cgroup_dirs(root=CGROUP_ROOT, proc="/proc/self/cgroup"):
    """This process's control group (version 2) and its parents, innermost first; empty when unknown."""
    try:
        with open(proc) as f:
            rel = next(line.strip().split("::", 1)[1] for line in f if line.startswith("0::"))
    except (OSError, StopIteration, IndexError):
        return []
    parts = [x for x in rel.split("/") if x and x != ".."]
    return [os.path.join(root, *parts[:n]) for n in range(len(parts), -1, -1)]


def _cgroup_value(folder, name):
    try:
        with open(os.path.join(folder, name)) as f:
            return f.read().split()
    except OSError:
        return []


def cgroup_gib(root=CGROUP_ROOT, proc="/proc/self/cgroup"):
    """Memory left under the tightest ``memory.max`` of this process's control groups (a container's
    or a systemd scope's limit), in GiB, or None when no limit is set or it cannot be read."""
    left = None
    for folder in _cgroup_dirs(root, proc):
        limit, used = _cgroup_value(folder, "memory.max"), _cgroup_value(folder, "memory.current")
        if limit and used and limit[0].isdigit() and used[0].isdigit():
            room = max(0, int(limit[0]) - int(used[0])) / 2**30
            left = room if left is None else min(left, room)
    return left


def cgroup_cpus(root=CGROUP_ROOT, proc="/proc/self/cgroup"):
    """The tightest CPU quota of this process's control groups in whole CPUs (at least 1), or None."""
    cpus = None
    for folder in _cgroup_dirs(root, proc):
        v = _cgroup_value(folder, "cpu.max")
        if len(v) == 2 and v[0].isdigit() and v[1].isdigit() and int(v[1]) > 0:
            n = max(1, -(-int(v[0]) // int(v[1])))
            cpus = n if cpus is None else min(cpus, n)
    return cpus


def cores():
    try:
        n = len(os.sched_getaffinity(0))
    except AttributeError:  # not on Linux
        n = os.cpu_count() or 1
    quota = cgroup_cpus()
    return n if quota is None else max(1, min(n, quota))


#: Memory a run needs, in GiB: a fixed part and a part per job (peaks measured on the reference chain:
#: quick 2.1 at 1 job, 4.2 at 4, 5.8 at 8; full 7.5 at 1 job, 14.7 at 8).
MEMORY_GIB = {"full": (6.5, 1.1)}
MEMORY_GIB_DEFAULT = (1.6, 0.6)


def available_gib():
    """Memory the system says is available (Linux), or None when it cannot be told."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 2**20
    except (OSError, ValueError, IndexError):
        pass
    return None


def default_jobs(profile="quick"):
    """All cores up to four, then half of them (at least four, at most 16), and no more than the
    memory holds for this profile: the memory the system says is available and, under a memory limit
    of a container or a systemd scope, what is left below that limit. ``DSD_MEASURE_JOBS`` overrides."""
    env = os.environ.get("DSD_MEASURE_JOBS", "")
    if env.isdigit() and int(env) > 0:
        return int(env)
    n = cores()
    jobs = max(1, min(n, max(4, n // 2), MAX_DEFAULT_JOBS))
    mem, limit = available_gib(), cgroup_gib()
    if limit is not None:
        mem = CGROUP_HEADROOM * limit if mem is None else min(mem, CGROUP_HEADROOM * limit)
    if mem is not None:
        fixed, each = MEMORY_GIB.get(profile, MEMORY_GIB_DEFAULT)
        jobs = max(1, min(jobs, int((mem - fixed) / each)))
    return jobs


class _SeededChain(Chain):
    """A chain that is told the device delay instead of measuring it; notes where it was asked."""

    def __init__(self, adapter, in_rate, lat):
        super().__init__(adapter, in_rate)
        self._seed = lat
        self.mark = None

    def latency(self, in_rate):
        if self._lat is None:
            self._lat = self._seed
            self.mark = (len(self.a.log), len(self.ntf))
        return self._lat[0]


def _terminate(*_):
    raise KeyboardInterrupt  # so a running tool's process group is killed (adapters.run_checked)


def _init_worker():
    signal.signal(signal.SIGTERM, _terminate)


def _adapter(spec, state):
    from .adapters import make_adapter
    a = make_adapter(spec)
    for k, v in state.items():
        setattr(a, k, v)
    return a


def _probe(spec, state, in_rate):
    """Worker: measure the device delay. Returns None when the probe fails (the tests then fail
    one by one with the device's own error, as in a serial run)."""
    stimcache.reset_stats()
    a = _adapter(spec, state)
    try:
        ch = Chain(a, in_rate)
        ch.latency(in_rate)
        return {"lat": ch._lat, "log": list(a.log), "ntf": dict(ch.ntf), "cache": stimcache.stats()}
    except Exception:
        return None
    finally:
        a.close()


def _tests(spec, state, profile, in_rate, names, lat):
    """Worker: run the tests ``names`` on a fresh adapter. Returns the unfinished result and the logs."""
    stimcache.reset_stats()
    a = _adapter(spec, state)
    t0 = time.time()
    try:
        ch = _SeededChain(a, in_rate, lat) if lat is not None else Chain(a, in_rate)
        res = measure_device(a, profile, in_rate, log=lambda *args, **kw: None, only=list(names), chain=ch, finish=False)
        return {"res": res, "log": list(a.log), "mark": getattr(ch, "mark", None), "cache": stimcache.stats(),
                "seconds": time.time() - t0}
    finally:
        a.close()


def _stop(ex, grace=5.0):
    """Stop the workers of ``ex`` now. SIGTERM first: a worker then kills the tool it is running
    and removes its work folder (``_terminate``); whatever is still alive after ``grace`` seconds
    is killed."""
    procs = list((getattr(ex, "_processes", None) or {}).values())
    ex.shutdown(wait=False, cancel_futures=True)
    for p in procs:
        if p.is_alive():
            p.terminate()
    end = time.time() + grace
    for p in procs:
        p.join(max(0.0, end - time.time()))
    for p in procs:
        if p.is_alive():
            p.kill()


def _splice(seq, at, extra):
    return seq[:at] + extra + seq[at:]


def merge(adapter, pieces, probe=None):
    """Join the results of ``pieces`` (worker returns, in run order) into one serial-run result."""
    res = {"metrics": {}, "plots": {}, "not_run": {}, "errors": [], "notes": [], "timing_s": {}}
    M = res["metrics"]
    log, ntf, probe_used = [], [], probe is None
    for pc in pieces:
        r = pc["res"]
        for k, v in r["metrics"].items():
            if isinstance(v, dict) and isinstance(M.get(k), dict):
                M[k].update(v)  # the filter summary: the impulse test starts it, the alias tones add to it
            else:
                M[k] = v
        res["plots"].update(r["plots"])
        res["not_run"].update(r["not_run"])
        res["errors"] += r["errors"]
        res["timing_s"].update(r["timing_s"])
        own = [n for n in r["notes"] if n not in res["notes"] or r["notes"].count(n) > 1]
        res["notes"] += own  # a note every delay-using test repeats is kept once, as a serial run writes it
        plog, pntf = list(pc["log"]), list(r["reference_chain_ntf"].items())
        if pc.get("mark") is not None and not probe_used:
            plog = _splice(plog, pc["mark"][0], probe["log"])
            pntf = _splice(pntf, pc["mark"][1], list(probe["ntf"].items()))
            probe_used = True
        log += plog
        ntf += pntf
    res["reference_chain_ntf"] = dict(ntf)
    adapter.log.extend(log)
    return finish_result(res, adapter)


def _serial_only(adapter):
    work = getattr(adapter, "_work", None)
    return work is not None and work.user is not None


def measure_all(adapters, specs, profile, in_rate, only=None, jobs=None, log=print):
    """Measure every adapter with ``jobs`` worker processes; returns one result per adapter, in order.

    ``specs`` are the suite tables the adapters were made from (a worker builds its own adapter).
    """
    from .plan import SECONDS, TESTS, applies, label
    jobs = jobs or default_jobs(profile)
    work = []  # (device index, [test names], estimated seconds)
    for d, a in enumerate(adapters):
        names = [t for t in TESTS if not only or t in only]
        est = SECONDS.get(profile, SECONDS["quick"]).get(a.klass, {})
        if _serial_only(a):
            work.append((d, names, sum(est.get(t, 0) for t in names)))
        else:
            work += [(d, [t], est.get(t, 0)) for t in names]
    total = sum(len(names) for _, names, _ in work)
    state = [{k: getattr(a, k) for k in SYNC_ATTRS if hasattr(a, k)} for a in adapters]
    needs_lat = [any(t in LATENCY_TESTS and applies(t, a.klass) for dd, names, _ in work if dd == d and len(names) == 1 for t in names)
                 for d, a in enumerate(adapters)]
    methods = mp.get_all_start_methods()
    ctx = mp.get_context("forkserver" if "forkserver" in methods else "spawn")
    if "forkserver" in methods:
        ctx.set_forkserver_preload(["dsd_measure.measure", "dsd_measure.adapters", "dsd_measure.floor"])
    done = {}       # (device, first test name) -> worker return
    probes = {}     # device -> probe return or None
    count = 0
    ex = ProcessPoolExecutor(max_workers=max(1, min(jobs, len(work) + sum(needs_lat))), mp_context=ctx, initializer=_init_worker)
    try:
        pending = {}
        waiting = []  # delay-using tests, started when their device's probe is back
        for d, need in enumerate(needs_lat):
            if need:
                pending[ex.submit(_probe, specs[d], state[d], in_rate)] = ("probe", d, None)
        for d, names, _ in sorted(work, key=lambda w: -w[2]):  # longest first
            if needs_lat[d] and len(names) == 1 and names[0] in LATENCY_TESTS:
                waiting.append((d, names))
            else:
                pending[ex.submit(_tests, specs[d], state[d], profile, in_rate, names, None)] = ("tests", d, names)
        while pending:
            ready, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in ready:
                kind, d, names = pending.pop(fut)
                out = fut.result()
                if out:
                    stimcache.add_stats(out["cache"])
                if kind == "probe":
                    probes[d] = out
                    for dd, nn in [w for w in waiting if w[0] == d]:
                        waiting.remove((dd, nn))
                        pending[ex.submit(_tests, specs[dd], state[dd], profile, in_rate, nn, out["lat"] if out else None)] = ("tests", dd, nn)
                    continue
                done[(d, names[0])] = out
                r = out["res"]
                for t in names:
                    count += 1
                    what = f" ({label(t)})" if t in TESTS else ""
                    tail = (f"skipped: {r['not_run'][t]}" if t in r["not_run"] else f"done in {r['timing_s'].get(t, 0):g} s")
                    log(f"[{count:>{len(str(total))}}/{total}] -> {adapters[d].name}: {t}{what} ... {tail}")
    except BaseException:
        _stop(ex)
        raise
    ex.shutdown()
    results = []
    for d, a in enumerate(adapters):
        pieces = [done[(dd, names[0])] for dd, names, _ in work if dd == d]
        results.append(merge(a, pieces, probes.get(d)))
    return results
