"""Deterministic text split and a train-only add-alpha bigram baseline."""
import hashlib
import json
import math
import random
from collections import Counter, defaultdict


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def split_sentences(sentences, seed=42):
    unique = sorted({tuple(s) for s in sentences if s})
    if len(unique) < 10:
        raise ValueError("At least ten distinct tokenized sentences are required")
    random.Random(seed).shuffle(unique)
    n_train, n_val = int(.7*len(unique)), max(1, int(.15*len(unique)))
    return {"train": unique[:n_train], "validation": unique[n_train:n_train+n_val],
            "test": unique[n_train+n_val:]}


class Bigram:
    def __init__(self, vocabulary, pad, bos, alpha=1.0):
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        self.allowed = [i for i in range(vocabulary) if i not in {pad, bos}]
        self.alpha = alpha
        self.counts = defaultdict(Counter)

    def fit(self, sequences):
        for sequence in sequences:
            for previous, token in zip(sequence, sequence[1:]):
                self.counts[previous][token] += 1
        return self

    def probabilities(self, previous):
        counts = self.counts[previous]
        denominator = sum(counts.values())+self.alpha*len(self.allowed)
        return {i:(counts[i]+self.alpha)/denominator for i in self.allowed}


def token_metrics(rows):
    # (target index, probability distribution) for exactly the same target tokens.
    hits1 = hits3 = count = 0
    loss = 0.0
    for target, distribution in rows:
        probability = distribution[target]
        if probability <= 0 or not math.isfinite(probability):
            raise ValueError("Invalid target probability")
        ranking = sorted(distribution, key=lambda k:(-distribution[k], k))
        hits1 += target == ranking[0]
        hits3 += target in ranking[:3]
        loss -= math.log(probability)
        count += 1
    return {"tokens":count, "top1":hits1/count if count else None,
            "top3":hits3/count if count else None,
            "negative_log_likelihood":loss/count if count else None,
            "perplexity":math.exp(loss/count) if count else None}


def word_accuracy(rows, word_ids, eos, unknown):
    count = hit1 = hit3 = oov = 0
    for target, distribution in rows:
        if target == eos:
            continue
        ranked = sorted(word_ids, key=lambda k:(-distribution[k], k))
        count += 1
        oov += target == unknown
        hit1 += target != unknown and target == ranked[0]
        hit3 += target != unknown and target in ranked[:3]
    return {'word_positions':count, 'word_oov':oov,
            'word_top1':hit1/count if count else None,
            'word_top3':hit3/count if count else None}
