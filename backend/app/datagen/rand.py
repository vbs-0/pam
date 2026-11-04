import math
import random


class Rand:
    """Deterministic RNG built only on ``random.random()``.

    ``random.Random(str_seed)`` seeding and ``random()`` are the parts of the stdlib RNG that Python guarantees
    to stay stable across versions; every other helper (choice, randint, gauss, ...) may change between
    releases. Building everything on ``random()`` keeps dataset checksums identical across interpreters.
    """

    __slots__ = ("_r",)

    def __init__(self, seed: str):
        self._r = random.Random(seed)

    def u(self) -> float:
        return self._r.random()

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.u()

    def randint(self, a: int, b: int) -> int:
        return a + min(int(self.u() * (b - a + 1)), b - a)

    def chance(self, p: float) -> bool:
        return self.u() < p

    def choice(self, seq):
        return seq[min(int(self.u() * len(seq)), len(seq) - 1)]

    def weighted(self, seq, weights):
        x, acc = self.u() * sum(weights), 0.0
        for item, w in zip(seq, weights, strict=True):
            acc += w
            if x < acc:
                return item
        return seq[-1]

    def normal(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        u1, u2 = max(self.u(), 1e-12), self.u()
        return mu + sigma * math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)

    def lognormal(self, mu: float, sigma: float) -> float:
        return math.exp(self.normal(mu, sigma))

    def shuffle(self, lst: list) -> None:
        for i in range(len(lst) - 1, 0, -1):
            j = self.randint(0, i)
            lst[i], lst[j] = lst[j], lst[i]

    def sample(self, seq, k: int) -> list:
        pool = list(seq)
        self.shuffle(pool)
        return pool[:k]
