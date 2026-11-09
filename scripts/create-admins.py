#!/usr/bin/env python3
"""Create the first admin account in Ask the Ark, Bookshelf, Music and Courses, all with one login.

Run by install.sh, which asks for the password. By hand:
    ARK_ADMIN_PASSWORD='your password' python3 scripts/create-admins.py

- Skips every app that already has an admin, so it's safe to run again (it never changes a password).
- Ask the Ark: also creates the API key the setup scripts use and saves it to .env as OPENWEBUI_API_KEY,
  when .env has none yet (it signs in with the password above to do that).
- Login: username "admin" (ARK_ADMIN_USER), and for Ask the Ark the email admin@ark.local.

Change passwords, or add more admins, in each app afterwards (README: "Accounts").
"""
import json, os, re, shlex, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
ENVF = HERE / ".env"
ENV = {k.strip(): v.strip().strip("\"'") for k, v in (l.split("=", 1) for l in ENVF.read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))}
USER = os.environ.get("ARK_ADMIN_USER", "admin")
EMAIL = os.environ.get("ARK_ADMIN_EMAIL", f"{USER}@ark.local")
PW = os.environ.get("ARK_ADMIN_PASSWORD", "")
# Where each app answers on this machine (overridable for testing).
OWUI = os.environ.get("ARK_OWUI_URL", "http://127.0.0.1:3000")
KAVITA = os.environ.get("ARK_KAVITA_URL", "http://127.0.0.1:5000")
NAVIDROME = os.environ.get("ARK_NAVIDROME_URL", "http://127.0.0.1:4533")
KOLIBRI = os.environ.get("ARK_KOLIBRI_URL", "http://127.0.0.1:8300")
COMPOSE_DIR = os.environ.get("ARK_COMPOSE_DIR", str(HERE))


def http(method, url, body=None, token=None, timeout=30):
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            t = r.read().decode()
            try:
                return r.status, json.loads(t) if t else None
            except ValueError:
                return r.status, t
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except (urllib.error.URLError, OSError) as e:
        return 0, str(e)


def wait_for(name, url, tries=60):
    """Apps can take a minute to start on the first run."""
    for _ in range(tries):
        code, _ = http("GET", url, timeout=5)
        if code and code < 500:
            return True
        time.sleep(3)
    print(f"  {name:12} not reachable at {url}; start the Ark and run this again")
    return False


def setenv(key, value):
    s = ENVF.read_text()
    s = re.sub(rf"(?m)^{key}=.*$", f"{key}={value}", s) if re.search(rf"(?m)^{key}=", s) else s.rstrip("\n") + f"\n{key}={value}\n"
    with open(ENVF, "r+") as f:   # keeps .env's 600 permissions
        f.seek(0); f.write(s); f.truncate()


def ask_the_ark():
    if not wait_for("Ask the Ark", OWUI + "/api/config"):
        return
    _, cfg = http("GET", OWUI + "/api/config")
    if isinstance(cfg, dict) and cfg.get("onboarding"):
        # No accounts yet: the first sign-up becomes the admin.
        code, res = http("POST", OWUI + "/api/v1/auths/signup", {"name": "Admin", "email": EMAIL, "password": PW})
        if code != 200 or not isinstance(res, dict) or res.get("role") != "admin":
            print(f"  Ask the Ark  could not create the admin ({code}) {res}"); return
        token = res["token"]
        print(f"  Ask the Ark  admin created: {EMAIL}")
    else:
        print("  Ask the Ark  already has an admin, left as is")
        if ENV.get("OPENWEBUI_API_KEY"):
            return
        code, res = http("POST", OWUI + "/api/v1/auths/signin", {"email": EMAIL, "password": PW})
        if code != 200:
            print(f"               no API key made: sign-in as {EMAIL} failed. Make one in Settings -> Account -> API Keys,\n"
                  "               put it in .env as OPENWEBUI_API_KEY=..., and run scripts/setup-ai.sh"); return
        token = res["token"]
    if ENV.get("OPENWEBUI_API_KEY"):
        return
    code, res = http("POST", OWUI + "/api/v1/auths/api_key", token=token)
    key = res.get("api_key") if isinstance(res, dict) else None
    if code == 200 and key:
        setenv("OPENWEBUI_API_KEY", key)
        print("               API key saved to .env (for scripts/setup-ai.sh)")
    else:
        print(f"               could not create an API key ({code}) {res}")


