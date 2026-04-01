#!/usr/bin/env python3.14
import csv
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional, Set

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont
from datetime import datetime
import argparse
# ============================================================
# Theme
# ============================================================

COLORS = {
    "bg": "#F1F5F9",
    "panel": "#FFFFFF",
    "panel_alt": "#F1F5F9",
    "border": "#E2E8F0",
    "shadow": "#E6EDF5",
    "primary": "#2563EB",
    "primary_dark": "#1D4ED8",
    "accent": "#10B981",
    "warning": "#F59E0B",
    "danger": "#EF4444",
    "text": "#0F172A",
    "secondary": "#475569",
    "muted": "#64748B",
    "chart_alt": "#EF4444",
    "chart_rec": "#2563EB",
    "hover": "#F8FBFF",
    "softblue":"#93C5FD",
}

FONT_FAMILY = "Segoe UI"
FONT_TITLE = (FONT_FAMILY, 20, "bold")
FONT_SUBTITLE = (FONT_FAMILY, 12, "bold")
FONT_UI = (FONT_FAMILY, 11)
FONT_UI_BOLD = (FONT_FAMILY, 11, "bold")
FONT_SMALL = (FONT_FAMILY, 9)
FONT_RESULT_TITLE = (FONT_FAMILY, 12, "bold")


# ============================================================
# Agents from i.lp
# ============================================================

AGENT_RANGE_RE = re.compile(r"\bagent\s*\(\s*(\d+)\s*\.\.\s*(\d+)\s*\)\s*\.", re.I)
AGENT_ANY_RE = re.compile(r"\bagent\s*\(\s*([^)]+?)\s*\)\s*\.", re.I)
IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def default_generated_q_path(i_lp: Path) -> Path:
    return i_lp.parent / "generated_q.lp"


def agent_sort_key(a: str) -> Tuple[int, int, str]:
    a = str(a).strip()
    if a.isdigit():
        return (0, int(a), "")
    return (1, 0, a.lower())


def agents_from_i_lp(i_lp: Path) -> List[str]:
    txt = i_lp.read_text(encoding="utf-8")
    agents: Set[str] = set()

    for a, b in AGENT_RANGE_RE.findall(txt):
        l, h = int(a), int(b)
        if l <= h:
            for k in range(l, h + 1):
                agents.add(str(k))
        else:
            for k in range(h, l + 1):
                agents.add(str(k))

    for raw in AGENT_ANY_RE.findall(txt):
        raw = raw.strip()
        if ".." in raw:
            continue
        raw = raw.strip('"').strip("'").strip()
        if raw:
            agents.add(raw)

    if not agents:
        raise ValueError(
            "No agent(...) facts found in matching/i.lp "
            "(expected agent(1)., agent(1..n)., agent(alice). etc)."
        )

    return sorted(agents, key=agent_sort_key)


def display_name(a: str) -> str:
    a = (a or "").strip()
    if not a:
        return a
    if a[0].isalpha():
        return a[0].upper() + a[1:]
    return a


def ui_to_raw(label: str, name_map: dict) -> str:
    label = (label or "").strip()
    return name_map.get(label, label)


# ============================================================
# Atom helpers
# ============================================================

def predicate_name(atom: str) -> str:
    return atom.split("(", 1)[0].strip()


def parse_atom(atom: str) -> Tuple[str, List[str]]:
    pred = predicate_name(atom)
    if "(" not in atom:
        return pred, []
    inside = atom.split("(", 1)[1].rstrip(").")
    args = [a.strip() for a in inside.split(",")] if inside else []
    return pred, args


ROOM_RE = re.compile(r"^\s*room\s*\(\s*([^,\s]+)\s*,\s*([^)]+?)\s*\)\s*$")
R_FACT_ANYWHERE_RE = re.compile(r"\br\s*\(\s*([^,\s]+)\s*,\s*([^)]+?)\s*\)\s*\.\s*", re.I)
VAL_RE = re.compile(r"^val\s*\(\s*([0-9]+)\s*,\s*([0-9]+)\s*\)\s*$", re.I)


def room_atoms_to_pairs(atoms: List[str], ignore_self: bool = True) -> List[Tuple[str, str]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Tuple[str, str]] = []
    for a in atoms:
        m = ROOM_RE.match(a.strip())
        if not m:
            continue
        x, y = m.group(1).strip(), m.group(2).strip()
        if ignore_self and x == y:
            key = (x,x)
            if key not in seen:
                seen.add(key)
                out.append(key)
        key = (x, y) if x < y else (y, x)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def r_facts_to_pairs_from_m_lp(m_lp: Path, ignore_self: bool = True) -> List[Tuple[str, str]]:
    txt = m_lp.read_text(encoding="utf-8")
    seen: Set[Tuple[str, str]] = set()
    out: List[Tuple[str, str]] = []

    for x, y in R_FACT_ANYWHERE_RE.findall(txt):
        x = x.strip().strip('"').strip("'")
        y = y.strip().strip('"').strip("'")

        if ignore_self and x == y:
            continue

        key = (x, y) if agent_sort_key(x) <= agent_sort_key(y) else (y, x)
        if key not in seen:
            seen.add(key)
            out.append(key)

    return out


def extract_val_by_k(atoms: List[str]) -> Dict[int, int]:
    out: Dict[int, int] = {}
    for a in atoms:
        m = VAL_RE.match(a.strip())
        if not m:
            continue
        N = int(m.group(1))
        k = int(m.group(2))
        if k not in out or N < out[k]:
            out[k] = N
    return out


def n_from_i_lp(i_lp: Path) -> int:
    return len(agents_from_i_lp(i_lp))


# ============================================================
# Clingo / matching helpers
# ============================================================

def run_clingo_optimum(common_inputs: List[Path], program_files: List[Path], models: int = 0) -> Tuple[str, List[str], Optional[Tuple[int, ...]]]:
    lp_files = [p.resolve() for p in (common_inputs + program_files)]
    cmd = ["clingo", f"-n{models}", "--opt-strategy=usc", "--outf=2"] + [str(p) for p in lp_files]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)

    if proc.returncode not in (0, 10, 20, 30):
        raise RuntimeError(
            "clingo failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"Exit code: {proc.returncode}\n"
            f"STDERR:\n{proc.stderr}\n"
            f"STDOUT:\n{proc.stdout}\n"
        )

    data = json.loads(proc.stdout)
    result = (data.get("Result") or "").upper()
    call = (data.get("Call") or [{}])[0]
    witnesses = call.get("Witnesses") or []

    if "UNSAT" in result or not witnesses:
        return "UNSAT", [], None

    def cost_vec(w):
        c = w.get("Costs", None)
        if c is None:
            c = w.get("Cost", None)
        if c is None:
            return None
        return tuple(int(x) for x in c)

    best_w = None
    best_cost = None
    for w in witnesses:
        cv = cost_vec(w)
        if cv is None:
            continue
        if best_w is None or cv < best_cost:
            best_w = w
            best_cost = cv

    chosen = best_w if best_w is not None else witnesses[-1]
    atoms = chosen.get("Value") or []

    if "UNKNOWN" in result:
        return "UNKNOWN", atoms, best_cost
    return "SAT", atoms, best_cost


def write_query_fact(q_lp: Path, qtype: str, sign: str, x: str, y: str) -> None:
    q_lp.write_text(f"query({qtype},{sign},({x},{y})).\n", encoding="utf-8")


