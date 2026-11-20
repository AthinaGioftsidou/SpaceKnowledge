"""Tests for LoginThrottle: wrong passwords lock a name for a while."""

import unittest

from spaceknowledge.users.login_throttle import LoginThrottle


class Clock:
    """A clock the test moves by hand, so nothing ever sleeps."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def a_throttle(clock: Clock, max_failures: int = 3, lockout: float = 60.0,
               max_tracked: int = 100) -> LoginThrottle:
    return LoginThrottle(clock, max_failures, lockout, max_tracked)


class TestLocking(unittest.TestCase):
    def setUp(self) -> None:
        self.clock = Clock()
        self.throttle = a_throttle(self.clock)

    def fail(self, name: str = "ada", times: int = 1) -> None:
        for _ in range(times):
            self.throttle.record_failure(name)

    def test_a_new_name_is_not_locked(self) -> None:
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_failures_below_the_limit_do_not_lock(self) -> None:
        self.fail(times=2)
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_reaching_the_limit_locks(self) -> None:
        self.fail(times=3)
        self.assertTrue(self.throttle.is_locked("ada"))

    def test_the_lock_ends_at_the_exact_moment_it_runs_out(self) -> None:
        self.fail(times=3)
        self.clock.now += 59
        self.assertTrue(self.throttle.is_locked("ada"))
        self.clock.now += 1
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_after_the_lock_the_counting_starts_again(self) -> None:
        self.fail(times=3)
        self.clock.now += 60
        self.fail(times=2)
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_a_failure_while_locked_does_not_extend_the_lock(self) -> None:
        self.fail(times=3)
        self.clock.now += 30
        self.fail()
        self.clock.now += 30
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_old_failures_are_forgotten(self) -> None:
        self.fail(times=2)
        self.clock.now += 61
        self.fail()
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_a_success_clears_the_failures(self) -> None:
        self.fail(times=2)
        self.throttle.record_success("ada")
        self.fail(times=2)
        self.assertFalse(self.throttle.is_locked("ada"))

    def test_names_are_not_case_sensitive_and_are_trimmed(self) -> None:
        self.fail("Ada ", 3)
        self.assertTrue(self.throttle.is_locked("ADA"))

    def test_one_name_does_not_lock_another(self) -> None:
        self.fail("ada", 3)
        self.assertFalse(self.throttle.is_locked("bob"))

    def test_a_name_that_does_not_exist_locks_just_the_same(self) -> None:
        # So the lock cannot be used to find out which names exist.
        self.fail("nobody-here", 3)
        self.assertTrue(self.throttle.is_locked("nobody-here"))


class TestMemoryIsBounded(unittest.TestCase):
    def test_it_never_tracks_more_names_than_the_limit(self) -> None:
        throttle = a_throttle(Clock(), max_tracked=3)
        for number in range(10):
            throttle.record_failure(f"name{number}")
        self.assertEqual(3, throttle.tracked_count())

    def test_expired_names_are_dropped_before_live_ones(self) -> None:
        clock = Clock()
        throttle = a_throttle(clock, max_tracked=2)
        throttle.record_failure("old")
        clock.now += 61
        throttle.record_failure("fresh")
        throttle.record_failure("newer")
        self.assertEqual(2, throttle.tracked_count())


class TestArguments(unittest.TestCase):
    def test_bad_arguments_are_refused(self) -> None:
        throttle = a_throttle(Clock())
        for call in (lambda: throttle.is_locked(5), lambda: throttle.record_failure(5),
                     lambda: throttle.record_success(5)):
            with self.assertRaisesRegex(TypeError, "must be"):
                call()  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            LoginThrottle(max_failures=0)
        with self.assertRaises(ValueError):
            LoginThrottle(lockout=0)
        with self.assertRaises(ValueError):
            LoginThrottle(max_tracked=0)


if __name__ == "__main__":
    unittest.main()