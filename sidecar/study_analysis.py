"""Reconstruct study exports and calculate explicitly scoped metrics; no cloud access."""
import hashlib
import json
import math
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from e1_protocol import summarize as summarize_e1
from research_stats import nap, percentile, randomization_test, wilcoxon_paired


def read_json(path):
    def reject(value):
        raise ValueError(f'Non-finite JSON value: {value}')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), parse_constant=reject)


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pseudonym(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,31}', value):
        raise ValueError('Use a pseudonymous code with letters/digits/_/- and no names')
    return value


def normalize(text):
    return unicodedata.normalize('NFC', text).casefold().strip()


def _immutable(event):
    return {k:event.get(k) for k in ('event_id','participant_id','user_id','session_id','event_type','sequence','timestamp','data')}


def load_e2(entries):
    sessions = {}
    for entry in entries:
        export = read_json(entry['path'])
        code = pseudonym(export['participant_code'])
        if entry['cohort'] not in {'pilot','target'} or entry['environment'] not in {'local','azure','synthetic'}:
            raise ValueError('Declare cohort and environment for every E2 export')
        identity = (code, entry['cohort'], entry['environment'], entry.get('prediction_policy','unknown'))
        key = (export['session_id'], entry['environment'])
        session = sessions.setdefault(key, {'identity':identity,'events':{},'session_id':export['session_id']})
        if session['identity'] != identity or export['count'] != len(export['logs']):
            raise ValueError('Inconsistent E2 export identity/count')
        for event in export['logs']:
            eid = event.get('event_id')
            if not isinstance(eid, str) or event.get('session_id') != export['session_id']:
                raise ValueError('Missing event ID or cross-session event')
            previous = session['events'].get(eid)
            if previous is not None and _immutable(previous) != _immutable(event):
                raise ValueError('Conflicting copies of one event ID')
            session['events'][eid] = event
    rows, diagnostics = [], []
    for session in sessions.values():
        events = list(session['events'].values())
        if any(type(e.get('sequence')) is not int or e['sequence'] < 1 for e in events):
            raise ValueError('Invalid event sequence')
        events.sort(key=lambda e:e['sequence'])
        sequences = [e['sequence'] for e in events]
        problems = []
        if sequences != list(range(1,len(events)+1)):
            problems.append('session_sequence_gap_or_duplicate')
        if any(e.get('schema_version') != 2 for e in events):
            problems.append('unsupported_event_schema')
        if len({e.get('user_id') for e in events}) != 1:
            problems.append('mixed_event_owners')
        if any(e.get('participant_id') != e.get('user_id') for e in events):
            problems.append('event_participant_owner_mismatch')
        groups = defaultdict(list)
        for event in events:
            data = event.get('data') or {}
            if data.get('study') == 'E2' and data.get('trial_id'):
                groups[data['trial_id']].append(event)
        diagnostics.append({'session_id':session['session_id'], 'participant_code':session['identity'][0],
                            'events':len(events), 'trials':len(groups), 'problems':problems})
        for tid,records in groups.items():
            rows.append(_trial_row(session, tid, records, problems))
    return rows, diagnostics