def write_alt_room_lp(path: Path, pairs: List[Tuple[str, str]], all_agents: List[str]) -> None:
    paired: Set[str] = set()
    lines: List[str] = []

    for x, y in pairs:
        if x == y:
            paired.add(x)
            lines.append(f"roommate({x},{x}).")
            continue
        paired.add(x)
        paired.add(y)
        lines.append(f"roommate({x},{y}).")
        lines.append(f"roommate({y},{x}).")

    for a in all_agents:
        if a not in paired:
            lines.append(f"roommate({a},{a}).")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def satisfaction_for_rec_and_alt(cfg, alt_r_lp: Path) -> Tuple[Optional[int], Optional[int], List[str]]:
    rank = cfg.base_dir / "c-p-rank.lp"
    prefer = cfg.base_dir / "prefer.lp"
    egal = cfg.base_dir / "egal.lp"

    for f in (cfg.m_lp, alt_r_lp, cfg.i_lp, rank, prefer, egal):
        if not f.exists():
            raise FileNotFoundError(f"Missing file needed for satisfaction: {f}")

    status, atoms, cost = run_clingo_optimum(
        common_inputs=[cfg.m_lp, alt_r_lp, cfg.i_lp],
        program_files=[rank, prefer, egal],
        models=1
    )
    if status == "UNSAT":
        return None, None, []

    vals = extract_val_by_k(atoms)
    n = n_from_i_lp(cfg.i_lp)
    n2 = n * n

    sat_rec = (n2 - vals[1]) if 1 in vals else None
    sat_alt = (n2 - vals[2]) if 2 in vals else None

    debug_vals = [a for a in atoms if a.strip().startswith("val(")]
    return sat_rec, sat_alt, debug_vals


def pairs_to_full_matching(pairs: List[Tuple[str, str]], all_agents: List[str]) -> List[Tuple[str, str]]:
    paired = set()
    for x, y in pairs:
        paired.add(x)
        paired.add(y)
    out = list(pairs)
    for a in all_agents:
        if a not in paired:
            out.append((a, a))
    return out


def write_matching_csv(path: Path, pairs: List[Tuple[str, str]], all_agents: List[str], label: str):
    full = pairs_to_full_matching(pairs, all_agents)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["agent1", "agent2"])
        for x, y in sorted(full, key=lambda t: (agent_sort_key(t[0]), agent_sort_key(t[1]))):
            w.writerow([x, y])


def write_metrics_csv(path: Path, categories: List[str], alt_raw: List[float], rec_raw: List[float],
                      sat_alt: Optional[int], sat_rec: Optional[int]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["metric", "alternative_value", "recommended_value"])
        for m, a, r in zip(categories, alt_raw, rec_raw):
            w.writerow([m.replace("\n", " "), a, r])
        w.writerow(["total_satisfaction(alt)", sat_alt if sat_alt is not None else "", ""])
        w.writerow(["total_satisfaction(rec)", "", sat_rec if sat_rec is not None else ""])


# ============================================================
# Styled dialogs
# ============================================================

