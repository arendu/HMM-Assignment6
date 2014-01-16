__author__ = 'arenduchintala'
from collections import defaultdict
from os import linesep
from math import log, exp
from sys import stderr, argv
import pdb
from pprint import pprint

START_STATE = 'START_STATE'
END_STATE = 'END_STATE'
START_WORD = 'START_WORD'
END_WORD = 'END_WORD'

global CURRENT_MLEs
CURRENT_MLEs = defaultdict(float)
global possible_states
possible_states = defaultdict(set)
possible_states[START_WORD] = set([START_STATE])
possible_states[END_WORD] = set([END_STATE])
global singleton_transitions
singleton_transitions = defaultdict(set)
global singleton_emissions
singleton_emissions = defaultdict(set)
global add_to_lambda
add_to_lambda = 1.0


def logadd(x, y):
    """
    trick to add probabilities in logspace
    without underflow
    """
    #Todo: handle special case when x,y=0
    if x >= y:
        return x + log(1 + exp(y - x))
    else:
        return y + log(1 + exp(x - y))


def make_mle_estimates(filepath):
    CURRENT_MLEs[(('observations',))] = set(['**OOV**'])  # will eventually store V these keys are also tuples
    CURRENT_MLEs[('states',)] = set([])                 # will contain Tag Vocab these keys are also tuples
    n = 0
    s = 0
    tagged_sentences = open(filepath, 'r').read().split('###/###' + linesep)
    for tagged_sentence in tagged_sentences:
        prev_state = START_STATE
        if tagged_sentence.strip() != '':
            for state_obs in tagged_sentence.strip().split(linesep):
                n += 1 # todo: this n does not count end-state or start-state, should it???
                obs = state_obs.split('/')[0]
                state = state_obs.split('/')[1]
                CURRENT_MLEs[('observations',)].update([obs])  # has a set of all seen observations [TYPES]
                CURRENT_MLEs[('observation_token_counts', obs)] += 1
                CURRENT_MLEs[('states',)].update([state])  # has a set of all seen states
                #Emission related counts
                CURRENT_MLEs[('any_emission_from', state)] += 1
                possible_states[obs].add(state)
                CURRENT_MLEs[('emission', obs, state)] += 1
                if CURRENT_MLEs[('emission', obs, state)] == 1:
                    #this obs is a singleton add to sing_tw (singleton_emission)
                    singleton_emissions[state].add(obs)
                elif CURRENT_MLEs[('emission', obs, state)] == 2:
                    #this is not a singleton anymore remove from sing_tw (singleton_emission)
                    singleton_emissions[state].remove(obs)

                CURRENT_MLEs[('any_transition_from', prev_state)] += 1
                CURRENT_MLEs[('transition', state, prev_state)] += 1
                if CURRENT_MLEs[('transition', state, prev_state)] == 1:
                    #this bigram of tags is a singleton add to sing_tt (singleton_transition)
                    singleton_transitions[prev_state].add(state)

                elif CURRENT_MLEs[('transition', state, prev_state)] == 2:
                    #this bigram of tags is no longer a singleton remove from sing_tt (singleton_transition)
                    singleton_transitions[prev_state].remove(state)

                prev_state = state
            CURRENT_MLEs[('transition', END_STATE, prev_state)] += 1
            CURRENT_MLEs[('any_transition_from', prev_state)] += 1  # counts the transition from a state -> END_STATE
            s += 1

    CURRENT_MLEs[('backoff_transition', END_STATE)] = s / float(n + s)

    for tag in CURRENT_MLEs[('states',)]:
        print 'count of states', tag, CURRENT_MLEs[('any_transition_from', tag)], CURRENT_MLEs[('any_emission_from', tag)]
        backoff_for_state = CURRENT_MLEs[('any_transition_from', tag)] / float(n + s)
        CURRENT_MLEs[('backoff_transition', tag)] = backoff_for_state

    for word in CURRENT_MLEs[('observations',)]:
        if word == '**OOV**':
            pass
        backoff_for_observation = (CURRENT_MLEs[('observation_token_counts', word)] + 1) / float(
            n + s + len(CURRENT_MLEs[('observations',)]))
        CURRENT_MLEs[('backoff_emission', word)] = backoff_for_observation
    stderr.write('completed counting...\n')


