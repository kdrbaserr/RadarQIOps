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