def _trial_row(session, tid, records, session_problems):
    starts = [e for e in records if e['event_type'] == 'trial_start']
    ends = [e for e in records if e['event_type'] == 'trial_end']
    first = (starts[0].get('data') or {}) if starts else {}
    final = (ends[-1].get('data') or {}) if ends else {}
    code,cohort,environment,policy = session['identity']
    reasons = list(session_problems)
    if len(starts) != 1 or len(ends) != 1:
        reasons.append('missing_or_duplicate_trial_boundary')
    metadata = ('target_phrase','phrase_id','condition','practice','block','order','protocol_session','bank_version','list','participant_number')
    if (any(first.get(k) is None for k in metadata)
            or first.get('condition') not in {'with_prediction','without_prediction'}
            or type(first.get('practice')) is not bool
            or first.get('protocol_session') not in {'practice','s2','s3'}
            or first.get('practice') != (first.get('protocol_session') == 'practice')
            or any(any((e.get('data') or {}).get(k) != first.get(k) for k in metadata) for e in records)):
        reasons.append('inconsistent_trial_metadata')
    text, choices, latencies = '', {}, []
    accepted, requests, selections, offered = 0, 0, 0, 0
    accepted_ids = set()
    for event in records:
        data = event.get('data') or {}
        action = data.get('action')
        if event['event_type'] in {'selection','delete','clear'}:
            selections += 1
            removed, inserted = data.get('removed_characters'), data.get('inserted_text')
            if type(removed) is not int or not 0 <= removed <= len(text) or not isinstance(inserted,str):
                reasons.append('invalid_edit')
                continue
            text = text[:len(text)-removed]+inserted
            if data.get('text_length') != len(text):
                reasons.append('edit_length_mismatch')
        elif event['event_type'] == 'settings' and action == 'board_mode':
            selections += 1
        request = data.get('request_id')
        if action == 'requested':
            requests += 1
        if action == 'shown':
            values, latency = data.get('suggestions'), data.get('latency_ms')
            if (not isinstance(request,str) or request in choices or not isinstance(values,list)
                    or any(not isinstance(v,str) for v in values)
                    or type(latency) not in {int,float} or not math.isfinite(latency) or latency < 0):
                reasons.append('invalid_suggestion_presentation')
            else:
                choices[request] = values
                offered += len(values)
                latencies.append(latency)
        if action == 'suggestion':
            rank = data.get('suggestion_rank')
            offered_values = choices.get(request, []) if isinstance(request,str) else []
            if (not isinstance(request,str) or request in accepted_ids or type(rank) is not int or not 1 <= rank <= len(offered_values)
                    or not isinstance(data.get('inserted_text'),str)
                    or data['inserted_text'].strip() != offered_values[rank-1]):
                reasons.append('invalid_suggestion_acceptance')
            if isinstance(request,str):
                accepted_ids.add(request)
            accepted += 1
    if text != final.get('final_text'):
        reasons.append('final_text_not_reconstructed')
    if final.get('status') != 'completed':
        reasons.append('trial_not_completed')
    duration = final.get('duration_ms')
    if type(duration) is not int or duration <= 0:
        reasons.append('invalid_duration')
        duration = None
    target = first.get('target_phrase')
    transcription = isinstance(target,str) and normalize(text) == normalize(target)
    if not transcription:
        reasons.append('incorrect_transcription')
    if first.get('practice') is True:
        reasons.append('practice')
    if first.get('condition') == 'without_prediction' and (requests or choices or accepted):
        reasons.append('prediction_in_without_condition')
    if policy == 'unknown':
        reasons.append('prediction_policy_unknown')
    if cohort == 'target' and first.get('provisional') is not False:
        reasons.append('provisional_bank_not_confirmatory')
    target_characters = len(unicodedata.normalize('NFC',target).strip()) if isinstance(target,str) else 0
    characters = len(unicodedata.normalize('NFC',text).strip())
    return {'participant_code':code,'cohort':cohort,'environment':environment,'prediction_policy':policy,
            'session_id':session['session_id'],'trial_id':tid,
            **{k:first.get(k) for k in metadata if k != 'target_phrase'},
            'status':final.get('status','open'),'provisional':first.get('provisional'),
            'analysis_eligible':not reasons,'exclusion_reasons':';'.join(sorted(set(reasons))),
            'transcription_match':transcription,'duration_s':duration/1000 if duration else None,
            'characters':characters,'target_characters':target_characters,'composition_selections':selections,
            'characters_per_minute':characters*60000/duration if duration else None,
            'ksr_literal_baseline':1-selections/target_characters if target_characters else None,
            'prediction_requests':requests,'suggestion_presentations':len(choices),'suggestion_candidates':offered,
            'suggestion_acceptances':accepted,
            'acceptance_per_presentation':accepted/len(choices) if choices else None,
            'acceptance_per_candidate':accepted/offered if offered else None,
            'latency_p95_shown_ms':percentile(latencies), '_latencies':latencies,
            'final_text_sha256':hashlib.sha256(text.encode()).hexdigest()}