def bookshelf():
    if not wait_for("Bookshelf", KAVITA + "/api/Admin/exists"):
        return
    _, exists = http("GET", KAVITA + "/api/Admin/exists")
    if exists is True or exists == "true":
        print("  Bookshelf    already has an admin, left as is"); return
    code, res = http("POST", KAVITA + "/api/Account/register", {"username": USER, "email": EMAIL, "password": PW})
    print(f"  Bookshelf    admin created: {USER}" if code == 200 else f"  Bookshelf    could not create the admin ({code}) {res}")


def music():
    if not wait_for("Music", NAVIDROME + "/app/"):
        return
    _, page = http("GET", NAVIDROME + "/app/")
    if '\\"firstTime\\":true' not in str(page) and '"firstTime":true' not in str(page):
        print("  Music        already has an admin, left as is"); return
    code, res = http("POST", NAVIDROME + "/auth/createAdmin", {"username": USER, "password": PW})
    print(f"  Music        admin created: {USER}" if code == 200 else f"  Music        could not create the admin ({code}) {res}")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None   # so the redirect Kolibri sends before setup (to /setup) can be read


def courses():
    if not wait_for("Courses", KOLIBRI + "/api/public/info/"):
        return
    try:
        urllib.request.build_opener(_NoRedirect).open(KOLIBRI + "/", timeout=10)
        location = ""
    except urllib.error.HTTPError as e:
        location = e.headers.get("Location", "")
    if "/setup" not in location:
        print("  Courses      already set up, left as is"); return
    cmd = ["docker", "compose", "exec", "-T", "-e", "ARK_PW", "kolibri", "sh", "-c",
           f'kolibri manage provisiondevice --facility "The Ark" --preset informal --language_id en '
           f'--superusername {shlex.quote(USER)} --superuserpassword "$ARK_PW" --noinput']
    env = dict(os.environ, ARK_PW=PW)
    run = lambda c: subprocess.run(c, cwd=COMPOSE_DIR, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    r = run(cmd)
    if r.returncode != 0 and "permission denied" in (r.stderr or "").lower():   # docker group not active in this login yet
        r = run(["sg", "docker", "-c", shlex.join(cmd)])
    if r.returncode == 0:
        print(f"  Courses      admin created: {USER} (home setup, facility \"The Ark\")")
    else:
        print(f"  Courses      could not set up ({r.returncode}) {(r.stderr or r.stdout).strip()[-300:]}")


def needed():
    """True when any app still has no admin, or .env has no Ask the Ark API key (quick check, no waiting)."""
    if not ENV.get("OPENWEBUI_API_KEY"):
        return True
    _, cfg = http("GET", OWUI + "/api/config", timeout=5)
    _, kav = http("GET", KAVITA + "/api/Admin/exists", timeout=5)
    _, nd = http("GET", NAVIDROME + "/app/", timeout=5)
    try:
        urllib.request.build_opener(_NoRedirect).open(KOLIBRI + "/", timeout=5); kol = ""
    except urllib.error.HTTPError as e:
        kol = e.headers.get("Location", "")
    except (urllib.error.URLError, OSError):
        kol = "/setup"
    return (not isinstance(cfg, dict) or bool(cfg.get("onboarding")) or kav not in (True, "true")
            or "firstTime" in str(nd) and "true" in str(nd).split("firstTime", 1)[1][:8] or "/setup" in kol)


def main():
    if "--needed" in sys.argv:   # exit 0 if there's anything to do (install.sh only asks for a password then)
        sys.exit(0 if needed() else 1)
    if len(PW) < 8:
        sys.exit("Set ARK_ADMIN_PASSWORD (8 characters or more) first.")
    ask_the_ark()
    bookshelf()
    music()
    courses()


if __name__ == "__main__":
    main()
