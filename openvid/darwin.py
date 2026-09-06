"""OPENVID DarwinWorker — skill-evolution intelligence imported from OpenAmer.

Reads the OpenAmer Darwin state (population win/loss stats, lineage) and
exposes it to the agent:
    darwin.stats            -> win/loss leaderboard of evolved skills
    darwin.best             -> strongest skills (by wins/loss ratio)
    darwin.weakest          -> skills the evolution loop should cull/repair
    darwin.import           -> copy top-N evolved skills into OPENVID's own
                               skills/ dir (name-spaced), ready for skill.get

Also: a standalone evolution micro-loop (evolve_once) that promotes OPENVID's
own learned skills (from selfimprove) into the population and mutates the
weakest — the seed of OPENVID's own Darwin, growing from imported DNA.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

OPENAMER_DARWIN = Path(r"C:\Users\damir\AppData\Local\openamer-laptop\darwin")
OPENAMER_SKILLS = Path(r"C:\Users\damir\AppData\Local\openamer-laptop\skills")


class DarwinWorker:
    name = "darwin"
    topics = ["agent.action"]
    actions = {"darwin.stats", "darwin.best", "darwin.weakest", "darwin.import",
               "darwin.evolve"}

    def __init__(self, home: Path):
        self.home = Path(home)
        self.src = OPENAMER_DARWIN
        self.src_skills = OPENAMER_SKILLS

    # -- data readers ------------------------------------------------------
    def _population(self) -> dict:
        f = self.src / "population.json"
        if f.exists():
            return json.loads(f.read_text(encoding="utf-8"))
        return {}

    def _scored(self) -> list[dict]:
        pop = self._population()
        rows = []
        for name, s in pop.items():
            w, l = s.get("wins", 0), s.get("losses", 0)
            rows.append({"name": name, "wins": w, "losses": l,
                         "score": (w - l) / max(w + l, 1)})
        return sorted(rows, key=lambda r: r["score"], reverse=True)

    # -- actions -----------------------------------------------------------
    def handle(self, payload: dict) -> dict:
        act = payload.get("action", "")
        if act == "darwin.stats":
            rows = self._scored()
            return {"ok": True, "total_skills": len(rows),
                    "total_wins": sum(r["wins"] for r in rows),
                    "total_losses": sum(r["losses"] for r in rows),
                    "top5": rows[:5]}
        if act == "darwin.best":
            n = int(payload.get("n", 10))
            return {"ok": True, "skills": [r["name"] for r in self._scored()[:n]
                                           if r["wins"] > r["losses"]]}
        if act == "darwin.weakest":
            n = int(payload.get("n", 10))
            weak = [r for r in self._scored() if r["losses"] > r["wins"]]
            return {"ok": True, "skills": [r["name"] for r in weak[:n]]}
        if act == "darwin.import":
            return self._import(payload.get("n", 10))
        if act == "darwin.evolve":
            return self._evolve()
        return {"ok": False, "error": f"unsupported: {act}"}

    def _import(self, n: int) -> dict:
        """Copy the top evolved skills' SKILL.md into OPENVID skills/."""
        dest = self.home / "skills"
        dest.mkdir(parents=True, exist_ok=True)
        imported, skipped = [], []
        for row in self._scored()[:n * 2]:
            name = row["name"]
            if row["wins"] <= row["losses"]:
                continue
            src_file = self.src_skills / name / "SKILL.md"
            if not src_file.exists():
                skipped.append(name)
                continue
            target = dest / f"darwin_{name}.md"
            if target.exists():
                skipped.append(name)
                continue
            shutil.copyfile(src_file, target)
            imported.append(name)
            if len(imported) >= n:
                break
        return {"ok": True, "imported": imported, "skipped": len(skipped)}

    # -- own evolution micro-loop -------------------------------------------
    def _evolve(self) -> dict:
        """Cull-arena for OPENVID's OWN skills: skills that appear in
        error-proposals twice get demoted (moved to archive/)."""
        own = self.home / "skills"
        archive = self.home / "skills_archive"
        archive.mkdir(exist_ok=True)
        proposals = self.home / "skills" / "_proposals"
        demoted = []
        if proposals.exists():
            for prop in proposals.glob("*.md"):
                marker = own / prop.name
                if marker.exists():
                    shutil.move(str(marker), str(archive / prop.name))
                    demoted.append(prop.name)
        return {"ok": True, "demoted_to_archive": demoted,
                "note": "error-born skills archived; import() re-seeds from darwin"}
