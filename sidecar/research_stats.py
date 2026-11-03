"""Small exact descriptive/statistical calculations, independent of UI and databases."""
import math
import statistics
from collections import Counter


def percentile(values, q=.95):
    ordered = sorted(values)
    if not ordered:
        return None
    if not 0 <= q <= 1 or not all(math.isfinite(x) for x in ordered):
        raise ValueError('Invalid percentile data')
    index = (len(ordered)-1)*q
    lo, hi = math.floor(index), math.ceil(index)
    return ordered[lo]+(ordered[hi]-ordered[lo])*(index-lo)


def nap(without, with_prediction):
    if not without or not with_prediction:
        return None
    return sum((b < a)+.5*(b == a) for a in without for b in with_prediction)/(len(without)*len(with_prediction))


def wilcoxon_paired(generic, calibrated):
    if len(generic) != len(calibrated) or not generic:
        raise ValueError('Wilcoxon requires paired measurements')
    differences = [round(b-a, 10) for a,b in zip(generic, calibrated)]
    nonzero = [(abs(d), d > 0) for d in differences if d]
    if not nonzero:
        return {'n_pairs':len(differences), 'n_nonzero':0, 'statistic':0, 'p_two_sided':1.0}
    ranked = sorted(nonzero)
    ranks, i = [], 0
    while i < len(ranked):
        j = i+1
        while j < len(ranked) and ranked[j][0] == ranked[i][0]:
            j += 1
        # Twice the average rank: integer arithmetic preserves half-rank ties.
        ranks.extend((i+1+j, sign) for _,sign in ranked[i:j])
        i = j
    observed = sum(rank for rank,positive in ranks if positive)
    total = sum(rank for rank,_ in ranks)
    smaller = min(observed, total-observed)
    counts = Counter({0:1})
    for rank,_ in ranks:
        following = counts.copy()
        for value,count in counts.items():
            following[value+rank] += count
        counts = following
    probability = min(1.0, 2*sum(count for value,count in counts.items() if value <= smaller)/(2**len(ranks)))
    return {'n_pairs':len(differences), 'n_nonzero':len(ranks), 'statistic':smaller/2,
            'p_two_sided':probability, 'method':'exact_conditional_signs_average_ties_wilcox_zeros',
            'difference_round_decimals':10}


def randomization_test(values, observed, assignments):
    # Caller must supply the prespecified allocation space; never shuffle labels freely.
    patterns = [tuple(row) for row in assignments]
    actual = tuple(observed)
    if (len(patterns) < 2 or len(patterns) > 100000 or len(set(patterns)) != len(patterns)
            or actual not in patterns or any(len(row) != len(values) or any(type(x) is not bool for x in row)
                                             or not any(row) or all(row) for row in patterns)):
        raise ValueError('Invalid enumerated randomization space')
    def contrast(row):
        return statistics.median(v for v,label in zip(values,row) if not label)-statistics.median(v for v,label in zip(values,row) if label)
    observed_statistic = contrast(actual)
    extreme = sum(abs(contrast(row)) >= abs(observed_statistic)-1e-12 for row in patterns)
    return {'statistic':observed_statistic, 'p_two_sided':extreme/len(patterns),
            'allocations':len(patterns), 'method':'enumerated_user_supplied_allocation_space',
            'allocation_design_validity':'requires_researcher_verification'}


def satisfaction(sus, quest):
    if len(sus) != 10 or len(quest) != 12:
        raise ValueError('SUS requires ten items; QUEST requires twelve')
    if any(x is not None and (type(x) is not int or not 1 <= x <= 5) for x in sus+quest):
        raise ValueError('Questionnaire responses must be integers 1..5 or missing')
    def mean_valid(values):
        valid = [x for x in values if x is not None]
        return statistics.mean(valid) if valid else None
    return {'sus_score':sum(x-1 if i%2 == 0 else 5-x for i,x in enumerate(sus))*2.5
            if all(x is not None for x in sus) else None,
            'sus_valid_items':sum(x is not None for x in sus),
            'quest_device_mean':mean_valid(quest[:8]), 'quest_device_valid_items':sum(x is not None for x in quest[:8]),
            'quest_services_mean':mean_valid(quest[8:]), 'quest_services_valid_items':sum(x is not None for x in quest[8:]),
            'quest_total_mean':mean_valid(quest), 'quest_valid_items':sum(x is not None for x in quest)}