def _center_modal(win: tk.Toplevel, parent: tk.Widget, width: int, height: int):
    win.update_idletasks()
    px = parent.winfo_rootx()
    py = parent.winfo_rooty()
    pw = parent.winfo_width()
    ph = parent.winfo_height()
    x = px + max(0, (pw - width) // 2)
    y = py + max(0, (ph - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


def ask_yes_no_dynamic(parent, title: str, message: str,
                      yes_text: str = "Yes", no_text: str = "No",
                      min_w: int = 420, min_h: int = 220,
                      max_w: int = 760, max_h: int = 540,
                      wrap_chars: int = 72) -> bool:
    result = {"value": False}

    win = tk.Toplevel(parent, bg=COLORS["bg"])
    win.title(title)
    win.transient(parent)
    win.grab_set()

    f = tkfont.nametofont("TkDefaultFont")
    line_h = f.metrics("linespace") + 2
    char_w = f.measure("0")
    lines = message.splitlines() or [message]
    est_lines = sum(max(1, math.ceil(len(ln) / max(1, wrap_chars))) for ln in lines)
    est_w = int(min(max_w, max(min_w, wrap_chars * char_w + 90)))
    est_h = int(min(max_h, max(min_h, est_lines * line_h + 180)))
    _center_modal(win, parent, est_w, est_h)
    win.minsize(min_w, min_h)

    outer = tk.Frame(win, bg=COLORS["bg"], padx=16, pady=16)
    outer.pack(fill="both", expand=True)

    shadow = tk.Frame(outer, bg=COLORS["shadow"])
    shadow.pack(fill="both", expand=True)

    card = tk.Frame(shadow, bg=COLORS["panel"])
    card.place(x=0, y=0, relwidth=1, relheight=1)

    body = tk.Frame(card, bg=COLORS["panel"], padx=18, pady=18)
    body.pack(fill="both", expand=True)

    tk.Label(body, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=FONT_SUBTITLE).pack(anchor="w", pady=(0, 10))

    txt = tk.Text(body, wrap="word", bg=COLORS["panel"], fg=COLORS["text"], relief="flat", bd=0, height=1, font=FONT_UI)
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", message)
    txt.configure(state="disabled")

    btns = tk.Frame(body, bg=COLORS["panel"])
    btns.pack(fill="x", pady=(14, 0))

    def choose(v: bool):
        result["value"] = v
        win.destroy()

    ttk.Button(btns, text=no_text, command=lambda: choose(False)).pack(side="right")
    ttk.Button(btns, text=yes_text, style="Primary.TButton", command=lambda: choose(True)).pack(side="right", padx=(0, 8))

    win.protocol("WM_DELETE_WINDOW", lambda: choose(False))
    win.wait_window()
    return result["value"]


def ask_option_1_2_dynamic(parent, title: str, message: str,
                           option1: str = "Option 1", option2: str = "Option 2",
                           min_w: int = 480, min_h: int = 250,
                           max_w: int = 800, max_h: int = 560,
                           wrap_chars: int = 72) -> int:
    result = {"value": 0}

    win = tk.Toplevel(parent, bg=COLORS["bg"])
    win.title(title)
    win.transient(parent)
    win.grab_set()

    f = tkfont.nametofont("TkDefaultFont")
    line_h = f.metrics("linespace") + 2
    char_w = f.measure("0")
    lines = message.splitlines() or [message]
    est_lines = sum(max(1, math.ceil(len(ln) / max(1, wrap_chars))) for ln in lines)
    est_w = int(min(max_w, max(min_w, wrap_chars * char_w + 90)))
    est_h = int(min(max_h, max(min_h, est_lines * line_h + 210)))
    _center_modal(win, parent, est_w, est_h)
    win.minsize(min_w, min_h)

    outer = tk.Frame(win, bg=COLORS["bg"], padx=16, pady=16)
    outer.pack(fill="both", expand=True)

    shadow = tk.Frame(outer, bg=COLORS["shadow"])
    shadow.pack(fill="both", expand=True)

    card = tk.Frame(shadow, bg=COLORS["panel"])
    card.place(x=0, y=0, relwidth=1, relheight=1)

    body = tk.Frame(card, bg=COLORS["panel"], padx=18, pady=18)
    body.pack(fill="both", expand=True)

    tk.Label(body, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=FONT_SUBTITLE).pack(anchor="w", pady=(0, 10))

    txt = tk.Text(body, wrap="word", bg=COLORS["panel"], fg=COLORS["text"], relief="flat", bd=0, height=1, font=FONT_UI)
    txt.pack(fill="both", expand=True)
    txt.insert("1.0", message)
    txt.configure(state="disabled")

    btns = tk.Frame(body, bg=COLORS["panel"])
    btns.pack(fill="x", pady=(14, 0))

    def choose(v: int):
        result["value"] = v
        win.destroy()

    ttk.Button(btns, text=option2, command=lambda: choose(2)).pack(side="right")
    ttk.Button(btns, text=option1, style="Primary.TButton", command=lambda: choose(1)).pack(side="right", padx=(0, 8))

    win.protocol("WM_DELETE_WINDOW", lambda: choose(0))
    win.wait_window()
    return result["value"]


# ============================================================
# Original chart preserved
# ============================================================

class FiveMetricStackedByMatching(ttk.Frame):
    """
    5 categories on X.
    Each category is one bar stacked into [alternative, recommended].
    """
    def __init__(self, parent, height=360):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, bg="white", highlightthickness=0, height=height)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda e: self.redraw())

        self.categories: List[str] = []
        self.alt_vals: List[float] = []
        self.rec_vals: List[float] = []

        self.color_alt = COLORS["chart_alt"]
        self.color_rec = COLORS["chart_rec"]
        self.title = " "

        self._rect_meta: Dict[int, Dict[str, Any]] = {}

        self._tip = tk.Toplevel(self)
        self._tip.withdraw()
        self._tip.overrideredirect(True)
        self._tip_label = ttk.Label(self._tip, text="", padding=6)
        self._tip_label.pack()
        self.canvas.bind("<Motion>", self._on_move)
        self.canvas.bind("<Leave>", lambda e: self._hide_tip())

    def set_data(self, categories: List[str], alt_raw: List[float], rec_raw: List[float], title: str = None):
        if not (len(categories) == len(alt_raw) == len(rec_raw)):
            raise ValueError("categories, alt_raw, rec_raw must have same length")
        self.categories = categories
        self.alt_vals = [float(x) for x in alt_raw]
        self.rec_vals = [float(x) for x in rec_raw]
        if title is not None:
            self.title = title
        self.redraw()

    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._rect_meta.clear()

        w = max(10, c.winfo_width())
        h = max(10, c.winfo_height())

        left = 70
        right = 20
        top = 35
        bottom = 85

        plot_w = max(10, w - left - right)
        plot_h = max(10, h - top - bottom)

        c.create_text(left, 12, anchor="nw", text=self.title,
                      fill=COLORS["text"], font=(FONT_FAMILY, 11, "bold"))

        ticks = [0, 25, 50, 75, 100]
        for t in ticks:
            y = top + plot_h * (1 - t / 100.0)
            c.create_line(left, y, left + plot_w, y, fill="#E5E7EB")
            c.create_text(left - 8, y, anchor="e", text=f"{t}%", fill=COLORS["text"], font=(FONT_FAMILY, 9))

        c.create_text(18, top + plot_h / 2, text="Percentages", angle=90,
                      fill=COLORS["text"], font=(FONT_FAMILY, 10, "bold"))

        n = len(self.categories)
        if n == 0:
            c.create_text(left + plot_w / 2, top + plot_h / 2, text="No data yet!",
                          fill=COLORS["muted"], font=FONT_UI)
            return

        group_w = plot_w / n
        bar_w = min(56, group_w * 0.55)

        def y_for(pct: float) -> float:
            pct = max(0.0, min(100.0, pct))
            return top + plot_h * (1 - pct / 100.0)

        y_base = top + plot_h

        for i, cat in enumerate(self.categories):
            cx = left + group_w * (i + 0.5)
            x0 = cx - bar_w / 2
            x1 = cx + bar_w / 2

            alt = self.alt_vals[i]
            rec = self.rec_vals[i]
            s = alt + rec

            if s <= 0:
                alt_pct = rec_pct = 0.0
            else:
                alt_pct = alt * 100.0 / s
                rec_pct = rec * 100.0 / s

            y_rec_top = y_for(rec_pct)
            rect_rec = c.create_rectangle(x0, y_rec_top, x1, y_base, fill=self.color_rec, outline="white")
            self._rect_meta[rect_rec] = {
                "category": cat,
                "part": "Recommended",
                "raw": rec,
                "total": s
            }

            y_alt_top = y_for(alt_pct + rec_pct)
            rect_alt = c.create_rectangle(x0, y_alt_top, x1, y_rec_top, fill=self.color_alt, outline="white")
            self._rect_meta[rect_alt] = {
                "category": cat,
                "part": "Alternative",
                "raw": alt,
                "total": s
            }

            c.create_rectangle(x0, top, x1, y_base, outline="#E5E7EB")
            c.create_text(cx, y_base + 18, text=cat, fill=COLORS["text"],
                          font=(FONT_FAMILY, 9), width=int(group_w * 0.95))

        leg_y = top + plot_h + 50
        leg_x = left + 10
        c.create_rectangle(leg_x, leg_y, leg_x + 14, leg_y + 14, fill=self.color_alt, outline="")
        c.create_text(leg_x + 20, leg_y + 7, anchor="w", text="alternative matching",
                      fill=COLORS["secondary"], font=(FONT_FAMILY, 9))

        leg_x2 = leg_x + 190
        c.create_rectangle(leg_x2, leg_y, leg_x2 + 14, leg_y + 14, fill=self.color_rec, outline="")
        c.create_text(leg_x2 + 20, leg_y + 7, anchor="w", text="recommended matching",
                      fill=COLORS["secondary"], font=(FONT_FAMILY, 9))

    def _on_move(self, event):
        item = self.canvas.find_withtag("current")
        if not item:
            self._hide_tip()
            return
        iid = item[0]
        meta = self._rect_meta.get(iid)
        if not meta:
            self._hide_tip()
            return

        pct = (meta["raw"] * 100 / meta["total"]) if meta["total"] > 0 else 0
        self._show_tip(
            event.x_root,
            event.y_root,
            f"{meta['category']}\n{meta['part']}: {meta['raw']} ({pct:.1f}%)"
        )

    def _show_tip(self, x, y, text):
        self._tip_label.config(text=text)
        self._tip.geometry(f"+{x + 12}+{y + 12}")
        self._tip.deiconify()

    def _hide_tip(self):
        self._tip.withdraw()


# ============================================================
# Stats
# ============================================================

AgentId = str
Criterion = str


@dataclass
class AgentData:
    agent: AgentId
    f: Dict[Criterion, int]
    w: Dict[Criterion, int]


@dataclass
class DiversityInfo:
    dept: Dict[AgentId, str]
    clazz: Dict[AgentId, str]


CHOICES = {
    "sleep": ["Early", "Before Midnight", "After Midnight"],
    "cleanliness": ["Clean", "Messy"],
    "smoking": ["Non-smoker", "Smoker"],
    "environment": ["Quiet", "Combination", "Social"],
    "study": ["InRoom", "OutRoom", "InAndOut"],
}

ALIASES = {
    "sleep": {
        "early": "Early",
        "goes to bed early": "Early",
        "before midnight": "Before Midnight",
        "after midnight": "After Midnight",
    },
    "cleanliness": {
        "i prefer to live in a clean place.": "Clean",
        "i prefer to live in a clean place": "Clean",
        "clean": "Clean",
        "messy": "Messy",
        "i prefer to live in a messy place.": "Messy",
        "i prefer to live in a messy place": "Messy",
    },
    "smoking": {
        "yes": "Smoker",
        "no": "Non-smoker",
        "smoker": "Smoker",
        "non-smoker": "Non-smoker",
    },
    "environment": {
        "quiet": "Quiet",
        "social": "Social",
        "a combination of social and quiet": "Combination",
        "combination": "Combination",
    },
    "study": {
        "in my room": "InRoom",
        "outside of my room": "OutRoom",
        "out of my room": "OutRoom",
        "both inside and outside of my room": "InAndOut",
        "both": "InAndOut",
    }
}


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _to_choice_index(crit: str, raw: str) -> int:
    key = _norm(raw)
    if key in ALIASES[crit]:
        canonical = ALIASES[crit][key]
    else:
        canonical = None
        for k, v in ALIASES[crit].items():
            if k and k in key:
                canonical = v
                break
        if canonical is None:
            raise ValueError(f"Unknown value for {crit}: {raw!r}. Add it to ALIASES['{crit}'].")
    return CHOICES[crit].index(canonical) + 1


def load_agents_from_questionnaire_csv(path: str) -> Tuple[Dict[str, AgentData], DiversityInfo]:
    agents: Dict[str, AgentData] = {}
    dept: Dict[str, str] = {}
    clazz: Dict[str, str] = {}

    with open(path, newline="", encoding="utf-8-sig") as f:
        rdr = csv.DictReader(f)
        class_keys = ["Class", "Year", "ClassYear", "Grade"]

        for row in rdr:
            a = str(row.get("Username", "")).strip()
            if not a:
                continue

            dept[a] = str(row.get("Department", "")).strip()
            ck = next((k for k in class_keys if k in row), None)
            clazz[a] = str(row.get(ck, "")).strip() if ck else ""

            f_map = {
                "sleep": _to_choice_index("sleep", row.get("SleepHabits", "")),
                "cleanliness": _to_choice_index("cleanliness", row.get("Cleanliness", "")),
                "smoking": _to_choice_index("smoking", row.get("Are you a smoker?", "")),
                "environment": _to_choice_index("environment", row.get("RoomEnvironment", "")),
                "study": _to_choice_index("study", row.get("StudyHabits", "")),
            }
            w_map = {
                "sleep": int(row.get("ImportanceSleepHabits", 0) or 0),
                "cleanliness": int(row.get("ImportanceCleanliness", 0) or 0),
                "smoking": int(row.get("ImportanceSmokingHabits", 0) or 0),
                "environment": int(row.get("ImportanceRoomEnvironment", 0) or 0),
                "study": int(row.get("ImportanceStudyHabits", 0) or 0),
            }
            agents[a] = AgentData(agent=a, f=f_map, w=w_map)

    return agents, DiversityInfo(dept=dept, clazz=clazz)


CRITERIA_ORDER = ["sleep", "cleanliness", "smoking", "environment", "study"]


def sorted_profile_groups(x: AgentData) -> List[List[str]]:
    buckets: Dict[int, List[str]] = {}
    for crit in CRITERIA_ORDER:
        w = int(x.w.get(crit, 0))
        if w > 0:
            buckets.setdefault(w, []).append(crit)
    groups: List[List[str]] = []
    for w in sorted(buckets.keys(), reverse=True):
        groups.append(sorted(buckets[w]))
    return groups


def H(x: AgentData, y: AgentData) -> Tuple[int, ...]:
    spx = sorted_profile_groups(x)
    out: List[int] = []
    for group in spx:
        cnt = 0
        for crit in group:
            if int(x.f.get(crit, -999)) == int(y.f.get(crit, -1000)):
                cnt += 1
        out.append(cnt)
    return tuple(out)


def vec_add(a: Tuple[int, ...], b: Tuple[int, ...]) -> Tuple[int, ...]:
    n = max(len(a), len(b))
    aa = [a[i] if i < len(a) else 0 for i in range(n)]
    bb = [b[i] if i < len(b) else 0 for i in range(n)]
    return tuple(aa[i] + bb[i] for i in range(n))


def H_sym(x: AgentData, y: AgentData) -> Tuple[int, ...]:
    return vec_add(H(x, y), H(y, x))


def total_habitual_sym(pairs: List[Tuple[str, str]], agents: Dict[str, AgentData]) -> Tuple[int, ...]:
    total: Tuple[int, ...] = tuple()
    for a, b in pairs:
        if a not in agents or b not in agents:
            continue
        total = vec_add(total, H_sym(agents[a], agents[b]))
    return total


def diversity_counts(pairs: List[Tuple[str, str]], div: DiversityInfo) -> Tuple[int, int]:
    dept_diff = 0
    class_diff = 0
    for x, y in pairs:
        dx, dy = div.dept.get(x, ""), div.dept.get(y, "")
        cx, cy = div.clazz.get(x, ""), div.clazz.get(y, "")
        if dx and dy and dx != dy:
            dept_diff += 1
        if cx and cy and cx != cy:
            class_diff += 1
    return dept_diff, class_diff


def compute_chart_metrics_for_two_matchings(
    pairs_rec: List[Tuple[str, str]],
    pairs_alt: List[Tuple[str, str]],
    agents: Dict[str, AgentData],
    div: DiversityInfo,
    sat_rec: Optional[int],
    sat_alt: Optional[int],
) -> Tuple[List[str], List[float], List[float]]:
    Hrec = total_habitual_sym(pairs_rec, agents)
    Halt = total_habitual_sym(pairs_alt, agents)

    def h_at(v: Tuple[int, ...], i: int) -> int:
        return v[i] if i < len(v) else 0

    drec_dept, _ = diversity_counts(pairs_rec, div)
    dalt_dept, _ = diversity_counts(pairs_alt, div)

    categories = [
        "total\nsatisfaction",
        "diversity\n(department)",
        "habitual\ncompatibility 1",
        "habitual\ncompatibility 2",
        "habitual\ncompatibility 3",
    ]

    rec_raw = [
        float(sat_rec or 0),
        float(drec_dept),
        float(h_at(Hrec, 0)),
        float(h_at(Hrec, 1)),
        float(h_at(Hrec, 2)),
    ]
    alt_raw = [
        float(sat_alt or 0),
        float(dalt_dept),
        float(h_at(Halt, 0)),
        float(h_at(Halt, 1)),
        float(h_at(Halt, 2)),
    ]
    return categories, alt_raw, rec_raw


# ============================================================
# UI helpers
# ============================================================

def add_hover_to_card(card: tk.Widget, normal_bg: str, hover_bg: str):
    def set_recursive_bg(widget: tk.Widget, color: str):
        try:
            if widget.cget("bg") in (normal_bg, hover_bg):
                widget.configure(bg=color)
        except Exception:
            return
        for child in widget.winfo_children():
            set_recursive_bg(child, color)

    def on_enter(_):
        set_recursive_bg(card, hover_bg)

    def on_leave(_):
        set_recursive_bg(card, normal_bg)

    card.bind("<Enter>", on_enter)
    card.bind("<Leave>", on_leave)
    for child in card.winfo_children():
        child.bind("<Enter>", on_enter)
        child.bind("<Leave>", on_leave)

def add_primary_hover(widget):
    # Standard Blue (Matches your COLORS["primary"])
    normal_bg = "#2563EB" 
    # Darker Blue for Hover (Matches your COLORS["primary_dark"])
    hover_bg = "#1D4ED8"   

    def on_enter(e):
        if widget["state"] == "normal": # Only hover if button is active
            widget.configure(background=hover_bg)

    def on_leave(e):
        if widget["state"] == "normal":
            widget.configure(background=normal_bg)

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

    # Initial Blue Setup
    widget.configure(
        background=normal_bg,
        foreground="white",
        relief="flat",
        borderwidth=0,
        cursor="hand2"
    )
def add_exit_hover(widget):
    # Match these to your COLORS dictionary
    quiet_bg = "#FFFFFF"  # Pure white to match your card
    quiet_fg = "#64748B"  # Muted slate
    
    danger_bg = "#FEE2E2" # Soft Red
    danger_fg = "#B91C1C" # Strong Red

    def on_enter(e):
        widget.configure(background=danger_bg, foreground=danger_fg)

    def on_leave(e):
        widget.configure(background=quiet_bg, foreground=quiet_fg)

    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)

    # Initial setup
    widget.configure(
        background=quiet_bg, 
        foreground=quiet_fg, 
        activebackground=danger_bg,
        activeforeground=danger_fg,
        cursor="hand2",
        relief="flat",
        borderwidth=0
    )

