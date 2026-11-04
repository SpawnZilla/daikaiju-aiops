#!/bin/bash
# Run on dokaisho as USER (uses sudo). Usage: bash install_relay_mcp.sh check | apply | rollback
# check    = READ ONLY: shows whether port 8301 is free, python libs exist, and whether mcpo already lists kaiju-relay.
# apply    = copies the server to /srv/mcpo, installs + starts kaiju-relay-mcp.service, adds "kaiju-relay" to /srv/mcpo/config.json (backup first), restarts the mcpo container.
# rollback = stops/disables the service, restores config.json from the backup, restarts mcpo.
S=/srv/kaiju-vault/angkai/staging/V5_relay_mcp
D=/srv/mcpo; C=$D/config.json; TAG=bak-relaymcp-20261101
case "$1" in
check)
  echo "port 8301 in use: $(ss -ltn 2>/dev/null | grep -c ':8301 ') (need 0)"
  python3 -c "import mcp, starlette, uvicorn, requests; from mcp.server import Server; assert hasattr(Server, 'list_tools'), 'mcp too new: no decorator API (graphify server needs the same)'; print('python libs OK')" 2>&1 | tail -1; pip list 2>/dev/null | grep -i '^mcp '
  echo "mcpo already lists kaiju-relay: $(grep -c kaiju-relay "$C")"
  echo "service present: $(systemctl list-unit-files kaiju-relay-mcp.service 2>/dev/null | grep -c kaiju-relay-mcp)";;
apply)
  [ "$(grep -c kaiju-relay "$C")" = 0 ] || { echo "STOP: already in config.json"; exit 1; }
  cp -p "$C" "$C.$TAG" || exit 1
  cp "$S/kaiju_relay_mcp_server.py" "$D/" || exit 1
  sudo ufw allow from 172.21.0.0/16 to any port 8301 proto tcp comment 'kaiju-relay-mcp from mcpo Docker' || exit 1
  sudo install -m 644 "$S/kaiju-relay-mcp.service" /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable --now kaiju-relay-mcp || exit 1
  python3 -I - "$C" <<'PY' || { echo "CONFIG PATCH FAILED"; cp -p "$C.$TAG" "$C"; exit 1; }
import json, sys
p = sys.argv[1]; d = json.load(open(p))
d["mcpServers"]["kaiju-relay"] = {"type": "sse", "url": "http://172.21.0.1:8301/sse"}
json.dump(d, open(p, "w"), indent=2); open(p, "a").write("\n")
PY
  docker restart mcpo >/dev/null && sleep 5 && curl -s -m 5 http://127.0.0.1:8200/kaiju-relay/openapi.json | head -c 200; echo; echo "applied; backup $C.$TAG";;
rollback)
  sudo ufw delete allow from 172.21.0.0/16 to any port 8301 proto tcp; sudo systemctl disable --now kaiju-relay-mcp; cp -p "$C.$TAG" "$C" && docker restart mcpo >/dev/null && echo restored;;
*) echo "usage: bash $0 check|apply|rollback"; exit 2;;
esac
