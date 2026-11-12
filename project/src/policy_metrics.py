"""Small dependency-free metrics for comparing sector acceptance policies."""


def binary_metrics(truth, accepted):
    truth, accepted = list(truth), list(accepted)
    if len(truth) != len(accepted):
        raise ValueError('Truth and decisions must have the same length')
    tp = sum(bool(y) and bool(p) for y, p in zip(truth, accepted))
    fp = sum(not bool(y) and bool(p) for y, p in zip(truth, accepted))
    fn = sum(bool(y) and not bool(p) for y, p in zip(truth, accepted))
    tn = len(truth) - tp - fp - fn
    return dict(n=len(truth), accepted=tp + fp, tp=tp, fp=fp, fn=fn, tn=tn,
                precision=tp / (tp + fp) if tp + fp else float('nan'),
                recall=tp / (tp + fn) if tp + fn else float('nan'),
                f1=2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else float('nan'))