def add_focus_highlight(widget):
    def on_focus(_):
        try:
            widget.configure(style="Focus.TCombobox")
        except Exception:
            pass

    def on_blur(_):
        try:
            widget.configure(style="TCombobox")
        except Exception:
            pass

    widget.bind("<FocusIn>", on_focus)
    widget.bind("<FocusOut>", on_blur)

def make_card(parent, title: str, subtitle: Optional[str] = None, padx=14, pady=12):
    outer = tk.Frame(parent, bg=COLORS["bg"])
    card = tk.Frame(
        outer,
        bg=COLORS["panel"],
        highlightbackground=COLORS["border"],
        highlightthickness=0
    )
    card.pack(fill="both", expand=True)
    add_hover_to_card(card, "#ffffff", "#f1f5f9")
    head = tk.Frame(card, bg=COLORS["panel"])
    head.pack(fill="x", padx=padx, pady=(pady, 0))

    tk.Label(head, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=FONT_SUBTITLE).pack(anchor="w")
    if subtitle:
        tk.Label(head, text=subtitle, bg=COLORS["panel"], fg=COLORS["secondary"], font=FONT_SMALL).pack(anchor="w", pady=(4, 0))

    body = tk.Frame(card, bg=COLORS["panel"])
    body.pack(fill="both", expand=True, padx=padx, pady=(10, pady))
    return outer, body

