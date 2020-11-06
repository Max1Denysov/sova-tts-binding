import json

import torch

from hparams import create_hparams
from model import load_model
from modules.layers import TacotronSTFT


class HparamsNotFound(Exception):
    pass


class Tacotron2Wrapper:
    def __init__(self, model_path, device, hparams_path=None, steps_per_symbol=10, gate_threshold=0.5):
        self.device = torch.device("cpu" if not torch.cuda.is_available() else device)
        self.dtype = torch.float if self.device.type == "cpu" else torch.half

        _checkpoint = torch.load(model_path, map_location=self.device)
        _hparams = _checkpoint.get("hparams", None)
        if _hparams is not None:
            _hparams = json.loads(_hparams)
        elif hparams_path is None:
            raise HparamsNotFound("The hparams dict is not presented either in a checkpoint or as a file.")
        else:
            _hparams = hparams_path

        self.hparams = create_hparams(_hparams)

        _charset = self.hparams.get("language", None)  # обратная совместимость со старыми конфигами
        if _charset is not None:
            self.hparams.charset = _charset
        self.hparams.device = self.device

        self.model = load_model(self.hparams)
        self.model.load_state_dict(_checkpoint["state_dict"])
        self.model.eval().to(device=self.device, dtype=self.dtype)

        self.stft = TacotronSTFT(
            self.hparams.filter_length, self.hparams.hop_length, self.hparams.win_length,
            self.hparams.n_mel_channels, self.hparams.sampling_rate, self.hparams.mel_fmin,
            self.hparams.mel_fmax
        )

        self.steps_per_symbol = steps_per_symbol
        self.gate_threshold = gate_threshold


    def __call__(self, sequence, **kwargs):
        sequence = torch.LongTensor(sequence).view(1, -1)
        sequence = sequence.to(device=self.device)

        kwargs["max_decoder_steps"] = int(self.steps_per_symbol * sequence.size(-1))

        mel_outputs, mel_outputs_postnet, gates, alignments = self.model.inference(sequence, **kwargs)

        return mel_outputs_postnet