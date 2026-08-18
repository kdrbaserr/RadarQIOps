from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from radariq.data.acquisition import AcquisitionError, acquire_from_config
from radariq.data.ingestion import RawIngestionError, ingest_from_config
from radariq.data.manifests import register_source_from_config
from radariq.data_inspect import DATASET_CHOICES, InspectError, inspect_dataset
from radariq.evaluation.pipeline import evaluate_from_config
from radariq.training.pipeline import train_from_config


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="radariq")
    subcommands = parser.add_subparsers(dest="command", required=True)

    data_parser = subcommands.add_parser("data", help="Veri seti işlemleri")
    data_commands = data_parser.add_subparsers(dest="data_command", required=True)

    acquire_parser = data_commands.add_parser(
        "acquire",
        help="Config içindeki HTTP, yerel dosya veya arşiv kaynağını atomik olarak al",
    )
    acquire_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Acquisition kaynak ve hedef ayarlarını içeren JSON uyumlu YAML",
    )

    register_parser = data_commands.add_parser(
        "register",
        help="Kaynağı checksum, lisans, atıf ve sürümlü data manifest ile kaydet",
    )
    register_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Acquisition ve zorunlu manifest metadata ayarlarını içeren config",
    )

    ingest_parser = data_commands.add_parser(
        "ingest",
        help="Edinilmiş ZIP/TAR arşivini deterministik ve değişmez raw stage'e aç",
    )
    ingest_parser.add_argument(
        "--config",
        required=True,
        type=Path,
        help="Arşiv, raw kök ve kaynak sürümü ayarlarını içeren config",
    )

    inspect_parser = data_commands.add_parser(
        "inspect",
        help="Bir aday veri setinden küçük bir örneği JSON olarak incele",
    )
    inspect_parser.add_argument(
        "--dataset",
        required=True,
        choices=DATASET_CHOICES,
        help="Veri seti okuyucusu",
    )
    inspect_parser.add_argument(
        "--path",
        required=True,
        type=Path,
        help="Veri dosyası veya veri seti dizini",
    )
    inspect_parser.add_argument(
        "--sample-index",
        type=int,
        default=0,
        help="İncelenecek örneğin sıfır tabanlı indeksi (varsayılan: 0)",
    )
    inspect_parser.add_argument(
        "--metadata",
        type=Path,
        help="NPY adayları için isteğe bağlı JSON yan dosyası",
    )
    inspect_parser.add_argument(
        "--allow-unsafe-pickle",
        action="store_true",
        help="Yalnızca güvenilen RadioML 2016 pickle dosyasını açmaya izin ver",
    )
    inspect_parser.add_argument(
        "--output",
        type=Path,
        help="JSON çıktısını stdout yerine bu dosyaya yaz",
    )
    inspect_parser.add_argument(
        "--compact",
        action="store_true",
        help="Girintisiz, tek satırlık JSON üret",
    )

    train_parser = subcommands.add_parser("train", help="Config ile model eğit")
    train_parser.add_argument("--config", type=Path, default=Path("configs/train.yaml"))

    evaluate_parser = subcommands.add_parser("evaluate", help="Modeli değerlendir")
    evaluate_parser.add_argument("--config", type=Path, default=Path("configs/evaluate.yaml"))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "train":
            print(json.dumps(train_from_config(args.config), ensure_ascii=False, indent=2))
            return 0
        if args.command == "evaluate":
            print(json.dumps(evaluate_from_config(args.config), ensure_ascii=False, indent=2))
            return 0
        if args.data_command == "acquire":
            print(
                json.dumps(
                    acquire_from_config(args.config).as_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.data_command == "register":
            print(
                json.dumps(
                    register_source_from_config(args.config).as_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
        if args.data_command == "ingest":
            print(
                json.dumps(
                    ingest_from_config(args.config).as_dict(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        result = inspect_dataset(
            dataset=args.dataset,
            path=args.path,
            sample_index=args.sample_index,
            metadata_path=args.metadata,
            allow_unsafe_pickle=args.allow_unsafe_pickle,
        )
        payload = json.dumps(
            result,
            ensure_ascii=False,
            indent=None if args.compact else 2,
            sort_keys=False,
            allow_nan=False,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return 0
    except (
        AcquisitionError,
        RawIngestionError,
        InspectError,
        OSError,
        KeyError,
        ValueError,
    ) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
