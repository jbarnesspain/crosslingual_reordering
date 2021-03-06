from keras.models import Sequential, load_model
from keras.layers import LSTM, Dropout, Dense, Embedding, Bidirectional
from keras.preprocessing.sequence import pad_sequences
from keras.callbacks import ModelCheckpoint
from keras import backend as K

from copy import deepcopy


import numpy as np
import sys
import os
import argparse
import pickle
import json
import re

import tensorflow as tf
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '4'

from artetxe_bilstm import *
from artetxe_svm import *
from sklearn.metrics import classification_report, f1_score
from Utils.Representations import *

######
def getMyData(fname, label, model, representation=sum_vecs, encoding='utf8'):
    data = []
    for sent in open(fname):
        data.append((representation(sent, model), label))
    return data
######

def to_array(X, n=2):
    """
    Converts a list scalars to an array of size len(X) x n
    >>> to_array([0,1], n=2)
    >>> array([[ 1.,  0.],
               [ 0.,  1.]])
    """
    return np.array([np.eye(n)[x] for x in X])

def per_class_f1(y, pred):
    """
    Returns the per class f1 score.
    Todo: make this cleaner.
    """

    num_classes = len(set(y))
    y = to_array(y, num_classes)
    pred = to_array(pred, num_classes)

    results = []
    for j in range(num_classes):
        class_y = y[:,j]
        class_pred = pred[:,j]
        f1 = f1_score(class_y, class_pred, average='binary')
        results.append([f1])
    return np.array(results)


def load_best_models(lang, embedding='artetxe', classifier='bilstm', binary=False):

    models = []


    if binary:
        base_dir = 'models/{0}-{1}/binary-en-{2}'.format(embedding, classifier, lang)
    else:
        base_dir = 'models/{0}-{1}/4class-en-{2}'.format(embedding, classifier, lang)

    print("importing models from {0}...".format(base_dir))
    for i in [1, 2, 3, 4, 5]:
        full_dir = os.path.join(base_dir, "run{0}".format(i))
        weights = os.listdir(full_dir)

        best_val = 0
        best_weights = ''
        for weight in weights:
            try:
                val_f1 = re.sub('weights.[0-9]*-', '', weight)
                val_f1 = re.sub('.hdf5', '', val_f1)
                val_f1 = float(val_f1)
                if val_f1 > best_val:
                    best_val = val_f1
                    best_weights = weight
            except ValueError:
                pass
        print(best_weights)
        models.append(load_model(os.path.join(full_dir, best_weights), custom_objects= {'f1': f1}))

    return models

def open_params(lang, embeddings='artetxe', classifier='bilstm', binary=True):
    if binary:
        with open('models/{0}-{1}/binary-en-{2}/en-{2}-w2idx.pkl'.format(embeddings, classifier, lang), 'rb') as out:
            w2idx, max_length = pickle.load(out)
    else:
        with open('models/{0}-{1}/4class-en-{2}/en-{2}-w2idx.pkl'.format(embeddings, classifier, lang), 'rb') as out:
            w2idx, max_length = pickle.load(out)
    return w2idx, max_length

class TestData():

    def __init__(self, test_dir, model, rep=words, binary=False, one_hot=True):
        self.binary = binary
        self.one_hot = one_hot
        self._Xtest, self._ytest = self.open_test_corpus(test_dir, model, rep, binary)

    def to_array(self, integer, num_labels):
        """quick trick to convert an integer to a one hot vector that
        corresponds to the y labels"""
        integer = integer - 1
        return np.array(np.eye(num_labels)[integer])

    def open_test_corpus(self, DIR, model, rep=words, binary=False):
        if binary:
            pos = getMyData(os.path.join(DIR, 'strpos.txt'),
                            1, model, encoding='latin',
                            representation=rep)
            pos += getMyData(os.path.join(DIR, 'pos.txt'),
                             1, model, encoding='latin',
                             representation=rep)
            neg = getMyData(os.path.join(DIR, 'strneg.txt'),
                            0, model, encoding='latin',
                            representation=rep)
            neg += getMyData(os.path.join(DIR, 'neg.txt'),
                             0, model, encoding='latin',
                             representation=rep)
            test_data = pos + neg
            Xtest = [data for data, y in test_data]
            if self.one_hot is True:
                ytest = np.array([self.to_array(y, 2) for data, y in test_data])
            else:
                ytest = np.array([y for data, y in test_data])
        else:
            strpos = getMyData(os.path.join(DIR, 'strpos.txt'),
                               3, model, encoding='latin',
                               representation=rep)
            pos = getMyData(os.path.join(DIR, 'pos.txt'),
                            2, model, encoding='latin',
                            representation=rep)
            neg = getMyData(os.path.join(DIR, 'neg.txt'),
                            1, model, encoding='latin',
                            representation=rep)
            strneg = getMyData(os.path.join(DIR, 'strneg.txt'),
                               0, model, encoding='latin',
                               representation=rep)
            test_data = strpos + pos + neg + strneg

            Xtest = [data for data, y in test_data]
            if self.one_hot is True:
                ytest = np.array([self.to_array(y, 4) for data, y in test_data])
            else:
                ytest = np.array([y for data, y in test_data])

        return Xtest, ytest

def convert_test_data(dataset, w2idx, maxlen=50):
    """
    Change dataset representation from a list of lists, where each outer list
    is a sentence and each inner list contains the tokens. The result
    is a matrix of size n x m, where n is the number of sentences
    and m = maxlen is the maximum sentence size in the corpus.
    This function operates directly on the dataset and does not return any value.
    """
    dataset = deepcopy(dataset)
    dataset._Xtest = np.array([idx_sent(s, w2idx) for s in dataset._Xtest])
    dataset._Xtest = pad_sequences(dataset._Xtest, maxlen)
    return dataset

