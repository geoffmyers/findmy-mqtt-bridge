# Contributing to Find My MQTT Bridge

Thanks for taking an interest. This project is developed inside a private
mono repo and published here as a snapshot, which shapes a couple of the
rules below — please read the last section before opening a PR.

## Getting set up

**Stack:** Python 3.9+.

```bash
git clone https://github.com/geoffmyers/findmy-mqtt-bridge.git
cd findmy-mqtt-bridge
python3 -m venv .venv && source .venv/bin/activate
pip install -e "_shared/ha-mqtt-bridge-toolkit[yaml]"
pip install -e ".[dev]"
pytest
```

The whole test suite (decryption math, record normalization, MQTT discovery
payload shaping) runs against synthetic fixtures and needs neither a Mac nor
a real Find My account — you do not need SIP/AMFI disabled, or anyone's real
location data, to contribute.

## Checks

<!-- CHECKS:START -->
Every push and pull request runs these checks in GitHub Actions
([`.github/workflows/checks.yml`](.github/workflows/checks.yml)), and every release has passed them.
To run one yourself, use the same commands from the directory shown.

**test** (Python 3.12, from the repository root):

```bash
python -m venv /tmp/venv
/tmp/venv/bin/pip install -q -e "./_shared/ha-mqtt-bridge-toolkit[yaml]"
/tmp/venv/bin/pip install -q -e ".[dev]"
/tmp/venv/bin/python -m pytest -q
```

<!-- CHECKS:END -->

## Before you open a pull request

- Keep the change focused. One concern per PR is much easier to review.
- Match the surrounding style rather than introducing a new one. There is no
  separate style guide; the existing code is the guide.
- Update the README if you change a published MQTT topic, a Home Assistant
  entity, or `config.example.yaml`.
- Explain **why** in the commit message, not just what. The diff already says
  what changed.

## Reporting a bug

Open an issue with what you did, what you expected, and what happened
instead. macOS version, Python version, and the bridge's log output help
more than anything else. **Never paste raw key material, coordinates, or
other Find My data from your own cache into an issue** — redact it first.

## Security

Please do **not** open a public issue for a security problem. Report it
privately through GitHub's *Report a vulnerability* button on the Security
tab. See [README.md → Permissions and security](README.md#permissions-and-security)
for what this project can access and why.

## How this repo is published

This project lives in a private mono repo. Each publish adds **one commit** on
top of the history here, so the history grows with every release, but one
commit here can stand for many upstream changes. Two consequences:

- Pull requests are reviewed here and applied upstream, then arrive back in the
  next published commit, which credits your authorship in its message. The pull
  request is closed with a link to that commit rather than merged, because the
  next publish is built from the upstream tree and would undo a change made
  only here.
- Operator configuration (`*.tpl` and similar) is deliberately excluded from
  the snapshot. If a config file looks missing, look for the matching
  `.example` file instead.

## Licence

By contributing you agree that your contribution is licensed under the same
terms as this project — see [LICENSE.md](LICENSE.md).
