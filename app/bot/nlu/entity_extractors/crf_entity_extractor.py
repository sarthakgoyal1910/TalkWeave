# -*- coding: utf-8 -*-

import pycrfsuite
from flask import current_app as app


class CRFEntityExtractor:
    """
    Performs NER training, prediction, model import/export
    """

    def __init__(self, synonyms=[]):
        self.synonyms = synonyms

    def pos_tagger(self, doc):
        """
        perform POS tagging on a given spacy doc
        :param doc: spacy doc
        :return: tagged sentence
        """
        tagged_sentence = []
        for token in doc:
            tagged_sentence.append((token.text, token.tag_))
        return tagged_sentence

    def pos_tag_and_label(self, text, doc):
        """
        Perform POS tagging and BIO labeling on given sentence
        :param text: original text
        :param doc: spacy doc
        :return:
        """
        tagged_sentence = self.pos_tagger(doc)
        tagged_sentence_json = []
        for token, postag in tagged_sentence:
            tagged_sentence_json.append([token, postag, "O"])
        return tagged_sentence_json

    def sentence_tokenize(self, doc):
        """
        Sentence tokenizer
        :param doc: spacy doc
        :return:
        """
        words = [token.text for token in doc]
        return " ".join(words)

    def replace_synonyms(self, entities):
        """
        replace extracted entity values with
        root word by matching with synonyms dict.
        :param entities:
        :return:
        """
        for entity in entities.keys():
            entity_value = str(entities[entity])
            if entity_value.lower() in self.synonyms:
                entities[entity] = self.synonyms[entity_value.lower()]
        return entities

    def extract_features(self, sent, i):
        """
        Extract features for a given sentence
        :param sent:
        :param i:
        :return:
        """
        word = sent[i][0]
        postag = sent[i][1]
        features = [
            'bias',
            'word.lower=' + word.lower(),
            'word[-3:]=' + word[-3:],
            'word[-2:]=' + word[-2:],
            'word.isupper=%s' % word.isupper(),
            'word.istitle=%s' % word.istitle(),
            'word.isdigit=%s' % word.isdigit(),
            'postag=' + postag,
            'postag[:2]=' + postag[:2],
        ]
        if i > 0:
            word1 = sent[i - 1][0]
            postag1 = sent[i - 1][1]
            features.extend([
                '-1:word.lower=' + word1.lower(),
                '-1:word.istitle=%s' % word1.istitle(),
                '-1:word.isupper=%s' % word1.isupper(),
                '-1:postag=' + postag1,
                '-1:postag[:2]=' + postag1[:2],
            ])
        else:
            features.append('BOS')

        if i < len(sent) - 1:
            word1 = sent[i + 1][0]
            postag1 = sent[i + 1][1]
            features.extend([
                '+1:word.lower=' + word1.lower(),
                '+1:word.istitle=%s' % word1.istitle(),
                '+1:word.isupper=%s' % word1.isupper(),
                '+1:postag=' + postag1,
                '+1:postag[:2]=' + postag1[:2],
            ])
        else:
            features.append('EOS')

        return features

    def sent_to_features(self, sent):
        """
        Extract features from training Data
        :param sent:
        :return:
        """
        return [self.extract_features(sent, i) for i in range(len(sent))]

    def sent_to_labels(self, sent):
        """
        Extract labels from training data
        :param sent:
        :return:
        """
        return [label for token, postag, label in sent]

    def sent_to_tokens(self, sent):
        """
        Extract tokens from training data
        :param sent:
        :return:
        """
        return [token for token, postag, label in sent]

    def train(self, train_sentences, model_name):
        """
        Train NER model for given model
        :param train_sentences:
        :param model_name:
        :return:
        """
        features = [self.sent_to_features(s) for s in train_sentences]
        labels = [self.sent_to_labels(s) for s in train_sentences]

        trainer = pycrfsuite.Trainer(verbose=False)
        for xseq, yseq in zip(features, labels):
            trainer.append(xseq, yseq)

        trainer.set_params({
            'c1': 1.0,  # coefficient for L1 penalty
            'c2': 1e-3,  # coefficient for L2 penalty
            'max_iterations': 50,  # stop earlier

            # include transitions that are possible, but not observed
            'feature.possible_transitions': True
        })
        trainer.train('model_files/%s.model' % model_name)
        return True

    def crf2json(self, tagged_sentence):
        """
        Extract label-value pair from NER prediction output
        :param tagged_sentence:
        :return:
        """
        labeled = {}
        labels = set()
        for s, tp in tagged_sentence:
            if tp != "O":
                label = tp[2:]
                if tp.startswith("B"):
                    labeled[label] = s
                    labels.add(label)
                elif tp.startswith("I") and (label in labels):
                    labeled[label] += " %s" % s
        return labeled

    def extract_ner_labels(self, predicted_labels):
        """
        Extract name of labels from NER
        :param predicted_labels:
        :return:
        """
        labels = []
        for tp in predicted_labels:
            if tp != "O":
                labels.append(tp[2:])
        return labels

    def predict(self, model_name, text, doc):
        """
        Predict NER labels for given model and query
        :param model_name: model name
        :param text: original text
        :param doc: spacy doc
        :return:
        """
        words = [token.text for token in doc]
        tagged_token = self.pos_tagger(doc)
        tagger = pycrfsuite.Tagger()
        tagger.open("{}/{}.model".format(app.config["MODELS_DIR"], model_name))
        predicted_labels = tagger.tag(self.sent_to_features(tagged_token))
        extracted_entities = self.crf2json(
            zip(words, predicted_labels))
        return self.replace_synonyms(extracted_entities)

    def json2crf(self, training_data):
        """
        Takes json annotated data and converts to
        CRFSuite training data representation
        :param training_data:
        :return labeled_examples:
        """
        labeled_examples = []

        for example in training_data:
            # POS tag and initialize bio label as 'O' for all the tokens
            tagged_example = self.pos_tag_and_label(example.get("text"), example.get("spacy_doc"))

            # find no of words before selection
            for entity in example.get("entities"):
                try:
                    begin_index = entity.get("begin")
                    end_index = entity.get("end")
                    # find no of words before the entity
                    inverse_selection = example.get("text")[0:begin_index - 1]
                    inverse_selection = self.sentence_tokenize(inverse_selection)
                    inverse_selection = inverse_selection.split(" ")
                    inverse_word_count = len(inverse_selection)

                    # get the entity value from selection
                    selection = example.get("text")[begin_index:end_index]

                    tokens = self.sentence_tokenize(selection).split(" ")

                    selection_word_count = len(tokens)

                    # build BIO tagging
                    for i in range(1, selection_word_count + 1):
                        if i == 1:
                            bio = "B-" + entity.get("name")
                        else:
                            bio = "I-" + entity.get("name")
                        tagged_example[(inverse_word_count + i) - 1][2] = bio
                except:
                    # catches and skips invalid offsets and annotation
                    continue

            labeled_examples.append(tagged_example)
        return labeled_examples
