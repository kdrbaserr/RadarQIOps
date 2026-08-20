# Canonical I/Q model tensor

Model-facing feature code accepts the versioned `IQBatch` data contract and emits a fixed,
channel-first PyTorch representation. The contract is intentionally separate from raw and
processed data artifacts: stored data remains NumPy while model input is always a tensor.

| Field | Contract |
|---|---|
| `values` | `torch.float32`, contiguous `[N, 2, target_length]`; channel order is I then Q |
| `valid_mask` | `torch.bool [N, target_length]`; `true` marks retained signal samples |
| `metadata` | Source representation/length plus exact crop and padding bounds |

`configs/features.yaml` selects the target length, start/center/end cropping, left/center/right
padding and the padding value. Cropping and padding contain no randomness. The same validated
batch and config therefore produce byte-identical values and masks in training and inference.

## Amplitude and wrapped phase

The optional amplitude/phase transform consumes the canonical tensor and emits two channels in
the fixed order `[amplitude, wrapped_phase]`. Amplitude is `sqrt(I² + Q²)` and phase is wrapped to
`[-pi, pi)`. Padding is zeroed and remains excluded by `valid_mask`.

Phase has no physical meaning at zero amplitude. `zero_amplitude_epsilon` defines that boundary;
`phase_valid_mask=false` marks those points and `undefined_phase_value` supplies a finite configured
value. This makes the uncertainty explicit and prevents zero-amplitude samples from producing NaN.

## Optional spectral representation

The `spectral.enabled` switch is `false` by default. When selected, `mode` produces either an FFT
tensor `[N, 1, F]` or a spectrogram `[N, 1, F, T]`; spectral values do not get silently appended
to the canonical I/Q channels. Padded time samples are zeroed before either transform.

`n_fft`, `window`, `overlap`, `scale`, `sample_rate_hz` and the log floor are part of the versioned
config identity. Output metadata records the full config and its SHA-256. The feature artifact hash
covers that metadata, tensor values and frequency/time axes, so any config or output change creates
a different artifact identity.

## Shared training and inference path

`FeaturePipeline` is the only composition point for train-fitted preprocessing, canonical tensor
conversion and the selected optional representation. It accepts an immutable `preprocessor.json`;
there is no fit operation in the shared or inference API. `transform_for_training` and
`transform_for_inference` are deliberately thin adapters over the same transform method.

The versioned golden fixture verifies the complete numerical output and mask for both adapters.
Changing held-out samples cannot change the fitted preprocessing or pipeline hash because fitting
receives only the explicit training indices. A mismatch between either runtime path fails the local
integration suite before model work proceeds.