def summarize_e2(rows, randomizations=None):
    groups = defaultdict(list)
    for row in rows:
        key = tuple(row[k] for k in ('participant_code','cohort','environment','prediction_policy','bank_version'))
        groups[key].append(row)
    summaries = []
    for key,group in groups.items():
        usable = [r for r in group if r['analysis_eligible']]
        without = [r for r in usable if r['condition'] == 'without_prediction']
        with_prediction = [r for r in usable if r['condition'] == 'with_prediction']
        result = dict(zip(('participant_code','cohort','environment','prediction_policy','bank_version'),key))
        result.update(total_trials=len(group),eligible_trials=len(usable),excluded_trials=len(group)-len(usable),
                      exclusions=dict(Counter(reason for r in group for reason in r['exclusion_reasons'].split(';') if reason)))
        for label,values in (('without',without),('with',with_prediction)):
            result[label] = {'n':len(values), **{f'median_{metric}':statistics.median(r[metric] for r in values) if values else None
                                               for metric in ('duration_s','composition_selections','characters_per_minute','ksr_literal_baseline')}}
            shown = sum(r['suggestion_presentations'] for r in values)
            candidates = sum(r['suggestion_candidates'] for r in values)
            accepted = sum(r['suggestion_acceptances'] for r in values)
            result[label].update(suggestions_shown=shown,suggestion_candidates=candidates,suggestions_accepted=accepted,
                                 acceptance_per_presentation=accepted/shown if shown else None,
                                 acceptance_per_candidate=accepted/candidates if candidates else None)
        result['nap_duration_lower_better'] = nap([r['duration_s'] for r in without],[r['duration_s'] for r in with_prediction])
        result['nap_selections_lower_better'] = nap([r['composition_selections'] for r in without],[r['composition_selections'] for r in with_prediction])
        result['latency_p95_primary_shown_ms'] = percentile([v for r in usable for v in r['_latencies']])
        result['latency_p95_all_observed_shown_ms'] = percentile([v for r in group for v in r['_latencies']])
        result['primary_requested'] = sum(r['prediction_requests'] for r in usable)
        result['primary_presented'] = sum(r['suggestion_presentations'] for r in usable)
        result['randomization'] = None
        result['randomization_reason'] = 'No verified prespecified allocation space; do not freely permute current E2 labels'
        for allocation in randomizations or []:
            if tuple(allocation[k] for k in ('participant_code','cohort','environment','prediction_policy','bank_version')) != key:
                continue
            by_id = {r['trial_id']:r for r in usable}
            ids = allocation['trial_ids']
            if set(ids) != set(by_id) or len(ids) != len(by_id):
                raise ValueError('Randomization manifest must match exactly the eligible trial IDs')
            ordered = [by_id[i] for i in ids]
            result['randomization'] = randomization_test([r['duration_s'] for r in ordered],
                [r['condition']=='with_prediction' for r in ordered], allocation['assignments'])
            result['randomization_reason'] = 'User-supplied allocation space; confirm its compatibility with list assignment and block scheduling'
        summaries.append(result)
    return summaries


def load_e1(entries):
    rows, sessions = [], {}
    for entry in entries:
        folder = Path(entry['path'])
        meta = read_json(folder/'session.json')
        pseudonym(meta['participant_code'])
        if meta['cohort'] not in {'pilot','target'} or entry.get('role','primary') not in {'primary','archive'}:
            raise ValueError('Invalid E1 cohort/role')
        events = [json.loads(line) for line in (folder/'events.jsonl').read_text(encoding='utf-8').splitlines() if line]
        rebuilt = summarize_e1(meta['plan'],events,meta['min_valid_samples'])
        if (folder/'report.json').exists() and read_json(folder/'report.json') != rebuilt:
            raise ValueError('E1 report does not match its journal')
        sid = meta['session_id']
        if sid in sessions:
            raise ValueError('Duplicate E1 session')
        sessions[sid] = {'metadata':meta,'folder':folder,'role':entry.get('role','primary')}
        for trial in rebuilt['trials']:
            measured = next((e for e in events if e['type']=='condition_confirmed' and e['condition']['condition_id']==trial['condition_id']), {})
            reasons = []
            if entry.get('role','primary') == 'archive':
                reasons.append('archived_run')
            if not trial['attempted']:
                reasons.append('not_run')
            if trial['status'] != 'completed':
                reasons.append(trial['status'])
            if trial['phase']=='observation' and any(label!='unintended' for label in trial['activation_labels']):
                reasons.append('observation_not_spontaneous_or_unreviewed')
            rows.append({'participant_code':meta['participant_code'],'cohort':meta['cohort'],
                         'session_id':sid,'root_session_id':(meta.get('continuation_of') or {}).get('session_id',sid),
                         'condition_id':trial['condition_id'],'engine':trial['engine'],'phase':trial['phase'],
                         'trial_id':trial['trial_id'],'target_id':trial['target']['id'],'repetition':trial['target']['repetition'],
                         'status':trial['status'],'attempted':trial['attempted'],'exclusion_reasons':';'.join(reasons),
                         'lighting':trial['lighting'],'nominal_camera_distance_cm':trial['nominal_camera_distance_cm'],
                         'posture':trial['posture'],'actual_camera_distance_cm':measured.get('actual_camera_distance_cm'),
                         'eye_screen_distance_mm':(measured.get('geometry') or {}).get('eye_screen_distance_mm'),
                         'angular_mean_screen_deg':trial['angular_mean_screen_deg'],
                         'angular_median_screen_deg':trial['angular_median_screen_deg'],
                         'open_loop_correct':trial['open_loop_correct'],'confirmed_cell':trial['confirmed_cell'],
                         'confirmed_correct':trial['confirmed_correct'],'selection_s':trial['selection_s'],
                         'tracking_ratio':trial['tracking_ratio'],'valid_samples':trial['valid_samples'],
                         'activations':trial['activations'],'observation_s':trial['observation_s'],
                         'unintended_per_min':trial['unintended_per_min'] if not reasons else None,
                         '_instrument':meta['instrument'], '_cnn_hash':meta['cnn_sha256'],
                         '_geometry':measured.get('geometry'),'_trial':trial})
    for sid,session in sessions.items():
        parent = session['metadata'].get('continuation_of')
        if parent:
            if parent['session_id'] not in sessions or file_hash(sessions[parent['session_id']]['folder']/'report.json') != parent['report_sha256']:
                raise ValueError('Include and verify the linked parent E1 session')
    return rows


