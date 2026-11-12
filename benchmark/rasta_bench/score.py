"""Word and character error rates.

WER tokenises on whitespace. CER compares code points with spaces removed,
so a missing space does not dominate a Hinglish line. Both return
insertions+deletions+substitutions over the reference length. An empty
reference scores 0.0 when the hypothesis is also empty, else 1.0.
"""


def wer(reference: str, hypothesis: str) -> float:
    return _rate(reference.split(), hypothesis.split())


def cer(reference: str, hypothesis: str) -> float:
    ref = list(reference.replace(" ", ""))
    hyp = list(hypothesis.replace(" ", ""))
    return _rate(ref, hyp)


def _rate(ref: list, hyp: list) -> float:
    if not ref:
        return 0.0 if not hyp else 1.0
    return _levenshtein(ref, hyp) / len(ref)


def _levenshtein(ref: list, hyp: list) -> int:
    prev = list(range(len(hyp) + 1))
    for i, left in enumerate(ref, start=1):
        cur = [i]
        for j, right in enumerate(hyp, start=1):
            insert = cur[j - 1] + 1
            delete = prev[j] + 1
            replace = prev[j - 1] + (left != right)
            cur.append(min(insert, delete, replace))
        prev = cur
    return prev[-1]
