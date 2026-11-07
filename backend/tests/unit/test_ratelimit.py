import threading

from app.core.ratelimit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_refuses_with_retry_after() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock=clock)
    for _ in range(3):
        assert limiter.hit("k", limit=3, window_s=60) is None
        clock.now += 10
    assert limiter.hit("k", limit=3, window_s=60) == 30  # oldest hit (t=1000) frees at 1060


def test_window_slides_one_hit_at_a_time() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock=clock)
    limiter.hit("k", 2, 60)
    clock.now += 30
    limiter.hit("k", 2, 60)
    clock.now += 30  # the first hit has just aged out, the second has not
    assert limiter.hit("k", 2, 60) is None
    assert limiter.hit("k", 2, 60) is not None


def test_refused_attempts_do_not_extend_the_wait() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(clock=clock)
    limiter.hit("k", 1, 60)
    for _ in range(5):
        limiter.hit("k", 1, 60)  # refused, not recorded
    clock.now += 60
    assert limiter.hit("k", 1, 60) is None


def test_keys_are_independent() -> None:
    limiter = SlidingWindowLimiter(clock=FakeClock())
    limiter.hit("a", 1, 60)
    assert limiter.hit("a", 1, 60) is not None
    assert limiter.hit("b", 1, 60) is None


def test_look_record_and_clear() -> None:
    limiter = SlidingWindowLimiter(clock=FakeClock())
    assert limiter.blocked_for("k", 2, 60) is None
    limiter.record("k", 60)
    limiter.record("k", 60)
    assert limiter.blocked_for("k", 2, 60) is not None
    limiter.clear("k")
    assert limiter.blocked_for("k", 2, 60) is None


def test_memory_is_bounded() -> None:
    limiter = SlidingWindowLimiter(max_keys=100, clock=FakeClock())
    for i in range(1_000):
        limiter.hit(f"ip:{i}", 5, 60)
    assert len(limiter) == 100


def test_least_recently_used_key_is_dropped_first() -> None:
    limiter = SlidingWindowLimiter(max_keys=2, clock=FakeClock())
    limiter.hit("busy", 1, 60)  # oldest by insertion
    limiter.hit("idle", 1, 60)
    limiter.hit("busy", 1, 60)  # used again, so now the most recent
    limiter.hit("new", 1, 60)  # must evict "idle": plain first-in-first-out would drop "busy"
    assert limiter.hit("busy", 1, 60) is not None  # still remembered, still limited
    assert limiter.hit("idle", 1, 60) is None  # forgotten


def test_thread_safe_under_contention() -> None:
    limiter = SlidingWindowLimiter()
    allowed: list[bool] = []
    start = threading.Barrier(50)

    def attempt() -> None:
        start.wait()
        allowed.append(limiter.hit("shared", limit=10, window_s=60) is None)

    threads = [threading.Thread(target=attempt) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert allowed.count(True) == 10