def convert_svm_test_dataset(dataset, w2idx, matrix):
    """
    Change dataset representation from a list of lists, where each outer list
    is a sentence and each inner list contains the tokens. The result
    is a matrix of size n x m, where n is the number of sentences
    and m = the dimensionality of the embeddings in the embedding matrix.
    """
    dataset = deepcopy(dataset)
    dataset._Xtest = np.array([ave_sent(s, w2idx, matrix) for s in dataset._Xtest])
    return dataset

def str2bool(v):
    # Converts a string to a boolean, for parsing command line arguments
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('test_directories', nargs= '+', default=["datasets/mono/original/es"], help='target dataset (directory that contains the test corpus, defaults to datasets/mono/original/es)')
    parser.add_argument('-l', '--lang', default='es', help='choose target language: es, ca, en (defaults to es)')
    parser.add_argument('-e', '--embedding', default='artetxe', help='whether to use artetxe or barista embeddings (defaults artetxe)')
    parser.add_argument('-c', '--classifier', default='bilstm', help='choose classifier: bilstm, cnn, or svm (defaults to bilstm)')
    parser.add_argument('-b', '--binary', default=False, help='whether to use binary or 4-class (defaults to False == 4-class)', type=str2bool)
    args = parser.parse_args()

    for el in vars(args):
        print((str(el) + ': ' + str(vars(args)[el])))

    print(args.classifier)

    # get data type (orginal, reordered, n_adj, random)
    #data_type = args.test_directory.split("/")[1]


    monol = []
    if args.lang == 'en':
            monol.append('1')
            print('monolingual')
    if args.classifier in ['bilstm', 'cnn']:
        if '1' in monol:
            args.lang = 'es'
        # load classifier
        models = load_best_models(args.lang, args.embedding, args.classifier, args.binary)

        # load params
        w2idx, max_length = open_params(args.lang, args.embedding, args.classifier, args.binary)

        # load test data
        for test_directory in args.test_directories:


            test_data = TestData(test_directory, None, rep=words,
                                 binary=args.binary, one_hot=True)

            # convert dataset
            converted_test_data = convert_test_data(test_data, w2idx, max_length)

            # test classifier
            f1s = []
            for model in models:
                pred = model.predict_classes(converted_test_data._Xtest)
                f1 = per_class_f1(converted_test_data._ytest.argmax(1), pred)
                #print(f1.mean())
                f1s.append(f1.mean())
            mean_f1 = np.array(f1s).mean()
            var_f1 = np.array(f1s).std()

            print(test_directory)
            print("Avg f1: {0:.3f}".format(mean_f1))
            print("Std Dev.: {0:.3f}".format(var_f1))
            print()


        # if '1' in monol:
        #     args.lang = 'en'
        # print(classification_report(converted_test_data._ytest.argmax(1), pred))
        # print('Macro F1: {0:.3f}'.format(f1.mean()))
        # info0 = 'classifier' + str(args.classifier) + '\n' + 'test language: ' + str(args.lang)
        # infob = 'binary: ' + str(args.binary)
        # info1 = str(classification_report(converted_test_data._ytest.argmax(1), pred))
        # info2 = str('Macro F1: {0:.3f}'.format(f1.mean()))
        # with open('evals/{}_{}_bi{}_evaluation_result.txt'.format(args.classifier, args.lang, args.binary), 'w') as file_pred:
        #     for el in vars(args):
        #         file_pred.write(str(el) + ': ' + str(vars(args)[el]) + ' \n')
        #     file_pred.write(' \n' + info1 + ' \n'*2 + info2)

    else: #svm
        if '1' in monol:
            args.lang = 'es'
        # load classifier
        if args.binary:
            weight_file = os.path.join('models',
            	'{0}-{1}'.format(args.embedding, args.classifier),
            	'binary-en-{0}'.format(args.lang),
            	'weights.pkl')
        else:
            weight_file = os.path.join('models',
            	'{0}-{1}'.format(args.embedding, args.classifier),
            	'4class-en-{0}'.format(args.lang),
            	'weights.pkl')
        print(weight_file)

        with open(weight_file, 'rb') as file:
            clf = pickle.load(file)

        # load params
        w2idx, matrix = open_params(args.lang, args.embedding, args.classifier, args.binary)

        # load test data
        for test_directory in args.test_directories:
            test_data = TestData(test_directory, None, rep=words,
                                 binary=args.binary, one_hot=True)

            # convert dataset
            converted_test_data = convert_svm_test_dataset(test_data, w2idx, matrix)

            # test classifier
            pred = clf.predict(converted_test_data._Xtest)
            f1 = per_class_f1(converted_test_data._ytest.argmax(1), pred)

            if '1' in monol:
                args.lang = 'en'
            #print(classification_report(converted_test_data._ytest.argmax(1), pred))
            print(test_directory)
            print('Macro F1: {0:.3f}'.format(f1.mean()))

        #info0 = 'classifier' + str(args.classifier) + '\n' + 'test language: ' + str(args.lang)
        #infob = 'binary: ' + str(args.binary)
        #info1 = str(classification_report(converted_test_data._ytest.argmax(1), pred))
        #info2 = str('Macro F1: {0:.3f}'.format(f1.mean()))
        #with open('evals/{}_{}_{}_bi{}_evaluation_result.txt'.format(args.classifier, args.lang, data_type, args.binary), 'w') as file_pred:
        #    for el in vars(args):
        #        file_pred.write(str(el) + ': ' + str(vars(args)[el]) + ' \n')
        #    file_pred.write(' \n' + info1 + ' \n'*2 + info2)