def summarize_e1_analysis(rows, reference='c1'):
    groups = defaultdict(list)
    for row in rows:
        if 'archived_run' not in row['exclusion_reasons'] and row['attempted']:
            groups[(row['participant_code'],row['cohort'],row['root_session_id'],row['condition_id'])].append(row)
    result = []
    for key,group in groups.items():
        record = dict(zip(('participant_code','cohort','root_session_id','condition_id'),key))
        record['engines'] = {}
        angles = {}
        duplicate_keys = False
        for engine in ('gazecnn_generic','mediapipe_ridge_calibrated'):
            subset = [r for r in group if r['engine']==engine]
            angular = [r for r in subset if r['phase']=='angular' and not r['exclusion_reasons']]
            angles[engine] = {(r['target_id'],r['repetition']):r for r in angular}
            duplicate_keys |= len(angles[engine]) != len(angular)
            opened = [r for r in subset if r['phase']=='open_loop']
            closed = [r for r in subset if r['phase']=='closed_loop']
            confirmed = [r for r in closed if r['confirmed_cell'] is not None]
            observations = [r for r in subset if r['phase']=='observation']
            valid_observation = [r for r in observations if not r['exclusion_reasons'] and r['unintended_per_min'] is not None]
            observation_seconds = sum(r['observation_s'] for r in valid_observation)
            values = [r['angular_mean_screen_deg'] for r in angular]
            record['engines'][engine] = {'angular_targets_measured':len(values),
                'angular_mean_of_targets_deg':statistics.mean(values) if values else None,
                'angular_median_of_target_means_deg':statistics.median(values) if values else None,
                'i2_correct':sum(r['open_loop_correct'] for r in opened),'i2_attempted':len(opened),
                'i3_wrong':sum(not r['confirmed_correct'] for r in confirmed),'i3_confirmed':len(confirmed),
                'closed_without_selection':len(closed)-len(confirmed),
                'i4_observations_eligible':len(valid_observation),
                'i4_observations_excluded':len(observations)-len(valid_observation),
                'i4_unintended_per_min':sum(r['activations'] for r in valid_observation)*60/observation_seconds if observation_seconds else None}
        a,b = angles['gazecnn_generic'],angles['mediapipe_ridge_calibrated']
        common = sorted(a.keys() & b.keys(), key=str)
        compatible = bool(common) and not duplicate_keys and all(
            a[k]['_geometry']==b[k]['_geometry'] and a[k]['_instrument']==b[k]['_instrument']
            and a[k]['_cnn_hash']==b[k]['_cnn_hash']
            and a[k]['_trial']['target']['point']==b[k]['_trial']['target']['point'] for k in common)
        record['paired_targets'] = len(common)
        record['wilcoxon'] = wilcoxon_paired([a[k]['angular_mean_screen_deg'] for k in common],
            [b[k]['angular_mean_screen_deg'] for k in common]) if compatible else None
        record['wilcoxon_reason'] = 'Exploratory pipeline comparison; symmetry/independence assumptions require review' if compatible else 'Missing or duplicated pairs, unequal geometry, targets or instrument/model version'
        result.append(record)
    # Descriptive degradation from the predeclared reference, never choose the best condition post hoc.
    for record in result:
        baseline = next((r for r in result if r['participant_code']==record['participant_code'] and r['cohort']==record['cohort']
                         and r['root_session_id']==record['root_session_id'] and r['condition_id']==reference),None)
        record['i9_reference_condition'] = reference
        record['i9_degradation'] = None
        if baseline and record['condition_id'] != reference:
            record['i9_degradation'] = {}
            for engine,value in record['engines'].items():
                base = baseline['engines'][engine]
                mean,refmean = value['angular_mean_of_targets_deg'],base['angular_mean_of_targets_deg']
                record['i9_degradation'][engine] = {'angular_increase_deg':mean-refmean if mean is not None and refmean is not None else None,
                    'accuracy_drop':base['i2_correct']/base['i2_attempted']-value['i2_correct']/value['i2_attempted'] if base['i2_attempted'] and value['i2_attempted'] else None}
    return result
