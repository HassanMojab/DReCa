import gc, os, pickle

import torch
from transformers import AutoTokenizer
from transformers.data.processors.squad import *
import pandas as pd

from torch.utils.data import Dataset


class CorpusQA(Dataset):
    def __init__(
        self, path, evaluate, model_name="xlm-roberta-base", local_files_only=False
    ):
        self.doc_stride = 128
        self.max_query_len = 64
        self.max_seq_len = 384

        self.model_name = model_name

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            do_lower_case=False,
            use_fast=False,
            local_files_only=local_files_only,
        )

        self.dataset, self.examples, self.features = self.preprocess(path, evaluate)

        self.data = {
            key: self.dataset[:][i]
            for i, key in enumerate(
                [
                    "input_ids",
                    "attention_mask",
                    "token_type_ids",
                    "answer_start",
                    "answer_end",
                ]
            )
        }

    def preprocess(self, file, evaluate=False):
        file = file.split("/")
        filename = file[-1]
        data_dir = "/".join(file[:-1])

        cached_features_file = os.path.join(
            data_dir, "cached_{}_{}".format(type(self.tokenizer).__name__, filename)
        )

        # Init features and dataset from cache if it exists
        if os.path.exists(cached_features_file):
            features_and_dataset = torch.load(cached_features_file)
            features, dataset, examples = (
                features_and_dataset["features"],
                features_and_dataset["dataset"],
                features_and_dataset["examples"],
            )
        else:
            processor = SquadV1Processor()
            if evaluate:
                examples = processor.get_dev_examples(data_dir, filename)
            else:
                examples = processor.get_train_examples(data_dir, filename)

            features, dataset = squad_convert_examples_to_features(
                examples=examples,
                tokenizer=self.tokenizer,
                max_seq_length=self.max_seq_len,
                doc_stride=self.doc_stride,
                max_query_length=self.max_query_len,
                is_training=not evaluate,
                return_dataset="pt",
                threads=1,
            )

            torch.save(
                {"features": features, "dataset": dataset, "examples": examples},
                cached_features_file,
            )

        return dataset, examples, features

    def __len__(self):
        return len(self.dataset)

    def __getitem__(self, id):
        return {
            "input_ids": self.dataset[id][0],
            "attention_mask": self.dataset[id][1],
            "token_type_ids": self.dataset[id][2],
            "answer_start": self.dataset[id][3],
            "answer_end": self.dataset[id][4],
        }


class CorpusSC(Dataset):
    def __init__(
        self, path, file, model_name="xlm-roberta-base", local_files_only=False
    ):
        self.max_sequence_length = 128

        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name, do_lower_case=False, local_files_only=local_files_only
        )

        self.label_dict = {"contradiction": 0, "entailment": 1, "neutral": 2}

        cached_data_file = path + f"_{type(self.tokenizer).__name__}.pickle"

        if os.path.exists(cached_data_file):
            self.data = pickle.load(open(cached_data_file, "rb"))
        else:
            self.data = self.preprocess(path, file)
            pickle.dump(
                self.data,
                open(cached_data_file, "wb"),
                protocol=pickle.HIGHEST_PROTOCOL,
            )

    def preprocess(self, path, file):
        header = ["premise", "hypothesis", "label"]
        df = pd.read_csv(path, sep="\t", header=None, names=header)

        premise_list = df["premise"].to_list()
        hypothesis_list = df["hypothesis"].to_list()
        label_list = df["label"].to_list()

        # Tokenize input pair sentences
        ids = self.tokenizer(
            premise_list,
            hypothesis_list,
            add_special_tokens=True,
            max_length=self.max_sequence_length,
            truncation=True,
            padding=True,
            return_attention_mask=True,
            return_token_type_ids=True,
            return_tensors="pt",
        )

        labels = torch.tensor([self.label_dict[label] for label in label_list])

        dataset = {
            "input_ids": ids["input_ids"],
            "token_type_ids": ids["attention_mask"],
            "attention_mask": ids["token_type_ids"],
            "label": labels,
        }

        return dataset

    def __len__(self):
        return self.data["input_ids"].shape[0]

    def __getitem__(self, id):
        return {
            "input_ids": self.data["input_ids"][id],
            "token_type_ids": self.data["token_type_ids"][id],
            "attention_mask": self.data["attention_mask"][id],
            "label": self.data["label"][id],
        }