def one_count_probabilty(type, *args):
    if type == 'transition':
        v = args[0]
        u = args[1]
        #print 'getting one count for transition', v, u
        if ('ocp_transition', v, u) not in CURRENT_MLEs:
            one_count_lambda = len(singleton_transitions[u]) + add_to_lambda
            backoff_transition_prob = CURRENT_MLEs[('backoff_transition', v)]
            count_uv = CURRENT_MLEs[('transition', v, u)]
            count_u = CURRENT_MLEs[('any_transition_from', u)]
            ocp = (count_uv + one_count_lambda * backoff_transition_prob) / float(count_u + one_count_lambda)
            if ocp == 0:
                pdb.set_trace()
                raise "One Count Smoothed Probability is 0!!"
            CURRENT_MLEs[('ocp_transition', v, u)] = log(ocp)
        return CURRENT_MLEs[('ocp_transition', v, u)]
    elif type == 'emission':
        obs = args[0]
        if obs is END_WORD:
            return 0.0
        v = args[1]
        #print 'getting one count for emission', obs, v
        if ('ocp_emission', obs, v) not in CURRENT_MLEs:
            one_count_lambda = len(singleton_emissions[v]) + add_to_lambda
            if obs not in CURRENT_MLEs[('observations',)]:
                backoff_emission_prob = CURRENT_MLEs[('backoff_emission', '**OOV**')]
            else:
                backoff_emission_prob = CURRENT_MLEs[('backoff_emission', obs)]
            count_obs_v = CURRENT_MLEs[('emission', obs, v)]
            count_v = CURRENT_MLEs[('any_emission_from', v)]
            ocp = (count_obs_v + one_count_lambda * backoff_emission_prob) / float(count_v + one_count_lambda)
            if ocp == 0:
                pdb.set_trace()
                raise "One Count Smoothed Probability is 0!!"
            CURRENT_MLEs[('ocp_emission', obs, v)] = log(ocp)
        return CURRENT_MLEs[('ocp_emission', obs, v)]
    else:
        raise "Invalid type of one count probability requested"


def get_backwards(words):
    words.pop(0)
    n = len(words) + 1
    words[n] = END_WORD #actually the end word
    beta_pi = {(n, END_STATE): 0.0}
    for k in range(max(words) - 1, 0, -1):
        for v in possible_states[words[k]]:
            sum_prob_to_bt = []
            for u in possible_states[words[k + 1]]:
                #print 'reverse transition', 'k', k, 'u', u, '->', 'v', v
                q = one_count_probabilty('transition', u, v)
                e = one_count_probabilty('emission', words[k + 1], u)
                beta_p = beta_pi[(k + 1, u)] + q + e
                sum_prob_to_bt.append(exp(beta_p)) # TODO convert this using logadd : see hints in handout
            new_pi_key = (k, v)
            beta_pi[new_pi_key] = log(sum(sum_prob_to_bt))
            print 'beta', new_pi_key, '=', exp(beta_pi[new_pi_key])
    return beta_pi


def get_viterbi_sequence(words):
    words[0] = START_WORD
    pi = {(0, START_STATE): 0.0}
    alpha_pi = {(0, START_STATE): 0.0}
    arg_pi = {(0, START_STATE): []}
    for k in range(1, max(words) + 1):  # the words are numbered from 1 to n, 0 is special start character
        for v in possible_states[words[k]]:
            max_prob_to_bt = {}
            sum_prob_to_bt = []
            for u in possible_states[words[k - 1]]:
                q = one_count_probabilty('transition', v, u)
                e = one_count_probabilty('emission', words[k], v)
                p = pi[(k - 1, u)] + q + e
                alpha_p = alpha_pi[(k - 1, u)] + q + e
                #print pi_key, v, u, p, '=', q, '*', e, '*', pi[(k - 1, u)]
                bt = list(arg_pi[(k - 1, u)])  # list(list1) makes copy of list1
                bt.append(u)
                max_prob_to_bt[p] = bt
                sum_prob_to_bt.append(exp(alpha_p))  # TODO convert this using logadd : see hints in handout

            max_bt = max_prob_to_bt[max(max_prob_to_bt)]
            new_pi_key = (k, v)
            pi[new_pi_key] = max(max_prob_to_bt)
            print 'mu   ', new_pi_key, '=', exp(pi[new_pi_key])
            alpha_pi[new_pi_key] = log(sum(sum_prob_to_bt))  # sum the real probabilities, then take the log of the sum
            print 'alpha', new_pi_key, '=', exp(alpha_pi[new_pi_key])
            arg_pi[new_pi_key] = max_bt

    k = max(words)
    max_prob_to_bt = {}
    for u in possible_states[words[k]]:
        q = one_count_probabilty('transition', END_STATE, u)
        p = pi[(k, u)] + q
        bt = list(arg_pi[(k, u)])
        bt.append(u)
        max_prob_to_bt[p] = bt
    max_bt = max_prob_to_bt[max(max_prob_to_bt)]
    max_p = max(max_prob_to_bt)
    max_bt.pop(0)
    return max_bt, max_p, alpha_pi


def get_observations_with_indexes(sentence):
    """
    Simply returns a dict with observations as values, and indexes to observations as keys
    Adds 0 index as the START_STATE
    e.g. observations : '1','2','3','2','2'
    will be returned as: { 1:'1', 2:'2', 3:'2', 4:'2', 5:'2'}
    """
    words = {}
    known = []
    i = 0
    for obs in sentence:
        if obs.strip() == '':
            print 'skipping empty word'
        else:
            i += 1
            if obs.strip() in possible_states:  # (seenObservations.has_key(word)):
                words[i] = obs.strip()
                known.append(1)
            else:
                possible_states[obs.strip()] = CURRENT_MLEs[('states',)] # giving unseen observation all possible states
                words[i] = obs.strip()
                known.append(0)

    return words, known