def make_shadow_card(parent, title: str, subtitle: Optional[str] = None, padx=16, pady=14):
    outer = tk.Frame(parent, bg=COLORS["bg"])
    shadow = tk.Frame(outer, bg=COLORS["shadow"])
    shadow.pack(fill="both", expand=True, padx=3, pady=3)

    card = tk.Frame(shadow, bg=COLORS["panel"], highlightbackground=COLORS["border"], highlightthickness=1)
    card.pack(fill="both", expand=True)
    add_hover_to_card(card, COLORS["panel"], COLORS["hover"])
    head = tk.Frame(card, bg=COLORS["panel"])
    head.pack(fill="x", padx=padx, pady=(pady, 0))

    tk.Label(head, text=title, bg=COLORS["panel"], fg=COLORS["text"], font=FONT_SUBTITLE).pack(anchor="w")
    if subtitle:
        tk.Label(head, text=subtitle, bg=COLORS["panel"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w", pady=(4, 0))

    body = tk.Frame(card, bg=COLORS["panel"])
    body.pack(fill="both", expand=True, padx=padx, pady=(10, pady))

    return outer, body
    
def create_modern_dropdown(parent, variable, options, command=None):
    # 1. Create a Menubutton (Standard widget = full color control)
    menu_btn = tk.Menubutton(
        parent, 
        textvariable=variable, 
        relief="flat",
        bg="white",
        fg=COLORS["text"],
        activebackground=COLORS["hover"],
        activeforeground=COLORS["primary"],
        font=("Inter", 10),
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        padx=10,
        pady=6,
        indicatoron=True, # Shows the small arrow
        direction="below",
        cursor="hand2"
    )

    # 2. Create the actual menu that pops up
    menu = tk.Menu(menu_btn, tearoff=0, bg="white", fg=COLORS["text"], font=("Inter", 10), relief="flat", bd=1)
    
    for opt in options:
        menu.add_command(
            label=opt, 
            command=lambda v=opt: [variable.set(v), command(None) if command else None]
        )
    
    menu_btn["menu"] = menu
    return menu_btn

def center_window(win, w, h):
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    x = max(0, (sw - w) // 2)
    y = max(0, (sh - h) // 2)
    win.geometry(f"{w}x{h}+{x}+{y}")


# ============================================================
# GUI
# ============================================================

@dataclass
class FileConfig:
    i_lp: Path
    m_lp: Path
    base_dir: Path
    csv_path: Optional[Path]


HOW_MAPS_TO_TYPE = "best"
PHRASES_FOR_WHY = ["is matched with", "is not matched with"]
PHRASES_FOR_WHATIF = ["is matched with", "is not matched with", "is single", "is not single"]


class App(tk.Tk):
    def __init__(self, input_dir: str | Path | None = None):
        super().__init__()
        self.input_dir = Path(input_dir) if input_dir else None        
        self.title("E-SRTI-ASP")
        center_window(self, 1200, 840)
        self.minsize(1020, 720)
        self.configure(bg=COLORS["bg"])

        self.nouns: List[str] = []
        self.name_map = {}

        self.csv_agents: Dict[str, AgentData] = {}
        self.csv_div: Optional[DiversityInfo] = None
        self.last_recommended_atoms: List[str] = []
        self.last_alternative_atoms: List[str] = []
        self.last_pairs_rec = []
        self.last_pairs_alt = []
        self.last_sat_rec = None
        self.last_sat_alt = None
        self.last_metrics = None

        self.status_var = tk.StringVar(value="Ready.")
        #self._setup_styles()
        self._build_ui()

        try:
            self._load_default_inputs()
        except Exception as e:
            messagebox.showerror("Startup error", str(e))
            self._set_status("Failed to load data from matching/ and rules/.")

        self.show_welcome_modal()
        self._sync_controls()

    # ---------- styles

    def _setup_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TFrame", background=COLORS["danger"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"], font=FONT_UI)
        style.configure("TEntry", padding=8)
        #style.configure("TCombobox",padding=6)
        style.configure("TCombobox", relief="flat", padding=6)

        style.configure("Focus.TCombobox", padding=6)

        style.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8), font=FONT_UI)

        style.configure("Primary.TButton", font=FONT_UI_BOLD, padding=(18, 11), borderwidth=0)
        style.map(
            "Primary.TButton",
            foreground=[("disabled", "#ffffff"), ("!disabled", "#ffffff")],
            background=[
                ("disabled", "#94A3B8"),
                ("active", COLORS["primary_dark"]),
                ("!disabled", COLORS["primary"]),
            ],
        )
        style.map("TCombobox", fieldbackground=[('readonly','white')])
        style.map("TCombobox", selectbackground=[('readonly', 'white')])
        style.map("TCombobox", selectforeground=[('readonly', 'black')])

        style.configure("Ghost.TButton", background="#FEE2E2", foreground="#991B1B",font=FONT_UI, padding=(16, 11))

    # ---------- auto config

    def _auto_cfg(self, input_dir: str | Path | None = None) -> FileConfig:
        selected_input_dir = input_dir if input_dir is not None else self.input_dir
        matching_dir = Path(selected_input_dir) if selected_input_dir else Path.cwd() / "matching"
        rules_dir = Path.cwd() / "rules"

        if not matching_dir.exists():
            raise FileNotFoundError(f"The folder '{matching_dir}' was not found.")
        if not rules_dir.exists():
            raise FileNotFoundError("The folder 'rules' was not found next to this program.")

        i_lp = matching_dir / "i.lp"
        m_lp = matching_dir / "M.lp"

        if not i_lp.exists():
            raise FileNotFoundError(f"Missing file: {i_lp}")
        if not m_lp.exists():
            raise FileNotFoundError(f"Missing file: {m_lp}")

        csv_candidates = sorted(matching_dir.glob("*.csv"))
        csv_path = csv_candidates[0] if csv_candidates else None

        return FileConfig(
            i_lp=i_lp,
            m_lp=m_lp,
            base_dir=rules_dir,
            csv_path=csv_path,
        )

    def _cfg(self) -> FileConfig:
        return self._auto_cfg(self.input_dir)

    def _load_default_inputs(self):
        cfg = self._cfg()

        nouns = agents_from_i_lp(cfg.i_lp)
        self.nouns = nouns
        self.name_map = {display_name(n): n for n in nouns}

        pretty = list(self.name_map.keys())
        pretty.sort(key=lambda s: s.lower())

        self.x_cb["values"] = pretty
        self.y_cb["values"] = pretty

        if pretty:
            self.x_var.set(pretty[0])
            self.y_var.set(pretty[1] if len(pretty) > 1 else pretty[0])

        add_focus_highlight(self.type_cb)
        add_focus_highlight(self.phrase_cb)
        add_focus_highlight(self.x_cb)
        add_focus_highlight(self.y_cb)

        if cfg.csv_path is not None and cfg.csv_path.exists():
            try:
                agents, div = load_agents_from_questionnaire_csv(str(cfg.csv_path))
                self.csv_agents = agents
                self.csv_div = div
                self._set_status(f"Loaded matching/ and rules/ · {len(pretty)} students · CSV found")
            except Exception:
                self.csv_agents = {}
                self.csv_div = None
                self._set_status(f"Loaded matching/ and rules/ · {len(pretty)} students · CSV failed")
        else:
            self.csv_agents = {}
            self.csv_div = None
            self._set_status(f"Loaded matching/ and rules/ · {len(pretty)} students")

    def _set_explain_state(self, enabled: bool):
        if not hasattr(self, "explain_btn"):
            return

        if enabled:
            self.explain_btn.configure(
                state="normal",
                bg=COLORS["primary"],      # Vibrant Blue (#2563EB)
                fg="white",
                cursor="hand2"
            )
        else:
            self.explain_btn.configure(
                state="disabled",
                bg="#E2E8F0",              # Soft Gray border color
                fg="#94A3B8",              # Muted Slate text
                cursor="arrow"             # Stop showing the "hand"
            )
    # ---------- UI

    def _build_ui(self):
        container = tk.Frame(self, bg=COLORS["bg"], padx=20, pady=20)
        container.pack(fill="both", expand=True)

        header = tk.Frame(container, bg=COLORS["bg"])
        header.pack(fill="x", pady=(0, 14))

        top = tk.Frame(container, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 14))
        top.grid_columnconfigure(0, weight=1)

        qc_card, qc = make_shadow_card(
            top,
            "Query Builder",
            "Choose a query and click Explain to generate an explanation."
        )
        qc_card.grid(row=0, column=0, sticky="ew")
        qc.grid_columnconfigure(1, weight=1)
        qc.grid_columnconfigure(3, weight=1)

        self.type_var = tk.StringVar(value="why")
        self.phrase_var = tk.StringVar(value="is matched with")
        self.x_var = tk.StringVar(value="")
        self.y_var = tk.StringVar(value="")
        
        tk.Label(qc, text="Type", bg=COLORS["panel"], fg=COLORS["text"], font=FONT_UI).grid(row=0, column=0, sticky="w", padx=4, pady=8)
        self.type_cb = ttk.Combobox(qc, textvariable=self.type_var, values=["why", "whatif", "fairness"], state="readonly")
        self.type_cb.grid(row=0, column=1, sticky="ew", padx=4, pady=8)
        self.type_cb.bind("<<ComboboxSelected>>", lambda e: self._sync_controls())

        tk.Label(qc, text="Condition", bg=COLORS["panel"], fg=COLORS["text"], font=FONT_UI).grid(row=0, column=2, sticky="w", padx=4, pady=8)
        self.phrase_cb = ttk.Combobox(qc, textvariable=self.phrase_var, values=PHRASES_FOR_WHATIF, state="readonly")
        self.phrase_cb.grid(row=0, column=3, sticky="ew", padx=4, pady=8)
        self.phrase_cb.bind("<<ComboboxSelected>>", lambda e: self._sync_controls())

        tk.Label(qc, text="Student", bg=COLORS["panel"], fg=COLORS["text"], font=FONT_UI).grid(row=1, column=0, sticky="w", padx=4, pady=8)
        self.x_cb = ttk.Combobox(qc, textvariable=self.x_var, values=[], state="readonly")
        self.x_cb.grid(row=1, column=1, sticky="ew", padx=4, pady=8)

        tk.Label(qc, text="Student", bg=COLORS["panel"], fg=COLORS["text"], font=FONT_UI).grid(row=1, column=2, sticky="w", padx=4, pady=8)
        self.y_cb = ttk.Combobox(qc, textvariable=self.y_var, values=[], state="readonly")
        self.y_cb.grid(row=1, column=3, sticky="ew", padx=4, pady=8)

        self.preview_nl = tk.StringVar(value="")
        self.preview_asp = tk.StringVar(value="")
        self.preview_q_path = tk.StringVar(value="")

        actions = tk.Frame(qc, bg=COLORS["panel"])
        actions.grid(row=3, column=0, columnspan=4, sticky="w", padx=4, pady=(8, 0))


        self.explain_btn = tk.Button(
            actions, 
            text="Explain", 
            command=self._run,
            font=("Inter", 10, "bold"),
            padx=20,
            pady=8
        )
        self.explain_btn.pack(side="left")
        # USE THE BLUE HOVER HERE
        add_primary_hover(self.explain_btn) 

        # --- EXIT BUTTON (Ghost/Red) ---
        exit_btn = tk.Button(
            actions, 
            text="Exit", 
            command=self._exit_flow,
            font=("Inter", 10),
            padx=20,
            pady=8
        )
        exit_btn.pack(side="left", padx=(12, 0))
        # USE THE RED HOVER HERE
        add_exit_hover(exit_btn)



        self.nb = ttk.Notebook(container)
        self.nb.pack(fill="both", expand=True)

        self.tab_results = tk.Frame(self.nb, bg=COLORS["bg"])
        self.tab_stats = tk.Frame(self.nb, bg=COLORS["bg"])
        self.nb.add(self.tab_results, text="Explanation")
        self.nb.add(self.tab_stats, text="Visual Summary")

        results_card, results_body = make_shadow_card(self.tab_results, " ")
        results_card.pack(fill="both", expand=True, padx=2, pady=2)

        self.out_text = tk.Text(
            results_body,
            wrap="word",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            relief="flat",
            bd=0,
            padx=6,
            pady=6,
            font=FONT_UI,
            insertbackground=COLORS["text"],
            spacing1=4,
            spacing3=6
        )
        self.out_text.pack(fill="both", expand=True)

        self.out_text.tag_configure("title", font=FONT_RESULT_TITLE, foreground=COLORS["text"], spacing1=6, spacing3=10)
        self.out_text.tag_configure("subtitle", font=FONT_SUBTITLE, foreground=COLORS["primary"], spacing1=8, spacing3=6)
        self.out_text.tag_configure("success", foreground="#166534")
        self.out_text.tag_configure("warning", foreground="#B45309")
        self.out_text.tag_configure("error", foreground=COLORS["danger"])
        self.out_text.tag_configure("muted", foreground=COLORS["muted"])
        self.out_text.tag_configure("bullet", lmargin1=18, lmargin2=32)
        self.out_text.tag_configure("spacer", spacing1=6, spacing3=6)

        stats_card, stats_body = make_shadow_card(
            self.tab_stats,
            "Visual Summary",
            "A comparison of the recommended and alternative matchings with respect to habitual compatibility."
        )
        stats_card.pack(fill="both", expand=True, padx=2, pady=2)

        self.eval_chart = FiveMetricStackedByMatching(stats_body, height=430)
        self.eval_chart.pack(fill="both", expand=True)

        status = tk.Frame(container, bg=COLORS["bg"])
        status.pack(fill="x", pady=(12, 0))
        tk.Frame(status, bg=COLORS["border"], height=1).pack(fill="x", pady=(0, 8))
        tk.Label(status, textvariable=self.status_var, bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL, anchor="w").pack(fill="x")

    # ---------- logging

    def _clear(self):
        self.out_text.delete("1.0", "end")

    def _log(self, txt: str):
        self.out_text.insert("end", txt + "\n")
        self.out_text.see("end")

    def _log_title(self, txt: str):
        self.out_text.insert("end", txt + "\n", "title")
        self.out_text.see("end")

    def _log_subtitle(self, txt: str):
        self.out_text.insert("end", txt + "\n", "subtitle")
        self.out_text.see("end")

    def _log_success(self, txt: str):
        self.out_text.insert("end", txt + "\n", "success")
        self.out_text.see("end")

    def _log_warning(self, txt: str):
        self.out_text.insert("end", txt + "\n", "warning")
        self.out_text.see("end")

    def _log_error(self, txt: str):
        self.out_text.insert("end", txt + "\n", "error")
        self.out_text.see("end")

    def _log_bullet(self, txt: str):
        self.out_text.insert("end", f"• {txt}\n", "bullet")
        self.out_text.see("end")

    def _spacer(self):
        self.out_text.insert("end", "\n", "spacer")
        self.out_text.see("end")

    def _set_status(self, s: str):
        self.status_var.set(s)
        self.update_idletasks()

    def _log_rooms(self, atoms: List[str],cfg: FileConfig):
        new_pairs = room_atoms_to_pairs(atoms)
        pairs=r_facts_to_pairs_from_m_lp(cfg.m_lp)
        if not new_pairs:
            self._log_warning("No roommate pairs found.")
            return

        self._log_subtitle("Roommate pairs")
        for x, y in new_pairs:
            if (x,y) not in pairs:
                self._log_bullet(f"{display_name(x)} ↔ {display_name(y)}")

    # ---------- welcome

    def show_welcome_modal(self):
        win = tk.Toplevel(self, bg=COLORS["bg"])
        win.title("Welcome")
        win.transient(self)
        win.grab_set()
        _center_modal(win, self, 600, 370)
        win.resizable(False, False)

        outer = tk.Frame(win, bg=COLORS["bg"], padx=16, pady=16)
        outer.pack(fill="both", expand=True)

        shadow = tk.Frame(outer, bg=COLORS["shadow"])
        shadow.pack(fill="both", expand=True)

        card = tk.Frame(shadow, bg=COLORS["panel"])
        card.place(x=0, y=0, relwidth=1, relheight=1)

        body = tk.Frame(card, bg=COLORS["panel"], padx=22, pady=20)
        body.pack(fill="both", expand=True)

        tk.Label(
            body,
            text="Roommate Matching Explanation Tool",
            bg=COLORS["panel"],
            fg=COLORS["primary"],
            font=(FONT_FAMILY, 14, "bold")
        ).pack(anchor="center", pady=(0, 12))

        tk.Label(
            body,
            text="This tool explains roommate matchings using files loaded automatically from the matching and rules folders.",
            bg=COLORS["panel"],
            fg=COLORS["text"],
            justify="center",
            wraplength=520,
            font=FONT_UI
        ).pack(anchor="center", pady=(0, 14))

        bullets = [
            "Explain why two students are matched or not matched",
            "Try what-if scenarios to see alternative matchings",
            "See why no solution exists, and explore good-enough matchings",
            "See how good a matching is",
            "Compare recommended and alternative matchings visually",
        ]

        bullet_wrap = tk.Frame(body, bg=COLORS["panel"])
        bullet_wrap.pack(fill="x", pady=(0, 14))
        for b in bullets:
            tk.Label(
                bullet_wrap,
                text=f"• {b}",
                bg=COLORS["panel"],
                fg=COLORS["text"],
                anchor="w",
                justify="left",
                font=FONT_UI
            ).pack(anchor="w", pady=2)

        tk.Label(
            body,
            text="The tool reads instance files from matching/ and rule files from rules/.",
            bg=COLORS["panel"],
            fg=COLORS["muted"],
            font=FONT_SMALL
        ).pack(anchor="w", pady=(0, 14))

        btns = tk.Frame(body, bg=COLORS["panel"])
        btns.pack(fill="x")

        def close():
            win.grab_release()
            win.destroy()

        ttk.Button(btns, text="Let’s start", style="Primary.TButton", command=close).pack(side="right")
        win.protocol("WM_DELETE_WINDOW", close)
        self.wait_window(win)

    # ---------- query sync

    def _sync_controls(self):
        if not hasattr(self, "explain_btn"):
            return
        qtype_ui = self.type_var.get().strip().lower()
        phrase = self.phrase_var.get().strip().lower()

        allowed = PHRASES_FOR_WHY if qtype_ui == "why" else PHRASES_FOR_WHATIF
        self.phrase_cb["values"] = allowed
        if phrase not in allowed:
            self.phrase_var.set(allowed[0])
            phrase = allowed[0]

        try:
            cfg = self._cfg()
            #self.preview_q_path.set(str(default_generated_q_path(cfg.i_lp)))
        except Exception:
            self.preview_q_path.set("")

        if qtype_ui == "fairness":
            self.phrase_cb.configure(state="disabled")
            self.x_cb.configure(state="disabled")
            self.y_cb.configure(state="disabled")
            #self.preview_nl.set("How fair is this matching?")
            #self.preview_asp.set(f"query({HOW_MAPS_TO_TYPE},pos,(none,none)).")
            self.explain_btn.configure(state="normal")
            return

        self.phrase_cb.configure(state="readonly")

        if not self.nouns:
            self.x_cb.configure(state="disabled")
            self.y_cb.configure(state="disabled")
            self.preview_nl.set("No students could be loaded from matching/i.lp.")
            self.preview_asp.set("")
            self.explain_btn.configure(state="disabled")
            return

        self.x_cb.configure(state="readonly")

        if phrase == "is single":
            self.y_cb.configure(state="disabled")
            sign = "pos"
            x = ui_to_raw(self.x_var.get(), self.name_map)
            y = x
            nl = f"What if {display_name(x)} is single?"
        elif phrase == "is not single":
            self.y_cb.configure(state="disabled")
            sign = "neg"
            x = ui_to_raw(self.x_var.get(), self.name_map)
            y = x
            nl = f"What if {display_name(x)} is not single?"
        else:
            self.y_cb.configure(state="readonly")
            x = ui_to_raw(self.x_var.get(), self.name_map)
            y = ui_to_raw(self.y_var.get(), self.name_map)
            sign = "pos" if phrase == "is matched with" else "neg"
            if qtype_ui == "why":
                nl = f"Why is {display_name(x)} {phrase} {display_name(y)}?"
            else:
                nl = f"What happens if {display_name(x)} {phrase} {display_name(y)}?"

        asp = f"query({qtype_ui},{sign},({x},{y}))."
        #self.preview_nl.set(nl)
        #self.preview_asp.set(asp)
        self.explain_btn.configure(state="normal")

    # ---------- run

    def _run(self):
        self._clear()
        self.last_alternative_atoms = []
        self.last_recommended_atoms = []
        self.nb.select(self.tab_results)

        try:
            cfg = self._cfg()
        except Exception as e:
            messagebox.showerror("Configuration error", str(e))
            return

        qtype_ui = self.type_var.get().strip().lower()
        if not self.nouns and qtype_ui != "fairness":
            messagebox.showerror("Missing students", "No students could be loaded from matching/i.lp.")
            return

        if qtype_ui == "fairness":
            qtype = HOW_MAPS_TO_TYPE
            sign = "pos"
            x, y = "none", "none"
            nl = "How fair is this matching?"
        else:
            phrase = self.phrase_var.get().strip().lower()
            x = ui_to_raw(self.x_var.get(), self.name_map)

            if phrase == "is single":
                sign = "pos"
                y = x
            elif phrase == "is not single":
                sign = "neg"
                y = x
            else:
                y = ui_to_raw(self.y_var.get(), self.name_map)
                sign = "pos" if phrase == "is matched with" else "neg"

            qtype = qtype_ui
            nl = self.preview_nl.get()

        q_lp = default_generated_q_path(cfg.i_lp)
        write_query_fact(q_lp, qtype, sign, x, y)

        #self._log_title("")
        self._log(nl)
        self._spacer()

        common = [cfg.i_lp, cfg.m_lp, q_lp]

        try:
            self._set_status("Running clingo…")
            if qtype == "why":
                self._run_why(cfg, common, sign, x, y)
            elif qtype == "whatif":
                self._run_whatif(cfg, common)
            elif qtype == "best":
                self._run_best(cfg, common)
            else:
                self._log_error(f"Unknown query type: {qtype}")
            self._set_status("Done.")
        except Exception as e:
            self._set_status("Error.")
            self._log_error(f"Run error: {e}")
            messagebox.showerror("Run error", str(e))

    # ---------- pipelines

    def _run_why(self, cfg: FileConfig, common: List[Path], sign: str, x: str, y: str):
        Pacc = cfg.base_dir / "P-accept.lp"
        C = cfg.base_dir / "C.lp"
        Qrel = cfg.base_dir / "queryRel.lp"
        for f in (Pacc, C, Qrel):
            if not f.exists():
                raise FileNotFoundError(f"Missing: {f}")

        status, atoms, cost = run_clingo_optimum(common, [Pacc, C, Qrel], models=0)

        accepts = [a for a in atoms if a.startswith("c_accept(")]
        inferred = [a for a in atoms if a.startswith("c_inferred(")]
        notaccepts = [a for a in atoms if a.startswith("c_not_accept(")]

        self._log_subtitle("Explanation")

        if sign == "pos":
            self._log_success("Sure!")
        #elif not notaccepts:
        #    self._log("Not exactly.:")

        if accepts:
            for a in accepts:
                _, args = parse_atom(a)
                if len(args) == 2:
                    self._log_bullet(f"Student {display_name(args[0])} listed Student {display_name(args[1])} in the preference list.")

        if inferred:
            for a in inferred:
                _, args = parse_atom(a)
                if len(args) == 2:
                    self._log_bullet(f"Their survey responses are compatible.")

        if notaccepts:
            for a in notaccepts:
                _, args = parse_atom(a)
                if len(args) == 2:
                    self._log_bullet(f"Student {display_name(args[0])} did not list Student {display_name(args[1])} as acceptable.")

        if not (accepts or inferred or notaccepts):
            self._log_warning("No explicit explanation facts were produced.")

        if sign == "neg" and not notaccepts:
            if ask_yes_no_dynamic(self, "Alternative?", "Would you like to see an alternative matching?"):
                write_query_fact(common[2], "whatif", "pos", x, y)
                self._spacer()
                self._run_whatif(cfg, common)

    def _run_whatif(self, cfg: FileConfig, common: List[Path]):
        P = cfg.base_dir / "P.lp"
        H = cfg.base_dir / "H.lp"
        Ppref = cfg.base_dir / "prefer.lp"
        Qrel = cfg.base_dir / "queryRel.lp"
        Sim = cfg.base_dir / "similar.lp"
        for f in (P, H, Ppref, Qrel):
            if not f.exists():
                raise FileNotFoundError(f"Missing: {f}")

        status, atoms, cost = run_clingo_optimum(common, [P, H, Ppref, Qrel,Sim], models=0)

        pairs = room_atoms_to_pairs(atoms)
        if pairs and status in ("SAT", "UNKNOWN"):
            #self._log_subtitle("Result")
            self._log_success("Good news! There is an alternative matching:")
            self._spacer()
            self._log_rooms(atoms,cfg)
            self._update_stats_chart_if_possible(cfg, atoms)
            return

        #self._log_subtitle("Result")
        self._log_warning("I looked for another matching. Unfortunately, there is no such a matching.")

        V = cfg.base_dir / "V.lp"
        PV = cfg.base_dir / "P_V.lp"
        if not V.exists() or not PV.exists():
            raise FileNotFoundError("No solution found and V.lp / P_V.lp missing for violation analysis.")

        status2, atoms2, cost2 = run_clingo_optimum(common, [PV, Ppref, H, V, Qrel], models=1)

        viols = sorted([a for a in atoms2 if predicate_name(a).startswith("violate")])
        if viols:
            self._spacer()
            self._log_subtitle("Why no stable matching exists")
            for v in viols:
                if v.startswith("violate_blocking("):
                    self._log_bullet("Satisfying this request would disappoint at least one other pair of students.")
                elif v.startswith("violate_acceptability("):
                    self._log_bullet("No acceptable roommate assignment exists under this condition.")
        else:
            self._log_warning("No explicit violation facts were produced.")

        Pv1 = cfg.base_dir / "P_V1.lp"
        Abd = cfg.base_dir / "abduction.lp"
        Sim = cfg.base_dir / "similar.lp"

        choice = ask_option_1_2_dynamic(
            self,
            title="Choose an option",
            message=(
                "Would you like to see a matching by\n\n"
                "Option 1: minimizing the number of disappointed pairs\n"
                "Option 2: minimally changing the students' preferences"
            ),
            option1="Minimize disappointment",
            option2="Minimal preference change"
        )

        if choice == 1:
            for f in (Pv1, PV, H, Ppref, Sim, Qrel):
                if not f.exists():
                    raise FileNotFoundError(f"Missing option-1 program: {f}")
            prog = [Pv1, Ppref, H, PV, Sim, Qrel]
            self._spacer()
            self._log_subtitle("Selected option")
            self._log("Minimizing disappointed pairs.")
        elif choice == 2:
            for f in (P, H, Abd, Sim, Qrel):
                if not f.exists():
                    raise FileNotFoundError(f"Missing option-2 program: {f}")
            prog = [P, H, Abd, Sim, Qrel]
            self._spacer()
            self._log_subtitle("Selected option")
            self._log("Minimally changing preferences.")
        else:
            self._log_warning("No option selected.")
            return

        status3, atoms3, cost3 = run_clingo_optimum(common, prog, models=0)
        self._spacer()
        self._log_subtitle("Alternative matching")
        self._log_rooms(atoms3,cfg)

        self.last_recommended_atoms = atoms3
        self._update_stats_chart_if_possible(cfg, atoms3)

    def _run_best(self, cfg: FileConfig, common: List[Path]):
        F = cfg.base_dir / "F.lp"
        Rank = cfg.base_dir / "c-p-rank.lp"
        egal=cfg.base_dir / "egal.lp"
        P=cfg.base_dir / "P.lp"
        Ppref = cfg.base_dir / "prefer.lp"
        for f in (F, Rank):
            if not f.exists():
                raise FileNotFoundError(f"Missing: {f}")

        status, atoms, cost = run_clingo_optimum(common, [F, Rank,egal,P,Ppref], models=0)

        

        self._spacer()
        #self._log_subtitle("Assessment")
        if any(a.startswith("conform_best") for a in atoms):
            self._log_success("This matching is fair under the selected criterion.")
        else:
            self._log_warning("A fairer matching exists under the selected criterion.")
            if ask_yes_no_dynamic(self, "Alternative?", "Would you like to see the better matching?"):
                self._log_subtitle("Better Matching")
                self._log_rooms(atoms,cfg)
                self._update_stats_chart_if_possible(cfg, atoms)

        #self.last_recommended_atoms = atoms
        #self._update_stats_chart_if_possible(cfg, atoms)

        """if ask_yes_no_dynamic(self, "Alternative?", "Would you like to see the best suboptimal matching?"):
            P = cfg.base_dir / "P.lp"
            NE = cfg.base_dir / "next_Egal.lp"
            Egal = cfg.base_dir / "egal.lp"
            Ppref = cfg.base_dir / "prefer.lp"
            for f in (P, NE, Egal, Ppref, Rank, F):
                if not f.exists():
                    raise FileNotFoundError(f"Missing next-best program: {f}")

            status2, atoms2, cost2 = run_clingo_optimum(common, [P, F, NE, Rank, Egal, Ppref], models=0)
            self._spacer()
            self._log_subtitle("Best suboptimal matching")
            self._log_rooms(atoms2,cfg)
            self._update_stats_chart_if_possible(cfg, atoms2)"""

    # ---------- stats

    def _update_stats_chart_if_possible(self, cfg: FileConfig, alt_atoms: List[str]):
        if not self.csv_agents or self.csv_div is None:
            self._log_warning("Visual summary not updated because no questionnaire CSV was found in matching/.")
            return

        pairs_alt = room_atoms_to_pairs(alt_atoms)
        if not pairs_alt:
            self._log_warning("Visual summary not updated because the alternative matching has no pair of roommates.")
            return

        pairs_rec = r_facts_to_pairs_from_m_lp(cfg.m_lp)
        if not pairs_rec:
            self._log_warning("Visual summary not updated because the recommended matching has no pair of roommates.")
            return

        try:
            alt_r_lp = cfg.i_lp.parent / "_alt_r.lp"
            all_agents = agents_from_i_lp(cfg.i_lp)
            write_alt_room_lp(alt_r_lp, pairs_alt, all_agents)

            sat_rec, sat_alt, _ = satisfaction_for_rec_and_alt(cfg, alt_r_lp)

            categories, alt_raw, rec_raw = compute_chart_metrics_for_two_matchings(
                pairs_rec,
                pairs_alt,
                self.csv_agents,
                self.csv_div,
                sat_rec,
                sat_alt
            )

            self.last_pairs_rec = pairs_rec
            self.last_pairs_alt = pairs_alt
            self.last_sat_rec = sat_rec
            self.last_sat_alt = sat_alt
            self.last_metrics = (categories, alt_raw, rec_raw)

        except Exception as e:
            self._log_warning(f"Visual summary could not be updated: {e}")
            return

        self.eval_chart.set_data(
            categories,
            alt_raw,
            rec_raw,
            title="Recommended vs alternative matching"
        )
        self.nb.select(self.tab_stats)

    # ---------- exit

    def _exit_flow(self):
        choice = ask_option_1_2_dynamic(
            self,
            title="Exit",
            message="Which matching would you like to prefer?",
            option1="Recommended",
            option2="Alternative (export CSV)"
        )

        if choice == 0:
            return

        if choice == 1:
            self.destroy()
            return

        if not self.last_pairs_alt:
            messagebox.showerror("No alternative", "No alternative matching is available.")
            return

        try:
            cfg = self._cfg()
            all_agents = agents_from_i_lp(cfg.i_lp)
        except Exception as e:
            messagebox.showerror("Configuration error", str(e))
            return

        out_dir = filedialog.askdirectory(title="Select a folder to save the CSV files")
        if not out_dir:
            return

        out_dir = Path(out_dir)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        matching_csv = out_dir / "final_matching.csv"
        matching_csv_backup = out_dir / f"final_matching_{stamp}.csv"

        write_matching_csv(matching_csv, self.last_pairs_alt, all_agents, label="alternative")
        write_matching_csv(matching_csv_backup, self.last_pairs_alt, all_agents, label="alternative")

        if self.last_metrics is not None:
            categories, alt_raw, rec_raw = self.last_metrics
            metrics_csv = out_dir / f"stats_{stamp}.csv"
            write_metrics_csv(metrics_csv, categories, alt_raw, rec_raw, self.last_sat_alt, self.last_sat_rec)
            messagebox.showinfo("Exported", f"Saved:\n{matching_csv}\n{metrics_csv}")
        else:
            messagebox.showinfo("Exported", f"Saved:\n{matching_csv}\n(Stats were not exported.)")

        self.destroy()
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=str,
        default=None,
        help="Path to input folder (defaults to ./matching)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = App(input_dir=args.input_dir)
    app.mainloop()
    