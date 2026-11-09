"""CLI.

  python -m controller run    --url http://127.0.0.1:8700 [--state-dir state]
  python -m controller view   [--db state/<scenario>.db] [--wf nw_renewal]       supervisor screen
  python -m controller why    --wf nw_renewal --at "D3 14:00" [--db ...]       why did X change, who approved, what next
  python -m controller heard  --person nw_renewal:p0004567 [--db ...]          what a customer heard and why
  python -m controller status [--db ...]                                       loop health + alerts
"""
import argparse
import glob
import os

from .store import Store


def _db(a):
    if a.db:
        return a.db
    dbs = sorted(glob.glob(os.path.join(a.state_dir, "*.db")), key=os.path.getmtime)
    if not dbs:
        raise SystemExit(f"no store in {a.state_dir}/")
    return dbs[-1]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="controller")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--url", required=True)
    for name in ("run", "view", "why", "heard", "status"):
        p = r if name == "run" else sub.add_parser(name)
        p.add_argument("--state-dir", default="state")
        if name != "run":
            p.add_argument("--db")
    sub.choices["view"].add_argument("--wf")
    sub.choices["why"].add_argument("--wf", required=True)
    sub.choices["why"].add_argument("--at", required=True, help='e.g. "D3 14:00"')
    sub.choices["heard"].add_argument("--person", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        from .loop import Controller
        Controller(a.url, a.state_dir).run()
        return
    from . import view
    s = Store(_db(a))
    if a.cmd == "view":
        print(view.supervisor(s, a.wf))
    elif a.cmd == "why":
        print(view.why(s, a.wf, view.parse_at(a.at)))
    elif a.cmd == "heard":
        print(view.heard(s, a.person))
    else:
        print(view.status(s))


if __name__ == "__main__":
    main()
