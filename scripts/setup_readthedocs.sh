#!/usr/bin/env bash
#
# Walks through the Read the Docs setup for misuka-blender.
#
# Every step here needs a browser and an account, so none of it can be
# automated. The script prompts, waits, and verifies the result at the end.

set -uo pipefail

SLUG="misuka-blender"
DOCS_URL="https://${SLUG}.readthedocs.io/latest/"
REPO_URL="https://github.com/misuka-renderer/misuka-blender"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
step() { printf '\n\033[1;34m[%s/%s]\033[0m %s\n' "$1" "$TOTAL" "$2"; }
ok()   { printf '  \033[32mok\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mx\033[0m %s\n' "$1"; }

confirm() {
    local answer
    while true; do
        read -r -p "  Done? [y/n] " answer
        case "$answer" in
            [Yy]*) return 0 ;;
            [Nn]*) fail "Stopping. Re-run this script when you are ready."; exit 1 ;;
            *) echo "  Please answer y or n." ;;
        esac
    done
}

TOTAL=7

bold "Read the Docs setup for ${SLUG}"
echo "Open https://readthedocs.org in a browser and follow along."

step 1 "Sign in"
echo "  Sign in at https://readthedocs.org with the GitHub account that can"
echo "  see the misuka-renderer organization."
confirm

step 2 "Connect the GitHub organization"
echo "  Go to your account settings, then Connected Services, then GitHub."
echo "  Grant access to the misuka-renderer organization. Without this the"
echo "  repository will not appear in the import list."
confirm

step 3 "Import the project"
echo "  Go to https://readthedocs.org/dashboard/import/ and pick"
echo "  misuka-renderer/misuka-blender."
echo "  Set the project slug to exactly: ${SLUG}"
echo "  The slug decides the domain, so it must match or the HELP buttons in"
echo "  the add-on will point at the wrong host."
confirm

step 4 "Drop the language prefix from the URL"
echo "  In the project's Settings, find the URL versioning scheme option and"
echo "  choose the one that keeps multiple versions but no translations."
echo "  Docs then serve at /latest/ instead of /en/latest/."
echo "  This is what the DOCS_URL constant in the add-on assumes."
confirm

step 5 "Check the active versions"
echo "  Under Versions, confirm that 'latest' is active and that nothing else"
echo "  is. Tags v0.1.0 and v0.1.1 contain no docs/ directory, so building"
echo "  them fails. The 'nightly' tag moves constantly and would rebuild for"
echo "  no benefit."
echo "  Turn 'stable' on later, after the first release tag that ships docs."
confirm

step 6 "Enable pull request previews"
echo "  In Settings, tick 'Build pull requests for this project'."
echo "  Each PR then gets its own preview build, which is how a broken page"
echo "  gets caught before it merges."
confirm

step 7 "Verify"
echo "  Trigger a build under Builds if one is not already running, wait for"
echo "  it to finish, then press enter."
read -r -p "  Press enter to check ${DOCS_URL} "

status=$(curl -s -o /dev/null -w '%{http_code}' -L "$DOCS_URL")
if [ "$status" = "200" ]; then
    ok "${DOCS_URL} returned 200."
    echo
    bold "Setup complete."
    echo "Add the docs badge to README.md if it is not there yet, and confirm"
    echo "the HELP buttons in Blender open the right pages."
else
    fail "${DOCS_URL} returned HTTP ${status}."
    echo
    warn "Things to check, in order:"
    echo "    - Did the build finish, and did it pass? See the Builds tab."
    echo "    - Is the project slug exactly '${SLUG}'?"
    echo "    - Did step 4 take effect? Try https://${SLUG}.readthedocs.io/en/latest/"
    echo "      If that one works, the URL versioning scheme was not changed."
    echo "    - Repository: ${REPO_URL}"
    exit 1
fi
