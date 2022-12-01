import fire
from glob import glob
import json
import numpy as np
import os
from pathlib import Path
import time
from tqdm import tqdm

curr_dir = os.path.dirname(os.path.realpath(__file__))
import sys

sys.path.insert(0, os.path.join(curr_dir, ".."))
from model_utils import ModelLoader, FeatExtractor
from utils import read_lst, load_dct, write_to_file


def save_rep(
    model_name,
    ckpt_pth,
    save_dir,
    utt_id_fn,
    model_type="pretrained",
    rep_type="contextualized",
    dict_fn=None,
    fbank_dir=None,
    offset=False,
    mean_pooling=False,
    span="frame",
    pckg_dir=None,
):
    """
    Extract layer-wise representations from the model

    ckpt_pth: path to the model checkpoint
    save_dir: directory where the representations are saved
    utt_id_fn: identifier for utterances
    model_type: pretrained or finetuned
    rep_type: contextualized or local or quantized
    dict_fn: path to dictionary file in case of finetuned models
    fbank_dir: directory that has filterbanks stored
    offset: span representation attribute
    mean_pooling: span representation attribute
    span: frame | phone | word
    """
    assert rep_type in ["local", "quantized", "contextualized"]

    model_obj = ModelLoader(ckpt_pth, model_type, pckg_dir, dict_fn)
    encoder, task_cfg = getattr(model_obj, model_name.split("_")[0])()

    Path(save_dir).mkdir(exist_ok=True, parents=True)
    if ".tsv" in utt_id_fn:
        utt_id_lst = read_lst(utt_id_fn)
        label_lst = None
    else:
        utt_id_dct = load_dct(utt_id_fn)
        utt_id_lst = list(utt_id_dct.keys())
        label_lst = []
        label_lst_fn = os.path.join(
            save_dir, "..", f'labels_{save_dir.split("/")[-1]}.lst'
        )
    rep_dct = {}
    write_flag = True
    # local representations
    transformed_fbank_lst, truncated_fbank_lst = [], []
    # quantized representations
    quantized_features, quantized_indices = [], []

    start = time.time()
    for item in tqdm(utt_id_lst):
        if span == "frame":
            time_stamp_lst = None
            utt_id, wav_fn = item.split("\t")
        else:
            utt_id = item
            wav_fn = utt_id_dct[utt_id][0]
            time_stamp_lst = utt_id_dct[utt_id][1:]
        extract_obj = FeatExtractor(
            encoder,
            utt_id,
            wav_fn,
            rep_type,
            model_name,
            fbank_dir,
            task_cfg,
            offset=offset,
            mean_pooling=mean_pooling,
        )
        getattr(extract_obj, model_name.split("_")[0])()
        if rep_type == "local":
            extract_obj.extract_local_rep(
                rep_dct, transformed_fbank_lst, truncated_fbank_lst
            )

        elif rep_type == "contextualized":
            extract_obj.extract_contextualized_rep(rep_dct, time_stamp_lst, label_lst)

        elif rep_type == "quantized":
            quantized_features, quantized_indices = extract_obj.extract_quantized_rep(
                quantized_features, quantized_indices
            )

    if span in ["phone", "word"]:
        write_to_file("\n".join(label_lst), label_lst_fn)

    if rep_type != "quantized":
        extract_obj.save_rep_to_file(rep_dct, save_dir)

    if rep_type == "local":
        if "avhubert" not in model_name:
            truncated_fbank_mat = np.concatenate(truncated_fbank_lst, 0)
            np.save(os.path.join(fbank_dir, "all_features.npy"), truncated_fbank_mat)
            sfx = ""
        else:
            sfx = "_by4"
        transformed_fbank_mat = np.concatenate(transformed_fbank_lst, 0)
        np.save(
            os.path.join(fbank_dir, f"all_features_downsampled{sfx}.npy"),
            transformed_fbank_mat,
        )

    elif rep_type == "quantized":
        rep_mat = np.concatenate(quantized_features, 0)
        idx_mat = np.concatenate(quantized_indices, 0)
        np.save(os.path.join(save_dir, "features.npy"), rep_mat)
        np.save(os.path.join(save_dir, "indices.npy"), idx_mat)

    print("%s representations saved to %s" % (rep_type, save_dir))

    print("Time required: %.1f mins" % ((time.time() - start) / 60))


if __name__ == "__main__":
    fire.Fire()
