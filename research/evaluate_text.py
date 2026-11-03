"""Offline pilot evaluation. Reuses backend architecture; never writes its weights/DB."""
import argparse
import copy
import hashlib
import json
import random
import sys
import uuid
from pathlib import Path

from text_protocol import Bigram, digest, split_sentences, token_metrics, word_accuracy


def evaluate(backend, output, seed=42, epochs=120, patience=12, test_file=None):
    backend = Path(backend).resolve()
    if not (backend/'ai_modules/rnn/model.py').is_file():
        raise ValueError("Provide the backend checkout containing ai_modules/rnn/model.py")
    sys.path.insert(0, str(backend))
    import torch
    from ai_modules.rnn.corpus import load_corpus
    from ai_modules.rnn.model import DEFAULT_CONFIG, PhraseLSTM
    from ai_modules.rnn.train import _batches, _build_sequences
    from ai_modules.rnn.vocab import Vocabulary, tokenize
    if epochs < 1 or patience < 1:
        raise ValueError("epochs and patience must be positive")
    torch.set_num_threads(1)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True)
    split = split_sentences([tokenize(s) for s in load_corpus()], seed)
    scope = 'retrospective_pilot_existing_development_corpus'
    if test_file:
        external = sorted({tuple(tokenize(s)) for s in Path(test_file).read_text(encoding='utf-8').splitlines() if tokenize(s)})
        if not external or set(external) & set().union(*(set(v) for v in split.values())):
            raise ValueError('External test phrases must be nonempty and disjoint from the development corpus')
        split['test'] = external
        scope = 'external_test_provided_independence_requires_researcher_verification'
    vocab = Vocabulary.build(split['train'])
    pairs = {name:_build_sequences(value, vocab) for name, value in split.items()}
    allowed = [i for i in range(len(vocab)) if i not in {vocab.pad_index, vocab.bos_index}]
    word_ids = [i for i in allowed if i not in {vocab.eos_index, vocab.unk_index}]
    model = PhraseLSTM(len(vocab), vocab.pad_index, **DEFAULT_CONFIG)
    optimizer = torch.optim.Adam(model.parameters(), lr=.003, weight_decay=.0001)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=vocab.pad_index)

    def rnn_metrics(examples):
        rows = []
        model.eval()
        with torch.no_grad():
            for inputs, targets in examples:
                logits, _ = model(inputs.unsqueeze(0))
                probabilities = torch.softmax(logits[0, :, allowed], dim=-1).tolist()
                rows.extend((int(target), dict(zip(allowed, probs))) for target, probs in zip(targets, probabilities))
        return {**token_metrics(rows), **word_accuracy(rows, word_ids, vocab.eos_index, vocab.unk_index)}

    history, best, state, stale, best_epoch = [], float('inf'), None, 0, 0
    rng = random.Random(seed)
    for epoch in range(1, epochs+1):
        model.train()
        order = list(pairs['train'])
        rng.shuffle(order)
        for inputs, targets in _batches(order, 16, vocab.pad_index):
            optimizer.zero_grad()
            logits, _ = model(inputs)
            loss = criterion(logits.reshape(-1, logits.size(-1)), targets.reshape(-1))
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 5)
            optimizer.step()
        validation = rnn_metrics(pairs['validation'])
        history.append({'epoch':epoch, **validation})
        if validation['negative_log_likelihood'] < best-1e-8:
            best, state, stale, best_epoch = validation['negative_log_likelihood'], copy.deepcopy(model.state_dict()), 0, epoch
        else:
            stale += 1
        if stale >= patience:
            break
    model.load_state_dict(state)
    train_sequences = [[vocab.bos_index]+vocab.encode(s)+[vocab.eos_index] for s in split['train']]
    alpha_values = (.01, .1, 1.0)
    baselines = {alpha:Bigram(len(vocab), vocab.pad_index, vocab.bos_index, alpha).fit(train_sequences) for alpha in alpha_values}

    def bigram_metrics(baseline, name):
        rows = [(int(t), baseline.probabilities(int(x))) for inputs, targets in pairs[name] for x,t in zip(inputs, targets)]
        return {**token_metrics(rows), **word_accuracy(rows, word_ids, vocab.eos_index, vocab.unk_index)}

    chosen_alpha = min(alpha_values, key=lambda a:bigram_metrics(baselines[a], 'validation')['negative_log_likelihood'])
    baseline = baselines[chosen_alpha]
    metrics = {name:{'rnn':rnn_metrics(pairs[name]), 'bigram':bigram_metrics(baseline, name)} for name in split}
    unknown = {name:{'word_tokens':sum(len(s) for s in sentences),
                     'oov_word_tokens':sum(w not in vocab.stoi for s in sentences for w in s)} for name,sentences in split.items()}
    folder = Path(output)/str(uuid.uuid4())
    folder.mkdir(parents=True, exist_ok=False)
    checkpoint = folder/'pilot_phrase_lstm.pt'
    torch.save({'state_dict':state, 'config':model.config, 'vocab':vocab.to_dict()}, checkpoint)
    report = {'schema_version':1, 'scope':scope, 'seed':seed, 'framework':str(torch.__version__),
              'split_counts':{k:len(v) for k,v in split.items()}, 'split_hashes':{k:digest(v) for k,v in split.items()},
              'vocabulary_origin':'training_only', 'vocabulary_size':len(vocab), 'oov':unknown,
              'candidate_targets':'word_tokens_including_UNK_and_EOS_excluding_PAD_and_BOS',
              'word_accuracy_definition':'lexical_candidates_only_OOV_always_miss_EOS_not_scored',
              'best_epoch':best_epoch, 'max_epochs':epochs, 'patience':patience,
              'bigram_alpha_candidates':alpha_values, 'bigram_alpha':chosen_alpha,
              'selection_criterion':'validation_negative_log_likelihood_only', 'metrics':metrics,
              'history':history, 'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
              'sources':{str(p.relative_to(backend)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                         [backend/'ai_modules/rnn/model.py',backend/'ai_modules/rnn/vocab.py',backend/'ai_modules/rnn/corpus.py',backend/'ai_modules/rnn/train.py']},
              'evaluation_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'protocol_code_sha256':hashlib.sha256((Path(__file__).parent/'text_protocol.py').read_bytes()).hexdigest(),
              'independent_validation':False, 'production_model_modified':False}
    (folder/'split.json').write_text(json.dumps(split, ensure_ascii=False, indent=2), encoding='utf-8')
    (folder/'metrics.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'folder':str(folder), 'split':report['split_counts'], 'best_epoch':best_epoch,
                      'test':metrics['test'], 'oov_test':unknown['test'], 'scope':scope},ensure_ascii=True))
    return folder


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--epochs', type=int, default=120)
    parser.add_argument('--patience', type=int, default=12)
    parser.add_argument('--test-file', type=Path)
    args = parser.parse_args()
    evaluate(args.backend_root, args.output, args.seed, args.epochs, args.patience, args.test_file)