def read_test_sentences(filepath):
    test_sentences = []
    test_tags = []
    tagged_sentences = open(filepath, 'r').read().split('###/###' + linesep)
    for tagged_sentence in tagged_sentences:
        sentence = []
        tags = []
        if tagged_sentence.strip() != '':
            for state_obs in tagged_sentence.strip().split(linesep):
                sentence.append(state_obs.split('/')[0])
                tags.append(state_obs.split('/')[1])
            test_sentences.append(sentence)
            test_tags.append(tags)
    return test_sentences, test_tags


if __name__ == "__main__":
    try:
        train_file = argv[1]
        test_file = argv[2]
    except:
        train_file = '../data/ictrain'
        test_file = '../data/ictest'
    try:
        add_to_lambda = float(argv[3])
    except:
        add_to_lambda = 0.0

    make_mle_estimates(train_file)
    pprint(CURRENT_MLEs)
    test_sentences, test_tags = read_test_sentences(test_file)
    correct_tags = [0, 0]  # first for viterbi decoding, second for posterior decoding
    correct_known_tags = [0, 0]  # first for viterbi decoding, second for posterior decoding
    total_known_tags = 0
    total_tags = 0
    perplexity_per_word = []
    total_n = 0
    for i in range(len(test_sentences)):
        sent = test_sentences[i]
        print sent
        answer_tags = test_tags[i]
        obs, known = get_observations_with_indexes(sent)
        predicted_tags, best_mu, alpha_pi = get_viterbi_sequence(obs)
        beta_pi = get_backwards(obs)
        posterior_predicted_tags = []
        xx = set(beta_pi).intersection(alpha_pi)
        for k in range(1, len(answer_tags) + 1):
            max_state = None
            max_alpha_beta = float('-inf')
            for state in possible_states[obs[k]]:
                alpha_beta = alpha_pi[(k, state)] + beta_pi[(k, state)]
                if alpha_beta > max_alpha_beta:
                    max_alpha_beta = alpha_beta
                    max_state = state
            posterior_predicted_tags.append(max_state)
        print 'Viterbi   prediction:', ''.join(predicted_tags)
        print 'Posterior prediction:', ''.join(posterior_predicted_tags)
        print 'Ground Truth        :', ''.join(answer_tags)
        weighted_perp = float(len(predicted_tags) + 1) * exp(-best_mu / float(len(predicted_tags) + 1))
        perplexity_per_word.append(weighted_perp)
        total_n += float(len(predicted_tags) + 1)
        #computing accuracy for viterbi
        correct_indexes = [i for i in range(len(predicted_tags)) if predicted_tags[i] == answer_tags[i]]
        correct_known_indexes = [idx for idx, i in enumerate(known) if
                                 (i == 1 and answer_tags[idx] == predicted_tags[idx])]
        correct_tags[0] += len(correct_indexes)
        correct_known_tags[0] += len(correct_known_indexes)

        #computing accuracy for posterior decoding
        correct_indexes = [i for i in range(len(posterior_predicted_tags)) if
                           posterior_predicted_tags[i] == answer_tags[i]]
        correct_known_indexes = [idx for idx, i in enumerate(known) if
                                 (i == 1 and answer_tags[idx] == posterior_predicted_tags[idx])]
        correct_tags[1] += len(correct_indexes)
        correct_known_tags[1] += len(correct_known_indexes)
        total_tags += len(answer_tags)
        total_known_tags += sum(known)

    known_accuracy = [0, 0]
    unknown_accuracy = [0, 0]
    known_accuracy[0] = 100 * correct_known_tags[0] / float(total_known_tags)
    known_accuracy[1] = 100 * correct_known_tags[1] / float(total_known_tags)
    try:
        unknown_accuracy[0] = 100 * (correct_tags[0] - correct_known_tags[0]) / float(total_tags - total_known_tags)
    except ZeroDivisionError:
        unknown_accuracy[0] = 0.0
    try:
        unknown_accuracy[1] = 100 * (correct_tags[1] - correct_known_tags[1]) / float(total_tags - total_known_tags)
    except ZeroDivisionError:
        unknown_accuracy[1] = 0.0

    tagging_accuracy = [0, 0]
    tagging_accuracy[0] = "%.2f" % (100 * float(correct_tags[0]) / float(total_tags))
    tagging_accuracy[1] = "%.2f" % (100 * float(correct_tags[1]) / float(total_tags))
    perplexity_per_word = "%.3f" % (sum(perplexity_per_word) / total_n)
    stderr.write(str('Tagging accuracy (Viterbi decoding): ' + str(tagging_accuracy[0]) + '%\t'))
    stderr.write(str('(known: ' + str("%.2f" % known_accuracy[0]) + '%\t'))
    stderr.write(str('novel: ' + str("%.2f" % unknown_accuracy[0]) + '%)\n'))
    stderr.write('Perplexity per Viterbi-tagged test word: ' + perplexity_per_word)
    stderr.write('\n')
    stderr.write(str('Tagging accuracy (Posterior decoding): ' + str(tagging_accuracy[1]) + '%\t'))
    stderr.write(str('(known: ' + str("%.2f" % known_accuracy[1]) + '%\t'))
    stderr.write(str('novel: ' + str("%.2f" % unknown_accuracy[1]) + '%)\n'))


