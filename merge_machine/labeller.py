#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 16 15:29:43 2017

@author: leo

Class used to label data with a deduper object

"""

import json
import os

import pandas as pd

def unique(seq) :
    seen = set()
    seen_add = seen.add
    return [x for x in seq if not (x in seen or seen_add(x))]

class DummyLabeller():
    """Just used to count training labels"""
    def __init__(self, paths, use_previous=False):
        training_path=paths['train']
        if (training_path is not None) and use_previous \
                        and os.path.isfile(training_path):
                            
            with open(training_path) as f:
                self.training = json.load(f)
                
            # Check that training examples match header
            source_cols = set(pd.read_csv(paths['source'], encoding='utf-8', nrows=0).columns)
            ref_cols = set(pd.read_csv(paths['source'], encoding='utf-8', nrows=0).columns)
            
            for pair in self.training['distinct'] + self.training['match']:
                if source_cols != set(pair['__value__'][0].keys())\
                        or ref_cols != set(pair['__value__'][1].keys()):
                    self.training = {'distinct': [], 'match': []}
                    break        
        else: 
            self.training = {'distinct': [], 'match': []}

    def to_emit(self, message=''):
        dict_to_emit = dict()
        dict_to_emit['n_match'] = len(self.training['match'])
        dict_to_emit['n_distinct'] = len(self.training['distinct'])
        return dict_to_emit
        
    
class Labeller():
    def __init__(self, deduper, training_path=None, use_previous=False):
        self.deduper = deduper
        self.finished = False
        self.use_previous = False
        self.fields = unique(field.field 
                              for field
                              in deduper.data_model.primary_fields)
        self.buffer_len = 1
        self.examples_buffer = []
        self.uncertain_pairs = []
        
        if (training_path is not None) and use_previous \
                        and os.path.isfile(training_path):
            try:
                with open(training_path) as f:
                    self.deduper.readTraining(f)
            except:
                # TODO: replace by logging
                print('WARNING: Unable to read training data')
        

    def answer_is_valid(self, user_input):
        '''Check if the user input is valid'''
        if self.examples_buffer:
            valid_responses = {'y', 'n', 'u', 'f', 'p'}
        else: 
            valid_responses = {'y', 'n', 'u', 'f'}
        return user_input in valid_responses

    def _format_record_pair(self):
        '''Return list of triplets (field, val_source, val_ref)'''
        formated_record_pair = [(field, self.record_pair[0][field], 
                        self.record_pair[1][field]) for field in self.fields]
        return formated_record_pair
        
    def to_emit(self, message):
        '''Creates a dict to be sent to the template'''
        dict_to_emit = dict()
        dict_to_emit['formated_record_pair'] = self._format_record_pair()
        dict_to_emit['formated_example'] = self._format_fields() # TODO: remove this
        dict_to_emit['n_match'] = str(self.n_match)
        dict_to_emit['n_distinct'] = str(self.n_distinct)
        dict_to_emit['has_previous'] = len(self.examples_buffer) >= 1
        if message:
            dict_to_emit['_message'] = message
        return dict_to_emit


    def _format_fields(self):
        '''Return string containing fields and field names'''
        # TODO: This should be done in template
        formated_example = ''
        for pair in self.record_pair:
            for field in self.fields:
                line = "{0!s} : {1!s}".format(field, pair[field])
                formated_example += line + '\n'
            formated_example += '\n'
        return formated_example
            
        
    def new_label(self):
        if self.use_previous:
            self.record_pair, _ = self.examples_buffer.pop(0)
            self.use_previous = False
        else:
            if not self.uncertain_pairs:
                self.uncertain_pairs = self.deduper.uncertainPairs()
            self.record_pair = self.uncertain_pairs.pop()
                     
        self.n_match = (len(self.deduper.training_pairs['match']) +
                   sum(label=='match' for _, label in self.examples_buffer))
        self.n_distinct = (len(self.deduper.training_pairs['distinct']) +
                      sum(label=='distinct' for _, label in self.examples_buffer))

        self.user_input = ''        
        

    def parse_valid_answer(self, user_input):
        if user_input == 'y':
            self.examples_buffer.insert(0, (self.record_pair, 'match'))
        elif user_input == 'n' :
            self.examples_buffer.insert(0, (self.record_pair, 'distinct'))
        elif user_input == 'u':
            self.examples_buffer.insert(0, (self.record_pair, 'uncertain'))
        elif user_input == 'f':
            self.finished = True
        elif user_input == 'p':
            self.use_previous = True
            self.uncertain_pairs.append(self.record_pair)
        
        if len(self.examples_buffer) > self.buffer_len:
            self.record_pair, label = self.examples_buffer.pop()
            if label in ['distinct', 'match']:
                examples = {'distinct' : [], 'match' : []}
                examples[label].append(self.record_pair)
                self.deduper.markPairs(examples)

    def cleanup_training(self):
        self.deduper.cleanupTraining()

    def write_training(self, file_path):
        with open(file_path, 'w') as f:
            self.deduper.writeTraining(f)