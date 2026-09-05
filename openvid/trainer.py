"""OPENVID Trainer — CPU LoRA fine-tune of a small local model on SFT data.

Trains a LoRA adapter on the exported conversations (phase 10) so the agent
learns from its own verified traffic. CPU-only by design: 0.5B model + r=8.
Output: adapters/<run>/ (peft adapter dir) ready for LocalLLMWorker reload.

Run: python -m openvid.trainer --data sft.jsonl --out adapters/run1
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path


def load_pairs(path: Path) -> list[dict]:
    pairs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            d = json.loads(line)
            msgs = d["messages"]
            if len(msgs) >= 2:
                pairs.append({"prompt": msgs[0]["content"],
                              "completion": msgs[1]["content"]})
    return pairs


def train(data: Path, out: Path, base_model: str = "Qwen/Qwen2.5-0.5B-Instruct",
          epochs: int = 3, lr: float = 1e-4, max_len: int = 256):
    import torch
    from transformers import (AutoModelForCausalLM, AutoTokenizer,
                              DataCollatorForLanguageModeling)
    from peft import LoraConfig, get_peft_model
    from torch.utils.data import DataLoader

    pairs = load_pairs(data)
    if not pairs:
        raise SystemExit("no training pairs in " + str(data))
    print(f"training on {len(pairs)} pairs | base={base_model} | cpu-only")

    tok = AutoTokenizer.from_pretrained(base_model)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model, dtype=torch.float32)
    model.config.use_cache = False

    lora = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05,
                      target_modules=["q_proj", "v_proj"],
                      task_type="CAUSAL_LM")
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()

    def encode(p):
        text = f"User: {p['prompt']}\nAssistant: {p['completion']}{tok.eos_token}"
        ids = tok(text, truncation=True, max_length=max_len, return_tensors=None)
        return {"input_ids": ids["input_ids"], "labels": list(ids["input_ids"])}

    ds = [encode(p) for p in pairs]
    pad_id = tok.pad_token_id

    def collate(batch):
        mx = max(len(b["input_ids"]) for b in batch)
        input_ids, labels, attn = [], [], []
        for b in batch:
            n = len(b["input_ids"]); pad = mx - n
            input_ids.append(b["input_ids"] + [pad_id] * pad)
            labels.append(b["labels"] + [-100] * pad)
            attn.append([1] * n + [0] * pad)
        return {"input_ids": torch.tensor(input_ids),
                "labels": torch.tensor(labels),
                "attention_mask": torch.tensor(attn)}

    dl = DataLoader(ds, batch_size=2, shuffle=True, collate_fn=collate)
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=lr)
    losses = []
    t0 = time.time()
    model.train()
    for epoch in range(epochs):
        for batch in dl:
            fwd = model(**batch)
            loss = fwd.loss
            loss.backward()
            opt.step(); opt.zero_grad()
            losses.append(loss.item())
        print(f"epoch {epoch+1}/{epochs} loss={losses[-1]:.4f}")

    outp = Path(out); outp.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(outp))
    tok.save_pretrained(str(outp))
    avg = sum(losses) / len(losses)
    report = {"pairs": len(pairs), "epochs": epochs, "avg_loss": avg,
              "first_loss": losses[0], "last_loss": losses[-1],
              "improved": losses[-1] < losses[0],
              "seconds": round(time.time() - t0, 1), "out": str(outp)}
    (outp / "train_report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--base", default="Qwen/Qwen2.5-0.5B-Instruct")
    ap.add_argument("--epochs", type=int, default=3)
    args = ap.parse_args()
    train(Path(args.data), Path(args.out), base_model=args.base, epochs=args.epochs)
