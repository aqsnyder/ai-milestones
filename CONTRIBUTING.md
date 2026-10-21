# Contributing

Spotted a missing milestone, a wrong date or a dead link? Contributions are welcome.

- **Suggest a milestone:** open an issue using the *Suggest a milestone* template, with at least two sources.
- **Add or fix one yourself:** edit [`data/milestones.yaml`](data/milestones.yaml) and open a pull request. Don't edit `README.md` — it's generated from the YAML by the Build workflow.

What qualifies, the quality bar for sources and images, and the exact entry format are all in [MAINTAINING.md](MAINTAINING.md).

To preview locally:

```bash
pip install -r scripts/requirements.txt
python scripts/build.py --check     # validate
python scripts/build.py --fetch     # validate, download images, regenerate README
```
