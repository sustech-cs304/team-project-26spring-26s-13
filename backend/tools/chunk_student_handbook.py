from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


sys.path.insert(0, str(_repo_root()))

from backend.utils.document_parser import parse_document
from backend.utils.semantic_chunker import semantic_chunk_text


def _expand_inputs(inputs: list[str]) -> list[Path]:
    files: list[Path] = []
    for raw in inputs:
        p = Path(raw)
        if any(ch in raw for ch in ("*", "?", "[")):
            files.extend(Path().glob(raw))
            continue
        if p.is_dir():
            files.extend(sorted(p.glob("*.pdf")))
            continue
        files.append(p)
    out: list[Path] = []
    seen: set[str] = set()
    for f in files:
        fp = str(f.resolve())
        if fp in seen:
            continue
        seen.add(fp)
        out.append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="PDF 路径（可多个），或目录（将扫描 *.pdf），或通配符（例如 test/handbook/*.pdf）",
    )
    ap.add_argument(
        "--out",
        default=str(_repo_root() / "temp" / "handbook_chunks"),
        help="输出目录（默认 temp/handbook_chunks）",
    )
    ap.add_argument("--chunk-size", type=int, default=1200)
    ap.add_argument("--chunk-max", type=int, default=1600)
    ap.add_argument("--overlap", type=int, default=150)
    args = ap.parse_args()

    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = _expand_inputs(args.input)
    if not pdfs:
        raise SystemExit("No input PDFs found.")

    index: list[dict[str, object]] = []

    for pdf_path in pdfs:
        if not pdf_path.exists():
            raise SystemExit(f"Missing file: {pdf_path}")
        parsed = parse_document(str(pdf_path), "application/pdf")
        chunks = semantic_chunk_text(
            parsed.text,
            target_size=int(args.chunk_size),
            hard_max_size=int(args.chunk_max),
            overlap=int(args.overlap),
        )

        stem = pdf_path.stem
        extracted_txt_path = out_dir / f"{stem}.extracted.txt"
        chunks_jsonl_path = out_dir / f"{stem}.chunks.jsonl"
        meta_path = out_dir / f"{stem}.meta.json"

        extracted_txt_path.write_text(parsed.text, encoding="utf-8")

        with chunks_jsonl_path.open("w", encoding="utf-8") as f:
            for i, c in enumerate(chunks):
                rec = {
                    "chunk_id": f"{stem}:{i:05d}",
                    "chunk_index": i,
                    "section_path": list(c.section_path),
                    "text": c.text,
                    "char_len": len(c.text),
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        meta = {
            "source_file": str(pdf_path),
            "file_name": pdf_path.name,
            "page_count": int(parsed.page_count),
            "extracted_chars": len(parsed.text),
            "chunk_count": len(chunks),
            "output": {
                "extracted_txt": str(extracted_txt_path),
                "chunks_jsonl": str(chunks_jsonl_path),
            },
            "chunking": {
                "chunk_size": int(args.chunk_size),
                "chunk_max": int(args.chunk_max),
                "overlap": int(args.overlap),
            },
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        index.append(meta)

    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

