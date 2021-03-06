# -*- coding: utf-8 -*-
# /usr/bin/python2


from __future__ import print_function

import argparse

from models import Net2
import numpy as np
from audio import spec2wav, inv_preemphasis, db2amp, denormalize_db
import datetime
import tensorflow as tf
from hparam import hparam as hp
from data_load import Net2DataFlow
from tensorpack.predict.base import OfflinePredictor
from tensorpack.predict.config import PredictConfig
from tensorpack.tfutils.sessinit import SaverRestore
from tensorpack.tfutils.sessinit import ChainInit
from tensorpack.callbacks.base import Callback
import os
import scipy
import numpy as np

# class ConvertCallback(Callback):
#     def __init__(self, logdir, test_per_epoch=1):
#         self.df = Net2DataFlow(hp.convert.data_path, hp.convert.batch_size)
#         self.logdir = logdir
#         self.test_per_epoch = test_per_epoch
#
#     def _setup_graph(self):
#         self.predictor = self.trainer.get_predictor(
#             get_eval_input_names(),
#             get_eval_output_names())
#
#     def _trigger_epoch(self):
#         if self.epoch_num % self.test_per_epoch == 0:
#             audio, y_audio, _ = convert(self.predictor, self.df)
#             # self.trainer.monitors.put_scalar('eval/accuracy', acc)
#
#             # Write the result
#             # tf.summary.audio('A', y_audio, hp.default.sr, max_outputs=hp.convert.batch_size)
#             # tf.summary.audio('B', audio, hp.default.sr, max_outputs=hp.convert.batch_size)


def convert(predictor, tensor):
    # tensor = next(df().get_data())
    # print(tensor.shape)
    pred_spec, y_spec, ppgs = predictor(tensor)
    # pred_spec, y_spec, ppgs = predictor(tf.expand_dims(df, 0))

    # Denormalizatoin
    pred_spec = denormalize_db(pred_spec, hp.default.max_db, hp.default.min_db)
    # y_spec = denormalize_db(y_spec, hp.default.max_db, hp.default.min_db)

    # Db to amp
    pred_spec = db2amp(pred_spec)
    # y_spec = db2amp(y_spec)

    # Emphasize the magnitude
    pred_spec = np.power(pred_spec, hp.convert.emphasis_magnitude)
    # y_spec = np.power(y_spec, hp.convert.emphasis_magnitude)

    # Spectrogram to waveform
    audio = np.array(map(lambda spec: spec2wav(spec.T, hp.default.n_fft, hp.default.win_length, hp.default.hop_length,
                                               hp.default.n_iter), pred_spec))
    # y_audio = np.array(map(lambda spec: spec2wav(spec.T, hp.default.n_fft, hp.default.win_length, hp.default.hop_length,
    #                                              hp.default.n_iter), y_spec))

    # Apply inverse pre-emphasis
    audio = inv_preemphasis(audio, coeff=hp.default.preemphasis)
    # y_audio = inv_preemphasis(y_audio, coeff=hp.default.preemphasis)
    # pickle.dump( y_audio, open( "y-audio.p", "wb" ) )
    # pickle.dump( audio, open( "o-audio.p", "wb" ) )

    # if hp.convert.one_full_wav:
    #     # Concatenate to a wav
    #     y_audio = np.reshape(y_audio, (1, y_audio.size), order='C')
    #     audio = np.reshape(audio, (1, audio.size), order='C')

    # return audio, y_audio, ppgs
    return audio, ppgs


def get_eval_input_names():
    return ['x_mfccs', 'y_spec', 'y_mel']


def get_eval_output_names():
    return ['pred_spec', 'y_spec', 'ppgs']


def do_convert(args, logdir1, logdir2, input_dir):
    # Load graph
    model = Net2()
    # input_dir = hp.convert.data_base_dir_original + hp.convert.data_path
    df = Net2DataFlow(input_dir, hp.convert.batch_size)

    ckpt1 = tf.train.latest_checkpoint(logdir1)
    ckpt2 = '{}/{}'.format(logdir2, args.ckpt) if args.ckpt else tf.train.latest_checkpoint(logdir2)
    session_inits = []
    if ckpt2:
        session_inits.append(SaverRestore(ckpt2))
    if ckpt1:
        session_inits.append(SaverRestore(ckpt1, ignore=['global_step']))
    pred_conf = PredictConfig(
        model=model,
        input_names=get_eval_input_names(),
        output_names=get_eval_output_names(),
        session_init=ChainInit(session_inits))
    predictor = OfflinePredictor(pred_conf)

    # loop over all the audio files
    for wav_file in df.wav_files:
        # check if file is present audio
        out_path = wav_file.replace(hp.convert.data_base_dir_original, hp.convert.data_base_dir_convert)
        # change file extension from wv1/wv2 to wav
        out_path = out_path[:-2] + 'av'
        if os.path.isfile(out_path):
            # file is already present, move on to the next one.
            print("skipping " + wav_file)
            continue

        print("converting " + wav_file)
        # convert audio
        audio_len, feats = df.get_features(wav_file)
        audio_full = []
        for feat in feats:
            input_arr = ([feat[0]], [feat[1]], [feat[2]])
            audio, ppgs = convert(predictor, input_arr)
            audio_full.append((audio[0]*hp.convert.amplitude_multiplier).astype(np.int16))
        scipy.io.wavfile.write(out_path, hp.default.sr, np.concatenate(audio_full)[:audio_len])

    # audio, ppgs = convert(predictor, df)
    # print(audio)

    # Write the result
    # tf.summary.audio('A', y_audio, hp.default.sr, max_outputs=hp.convert.batch_size)
    # tf.summary.audio('B', audio, hp.default.sr, max_outputs=hp.convert.batch_size)

    # Visualize PPGs
    # heatmap = np.expand_dims(ppgs, 3)  # channel=1
    # tf.summary.image('PPG', heatmap, max_outputs=ppgs.shape[0])

    # writer = tf.summary.FileWriter(logdir2)
    # with tf.Session() as sess:
    #     summ = sess.run(tf.summary.merge_all())
    # writer.add_summary(summ)
    # writer.close()

    # session_conf = tf.ConfigProto(
    #     allow_soft_placement=True,
    #     device_count={'CPU': 1, 'GPU': 0},
    #     gpu_options=tf.GPUOptions(
    #         allow_growth=True,
    #         per_process_gpu_memory_fraction=0.6
    #     ),
    # )


def get_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument('case1', type=str, help='experiment case name of train1')
    parser.add_argument('case2', type=str, help='experiment case name of train2')
    parser.add_argument('input_dir', type=str, help='input dir to convert')
    parser.add_argument('-ckpt', help='checkpoint to load model.')
    arguments = parser.parse_args()
    return arguments


if __name__ == '__main__':
    args = get_arguments()
    hp.set_hparam_yaml(args.case2)
    logdir_train1 = '{}/{}/train1'.format(hp.logdir_path, args.case1)
    logdir_train2 = '{}/{}/train2'.format(hp.logdir_path, args.case2)

    print('case1: {}, case2: {}, logdir1: {}, logdir2: {}'.format(args.case1, args.case2, logdir_train1, logdir_train2))
    print("input dir " + args.input_dir)

    s = datetime.datetime.now()

    do_convert(args, logdir1=logdir_train1, logdir2=logdir_train2, input_dir = args.input_dir)

    e = datetime.datetime.now()
    diff = e - s
    print("Done. elapsed time:{}s".format(diff.seconds))
