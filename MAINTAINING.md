# Maintaining this timeline

This repo is kept current by a **weekly scheduled review** (run by Claude) plus two GitHub Actions.
This file is the playbook that review follows, so a human maintainer can follow it too.

## What counts as a milestone

Add an entry only if it clears at least one of these bars:

1. **Humans beaten.** The first time an AI system beat (or clearly matched) top human experts or a world champion in a recognised game, sport or competition — e.g. Deep Blue vs. Kasparov, AlphaGo vs. Lee Sedol, AlphaStar reaching Grandmaster.
2. **Open problem solved.** AI solved, or materially advanced, a recognised open problem in mathematics, computer science or science, and domain experts accept the result — e.g. the Robbins conjecture, new cap-set constructions, Erdős problems.
3. **Human-level threshold crossed.** A system reached or passed a widely used human benchmark in a peer-reviewed paper or official result that the field treats as a landmark — e.g. IMO gold-medal standard, human parity in speech recognition.
4. **Science changed.** A major scientific advance or recognition credited substantially to AI — e.g. AlphaFold 2, the 2024 Nobel Prizes.
5. **Foundations (sparingly).** An idea or release that changed what came after — e.g. backpropagation, the Transformer, ChatGPT.

Leave out: routine model launches, small benchmark gains, product announcements, and claims nobody outside the lab has been able to check. A self-reported result can go in once it is widely reported, but the summary must say it is self-reported, and how it was graded.

## Quality bar for every entry

- **Sources:** at least two, ideally one primary (paper, DOI, arXiv, official lab or organiser page) and one reputable secondary (Nature/Science news, Quanta, major newspaper, Wikipedia, museum). Never guess a URL — only use links you have opened or seen in search results.
- **Accuracy:** dates and numbers checked against the primary source. Contested or later-corrected claims are described honestly (see the GPT-4 bar exam and Erdős entries for the tone).
- **Own words:** summaries are written fresh; no copied sentences.
- **Image:** a freely licensed file on Wikimedia Commons (public domain, CC0, CC BY, CC BY-SA). No press photos, logos, screenshots or anything non-free. If there is no suitable free image, use `image: null`.

## Status flags and the watchlist

Big claims sometimes arrive before anyone outside the lab has checked them. When a claim is too significant to leave out but not yet confirmed, include it with a `status` field, which shows a visible banner in the README:

| `status` | Use when |
|---|---|
| *(omitted)* | Confirmed: peer reviewed, officially graded, or checked by independent experts. |
| `self-reported` | Announced by the developers, widely reported, but not independently confirmed. |
| `under-review` | A claimed result that experts are still checking (e.g. the 2026 Navier–Stokes claim). |
| `disputed` | The result or its framing has been publicly challenged. |

Candidates that aren't ready yet go on the `watchlist` in [`data/meta.yaml`](data/meta.yaml), with what would settle them. Every weekly review re-checks the watchlist and the flagged entries: add a candidate once it clears the bar, upgrade or remove a status once it's settled, and record the change in the changelog.

## Entry format

Entries live in [`data/milestones.yaml`](data/milestones.yaml). Order doesn't matter (the build sorts by date).

```yaml
- id: deep-blue-kasparov            # kebab-case, unique, never changed once published
  date: "1997-05-11"                # YYYY-MM-DD, or YYYY-MM / YYYY if that's all that is known
  title: "Deep Blue defeats world chess champion Garry Kasparov"
  category: games                   # games | math | science | perception | language | robotics | foundations
  field: Chess
  system: "Deep Blue (IBM)"
  opponent: "Garry Kasparov, reigning world chess champion"   # only for human-vs-machine events
  status: under-review              # optional: self-reported | under-review | disputed (omit when confirmed)
  summary: >-
    Two or three sentences with the concrete facts.
  significance: >-
    One sentence on why it mattered.
  image:
    file: "Deep Blue.jpg"           # exact Commons filename, no "File:" prefix
    alt: "IBM's Deep Blue on display at the Computer History Museum"
    license: "CC BY 2.0"
  sources:
    - title: "Deep Blue"
      publisher: "IBM"
      url: "https://..."
      kind: primary                 # primary | paper | news | reference
```

## The weekly review, step by step

1. **Set the window.** Read `last_reviewed` in [`data/meta.yaml`](data/meta.yaml). Search from two weeks before that date to today, so nothing slips through the gap.
2. **Search widely.** Look for: AI beating human champions; open problems solved with AI (Erdős problems, conjectures, Terence Tao's and other mathematicians' write-ups, Quanta coverage); olympiad and contest results (IMO in July, IOI in August, ICPC World Finals around September); AI papers in Nature and Science; major prizes. Prefer the original announcement and an independent report.
3. **Screen each candidate** against the bars above, and check it isn't already listed. If an existing entry has new information (peer-reviewed publication, a correction, a retraction), update that entry instead of adding a new one. Re-check every item on the `watchlist` and every entry with a `status` flag (see above).
4. **Fix broken links.** List open issues labelled `broken-links`:
   `gh api "repos/aqsnyder/ai-milestones/issues?labels=broken-links&state=open"`.
   Replace each dead link with the moved page, an equivalent source, or a Wayback Machine snapshot, then close the issue with a short comment.
5. **Check the last build.** `gh api "repos/aqsnyder/ai-milestones/actions/runs?per_page=5"` — if the Build workflow logged image warnings (a Commons file not found or not freely licensed), fix that entry's `image.file`.
6. **Rebuild and commit.** Run `pip install -r scripts/requirements.txt` if needed, then `python scripts/build.py` (validates and regenerates the README; images are downloaded later by the Build action). Set `last_reviewed` in `data/meta.yaml` to today. If content changed, add a dated line to [CHANGELOG.md](CHANGELOG.md). Commit with a message like `Add: <title>` / `Fix links` / `Weekly review: no new milestones`, and push to `main`.

## GitHub Actions

| Workflow | When | What it does |
|---|---|---|
| [Build](.github/workflows/build.yml) | Every push that changes data or scripts; manual | Validates the YAML, downloads image thumbnails and attribution from Wikimedia Commons, regenerates `README.md`, `CREDITS.md` and `data/milestones.json`, and commits them. |
| [Link check](.github/workflows/links.yml) | Mondays 06:17 UTC; pull requests; manual | Checks every source URL and opens or updates a `broken-links` issue for the weekly review to fix. |

Generated files — `README.md`, `CREDITS.md`, `data/milestones.json`, `data/image-credits.json`, `assets/img/*` — should not be edited by hand.
