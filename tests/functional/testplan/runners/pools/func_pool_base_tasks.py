"""Base Testplan Tasks shared by different functional tests."""

import os
from pathlib import Path

import psutil
import tempfile


from testplan.report import Status
from testplan.common.utils.path import fix_home_prefix
from testplan.testing.multitest import MultiTest, testsuite, testcase
from testplan.testing.multitest.base import MultiTestConfig
from testplan.common.utils.strings import slugify


@testsuite
class MySuite:
    @testcase
    def test_comparison(self, env, result):
        result.equal(1, 1, "equality description")
        result.log(env.parent.runpath)
        assert isinstance(env.parent.cfg, MultiTestConfig)
        assert os.path.exists(env.parent.runpath) is True
        assert env.parent.runpath.endswith(slugify(env.parent.cfg.name))

    @testcase
    def test_attach(self, env, result):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as tmpfile:
            tmpfile.write("testplan\n")

        result.attach(tmpfile.name, description=os.path.basename(tmpfile.name))
        os.remove(tmpfile.name)


def get_mtest(name):
    """TODO."""
    return MultiTest(name="MTest{}".format(name), suites=[MySuite()])


def get_mtest_imported(name):
    """TODO."""
    return MultiTest(name="MTest{}".format(name), suites=[MySuite()])


@testsuite
class SuiteKillingWorker:
    def __init__(self, boobytrap_path: str):
        self._boobytrap_path = Path(boobytrap_path)

    @testcase
    def test_comparison(self, env, result):
        if self._boobytrap_path.exists():
            self._boobytrap_path.unlink()
            print("Killing worker {}".format(os.getpid()))
            os.kill(os.getpid(), 9)
        result.equal(1, 1, "equality description")
        result.log(env.parent.runpath)
        assert isinstance(env.parent.cfg, MultiTestConfig)
        assert os.path.exists(env.parent.runpath) is True
        assert env.parent.runpath.endswith(slugify(env.parent.cfg.name))


def multitest_kill_one_worker(boobytrap: str):
    """Test that kills one worker."""
    return MultiTest(
        name="MTestKiller", suites=[SuiteKillingWorker(boobytrap)]
    )


@testsuite
class SimpleSuite:
    @testcase
    def test_simple(self, env, result):
        pass


def multitest_kill_workers(parent_pid):
    """To kill all child workers."""
    if os.getpid() != parent_pid:  # Main process should not be killed
        os.kill(os.getpid(), 9)
    else:
        return MultiTest(name="MTestKiller", suites=[SimpleSuite()])


@testsuite
class SuiteKillRemoteWorker:
    @testcase
    def kill_remote_worker(self, env, result):
        os.kill(os.getpid(), 9)


def multitest_kill_remote_workers():
    return MultiTest(
        name="MTestKillRemoteWorker", suites=[SuiteKillRemoteWorker()]
    )


def schedule_tests_to_pool(plan, pool, schedule_path=None, **pool_cfg):
    pool_name = pool.__name__
    pool = pool(name=pool_name, **pool_cfg)
    plan.add_resource(pool)

    if schedule_path is None:
        schedule_path = fix_home_prefix(
            os.path.dirname(os.path.abspath(__file__))
        )

    uids = []
    for idx in range(1, 10):
        uids.append(
            plan.schedule(
                target="get_mtest",
                module="func_pool_base_tasks",
                path=schedule_path,
                kwargs=dict(name=idx),
                resource=pool_name,
            )
        )

    res = plan.run()

    assert res.run is True
    assert res.success is True
    assert plan.report.passed is True
    assert plan.report.status == Status.PASSED
    # 2 testcase * 9 iterations
    assert plan.report.counter == {"passed": 18, "total": 18, "failed": 0}

    names = sorted(["MTest{}".format(x) for x in range(1, 10)])
    assert sorted([entry.name for entry in plan.report.entries]) == names

    assert isinstance(plan.report.serialize(), dict)

    for idx in range(1, 10):
        name = "MTest{}".format(idx)
        assert plan.result.test_results[uids[idx - 1]].report.name == name

    # check attachment exists in local
    assert os.path.exists(
        plan.report.entries[0].entries[0].entries[1].entries[0]["source_path"]
    )

    # All tasks assigned once
    for uid in pool._task_retries_cnt:
        assert pool._task_retries_cnt[uid] == 0
        assert pool.added_item(uid).reassign_cnt == 0


def target_raises_in_worker(parent_pid):
    """
    Task target that raises when being materialized in process/remote worker.
    """
    if os.getpid() != parent_pid:
        raise RuntimeError("Materialization failed in worker")

    return MultiTest(name="MTest", suites=[MySuite()])
