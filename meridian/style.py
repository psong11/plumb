"""Shared chart styling, so every figure in `plumb` looks like it came from the
same place — and so the colors mean the same thing everywhere.

    bronze  = raw / before / what arrived
    silver  = cleaned / after / what we kept
    brass   = the governed answer
    red     = loss, error, the thing that should worry you
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

BRONZE, SILVER, BRASS = "#A0602A", "#5F7183", "#A87A17"
INK, INK2, INK3 = "#17191D", "#4A4F57", "#7C838D"
GROUND, PANEL, LINE = "#FFFDF8", "#F6F3EC", "#DED7C9"
DANGER, GOOD = "#A33726", "#3D6B44"


def figure(w=11, h=5.2, title="", subtitle=""):
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(GROUND)
    ax.set_facecolor(GROUND)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(LINE)
    ax.tick_params(colors=INK3, labelsize=9)
    ax.grid(axis="y", color=LINE, lw=.7, alpha=.7)
    ax.set_axisbelow(True)
    if title:
        ax.set_title(title, color=INK, fontsize=14, fontweight="600",
                     loc="left", pad=18 if subtitle else 10)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK2,
                fontsize=10, va="bottom")
    return fig, ax


def save(fig, path):
    from pathlib import Path
    p = Path(path); p.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(p, facecolor=fig.get_facecolor())
    plt.close(fig)
    return p
