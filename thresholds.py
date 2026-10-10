"""
Erasure-tolerance threshold estimation.

The threshold of a scheme is the erasure probability at which it recovers
the blob half the time. It is reported throughout the project, so how it is
estimated matters more than any single figure that uses it.

WHY THIS REPLACES LINEAR INTERPOLATION

The original estimator interpolated linearly between the two swept rates
that bracket the 50% crossing. With few trials per rate that is fragile,
because it rests on exactly two points and ignores everything else. It
produced a threshold of 0.505 for 1D-RS -- above the 0.5 an MDS code with
n = 2k can possibly sustain. Nothing was wrong with the decoder: at erasure
probability 0.50 three trials happened to give 2/3 successes where the true
probability is 0.504, a coin flip's worth of luck, and the interpolation
turned that into a third decimal place the data never supported.

The estimator here fits a logistic curve to every trial at every rate by
maximum likelihood, so a lucky bin is weighed against all the others instead
of defining the answer, and it reports a confidence interval so the
precision is stated rather than implied.

THE AXIS

Thresholds are on the erasure-probability axis -- the per-symbol erasure
probability epsilon of a binary erasure channel BEC(epsilon), which is the
target rate the sweep feeds to its random mask. That is the standard model
in coding theory. The realised fraction of erased symbols in a given trial
is a random variable around epsilon, not a better axis: a code's threshold
is a property of the channel it can survive.

For an MDS code the answer is known exactly, which makes 1D-RS a check on
the whole method -- see mds_success_probability().
"""
import math
import random


def _fit_logistic(xs, ks, ns, ridge=1e-3, iters=100):
    """Maximum-likelihood logistic regression on binomial counts.

    xs: covariate per group; ks: successes; ns: trials. Returns (a, b) with
    P(success) = 1 / (1 + exp(-(a + b x))).

    A small ridge penalty on the slope keeps the fit finite when the data are
    perfectly separated -- which a sharp threshold sampled coarsely can be --
    without visibly moving it when they are not.
    """
    a, b = 0.0, 0.0
    for _ in range(iters):
        g_a = g_b = 0.0
        h_aa = h_ab = h_bb = 0.0
        for x, k, n in zip(xs, ks, ns):
            z = max(-40.0, min(40.0, a + b * x))
            p = 1.0 / (1.0 + math.exp(-z))
            w = n * p * (1.0 - p)
            r = k - n * p
            g_a += r
            g_b += r * x
            h_aa += w
            h_ab += w * x
            h_bb += w * x * x
        g_b -= ridge * b
        h_bb += ridge
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-12:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (h_aa * g_b - h_ab * g_a) / det
        a += da
        b += db
        if abs(da) < 1e-10 and abs(db) < 1e-10:
            break
    return a, b


def _pool(points):
    """Collapse (rate, success) pairs into per-rate binomial counts."""
    by = {}
    for x, s in points:
        k, n = by.get(x, (0, 0))
        by[x] = (k + int(s), n + 1)
    xs = sorted(by)
    return xs, [by[x][0] for x in xs], [by[x][1] for x in xs]


def estimate_threshold(points, n_boot=2000, seed=20261010):
    """Estimate the 50% erasure-tolerance threshold with a 95% interval.

    points: iterable of (erasure_probability, recovered_bool), one per trial.

    Returns dict(threshold, ci_low, ci_high, n_trials). The covariate is
    centred and scaled before fitting, for numerical stability, and the
    threshold is mapped back. The interval is a nonparametric bootstrap over
    trials within each rate, so it reflects the actual trial counts.
    """
    points = list(points)
    xs, ks, ns = _pool(points)
    if not any(0 < k for k in ks) or not any(k < n for k, n in zip(ks, ns)):
        return None                       # never or always recovered
    mu = sum(x * n for x, n in zip(xs, ns)) / sum(ns)
    sd = (sum(n * (x - mu) ** 2 for x, n in zip(xs, ns)) / sum(ns)) ** 0.5 or 1.0

    def fit(xs_, ks_, ns_):
        a, b = _fit_logistic([(x - mu) / sd for x in xs_], ks_, ns_)
        if b >= 0:                        # must fall as erasure rises
            return None
        return mu + sd * (-a / b)

    th = fit(xs, ks, ns)
    if th is None:
        return None

    # Bootstrap: resample trials with replacement within each rate.
    rng = random.Random(seed)
    groups = {}
    for x, s in points:
        groups.setdefault(x, []).append(int(s))
    boots = []
    for _ in range(n_boot):
        bk = [sum(rng.choice(groups[x]) for _ in groups[x]) for x in xs]
        t = fit(xs, bk, ns)
        if t is not None:
            boots.append(t)
    boots.sort()
    lo = boots[int(0.025 * len(boots))] if boots else th
    hi = boots[int(0.975 * len(boots)) - 1] if boots else th
    return dict(threshold=th, ci_low=lo, ci_high=hi, n_trials=len(points))


def points_from_trials(trial_records):
    """(rate, recovered) per trial, from benchmark-style per-rate records.

    Uses success_per_trial where the record has it. Older records carry only
    a success count, so the per-trial list is rebuilt from that count: on the
    erasure-probability axis every trial at a given rate shares the same
    covariate, so only the count is needed and nothing is assumed about which
    individual trial succeeded.
    """
    pts = []
    for t in trial_records:
        if "success_per_trial" in t:
            pts.extend((t["rate"], s) for s in t["success_per_trial"])
        else:
            pts.extend([(t["rate"], True)] * t["successes"]
                       + [(t["rate"], False)] * (t["trials"] - t["successes"]))
    return pts


# ------------------------------------------------------------ exact MDS curve
def binom_cdf(x, n, p):
    """P(Binomial(n, p) <= x), summed in log space so large n is safe."""
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 1.0 if x >= n else 0.0
    lp, lq = math.log(p), math.log1p(-p)
    lg = math.lgamma
    terms = [lg(n + 1) - lg(j + 1) - lg(n - j + 1) + j * lp + (n - j) * lq
             for j in range(0, x + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * sum(math.exp(t - m) for t in terms))


def mds_success_probability(epsilon, n, k):
    """Exact recovery probability of an [n, k] MDS code on BEC(epsilon).

    An MDS code recovers if and only if at most n - k symbols are erased, and
    on BEC(epsilon) the erasure count is Binomial(n, epsilon). No simulation
    involved -- this is what 1D-RS must do if the harness is sound.
    """
    return binom_cdf(n - k, n, epsilon)


def mds_threshold(n, k):
    """Exact 50% point of mds_success_probability, by bisection."""
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if mds_success_probability(mid, n, k) > 0.5:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2
