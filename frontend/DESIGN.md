# Copy Arena — design tokens

Trading-hall terminal: the room where you size up people, not charts.
Dark navy hall, paper-white type, brass for reputation and splits.

## Tokens

| Token | Value | Role |
|---|---|---|
| `--abyss` | `#0C1F33` | Page ground — deep navy, never pure black |
| `--water` | `#14304A` | Panels, raised surfaces |
| `--water-2` | `#1B3C5A` | Hover / active surface |
| `--paper` | `#F6F1E7` | Primary text, paper-white |
| `--paper-dim` | `#B9C4CE` | Secondary text on dark |
| `--brass` | `#C9973F` | Reputation, badges, splits, the one warm accent |
| `--tide` | `#57B98A` | Positive PnL, PASS verdicts |
| `--coral` | `#E0654A` | Negative PnL, FAIL verdicts, disputes |
| `--line` | `rgba(246,241,231,0.16)` | Hairlines on dark |

Six colours total (abyss, water, paper, brass, tide, coral; water-2 is a
step of water, not a new hue). No purple gradient, no cream-plus-terracotta
pastel set, no black-plus-single-acid accent.

## Type

- **Display — Fraunces** (Google Fonts, OFL). A serif with optical size
  and real weight range. Trader names and the hall headline are set in it;
  when a verdict lands, the verdict word sinks from weight 600 to 900.
- **Body / UI — Public Sans.** Plain, humanist, readable at small sizes.
  Not Inter, not Roboto, not Arial.
- **Numbers — JetBrains Mono**, tabular figures. Every PnL, stake,
  follower count and pool figure is set in it so digits never jitter
  as they tick.

## Layout sketch (ASCII)

```
┌──────────────────────────────────────────────────┐
│ Copy Arena        Hall · Room · Desk · Activity  │  ← sticky top bar
│ [EN|中文]  [Connect wallet]                      │
├──────────────────────────────────────────────────┤
│ Follow people, not charts.                       │  ← Fraunces headline
│ Pool 12,400 GEN · 6 traders · +312 GEN copied    │  ← live mono ticker
├──────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐          │
│ │ (M) Mara │ │ (J) Jin  │ │ (A) Ada  │  ← trader wall:
│ │ +48.2 GEN│ │ +31.0 GEN│ │ −4.1 GEN │     people, not coins
│ │ 214 follow│ │ 96 follow│ │ 41 follow│
│ └──────────┘ └──────────┘ └──────────┘          │
├──────────────────────────────────────────────────┤
│ Record room — Mara                               │
│ Evidence (full text) · verdict timeline          │
│ [Audit] [Appeal] [Dispute] [Witness]             │
├──────────────────────────────────────────────────┤
│ Desk — claim · register · record · follow ·      │
│ copy · settle (forms, dark panels)               │
├──────────────────────────────────────────────────┤
│ Copies ledger · Activity (tx feed, explorer links)│
└──────────────────────────────────────────────────┘
```

Mobile first: single column, wall becomes one card per row, no horizontal
scroll, no hover dependency.

## Project principles

1. **The board is people.** Rank, avatar medallion, name, PnL — a trader
   card is a person. Coins never appear as rows.
2. **Numbers are alive.** PnL, followers and the pool are wired to chain
   reads; on refresh they tween to the new value instead of flashing.
3. **A verdict has weight.** When consensus lands, the verdict word gets
   heavier (Fraunces 600 → 900) and the card travels to its new rank
   with the View Transitions API — never a blink. Unsupported browsers
   just switch instantly.
4. **Waiting tells the truth.** Every write shows three honest steps —
   submitted → validators judging → finalized — with the real
   transaction hash and explorer link. No fake progress bar.
5. **Motion is cheap and honest.** Only `transform` and `opacity` move.
   Interaction feedback under 200 ms. `prefers-reduced-motion` kills all
   of it; touch gets the same flows without hover.

## Blacklist self-check (before build)

- [x] No Inter / Roboto / Arial as the workhorse — Fraunces + Public Sans
      + JetBrains Mono.
- [x] No purple gradient on white, no cream + serif + terracotta set.
- [x] No SaaS card套装 / card-in-card / rounded-square icon above a title.
      Trader cards are the content, not a component套装; the desk panels
      are flat dark surfaces with hairlines.
- [x] No all-caps eyebrow labels, no A·B·C meta strings, no bare
      single-word emphasized titles, no meaningless 01/02/03 numbering.
      Sections are named in plain sentence case ("The hall",
      "Record room", "The desk").
- [x] No decorative motion, no layout-property animation (width / height /
      top / left / margin), no large-area blur animation.
